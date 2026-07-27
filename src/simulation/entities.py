"""One identity space for everything that occupies the world.

The world is a canvas. A person, an animal, a plant, and a shelter are all
things that are somewhere, and the engine identifies and places them the same
way. What differs between them is behavior, which belongs with each kind, not
identity or placement, which belong here.

The registry encodes one rule about how things come to exist:

- A living thing registers itself. Nothing else is responsible for its
  presence, and it deregisters when it dies.
- An inert thing is registered by whatever made it, and carries that creator's
  identity for as long as it exists. Provenance outlives the creator: a
  shelter still records the person who built it after that person has died.

Kinds are deliberately physical rather than social. The registry knows that
something is an artifact; it never knows that the artifact is a house, a
granary, or a hospital. Those are labels a reader may apply to a structure's
measurable effects, not categories the engine simulates.
"""

from enum import IntEnum
from typing import (
    Dict,
    Iterator,
    Mapping,
    Optional,
    Protocol,
    runtime_checkable,
)


class EntityKind(IntEnum):
    """What something fundamentally is, for identity and placement."""

    PERSON = 0
    FAUNA = 1
    FLORA = 2
    ARTIFACT = 3


#: Kinds that register themselves and deregister when they die.
LIVING_KINDS = frozenset({
    EntityKind.PERSON,
    EntityKind.FAUNA,
    EntityKind.FLORA,
})

#: Kinds that exist only because something made them.
INERT_KINDS = frozenset({EntityKind.ARTIFACT})


@runtime_checkable
class Placeable(Protocol):
    """Anything the world can hold: an identity, a kind, and a position."""

    id: int
    x: int
    y: int

    @property
    def kind(self) -> EntityKind:
        ...


class EntityRegistry:
    """The single authority for what exists in the world and what it is.

    Storage is kept per kind so that iterating people costs nothing extra once
    plants and structures outnumber them. The mapping returned by
    :meth:`of_kind` is the live store rather than a copy, so a caller may hold
    it and read it cheaply, but must register and deregister through this
    class or the kind index falls out of step with it.
    """

    __slots__ = ("_next_id", "_by_kind", "_kind_of", "_creators")

    def __init__(self) -> None:
        self._next_id = 0
        self._by_kind: Dict[EntityKind, Dict[int, Placeable]] = {
            kind: {} for kind in EntityKind
        }
        self._kind_of: Dict[int, EntityKind] = {}
        self._creators: Dict[int, int] = {}

    def claim_id(self) -> int:
        """Reserve the next identity in the single world-wide id space."""

        entity_id = self._next_id
        self._next_id += 1
        return entity_id

    @property
    def claimed_ids(self) -> int:
        """How many identities have ever been issued, living or not."""

        return self._next_id

    def register(
        self,
        entity: Placeable,
        *,
        created_by: Optional[int] = None,
    ) -> None:
        kind = entity.kind
        if entity.id >= self._next_id or entity.id < 0:
            raise ValueError(
                f"entity {entity.id} was never claimed from this registry"
            )
        if entity.id in self._kind_of:
            raise ValueError(f"entity {entity.id} is already registered")
        if kind in INERT_KINDS:
            if created_by is None:
                raise ValueError(
                    f"{kind.name.lower()} {entity.id} needs the identity of "
                    "whatever made it"
                )
            if created_by < 0 or created_by >= self._next_id:
                raise ValueError(
                    f"creator {created_by} was never claimed from this "
                    "registry"
                )
            self._creators[entity.id] = created_by
        elif created_by is not None:
            raise ValueError(
                f"{kind.name.lower()} {entity.id} is living and registers "
                "itself; it cannot have a creator"
            )
        self._by_kind[kind][entity.id] = entity
        self._kind_of[entity.id] = kind

    def deregister(self, entity_id: int) -> Optional[Placeable]:
        """Remove an entity from the world, returning it if it was there.

        The creator record is kept: what a dead person built is still theirs.
        """

        kind = self._kind_of.pop(entity_id, None)
        if kind is None:
            return None
        return self._by_kind[kind].pop(entity_id, None)

    def get(self, entity_id: int) -> Optional[Placeable]:
        kind = self._kind_of.get(entity_id)
        if kind is None:
            return None
        return self._by_kind[kind].get(entity_id)

    def kind_of(self, entity_id: int) -> Optional[EntityKind]:
        return self._kind_of.get(entity_id)

    def creator_of(self, entity_id: int) -> Optional[int]:
        return self._creators.get(entity_id)

    def of_kind(self, kind: EntityKind) -> Dict[int, Placeable]:
        """The live store for one kind. See the class note before mutating."""

        return self._by_kind[kind]

    def counts(self) -> Mapping[str, int]:
        return {
            kind.name.lower(): len(self._by_kind[kind])
            for kind in EntityKind
            if self._by_kind[kind]
        }

    def placed(self) -> Iterator[Placeable]:
        """Every registered entity, grouped by kind."""

        for store in self._by_kind.values():
            yield from store.values()

    def __len__(self) -> int:
        return len(self._kind_of)

    def __contains__(self, entity_id: object) -> bool:
        return entity_id in self._kind_of
