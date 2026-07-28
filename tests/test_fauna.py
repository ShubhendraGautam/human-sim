"""Animals: present from the start, and consequential.

These pin the mechanism, not the outcome. Whether a herd booms, crashes, or
is hunted out is a measurement; what is tested here is that animals exist,
that they eat the same grass people do, that they can be eaten, and that
nothing quietly puts them back when they are gone.
"""

import unittest

from src.simulation import Simulation, SimulationConfig
from src.simulation import fauna
from src.simulation.entities import EntityKind


def world(**overrides) -> Simulation:
    values = {
        "width": 24,
        "height": 24,
        "initial_population": 40,
    }
    values.update(overrides)
    return Simulation(config=SimulationConfig(**values), seed=5)


class HerdExistsTest(unittest.TestCase):
    def test_a_new_world_already_has_animals_in_it(self) -> None:
        simulation = world()

        self.assertGreater(len(simulation.fauna), 0)

    def test_animals_are_registered_as_fauna(self) -> None:
        simulation = world()

        for entity_id, animal in simulation.fauna.items():
            self.assertIs(animal.kind, EntityKind.FAUNA)
            self.assertIs(
                simulation.entities.kind_of(entity_id),
                EntityKind.FAUNA,
            )
            # Living things register themselves and have no creator.
            self.assertIsNone(simulation.entities.creator_of(entity_id))

    def test_animals_and_people_share_one_identity_space(self) -> None:
        simulation = world()

        overlap = set(simulation.fauna) & set(simulation.agents)

        self.assertEqual(overlap, set())

    def test_a_world_can_be_built_with_no_animals(self) -> None:
        simulation = world(initial_fauna_density=0.0)

        self.assertEqual(len(simulation.fauna), 0)
        simulation.run(20)
        self.assertEqual(len(simulation.fauna), 0)


class HerdLivesTest(unittest.TestCase):
    def test_animals_eat_the_same_grass_people_harvest(self) -> None:
        """Not a separate larder: a herd is competition for the food layer.

        Compared against the same world with no animals in it rather than
        against its own previous tick, because regrowth alone outpaces one
        tick of grazing and would hide the draw.
        """

        grazed = world(initial_population=0)
        empty = world(initial_population=0, initial_fauna_density=0.0)

        grazed.run(30)
        empty.run(30)

        self.assertGreater(grazed.herd.last_grazed, 0.0)
        self.assertLess(
            grazed.world.total_resources(),
            empty.world.total_resources(),
        )

    def test_a_herd_without_grass_starves(self) -> None:
        simulation = world(
            initial_population=0,
            initial_resource_fraction=0.0,
            resource_regeneration=0.0,
        )
        start = len(simulation.fauna)

        simulation.run(60)

        self.assertGreater(start, 0)
        self.assertLess(len(simulation.fauna), start)
        self.assertGreater(simulation.herd.total_starved, 0)

    def test_grazing_falls_away_as_a_patch_empties(self) -> None:
        """Otherwise a herd strips the world and sits on the bare ground.

        This world regrows fastest where it is emptiest, so a grazer that
        could take the last blade would camp on top of maximum regrowth and
        take all of it forever.
        """

        rich = world(initial_population=0, initial_resource_fraction=1.0)
        poor = world(initial_population=0, initial_resource_fraction=0.08)

        rich.step()
        poor.step()

        self.assertGreater(
            rich.herd.last_grazed / max(len(rich.fauna), 1),
            poor.herd.last_grazed / max(len(poor.fauna), 1),
        )

    def test_nothing_puts_a_vanished_herd_back(self) -> None:
        """A population hunted or starved to nothing stays nothing."""

        simulation = world(initial_population=0)
        for entity_id in list(simulation.fauna):
            simulation.herd.remove(entity_id)

        simulation.run(40)

        self.assertEqual(len(simulation.fauna), 0)


class HuntingTest(unittest.TestCase):
    def test_a_caught_animal_becomes_food_and_leaves_the_world(self) -> None:
        simulation = world()
        agent = simulation.agents[min(simulation.agents)]
        animal = simulation.fauna[min(simulation.fauna)]
        animal.x, animal.y = agent.x, agent.y
        animal.energy = simulation.config.fauna_energy_maximum
        agent.inventory = 0.0
        agent.energy = simulation.config.maximum_energy
        # Catchable regardless of the draw.
        animal.vigilance = 0.0
        simulation.world.rebuild_spatial_index(simulation.entities.placed())

        caught = False
        for _ in range(40):
            if simulation._hunt(agent, animal.id):
                caught = True
                break
            agent.energy = simulation.config.maximum_energy
            simulation.tick += 1

        self.assertTrue(caught)
        self.assertNotIn(animal.id, simulation.fauna)
        self.assertNotIn(animal.id, simulation.entities)
        self.assertGreater(agent.inventory, 0.0)

    def test_a_wary_animal_is_harder_to_catch_than_a_placid_one(self) -> None:
        config = SimulationConfig()
        placid = fauna.Animal(
            id=1, x=0, y=0, age=3.0, energy=10.0,
            metabolism=1.0, vigilance=0.0, fecundity=0.5,
        )
        wary = fauna.Animal(
            id=2, x=0, y=0, age=3.0, energy=10.0,
            metabolism=1.0, vigilance=1.0, fecundity=0.5,
        )

        self.assertGreater(
            fauna.catch_probability(placid, 1.0, config),
            fauna.catch_probability(wary, 1.0, config),
        )

    def test_a_failed_hunt_still_costs_the_hunter(self) -> None:
        simulation = world()
        agent = simulation.agents[min(simulation.agents)]
        animal = simulation.fauna[min(simulation.fauna)]
        animal.x, animal.y = agent.x, agent.y
        # Uncatchable, so the attempt can only fail.
        animal.vigilance = 1.0
        simulation.world.rebuild_spatial_index(simulation.entities.placed())
        agent.energy = simulation.config.maximum_energy
        before = agent.energy

        simulation._hunt(agent, animal.id)

        self.assertLess(agent.energy, before)

    def test_a_leaner_animal_is_worth_less(self) -> None:
        config = SimulationConfig()
        fat = fauna.Animal(
            id=1, x=0, y=0, age=3.0, energy=20.0,
            metabolism=1.0, vigilance=0.5, fecundity=0.5,
        )
        thin = fauna.Animal(
            id=2, x=0, y=0, age=3.0, energy=4.0,
            metabolism=1.0, vigilance=0.5, fecundity=0.5,
        )

        self.assertGreater(
            fauna.meat_yield(fat, config),
            fauna.meat_yield(thin, config),
        )


class HerdDeterminismTest(unittest.TestCase):
    def test_the_same_seed_produces_the_same_herd(self) -> None:
        first = world()
        second = world()
        first.run(40)
        second.run(40)

        self.assertEqual(
            [
                (animal.id, animal.x, animal.y, round(animal.energy, 8))
                for animal in sorted(
                    first.fauna.values(), key=lambda item: item.id
                )
            ],
            [
                (animal.id, animal.x, animal.y, round(animal.energy, 8))
                for animal in sorted(
                    second.fauna.values(), key=lambda item: item.id
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
