"""Inert things people make, described only by measurable effects."""

from dataclasses import dataclass

from .entities import EntityKind


@dataclass(slots=True)
class Artifact:
    """A material object without an engine-side social label.

    A reader may call a durable, insulating, occupied object a dwelling.  The
    simulation stores only the properties that make that reading true.
    """

    kind = EntityKind.ARTIFACT

    id: int
    x: int
    y: int
    durability: float
    insulation: float
    storage_capacity: float
    occupancy_capacity: int
    food_stored: float = 0.0

    @property
    def storage_room(self) -> float:
        return max(0.0, self.storage_capacity - self.food_stored)

    def store(self, amount: float) -> float:
        accepted = min(max(amount, 0.0), self.storage_room)
        self.food_stored += accepted
        return accepted

    def take_food(self, amount: float) -> float:
        taken = min(max(amount, 0.0), self.food_stored)
        self.food_stored -= taken
        return taken


def effective_insulation(
    artifacts: tuple[Artifact, ...],
    occupants: int,
) -> float:
    """Shared protection supplied by current condition and capacity.

    Capacity is pooled across objects in a cell. Overcrowding degrades the
    protection smoothly for everyone rather than privileging low entity IDs.
    """

    if not artifacts or occupants <= 0:
        return 0.0
    protection = sum(
        artifact.insulation
        * artifact.durability
        * min(1.0, artifact.occupancy_capacity / occupants)
        for artifact in artifacts
    )
    return min(1.0, max(0.0, protection))
