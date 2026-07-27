"""What the sea does to people who are on it.

Open water is not a place anyone can occupy indefinitely. A vessel is spent
by time at sea rather than by distance, and when it fails the geography
decides the outcome: a coast within reach can be waded to, and open water
cannot. Nothing here bans an action; the sea is simply expensive.
"""

import unittest

from src.simulation import (
    Rectangle,
    Scenario,
    Simulation,
    SimulationConfig,
    observation,
)
from src.simulation.scenario import CountrySpec


def sea_simulation(**overrides) -> Simulation:
    """A land column, then open sea wide enough to die in."""

    config = SimulationConfig(
        width=8,
        height=5,
        initial_population=0,
        initial_exposed_fraction=0.0,
        baseline_mortality_rate_per_year=0.0,
        **overrides,
    )
    scenario = Scenario(
        countries=(
            CountrySpec(
                id=0,
                name="Shore",
                region=Rectangle(0, 0, 2, 5),
                population=3,
                religion="tide",
            ),
        ),
        seas=(Rectangle(2, 0, 6, 5),),
    )
    simulation = Simulation(config=config, seed=5, scenario=scenario)
    simulation.world.rebuild_spatial_index(simulation.entities.placed())
    return simulation


def put_to_sea(
    simulation: Simulation,
    x: int,
    y: int,
    durability: float,
):
    agent = simulation._ordered_agents()[0]
    agent.x, agent.y = x, y
    agent.vessel_durability = durability
    agent.knows_seafaring = True
    agent.age = 30.0
    agent.energy = simulation.config.maximum_energy
    simulation.world.rebuild_spatial_index(simulation.entities.placed())
    return agent


class VesselWearTests(unittest.TestCase):
    def test_a_vessel_is_spent_by_time_at_sea_not_by_distance(self) -> None:
        simulation = sea_simulation()
        agent = put_to_sea(simulation, x=5, y=2, durability=10.0)
        start = (agent.x, agent.y)

        simulation._advance_voyages()

        self.assertEqual((agent.x, agent.y), start, "nobody moved")
        self.assertEqual(agent.vessel_durability, 9.0)

    def test_a_hull_on_land_is_not_worn_by_sitting_there(self) -> None:
        simulation = sea_simulation()
        agent = put_to_sea(simulation, x=0, y=2, durability=10.0)

        simulation._advance_voyages()

        self.assertEqual(agent.vessel_durability, 10.0)

    def test_nobody_can_wait_out_a_voyage_forever(self) -> None:
        """The bug: resting on open water was free and unbounded."""

        simulation = sea_simulation()
        agent = put_to_sea(simulation, x=5, y=2, durability=4.0)
        agent_id = agent.id

        for _ in range(12):
            simulation._advance_voyages()

        self.assertNotIn(agent_id, simulation.agents)
        self.assertEqual(simulation.deaths[agent_id].cause, "drowned")


class WreckTests(unittest.TestCase):
    def test_a_coast_within_reach_is_waded_to(self) -> None:
        simulation = sea_simulation()
        agent = put_to_sea(simulation, x=2, y=2, durability=1.0)
        energy_before = agent.energy

        simulation._advance_voyages()

        self.assertEqual((agent.x, agent.y), (1, 2))
        self.assertFalse(simulation.world.is_sea(agent.x, agent.y))
        self.assertIn(agent.id, simulation.agents)
        self.assertLess(agent.energy, energy_before, "wading costs something")
        self.assertEqual(agent.voyage_dx, 0)
        self.assertEqual(agent.voyage_dy, 0)

    def test_open_water_drowns_whoever_is_in_it(self) -> None:
        simulation = sea_simulation()
        agent = put_to_sea(simulation, x=5, y=2, durability=1.0)
        agent_id = agent.id

        simulation._advance_voyages()

        self.assertNotIn(agent_id, simulation.agents)
        self.assertEqual(simulation.total_deaths, 1)
        self.assertEqual(simulation.deaths_by_cause["drowned"], 1)
        self.assertEqual(simulation.deaths[agent_id].cause, "drowned")

    def test_a_failed_hull_never_leaves_someone_adrift(self) -> None:
        """The other half of the bug: zero durability meant stuck, not lost."""

        simulation = sea_simulation()
        put_to_sea(simulation, x=5, y=2, durability=1.0)

        simulation._advance_voyages()

        adrift = [
            agent.id
            for agent in simulation.agents.values()
            if simulation.world.is_sea(agent.x, agent.y)
            and agent.vessel_durability <= 0.0
        ]
        self.assertEqual(adrift, [])
        observation.validate_state(simulation)


class PassengerTests(unittest.TestCase):
    def _family_at_sea(self, x: int, durability: float):
        simulation = sea_simulation()
        adults = simulation._ordered_agents()
        guardian, child = adults[0], adults[1]
        guardian.x, guardian.y = x, 2
        guardian.vessel_durability = durability
        guardian.age = 30.0
        child.x, child.y = x, 2
        child.vessel_durability = 0.0
        child.age = 3.0
        simulation._set_guardian(child, guardian.id)
        simulation.world.rebuild_spatial_index(simulation.entities.placed())
        return simulation, guardian, child

    def test_a_passenger_rides_on_an_intact_hull(self) -> None:
        simulation, guardian, child = self._family_at_sea(5, durability=10.0)

        simulation._advance_voyages()

        self.assertIn(child.id, simulation.agents)
        self.assertEqual((child.x, child.y), (guardian.x, guardian.y))
        self.assertEqual(child.vessel_durability, 0.0, "the boat is not hers")

    def test_a_passenger_goes_ashore_with_the_hull(self) -> None:
        simulation, guardian, child = self._family_at_sea(2, durability=1.0)

        simulation._advance_voyages()

        self.assertEqual((guardian.x, guardian.y), (1, 2))
        self.assertEqual((child.x, child.y), (1, 2))
        self.assertIn(child.id, simulation.agents)

    def test_a_passenger_drowns_with_the_hull(self) -> None:
        simulation, guardian, child = self._family_at_sea(5, durability=1.0)
        guardian_id, child_id = guardian.id, child.id

        simulation._advance_voyages()

        self.assertNotIn(guardian_id, simulation.agents)
        self.assertNotIn(child_id, simulation.agents)
        self.assertEqual(simulation.deaths_by_cause["drowned"], 2)


class LandRunsAreUnaffectedTests(unittest.TestCase):
    def test_a_world_without_sea_pays_nothing_for_voyages(self) -> None:
        simulation = Simulation(
            config=SimulationConfig(
                width=12,
                height=12,
                initial_population=30,
            ),
            seed=2,
        )
        before = simulation.state_digest()

        simulation._advance_voyages()

        self.assertEqual(simulation.state_digest(), before)


if __name__ == "__main__":
    unittest.main()
