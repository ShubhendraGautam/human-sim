"""Going hungry costs something before it costs everything.

The old rule did nothing at all until energy hit exactly zero, so a
population got no signal on the way down: everyone crossed the line within a
few ticks of each other and the crash overshot to extinction instead of
settling anywhere. These pin the ramp, not any particular population curve.
"""

import unittest

from src.simulation import Simulation, SimulationConfig


def hungry_world(**overrides) -> Simulation:
    values = {
        "width": 16,
        "height": 16,
        "initial_population": 120,
        "cell_capacity": 4.0,
        "initial_resource_fraction": 0.25,
        "resource_regeneration": 0.01,
        "initial_fauna_density": 0.0,
    }
    values.update(overrides)
    return Simulation(config=SimulationConfig(**values), seed=3)


class MalnutritionTest(unittest.TestCase):
    def test_health_falls_before_energy_is_completely_spent(self) -> None:
        simulation = Simulation(
            config=SimulationConfig(
                width=8,
                height=8,
                initial_population=1,
                initial_fauna_density=0.0,
            ),
            seed=1,
        )
        agent = simulation.agents[min(simulation.agents)]
        # Under-fed but not empty: the old rule ignored this entirely.
        agent.energy = simulation.config.maximum_energy * 0.05
        agent.body_condition = 0.05
        agent.health = 80.0
        before = agent.health

        simulation._apply_time_and_metabolism()

        self.assertGreater(agent.energy, 0.0)
        self.assertLess(agent.health, before)

    def test_a_well_fed_person_takes_no_starvation_damage(self) -> None:
        simulation = Simulation(
            config=SimulationConfig(
                width=8,
                height=8,
                initial_population=1,
                initial_fauna_density=0.0,
            ),
            seed=1,
        )
        agent = simulation.agents[min(simulation.agents)]
        agent.energy = simulation.config.maximum_energy
        agent.body_condition = 1.0
        agent.health = 50.0
        before = agent.health

        simulation._apply_time_and_metabolism()

        self.assertGreaterEqual(agent.health, before)

    def test_the_damage_scales_with_how_far_short_someone_is(self) -> None:
        config = SimulationConfig(
            width=8,
            height=8,
            initial_population=2,
            initial_fauna_density=0.0,
        )

        def damage(nutrition: float) -> float:
            simulation = Simulation(config=config, seed=1)
            agent = simulation.agents[min(simulation.agents)]
            agent.energy = config.maximum_energy * nutrition
            agent.body_condition = nutrition
            agent.health = 90.0
            agent.frailty = 0.0
            agent.age = 20.0
            before = agent.health
            simulation._apply_time_and_metabolism()
            return before - agent.health

        self.assertGreater(damage(0.02), damage(0.20))

    def test_starvation_is_recorded_as_the_cause(self) -> None:
        simulation = hungry_world()

        simulation.run(160)

        self.assertGreater(
            simulation.deaths_by_cause.get("starvation", 0),
            0,
        )

    def test_scarcity_reduces_the_population(self) -> None:
        """The whole point: a world that cannot feed everyone stops trying."""

        simulation = hungry_world()
        start = len(simulation.agents)

        simulation.run(200)

        self.assertLess(len(simulation.agents), start)

    def test_the_threshold_can_be_closed_to_recover_the_old_cliff(
        self,
    ) -> None:
        """At zero, being short of food costs nothing until it is all gone.

        Compared against the ramped run rather than against no loss at all,
        because an underfed body also loses health to its own reduced
        capacity, and that is a different mechanism which stays either way.
        """

        def health_lost(threshold: float) -> float:
            simulation = Simulation(
                config=SimulationConfig(
                    width=8,
                    height=8,
                    initial_population=1,
                    malnutrition_threshold=threshold,
                    initial_fauna_density=0.0,
                ),
                seed=1,
            )
            agent = simulation.agents[min(simulation.agents)]
            agent.energy = simulation.config.maximum_energy * 0.05
            agent.body_condition = 0.05
            agent.health = 80.0
            agent.frailty = 0.0
            agent.age = 20.0
            before = agent.health
            simulation._apply_time_and_metabolism()
            return before - agent.health

        self.assertLess(health_lost(0.0), health_lost(0.30))


if __name__ == "__main__":
    unittest.main()
