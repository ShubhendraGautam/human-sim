"""Animals: the other things that eat.

Until now the world contained exactly one kind of living thing, which made
the food layer a private resource that people drew down at whatever rate they
chose. Animals change that without any new rules being written for people.
They eat from the same grid, so a herd is competition; they carry energy in
their bodies, so a herd is also food; and both of those follow from grazing
and being catchable rather than from anything that names humans.

What is deliberately *not* here:

- No spawner. Animals are seeded when the world is built and thereafter exist
  only because their parents did. If people hunt a population to nothing, it
  stays nothing — a refill valve would make the herd a backdrop rather than a
  participant, and would hide overhunting instead of showing it.
- No aggression, no flocking, no predator among the animals. Grazers that
  follow food and breed when fed are enough to produce boom, crash, and
  spread; adding a wolf would be adding an answer rather than a cause.
- No behaviour written against people. An animal does not know what a person
  is. Being caught is something that happens to it, decided by the hunter's
  side of the interaction and the animal's own vigilance.

The traits are heritable and mutate, so hunting pressure is selection and not
merely subtraction: a herd that is hunted hard is a herd whose survivors were
the harder ones to catch. Nothing in the model asserts that this will happen,
and whether it does is a measurement.

Cost matters here more than anywhere else, because animals can outnumber
people. Every decision below reads only the cell an animal is standing in and
its four neighbours, so the per-tick cost is a constant per animal rather
than anything that grows with how many others there are.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .entities import EntityKind

#: Order in which neighbouring cells are considered. Fixed so that ties break
#: the same way in every run.
STEPS: Tuple[Tuple[int, int], ...] = (
    (0, 0),
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
)


@dataclass(slots=True)
class Animal:
    """One grazing animal.

    Small on purpose. Every field is either something the world needs to
    place it, something its own metabolism needs, or a heritable trait that
    selection can act on.
    """

    # Fixed like a person's, and read once per entity per tick by the
    # spatial rebuild, so it is a class attribute rather than a field.
    kind = EntityKind.FAUNA

    id: int
    x: int
    y: int
    age: float
    energy: float
    #: What it costs to be this animal, per year.
    metabolism: float
    #: How hard it is to catch. Selection acts on this under hunting.
    vigilance: float
    #: How readily it breeds when it has the energy to.
    fecundity: float
    birth_tick: int = 0
    generation: int = 0


def founder(
    entity_id: int,
    x: int,
    y: int,
    draw: "RandomDraws",
    config,
) -> Animal:
    """A first-generation animal, varied but not selected for anything."""

    spread = config.fauna_trait_variation
    return Animal(
        id=entity_id,
        x=x,
        y=y,
        age=draw.uniform() * config.fauna_maximum_age * 0.5,
        energy=(
            config.fauna_energy_maximum
            * (0.45 + 0.45 * draw.uniform())
        ),
        metabolism=_vary(config.fauna_metabolism, spread, draw),
        vigilance=_clamp01(_vary(config.fauna_vigilance, spread, draw)),
        fecundity=_clamp01(_vary(config.fauna_fecundity, spread, draw)),
        birth_tick=0,
        generation=0,
    )


def offspring(
    entity_id: int,
    parent: Animal,
    other: Animal,
    draw: "RandomDraws",
    config,
    tick: int,
) -> Animal:
    """A calf, from two parents, with an imperfect copy of their traits.

    Blending rather than recombining loci: an animal's traits are continuous
    and there is no genome here to cross over. Mutation is what keeps a herd
    from freezing at whatever its founders happened to be.
    """

    scale = config.fauna_mutation_scale
    return Animal(
        id=entity_id,
        x=parent.x,
        y=parent.y,
        age=0.0,
        energy=config.fauna_birth_energy,
        metabolism=max(
            0.05,
            _mix(parent.metabolism, other.metabolism, draw)
            + draw.gauss(scale),
        ),
        vigilance=_clamp01(
            _mix(parent.vigilance, other.vigilance, draw) + draw.gauss(scale)
        ),
        fecundity=_clamp01(
            _mix(parent.fecundity, other.fecundity, draw) + draw.gauss(scale)
        ),
        birth_tick=tick,
        generation=max(parent.generation, other.generation) + 1,
    )


class RandomDraws:
    """A deterministic supply of numbers for one animal at one tick.

    Animals are updated in id order from a stream that depends only on the
    run's seed, the tick, and the animal's identity, so the herd reproduces
    exactly whether or not anything else in the world changed.
    """

    __slots__ = ("_uniform", "_entity_id", "_channel")

    def __init__(self, uniform, entity_id: int, channel: int) -> None:
        self._uniform = uniform
        self._entity_id = entity_id
        self._channel = channel

    def uniform(self) -> float:
        self._channel += 1
        return self._uniform(self._entity_id, self._channel)

    def gauss(self, scale: float) -> float:
        """A bounded, symmetric perturbation.

        Two uniforms summed rather than a true normal: it needs to be small,
        centred, and cheap, and it must not have a tail that can move a trait
        across its whole range in one birth.
        """

        if scale <= 0.0:
            return 0.0
        return (self.uniform() + self.uniform() - 1.0) * scale


def _vary(center: float, spread: float, draw: "RandomDraws") -> float:
    return center * (1.0 - spread + 2.0 * spread * draw.uniform())


def _mix(first: float, second: float, draw: "RandomDraws") -> float:
    share = draw.uniform()
    return first * share + second * (1.0 - share)


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def catch_probability(
    animal: Animal,
    skill: float,
    config,
) -> float:
    """How likely one attempt on this animal is to succeed.

    A hunter's capability and the animal's vigilance are the only inputs.
    There is no bonus for numbers, no cooperative hunting, and no weapon: if
    those appear they should appear because something else in the model made
    them possible, not because this function granted them.
    """

    resistance = 1.0 + config.fauna_vigilance_weight * animal.vigilance
    chance = config.hunt_success_base * skill / resistance
    return 0.0 if chance < 0.0 else (1.0 if chance > 1.0 else chance)


def meat_yield(animal: Animal, config) -> float:
    """Food recovered from a carcass.

    Proportional to the energy the animal was carrying, so a lean animal at
    the end of a hard winter is worth less than a fat one. This is the only
    place an animal's body becomes a person's food.
    """

    return max(0.0, animal.energy) * config.fauna_meat_per_energy


class Herd:
    """Every animal in the world, and the one rule that moves them.

    Holds no reference to people. The engine hands it the world and the
    registry; what happens to an animal because of a person happens on the
    person's side of the interaction.
    """

    __slots__ = ("config", "world", "entities", "animals", "_uniform",
                 "last_born", "last_died", "last_grazed", "total_born",
                 "total_died", "total_starved", "total_hunted")

    def __init__(self, config, world, entities, uniform) -> None:
        self.config = config
        self.world = world
        self.entities = entities
        self.animals: Dict[int, Animal] = entities.of_kind(EntityKind.FAUNA)
        self._uniform = uniform
        self.last_born = 0
        self.last_died = 0
        self.last_grazed = 0.0
        self.total_born = 0
        self.total_died = 0
        self.total_starved = 0
        self.total_hunted = 0

    def seed(self, rng) -> None:
        """Populate a fresh world.

        Animals go on productive land, weighted by nothing but where the land
        is, so the starting herd carries no assumption about where it ought
        to do well.
        """

        config = self.config
        if not config.fauna_enabled or config.initial_fauna_density <= 0.0:
            return
        world = self.world
        land = [
            index
            for index in range(config.width * config.height)
            if world.capacity[index] > 0.0
        ]
        if not land:
            return
        count = int(round(len(land) * config.initial_fauna_density))
        for _ in range(count):
            index = land[rng.randrange(len(land))]
            x, y = world.coordinates(index)
            entity_id = self.entities.claim_id()
            draw = RandomDraws(
                lambda _id, _channel: rng.random(),
                entity_id,
                0,
            )
            animal = founder(entity_id, x, y, draw, config)
            self.entities.register(animal)

    def advance(self, tick: int) -> None:
        """One tick for every animal: eat, move, breed, age, die.

        Order is fixed by id so the herd is reproducible, and each animal
        reads only its own cell and that cell's four neighbours.
        """

        config = self.config
        self.last_born = 0
        self.last_died = 0
        self.last_grazed = 0.0
        if not config.fauna_enabled or not self.animals:
            return
        world = self.world
        elapsed_years = 1.0 / config.ticks_per_year
        occupants = world.occupants_of_kind(EntityKind.FAUNA)
        dead: List[int] = []
        newborns: List[Animal] = []
        for entity_id in sorted(self.animals):
            animal = self.animals[entity_id]
            draw = RandomDraws(self._uniform, entity_id, 0xFA00)
            animal.age += elapsed_years
            animal.energy -= animal.metabolism * elapsed_years
            # What an animal actually gets falls away as the patch empties.
            # A grazer on bare ground does not scrape up the last blade; it
            # goes hungry. Without this the herd eats the world flat and
            # holds it there, because bare ground is exactly where this
            # world regrows fastest — so the animals would sit on top of
            # maximum regrowth, take all of it, and leave nothing standing
            # for anything else. With it, thin grass feeds fewer animals,
            # the herd shrinks, and the grass comes back.
            conditions = world.local_conditions(animal.x, animal.y)
            available = conditions.food_fraction
            grazed = world.harvest(
                animal.x,
                animal.y,
                min(
                    config.fauna_graze_amount * available,
                    max(
                        0.0,
                        config.fauna_energy_maximum - animal.energy,
                    )
                    / max(config.fauna_forage_energy, 1e-9),
                ),
            )
            if grazed > 0.0:
                self.last_grazed += grazed
                animal.energy = min(
                    config.fauna_energy_maximum,
                    animal.energy + grazed * config.fauna_forage_energy,
                )
            if animal.energy <= 0.0:
                dead.append(entity_id)
                self.total_starved += 1
                continue
            if animal.age >= config.fauna_maximum_age:
                dead.append(entity_id)
                continue
            # Old age is a hazard rather than a wall, so a herd has an age
            # structure instead of a cohort that vanishes together.
            hazard = config.fauna_mortality_rate_per_year * elapsed_years
            if hazard > 0.0 and draw.uniform() < hazard:
                dead.append(entity_id)
                continue
            # Breeding is judged before moving, so the cell an animal is
            # asked about is the cell the spatial index was built for. The
            # other way round it would look itself up at a position the
            # index has never seen.
            calf = self._breed(animal, occupants, draw, tick)
            if calf is not None:
                newborns.append(calf)
            self._wander(animal, draw)
        for entity_id in dead:
            animal = self.entities.deregister(entity_id)
            if animal is not None:
                self.last_died += 1
                self.total_died += 1
        for calf in newborns:
            self.entities.register(calf)
            self.last_born += 1
            self.total_born += 1

    def remove(self, entity_id: int, hunted: bool = False) -> Optional[Animal]:
        """Take an animal out of the world. Used when something eats it."""

        animal = self.entities.deregister(entity_id)
        if animal is not None:
            self.total_died += 1
            if hunted:
                self.total_hunted += 1
        return animal

    def _wander(self, animal: Animal, draw: "RandomDraws") -> None:
        """Step toward the best food in reach, or drift if it is all the same.

        Following the gradient is the whole of an animal's navigation. It is
        what turns a uniform grid into herds standing where the grass is, and
        it is also what empties a patch and pushes them on.
        """

        world = self.world
        config = self.config
        best_index = world.try_cell_index(animal.x, animal.y)
        if best_index is None:
            return
        best_value = world.resources[best_index]
        best_x, best_y = animal.x, animal.y
        # A little indifference to the gradient, so a herd explores instead
        # of every animal in a cell making the identical move forever.
        if draw.uniform() < config.fauna_wander_rate:
            step = STEPS[int(draw.uniform() * len(STEPS)) % len(STEPS)]
            target = world.normalize(animal.x + step[0], animal.y + step[1])
            if target is not None and world.capacity[
                world.cell_index(*target)
            ] > 0.0:
                animal.x, animal.y = target
            return
        for offset_x, offset_y in STEPS[1:]:
            target = world.normalize(animal.x + offset_x, animal.y + offset_y)
            if target is None:
                continue
            index = world.cell_index(*target)
            # Sea is not somewhere a grazing animal goes.
            if world.capacity[index] <= 0.0:
                continue
            value = world.resources[index]
            if value > best_value:
                best_value = value
                best_x, best_y = target
        animal.x, animal.y = best_x, best_y

    def _breed(
        self,
        animal: Animal,
        occupants: Dict[int, List[int]],
        draw: "RandomDraws",
        tick: int,
    ) -> Optional[Animal]:
        """Breed if fed, grown, and standing with another grown animal.

        Needing a second animal present is what makes a herd density
        dependent: a scattered remnant breeds slowly however much grass
        there is, so overhunting does not simply reduce a population, it can
        put one below the density at which it recovers. Nothing enforces
        that threshold; it is a consequence of having to find each other.
        """

        config = self.config
        if (
            animal.age < config.fauna_maturity_age
            or animal.energy < config.fauna_reproduction_energy
        ):
            return None
        mate: Optional[Animal] = None
        # The cell it stands in and the four it can see into. Wider than a
        # single cell because a herd spread thinly over open country would
        # otherwise never breed at all, and narrow enough that finding each
        # other still fails once a population is scattered — which is the
        # threshold that makes overhunting irreversible rather than merely
        # costly.
        for offset_x, offset_y in STEPS:
            target = self.world.normalize(
                animal.x + offset_x,
                animal.y + offset_y,
            )
            if target is None:
                continue
            index = self.world.cell_index(*target)
            for other_id in occupants.get(index, ()):
                if other_id == animal.id:
                    continue
                other = self.animals.get(other_id)
                if (
                    other is not None
                    and other.age >= config.fauna_maturity_age
                    and other.energy >= config.fauna_reproduction_energy
                ):
                    mate = other
                    break
            if mate is not None:
                break
        if mate is None:
            return None
        if draw.uniform() >= animal.fecundity * config.fauna_birth_rate:
            return None
        animal.energy -= config.fauna_reproduction_cost
        return offspring(
            self.entities.claim_id(),
            animal,
            mate,
            draw,
            config,
            tick,
        )

    def statistics(self) -> Tuple[int, float, float, float]:
        """Population, mean energy, mean vigilance, mean age."""

        if not self.animals:
            return (0, 0.0, 0.0, 0.0)
        count = len(self.animals)
        energy = 0.0
        vigilance = 0.0
        age = 0.0
        for animal in self.animals.values():
            energy += animal.energy
            vigilance += animal.vigilance
            age += animal.age
        return (
            count,
            energy / count,
            vigilance / count,
            age / count,
        )
