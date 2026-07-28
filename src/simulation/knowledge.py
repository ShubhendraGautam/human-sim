"""Things that can be worked out, and passed on.

The model used to know how to do exactly one thing. ``knows_seafaring`` was a
boolean on every person, research could discover only that, and teaching could
only transmit it. Every part of the loop — noticing an opportunity, working at
it, succeeding, showing someone else — was written once, against one named
skill, so nothing else could ever be learned without writing the whole loop
again.

Here the loop is written once against no skill in particular, and what can be
learned is a table.

A technique is three things:

- an **affordance**: the circumstance that makes it thinkable at all. Nobody
  works out how to cross water inland. This is why discovery is grounded
  rather than arbitrary — a person has to be somewhere that poses the problem.
- an **effort**: how much accumulated work it takes, relative to the run's
  discovery threshold.
- its **effects**: what carrying it changes about what that person can do.

The effects vocabulary is deliberately narrow — multipliers on capacities the
engine already has, plus one gate on open water. That narrowness is the point.
A technique cannot introduce new behaviour, only change the terms of behaviour
that already exists, so adding a row here can never smuggle in a scripted
outcome. Anything that genuinely needs new behaviour has to earn it in the
engine, in the open.

Nothing here decides that a technique is worth having. A population that never
meets the affordance never discovers it; one that does may still find the
effort is not worth the energy. Whether any of these spread is a measurement.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, Optional, Tuple


class Affordance(IntEnum):
    """A circumstance that poses a problem worth solving."""

    #: Standing on land that touches open water.
    COAST = 0
    #: Standing where there is workable material.
    MATERIALS = 1
    #: Standing within reach of animals.
    FAUNA = 2


@dataclass(frozen=True, slots=True)
class Technique:
    """One learnable thing.

    ``index`` is its bit in a person's ``known_techniques`` mask and its slot
    in their progress list, so it is fixed and must not be reordered between
    runs that are meant to be comparable.
    """

    index: int
    name: str
    affordance: Affordance
    #: Multiplier on the run's discovery threshold.
    effort: float
    #: Proportional increase to how much a person takes from the ground.
    harvest_bonus: float = 0.0
    #: Proportional increase to a person's effectiveness against an animal.
    hunt_bonus: float = 0.0
    #: Whether carrying this lets someone put out onto open water.
    opens_water: bool = False


#: Everything that can be learned. Append-only: an index is an identity.
TECHNIQUES: Tuple[Technique, ...] = (
    Technique(
        index=0,
        name="seafaring",
        affordance=Affordance.COAST,
        effort=1.0,
        opens_water=True,
    ),
    Technique(
        index=1,
        name="toolmaking",
        affordance=Affordance.MATERIALS,
        effort=0.8,
        harvest_bonus=0.30,
    ),
    Technique(
        index=2,
        name="tracking",
        affordance=Affordance.FAUNA,
        effort=0.7,
        hunt_bonus=0.40,
    ),
)

TECHNIQUE_COUNT: int = len(TECHNIQUES)

BY_NAME: Dict[str, Technique] = {
    technique.name: technique for technique in TECHNIQUES
}

#: The one technique the rest of the engine still names, because crossing
#: water is a movement rule rather than a modifier and has to be asked about
#: somewhere. Everything else is consulted only through the totals below.
SEAFARING: Technique = BY_NAME["seafaring"]


def knows(mask: int, technique: Technique) -> bool:
    return bool(mask & (1 << technique.index))


def with_technique(mask: int, technique: Technique) -> int:
    return mask | (1 << technique.index)


def count(mask: int) -> int:
    total = 0
    while mask:
        mask &= mask - 1
        total += 1
    return total


def names(mask: int) -> Tuple[str, ...]:
    return tuple(
        technique.name
        for technique in TECHNIQUES
        if knows(mask, technique)
    )


def harvest_multiplier(mask: int) -> float:
    """How much better than bare hands this person gathers.

    Bonuses add rather than compound: two techniques that each help a little
    should not multiply into something neither of them earned.
    """

    total = 1.0
    for technique in TECHNIQUES:
        if technique.harvest_bonus and knows(mask, technique):
            total += technique.harvest_bonus
    return total


def hunt_multiplier(mask: int) -> float:
    total = 1.0
    for technique in TECHNIQUES:
        if technique.hunt_bonus and knows(mask, technique):
            total += technique.hunt_bonus
    return total


def opens_water(mask: int) -> bool:
    for technique in TECHNIQUES:
        if technique.opens_water and knows(mask, technique):
            return True
    return False


def discoverable(
    mask: int,
    available: int,
) -> Optional[Technique]:
    """The first unlearned technique whose affordance is present here.

    ``available`` is a mask of :class:`Affordance` bits describing where the
    person is standing. Fixed order rather than a choice: which problem a
    person happens to work on when several are in front of them is not
    something this model has any basis for deciding, and pretending otherwise
    would be inventing a preference.
    """

    for technique in TECHNIQUES:
        if knows(mask, technique):
            continue
        if available & (1 << technique.affordance):
            return technique
    return None


def teachable(
    teacher_mask: int,
    learner_mask: int,
) -> Optional[Technique]:
    """The first thing the teacher has and the learner does not."""

    missing = teacher_mask & ~learner_mask
    if not missing:
        return None
    for technique in TECHNIQUES:
        if missing & (1 << technique.index):
            return technique
    return None
