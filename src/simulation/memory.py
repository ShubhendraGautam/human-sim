"""Where a person has been, and what it was worth when they were there.

A forager that cannot remember a good patch is not foraging, it is drifting
downhill. Until now movement was pure local gradient: an agent compared the
cells it could see and stepped toward the best one, with no way to hold the
thought "there was food over the ridge last spring". That is the difference
between an animal and a thermostat, and it is cheap to fix.

What is stored is deliberately thin:

- A **cell**, a **quality**, and **when**. Nothing about who else was there,
  nothing about what happened next, no route. This is a place worth returning
  to, not a map.
- A **fixed capacity**. Remembering everywhere is the same as remembering
  nowhere, and an unbounded store would make the per-agent cost grow with how
  long someone lives.
- **Decay**. The world moves on: a patch stripped last year may have grown
  back, and one that was rich may have been eaten out by somebody else. A
  memory that never faded would send people confidently to places that no
  longer exist, which is worse than not remembering.

Nothing here is knowledge the agent did not earn. A place is only recorded
when the agent stood in it and took something out of it, so the memory is a
record of its own experience rather than a readout of the world.
"""

from typing import List, Optional, Tuple

#: (cell index, how good it was, the tick it was learned)
Place = Tuple[int, float, int]


class PlaceMemory:
    """A person's handful of remembered places.

    Kept as a plain list because the capacity is small enough that scanning
    it is cheaper than any structure that would avoid scanning it.
    """

    __slots__ = ("places",)

    def __init__(self) -> None:
        self.places: List[Place] = []

    def __len__(self) -> int:
        return len(self.places)

    def remember(
        self,
        cell: int,
        quality: float,
        tick: int,
        capacity: int,
    ) -> None:
        """Record a place worth coming back to.

        Standing somewhere again updates what is held rather than adding a
        second entry, so a place a person works often stays one memory with
        a fresh date on it instead of crowding out everywhere else.
        """

        if capacity <= 0 or quality <= 0.0:
            return
        for index, (known_cell, known_quality, _) in enumerate(self.places):
            if known_cell == cell:
                self.places[index] = (
                    cell,
                    max(known_quality, quality),
                    tick,
                )
                return
        if len(self.places) < capacity:
            self.places.append((cell, quality, tick))
            return
        # Full: the weakest memory gives way, judged as it would be judged
        # now rather than as it was when it was formed.
        weakest = 0
        weakest_value = None
        for index, (_, known_quality, known_tick) in enumerate(self.places):
            value = _faded(known_quality, known_tick, tick, capacity)
            if weakest_value is None or value < weakest_value:
                weakest = index
                weakest_value = value
        if weakest_value is not None and weakest_value < quality:
            self.places[weakest] = (cell, quality, tick)

    def best(
        self,
        tick: int,
        half_life_ticks: float,
        exclude_cell: Optional[int] = None,
    ) -> Optional[Tuple[int, float]]:
        """The most promising place still worth believing in.

        Returns the cell and its faded quality, or ``None`` when nothing is
        remembered that is still worth anything.
        """

        best_cell = None
        best_value = 0.0
        for cell, quality, learned_tick in self.places:
            if cell == exclude_cell:
                continue
            value = _faded(quality, learned_tick, tick, half_life_ticks)
            if value > best_value:
                best_value = value
                best_cell = cell
        if best_cell is None:
            return None
        return best_cell, best_value

    def forget(self, cell: int) -> None:
        """Drop a place that turned out to be nothing.

        Called when someone arrives and finds it bare, so that a memory
        which has stopped being true stops being acted on.
        """

        self.places = [
            place for place in self.places if place[0] != cell
        ]


def _faded(
    quality: float,
    learned_tick: int,
    tick: int,
    half_life_ticks: float,
) -> float:
    """What a memory is worth now, given how long ago it was formed.

    Halving rather than a hard expiry: an old memory of somewhere very good
    can still beat a fresh memory of somewhere poor, which is the ordering
    a forager actually wants.
    """

    if half_life_ticks <= 0.0:
        return quality
    age = tick - learned_tick
    if age <= 0:
        return quality
    return quality * (0.5 ** (age / half_life_ticks))
