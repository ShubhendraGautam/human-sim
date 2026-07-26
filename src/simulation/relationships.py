"""Bounded, data-oriented memory for asymmetric social relationships.

The store owns fixed-width rows of contacts.  Agents keep only an integer row
handle; contacts are integer agent IDs rather than Python object references.
All causal arrays are flattened structures-of-arrays so the storage can later
be moved behind a native implementation without changing engine semantics.

Invariants:

* An allocated row contains at most ``capacity`` distinct contact IDs.
* ``trust`` is in ``[-1, 1]``.
* ``balance`` is from the row owner's perspective and is clipped to
  ``[-balance_limit, balance_limit]``.  Positive balance means the other agent
  has benefited the owner more than the owner has benefited the other agent.
* Merely observing or helping another agent never increases trust.  Trust is
  updated only by an effect the owner receives from that other agent.
* Trust and balance decay toward zero with a configured half-life.  Decay is
  evaluated lazily and reads do not alter raw state, so inspection frequency
  cannot change later behavior.
* Full rows evict deterministically: least important, then least recently
  observed, then greatest contact ID.
* Released rows are cleared and the lowest available row is reused.
"""

import heapq
import math
from array import array
from dataclasses import dataclass
from typing import Optional, Tuple


EMPTY_AGENT_ID = -1
MAX_ENCOUNTERS = (1 << 16) - 1

RawRelationship = Tuple[int, float, float, int, int, int]
RawRow = Tuple[RawRelationship, ...]


@dataclass(frozen=True, slots=True)
class RelationshipView:
    """A contact's values as decayed to one simulation tick."""

    other_id: int
    trust: float
    balance: float
    encounters: int
    last_seen_tick: int


class RelationshipStore:
    """Central fixed-capacity relationship memory.

    ``half_life_ticks`` applies to trust, balance, and the recency component
    used for eviction.  Relationship evidence is asymmetric: callers record a
    received signed effect on the recipient's row and separately record a
    nonnegative given amount on the giver's row.
    """

    __slots__ = (
        "capacity",
        "half_life_ticks",
        "balance_limit",
        "_other_ids",
        "_trust",
        "_balance",
        "_encounters",
        "_value_ticks",
        "_last_seen_ticks",
        "_active_rows",
        "_entry_counts",
        "_free_rows",
        "_active_count",
    )

    def __init__(
        self,
        capacity: int,
        half_life_ticks: float,
        balance_limit: float = 8.0,
    ) -> None:
        if capacity <= 0:
            raise ValueError("relationship capacity must be positive")
        if capacity > 255:
            raise ValueError("relationship capacity cannot exceed 255")
        if not math.isfinite(half_life_ticks) or half_life_ticks <= 0.0:
            raise ValueError("relationship half-life must be finite and positive")
        if not math.isfinite(balance_limit) or balance_limit <= 0.0:
            raise ValueError("relationship balance limit must be finite and positive")

        self.capacity = capacity
        self.half_life_ticks = float(half_life_ticks)
        self.balance_limit = float(balance_limit)
        self._other_ids = array("q")
        self._trust = array("f")
        self._balance = array("f")
        self._encounters = array("H")
        self._value_ticks = array("Q")
        self._last_seen_ticks = array("Q")
        self._active_rows = bytearray()
        self._entry_counts = bytearray()
        self._free_rows = []
        self._active_count = 0

    def __len__(self) -> int:
        """Return the number of active rows."""

        return self._active_count

    @property
    def allocated_row_count(self) -> int:
        """Return active plus currently reusable rows."""

        return len(self._active_rows)

    def row_is_active(self, row: int) -> bool:
        return (
            isinstance(row, int)
            and 0 <= row < len(self._active_rows)
            and bool(self._active_rows[row])
        )

    def allocate(self) -> int:
        """Allocate an empty row, reusing the lowest released row first."""

        if self._free_rows:
            row = heapq.heappop(self._free_rows)
            self._active_rows[row] = 1
        else:
            row = len(self._active_rows)
            self._active_rows.append(1)
            self._entry_counts.append(0)
            self._other_ids.extend([EMPTY_AGENT_ID] * self.capacity)
            self._trust.extend([0.0] * self.capacity)
            self._balance.extend([0.0] * self.capacity)
            self._encounters.extend([0] * self.capacity)
            self._value_ticks.extend([0] * self.capacity)
            self._last_seen_ticks.extend([0] * self.capacity)
        self._active_count += 1
        return row

    def contact_count(self, row: int) -> int:
        self._require_active(row)
        return self._entry_counts[row]

    def release(self, row: int) -> None:
        """Clear and release a row.

        Releasing an inactive row is an integration error rather than an
        idempotent no-op; detecting it prevents two live agents from later
        receiving the same row.
        """

        self._require_active(row)
        start = self._row_start(row)
        for offset in range(start, start + self.capacity):
            self._clear_entry(offset)
        self._active_rows[row] = 0
        self._entry_counts[row] = 0
        self._active_count -= 1
        heapq.heappush(self._free_rows, row)

    def observe(
        self,
        row: int,
        other_id: int,
        tick: int,
    ) -> RelationshipView:
        """Remember a passive encounter without changing trust or balance."""

        self._validate_contact(other_id)
        self._validate_tick(tick)
        offset = self._get_or_create_offset(row, other_id, tick)
        self._mark_encounter(offset, tick)
        return self._view_at(offset, tick)

    def record_received(
        self,
        row: int,
        other_id: int,
        effect: float,
        tick: int,
        learning_rate: float,
    ) -> RelationshipView:
        """Record an effect received by the row owner from ``other_id``.

        ``effect`` is signed: positive values are benefits and negative values
        are harms.  Its full clipped value changes reciprocity balance, while a
        value clipped to ``[-1, 1]`` is the new trust evidence.  Callers should
        normalize effects to a consistent welfare scale before passing them.
        """

        self._validate_contact(other_id)
        self._validate_tick(tick)
        self._validate_finite(effect, "relationship effect")
        if (
            not math.isfinite(learning_rate)
            or learning_rate < 0.0
            or learning_rate > 1.0
        ):
            raise ValueError("relationship learning rate must be between 0 and 1")

        offset = self._get_or_create_offset(row, other_id, tick)
        self._mark_encounter(offset, tick)
        previous_trust = self._trust[offset]
        evidence = _clamp(effect, -1.0, 1.0)
        self._trust[offset] = _clamp(
            previous_trust
            + learning_rate * (evidence - previous_trust),
            -1.0,
            1.0,
        )
        self._balance[offset] = _clamp(
            self._balance[offset] + effect,
            -self.balance_limit,
            self.balance_limit,
        )
        return self._view_at(offset, tick)

    def record_given(
        self,
        row: int,
        other_id: int,
        amount: float,
        tick: int,
    ) -> RelationshipView:
        """Record a benefit voluntarily given by the owner to ``other_id``.

        Giving lowers the owner's balance toward the recipient but deliberately
        does not increase the owner's trust in that recipient.
        """

        self._validate_contact(other_id)
        self._validate_tick(tick)
        self._validate_finite(amount, "given amount")
        if amount < 0.0:
            raise ValueError("given amount cannot be negative")

        offset = self._get_or_create_offset(row, other_id, tick)
        self._mark_encounter(offset, tick)
        self._balance[offset] = _clamp(
            self._balance[offset] - amount,
            -self.balance_limit,
            self.balance_limit,
        )
        return self._view_at(offset, tick)

    def view(
        self,
        row: int,
        other_id: int,
        tick: int,
    ) -> Optional[RelationshipView]:
        """Return a decayed view, or ``None`` when the contact is not remembered."""

        self._validate_contact(other_id)
        self._validate_tick(tick)
        self._require_active(row)
        offset = self._find_offset(row, other_id)
        if offset is None:
            return None
        return self._view_at(offset, tick)

    def views(self, row: int, tick: int) -> Tuple[RelationshipView, ...]:
        """Return all remembered contacts in stable slot order.

        The tuple length is bounded by ``capacity``.  Values are decayed to
        ``tick`` without mutating the raw stored row.
        """

        self._validate_tick(tick)
        self._require_active(row)
        if self._entry_counts[row] == 0:
            return ()
        result = []
        start = self._row_start(row)
        for offset in range(start, start + self.capacity):
            if self._other_ids[offset] != EMPTY_AGENT_ID:
                result.append(self._view_at(offset, tick))
        return tuple(result)

    def forget(self, row: int, other_id: int) -> bool:
        """Forget one contact, returning whether it existed."""

        self._validate_contact(other_id)
        self._require_active(row)
        offset = self._find_offset(row, other_id)
        if offset is None:
            return False
        self._clear_entry(offset)
        return True

    def raw_row(self, row: int) -> RawRow:
        """Export an exact, side-effect-free row for state digests/checkpoints.

        Empty slots and their ordering are retained because slot order affects
        future deterministic insertion and eviction.  Stored trust/balance may
        predate the current simulation tick; ``value_tick`` is included so this
        raw representation remains complete.
        """

        self._require_allocated(row)
        start = self._row_start(row)
        return tuple(
            (
                self._other_ids[offset],
                self._trust[offset],
                self._balance[offset],
                self._encounters[offset],
                self._value_ticks[offset],
                self._last_seen_ticks[offset],
            )
            for offset in range(start, start + self.capacity)
        )

    def raw_rows(self) -> Tuple[Tuple[bool, RawRow], ...]:
        """Export every allocated row and its active flag in row-number order."""

        return tuple(
            (bool(active), self.raw_row(row))
            for row, active in enumerate(self._active_rows)
        )

    def _get_or_create_offset(
        self,
        row: int,
        other_id: int,
        tick: int,
    ) -> int:
        self._require_active(row)
        existing = self._find_offset(row, other_id)
        if existing is not None:
            self._materialize_decay(existing, tick)
            return existing

        start = self._row_start(row)
        empty = next(
            (
                offset
                for offset in range(start, start + self.capacity)
                if self._other_ids[offset] == EMPTY_AGENT_ID
            ),
            None,
        )
        offset = (
            empty
            if empty is not None
            else self._eviction_offset(row, tick)
        )
        self._initialize_entry(offset, other_id, tick)
        return offset

    def _eviction_offset(self, row: int, tick: int) -> int:
        start = self._row_start(row)

        def eviction_key(offset: int) -> Tuple[float, int, int]:
            trust, balance = self._decayed_values(offset, tick)
            elapsed_since_seen = tick - self._last_seen_ticks[offset]
            recency = self._decay_factor(elapsed_since_seen)
            encounters = self._encounters[offset]
            familiarity = encounters / (encounters + 1.0)
            importance = (
                abs(trust)
                + abs(balance) / self.balance_limit
                + familiarity * recency
            )
            return (
                importance,
                self._last_seen_ticks[offset],
                -self._other_ids[offset],
            )

        return min(
            range(start, start + self.capacity),
            key=eviction_key,
        )

    def _find_offset(self, row: int, other_id: int) -> Optional[int]:
        start = self._row_start(row)
        for offset in range(start, start + self.capacity):
            if self._other_ids[offset] == other_id:
                return offset
        return None

    def _view_at(self, offset: int, tick: int) -> RelationshipView:
        trust, balance = self._decayed_values(offset, tick)
        return RelationshipView(
            other_id=self._other_ids[offset],
            trust=trust,
            balance=balance,
            encounters=self._encounters[offset],
            last_seen_tick=self._last_seen_ticks[offset],
        )

    def _decayed_values(self, offset: int, tick: int) -> Tuple[float, float]:
        value_tick = self._value_ticks[offset]
        if tick < value_tick:
            raise ValueError("relationship ticks cannot move backwards")
        factor = self._decay_factor(tick - value_tick)
        return self._trust[offset] * factor, self._balance[offset] * factor

    def _materialize_decay(self, offset: int, tick: int) -> None:
        trust, balance = self._decayed_values(offset, tick)
        self._trust[offset] = trust
        self._balance[offset] = balance
        self._value_ticks[offset] = tick

    def _decay_factor(self, elapsed_ticks: int) -> float:
        if elapsed_ticks <= 0:
            return 1.0
        return 2.0 ** (-elapsed_ticks / self.half_life_ticks)

    def _mark_encounter(self, offset: int, tick: int) -> None:
        if self._encounters[offset] < MAX_ENCOUNTERS:
            self._encounters[offset] += 1
        self._last_seen_ticks[offset] = tick

    def _initialize_entry(self, offset: int, other_id: int, tick: int) -> None:
        if self._other_ids[offset] == EMPTY_AGENT_ID:
            self._entry_counts[offset // self.capacity] += 1
        self._other_ids[offset] = other_id
        self._trust[offset] = 0.0
        self._balance[offset] = 0.0
        self._encounters[offset] = 0
        self._value_ticks[offset] = tick
        self._last_seen_ticks[offset] = tick

    def _clear_entry(self, offset: int) -> None:
        if self._other_ids[offset] != EMPTY_AGENT_ID:
            self._entry_counts[offset // self.capacity] -= 1
        self._other_ids[offset] = EMPTY_AGENT_ID
        self._trust[offset] = 0.0
        self._balance[offset] = 0.0
        self._encounters[offset] = 0
        self._value_ticks[offset] = 0
        self._last_seen_ticks[offset] = 0

    def _row_start(self, row: int) -> int:
        return row * self.capacity

    def _require_active(self, row: int) -> None:
        self._require_allocated(row)
        if not self._active_rows[row]:
            raise ValueError("relationship row is not active")

    def _require_allocated(self, row: int) -> None:
        if not isinstance(row, int) or row < 0 or row >= len(self._active_rows):
            raise IndexError("relationship row is outside allocated storage")

    @staticmethod
    def _validate_contact(other_id: int) -> None:
        if not isinstance(other_id, int) or other_id < 0:
            raise ValueError("contact agent ID must be a nonnegative integer")

    @staticmethod
    def _validate_tick(tick: int) -> None:
        if not isinstance(tick, int) or tick < 0:
            raise ValueError("relationship tick must be a nonnegative integer")

    @staticmethod
    def _validate_finite(value: float, name: str) -> None:
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))
