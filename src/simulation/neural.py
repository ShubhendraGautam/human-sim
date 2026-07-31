"""Brains that are inherited rather than written.

Every person carries a small network. It reads their circumstances and adds a
bias to each action they might take; the rest of the decision — what the
options are, what they cost, whether they succeed — is unchanged. Nothing
trains these networks. There is no loss function, no gradient, and no target
behaviour anywhere in this file. Children get a recombined, slightly mutated
copy of their parents' weights, and whatever those weights do is judged only
by whether the person carrying them lives long enough to have children.

That is the whole point of doing it this way. A trained network would encode
an outcome somebody chose in advance, which is the one thing this project
refuses to do. An inherited one encodes nothing at the start — founders begin
with near-zero weights, so the first generation behaves exactly as it did
before networks existed — and any structure that appears later got there by
being survived with.

Three properties are load-bearing and worth stating plainly:

- **Deterministic.** Plain Python floats, fixed evaluation order, weights
  drawn from the run's own seeded generator. The digest still reproduces.
- **No dependency.** The simulation core promises no third-party runtime
  imports and this keeps that promise; a matrix library would be faster and
  is not worth the debt at this size.
- **Bounded.** Fixed ceilings, fixed cost per decision, weights bounded. A
  recurrent brain can remember its previous hidden state, but it cannot add
  connections or retain an unbounded history.
"""

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

#: What a brain can perceive.
#:
#: Every entry is something the agent already has bounded local access to.
#: Nothing here is global knowledge, and nothing is a summary the engine
#: computes for the agent's benefit — a network that could see the population
#: total would be reading the observer's notes rather than its own senses.
#: The first thirteen are the body reporting on itself. The rest are the
#: world, and they were the thing missing: a brain that can only feel its own
#: hunger has nothing to have a policy *about*. It cannot notice that the
#: ground here is bare, that it is better one step over, that winter is
#: coming, or that there is an animal within reach — so every one of those
#: judgements had to be made for it by a constant in the config.
SENSE_NAMES = (
    "bias",
    "energy",
    "health",
    "inventory",
    "materials",
    "age",
    "body_condition",
    "frailty",
    "neighbours",
    "infected",
    "has_partner",
    "knows_seafaring",
    "has_vessel",
    "research",
    "food_here",
    "food_nearby",
    "material_here",
    "season",
    "animal_near",
    "on_coast",
    "remembered_place",
)

SENSES = len(SENSE_NAMES)


@dataclass(frozen=True, slots=True)
class GrowthRules:
    """How large a brain may become, and how quickly.

    Passed in rather than read from the config so this module keeps knowing
    nothing about the rest of the simulation. Its absence is the off switch:
    with no rules, every brain is born at full size and nothing here behaves
    differently from before growth existed.
    """

    #: Hidden units a person is born with, before any development.
    birth_units: int
    #: Founder ceilings are drawn from this inclusive range.
    minimum_ceiling: int
    maximum_ceiling: int
    #: Founder growth rates, in hidden units gained per year of life.
    minimum_rate: float
    maximum_rate: float
    #: Chance a child's inherited ceiling shifts by one unit either way.
    ceiling_mutation_rate: float
    #: Standard deviation of the mutation applied to an inherited rate.
    rate_mutation_scale: float


def squash(value: float) -> float:
    """A bounded activation that keeps runaway weights from taking over."""

    if value > 20.0:
        return 1.0
    if value < -20.0:
        return -1.0
    return math.tanh(value)


class Network:
    """One person's inherited decision bias: senses in, action scores out.

    Deliberately small. The optional recurrent layer makes the hidden state a
    bounded memory of the previous decision: it can represent a temporal
    disposition ("food was nearby a moment ago") without becoming a planner
    or reading any history the person did not experience. Recurrent weights
    are inherited and mutated; recurrent *state* is lifetime state and is
    supplied by ``BrainState``, so children never inherit a parent's thoughts.
    """

    __slots__ = (
        "hidden",
        "output",
        "recurrent",
        "units",
        "outputs",
        "magnitude",
        "active",
        "growth_rate",
    )

    def __init__(
        self,
        units: int,
        outputs: int,
        active: Optional[int] = None,
        growth_rate: float = 0.0,
        recurrent: bool = False,
    ) -> None:
        #: Allocated hidden units — the ceiling this brain could ever reach.
        #: Inherited, and the one number a child gets from its parents about
        #: how large a brain it is allowed to become.
        self.units = units
        self.outputs = outputs
        #: Hidden units currently grown, which is what actually thinks.
        #:
        #: Developmental rather than inherited: a person grows toward their
        #: ceiling over their own life, and what they grew dies with them.
        #: A child starts small again however large its parents ended up,
        #: for the same reason learned weights are not passed on — otherwise
        #: a life's development would quietly become heritable, which is
        #: Lamarck by accident.
        self.active: int = units if active is None else active
        #: Hidden units gained per year of life. Inherited, mutable, and the
        #: thing selection can actually act on: how fast to build a brain,
        #: and — with an upkeep cost — whether to bother.
        self.growth_rate: float = growth_rate
        #: hidden[unit][sense]
        self.hidden: List[List[float]] = [
            [0.0] * SENSES for _ in range(units)
        ]
        #: output[action][unit]
        self.output: List[List[float]] = [
            [0.0] * units for _ in range(outputs)
        ]
        #: recurrent[target unit][source unit]. Empty is the exact off switch.
        #: The matrix is fixed at the inherited ceiling, while evaluation
        #: reads only the square belonging to units that have actually grown.
        self.recurrent: List[List[float]] = (
            [[0.0] * units for _ in range(units)]
            if recurrent
            else []
        )
        #: Mean absolute weight — how strongly this brain pushes at all.
        #:
        #: Held rather than derived because a weight is only ever written by
        #: the two factories below, and because anything that charges for a
        #: brain has to read this every tick for every person. Recomputing
        #: 168 absolute values per person per tick to answer a question whose
        #: answer cannot have changed would be the most expensive line in the
        #: engine. Any future code that writes a weight must call
        #: ``refresh_magnitude``.
        self.magnitude: float = 0.0

    def refresh_magnitude(self) -> None:
        """Recompute the held mean absolute weight after weights change.

        Counted over the units that have actually grown, not over the ones
        allocated for a ceiling that may never be reached. What a person is
        charged for, and what shows up in the metrics, should be the brain
        they are running rather than the one they might one day have.
        """

        active = self.active
        total = 0.0
        count = 0
        for row in self.hidden[:active]:
            for weight in row:
                total += abs(weight)
                count += 1
        for row in self.output:
            for weight in row[:active]:
                total += abs(weight)
                count += 1
        for row in self.recurrent[:active]:
            for weight in row[:active]:
                total += abs(weight)
                count += 1
        self.magnitude = total / count if count else 0.0

    @property
    def recurrent_magnitude(self) -> float:
        """Mean absolute temporal weight in the brain that has grown."""

        active = self.active
        if not self.recurrent or active == 0:
            return 0.0
        total = sum(
            abs(weight)
            for row in self.recurrent[:active]
            for weight in row[:active]
        )
        return total / (active * active)

    def grow_to(self, units: int) -> bool:
        """Bring this many hidden units online, up to the ceiling.

        Returns whether anything changed, so a caller only pays the cost of
        refreshing the magnitude on the few ticks of a life where a brain
        actually gains something.
        """

        target = units if units < self.units else self.units
        if target <= self.active:
            return False
        self.active = target
        self.refresh_magnitude()
        return True

    def respond(
        self,
        senses: Sequence[float],
        overlay: Optional[List[List[float]]] = None,
        previous: Optional[Sequence[float]] = None,
        recurrent_weight: float = 0.0,
    ) -> Tuple[List[float], List[float]]:
        """Score every action, and report the hidden state that produced it.

        The activations come back because lifetime learning needs to know
        *which* internal state earned the outcome, not merely that something
        did. Crediting the whole brain for one result would make learning a
        wash; crediting the units that were actually active is what lets a
        person end up preferring an action in the circumstances where it
        works rather than everywhere.

        ``overlay`` is the learned adjustment to the output layer. It is
        added rather than blended, and it lives outside this object, so what
        a person was born with stays legible next to what they picked up.

        ``previous`` is the hidden state from this person's prior decision.
        It is deliberately passed in rather than stored on the inherited
        network: weights cross generations, thoughts do not. With no
        recurrent matrix or a weight of zero this takes the old feed-forward
        path exactly.
        """

        # Only grown units think. Ungrown ones are allocated storage for a
        # ceiling this person may never reach, and reading them would let a
        # child decide with a brain it has not built yet.
        active = self.active
        scores = [0.0] * self.outputs
        activations = [0.0] * active
        for unit in range(active):
            weights = self.hidden[unit]
            total = 0.0
            for index in range(SENSES):
                total += weights[index] * senses[index]
            if (
                recurrent_weight != 0.0
                and previous is not None
                and self.recurrent
            ):
                memory = self.recurrent[unit]
                for source in range(min(active, len(previous))):
                    total += (
                        recurrent_weight
                        * memory[source]
                        * previous[source]
                    )
            activations[unit] = squash(total)
        for action in range(self.outputs):
            weights = self.output[action]
            learned = overlay[action] if overlay is not None else None
            total = 0.0
            for unit in range(active):
                weight = weights[unit]
                if learned is not None and unit < len(learned):
                    weight += learned[unit]
                total += weight * activations[unit]
            scores[action] = squash(total)
        return scores, activations

    def evaluate(self, senses: Sequence[float]) -> List[float]:
        """Scores only, for callers that do not learn from the result."""

        return self.respond(senses)[0]


def founder_network(
    rng: random.Random,
    units: int,
    outputs: int,
    scale: float,
    growth: Optional["GrowthRules"] = None,
    recurrent_rng: Optional[random.Random] = None,
) -> Network:
    """A first-generation brain.

    At ``scale`` zero every founder is born with no opinions at all and the
    population behaves exactly as it did before brains were heritable. A small
    scale gives selection something to act on immediately without deciding in
    advance what it should favour.

    Without ``growth`` every founder gets exactly ``units``, all of them
    grown from the start, and draws the same weights in the same order as it
    always did — which is what keeps a run with growth switched off
    bit-identical to one from before growth existed.
    """

    if growth is None:
        network = Network(
            units,
            outputs,
            recurrent=recurrent_rng is not None,
        )
        if scale <= 0.0:
            return network
        for unit in range(units):
            for index in range(SENSES):
                network.hidden[unit][index] = rng.gauss(0.0, scale)
        for action in range(outputs):
            for unit in range(units):
                network.output[action][unit] = rng.gauss(0.0, scale)
        if recurrent_rng is not None:
            _fill_recurrent(network, recurrent_rng, scale)
        network.refresh_magnitude()
        return network

    ceiling = rng.randint(growth.minimum_ceiling, growth.maximum_ceiling)
    rate = rng.uniform(growth.minimum_rate, growth.maximum_rate)
    network = Network(
        ceiling,
        outputs,
        active=min(growth.birth_units, ceiling),
        growth_rate=rate,
        recurrent=recurrent_rng is not None,
    )
    if scale <= 0.0:
        return network
    # Weights are drawn for the whole ceiling, including units this person
    # may never grow into. They are inherited whether or not they were ever
    # used, so a child can grow into a unit its parents never reached — which
    # is what lets a lineage's capacity be selected rather than reinvented.
    for unit in range(ceiling):
        for index in range(SENSES):
            network.hidden[unit][index] = rng.gauss(0.0, scale)
    for action in range(outputs):
        for unit in range(ceiling):
            network.output[action][unit] = rng.gauss(0.0, scale)
    if recurrent_rng is not None:
        _fill_recurrent(network, recurrent_rng, scale)
    network.refresh_magnitude()
    return network


def _fill_recurrent(
    network: Network,
    rng: random.Random,
    scale: float,
) -> None:
    """Give a founder temporal connections from an independent stream.

    Founder construction historically draws all later biology from the run's
    main generator. Recurrence uses its own keyed generator so switching this
    experimental mechanism on does not quietly give the comparison different
    bodies, locations, or reproductive roles.
    """

    for target in range(network.units):
        for source in range(network.units):
            network.recurrent[target][source] = rng.gauss(0.0, scale)


def append_output(
    network: Network,
    rng: random.Random,
    scale: float,
) -> None:
    """Append one action disposition without perturbing founder biology.

    New action mechanisms use a keyed stream for their new row. The existing
    network is first built at its historical width from the main run stream,
    so enabling the action does not silently give the treatment different
    bodies, locations, roles, or legacy action weights.
    """

    row = [0.0] * network.units
    if scale > 0.0:
        for unit in range(network.units):
            row[unit] = rng.gauss(0.0, scale)
    network.output.append(row)
    network.outputs += 1
    network.refresh_magnitude()


def inherit(
    first: Network,
    second: Network,
    rng: random.Random,
    mutation_rate: float,
    mutation_scale: float,
    limit: float,
    growth: Optional["GrowthRules"] = None,
    recurrent: bool = False,
) -> Network:
    """Recombine two brains and let the copy be imperfect.

    Per-weight choice rather than whole-layer, which mixes parental structure
    more finely than the packed genome does for traits. The two inheritance
    channels are deliberately separate: traits are discrete loci with
    crossover, dispositions are continuous weights, and conflating them would
    make either one harder to reason about.

    With ``growth``, two more things are inherited: the ceiling a brain may
    grow to, and how fast it grows. Both mutate. What is emphatically *not*
    inherited is how large the parents' brains actually became — a child is
    born at ``birth_units`` however developed its parents were, because the
    alternative is a life's development becoming heritable.

    Parents of different ceilings are recombined over the units they share,
    and any units beyond that are taken from whichever parent has them. This
    is positional rather than NEAT's historical markings: unit three of one
    brain is treated as the counterpart of unit three of the other. Crude,
    and consistent with how every other weight here is already recombined.
    """

    if growth is None:
        ceiling = first.units
    else:
        ceiling = first.units if rng.random() < 0.5 else second.units
        if rng.random() < growth.ceiling_mutation_rate:
            ceiling += 1 if rng.random() < 0.5 else -1
        ceiling = max(
            growth.minimum_ceiling,
            min(growth.maximum_ceiling, ceiling),
        )

    if growth is None:
        child = Network(ceiling, first.outputs, recurrent=recurrent)
    else:
        rate = (
            first.growth_rate
            if rng.random() < 0.5
            else second.growth_rate
        )
        rate = max(
            growth.minimum_rate,
            min(
                growth.maximum_rate,
                rate + rng.gauss(0.0, growth.rate_mutation_scale),
            ),
        )
        child = Network(
            ceiling,
            first.outputs,
            active=min(growth.birth_units, ceiling),
            growth_rate=rate,
            recurrent=recurrent,
        )

    # A unit beyond one parent's ceiling has only one source; a unit beyond
    # both starts blank, which is the honest beginning for a capacity no
    # ancestor ever had. When ceilings are fixed both parents always have
    # every unit, so this reduces to the coin flip it always was and draws
    # from the generator in exactly the same order.
    for unit in range(ceiling):
        in_first = unit < first.units
        in_second = unit < second.units
        source_hidden = first.hidden[unit] if in_first else None
        other_hidden = second.hidden[unit] if in_second else None
        target = child.hidden[unit]
        for index in range(SENSES):
            if source_hidden is not None and other_hidden is not None:
                weight = (
                    source_hidden[index]
                    if rng.random() < 0.5
                    else other_hidden[index]
                )
            elif source_hidden is not None:
                weight = source_hidden[index]
            elif other_hidden is not None:
                weight = other_hidden[index]
            else:
                weight = 0.0
            if rng.random() < mutation_rate:
                weight += rng.gauss(0.0, mutation_scale)
            target[index] = min(limit, max(-limit, weight))
    for action in range(first.outputs):
        source_output = first.output[action]
        other_output = second.output[action]
        target_output = child.output[action]
        for unit in range(ceiling):
            in_first = unit < first.units
            in_second = unit < second.units
            if in_first and in_second:
                weight = (
                    source_output[unit]
                    if rng.random() < 0.5
                    else other_output[unit]
                )
            elif in_first:
                weight = source_output[unit]
            elif in_second:
                weight = other_output[unit]
            else:
                weight = 0.0
            if rng.random() < mutation_rate:
                weight += rng.gauss(0.0, mutation_scale)
            target_output[unit] = min(limit, max(-limit, weight))
    if recurrent:
        for target_unit in range(ceiling):
            for source_unit in range(ceiling):
                weight = _inherit_recurrent_weight(
                    first,
                    second,
                    target_unit,
                    source_unit,
                    rng,
                )
                if rng.random() < mutation_rate:
                    weight += rng.gauss(0.0, mutation_scale)
                child.recurrent[target_unit][source_unit] = min(
                    limit,
                    max(-limit, weight),
                )
    child.refresh_magnitude()
    return child


def _inherit_recurrent_weight(
    first: Network,
    second: Network,
    target: int,
    source: int,
    rng: random.Random,
) -> float:
    """Recombine one temporal connection across unequal brain ceilings."""

    in_first = (
        bool(first.recurrent)
        and target < first.units
        and source < first.units
    )
    in_second = (
        bool(second.recurrent)
        and target < second.units
        and source < second.units
    )
    if in_first and in_second:
        parent = first if rng.random() < 0.5 else second
        return parent.recurrent[target][source]
    if in_first:
        return first.recurrent[target][source]
    if in_second:
        return second.recurrent[target][source]
    return 0.0
