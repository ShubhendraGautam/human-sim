"""Observation must never change the thing it observes.

`docs/architecture.md` requires that metrics are measurements which do not feed
back into behavior. These tests pin that property directly, so an observer that
starts mutating state fails here rather than silently perturbing a run.
"""

import unittest

from src.simulation import Scenario, Simulation, SimulationConfig
from src.simulation import observation


def populated_simulation(ticks: int = 6) -> Simulation:
    """Build a run with agents, relationships, disease, and pregnancies."""
    config = SimulationConfig(
        width=14,
        height=14,
        initial_population=60,
    )
    simulation = Simulation(config=config, seed=17)
    for _ in range(ticks):
        simulation.step()
    return simulation


class ObservationPurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.simulation = populated_simulation()
        self.assertTrue(
            self.simulation.agents,
            "run died out; test would be vacuous",
        )

    def assert_pure(self, name: str, call) -> None:
        before = self.simulation.state_digest()
        call()
        after = self.simulation.state_digest()
        self.assertEqual(before, after, f"{name} mutated simulation state")

    def test_measure_does_not_mutate(self) -> None:
        self.assert_pure("measure", self.simulation.measure)

    def test_snapshot_does_not_mutate(self) -> None:
        self.assert_pure("snapshot", self.simulation.snapshot)

    def test_validate_state_does_not_mutate(self) -> None:
        self.assert_pure("validate_state", self.simulation.validate_state)

    def test_state_digest_is_repeatable(self) -> None:
        self.assertEqual(
            self.simulation.state_digest(),
            self.simulation.state_digest(),
        )

    def test_repeated_observation_does_not_drift(self) -> None:
        """Relationship views decay on read; that must not persist."""
        before = self.simulation.state_digest()
        for _ in range(5):
            self.simulation.measure()
            self.simulation.snapshot()
        self.assertEqual(before, self.simulation.state_digest())

    def test_observing_does_not_change_a_later_run(self) -> None:
        """The strongest form: observation cannot alter future trajectory."""
        observed = populated_simulation()
        quiet = populated_simulation()

        for _ in range(4):
            observed.measure()
            observed.snapshot()
            observed.validate_state()
            observed.step()
            quiet.step()

        self.assertEqual(observed.state_digest(), quiet.state_digest())


class ObservationModuleTests(unittest.TestCase):
    """The engine's methods must stay thin delegates to the module."""

    def test_methods_match_module_functions(self) -> None:
        simulation = populated_simulation(ticks=3)

        self.assertEqual(
            simulation.measure().to_dict(),
            observation.measure(simulation).to_dict(),
        )
        self.assertEqual(
            simulation.state_digest(),
            observation.state_digest(simulation),
        )
        self.assertEqual(
            simulation.snapshot(),
            observation.snapshot(simulation),
        )

    def test_snapshot_flags_are_forwarded(self) -> None:
        simulation = populated_simulation(ticks=3)

        lean = simulation.snapshot(
            include_world=False,
            include_agents=False,
            include_relationships=False,
        )

        self.assertNotIn("world", lean)
        self.assertNotIn("agents", lean)
        self.assertNotIn("relationships", lean)
        self.assertEqual(
            lean,
            observation.snapshot(
                simulation,
                include_world=False,
                include_agents=False,
                include_relationships=False,
            ),
        )

    def test_scenario_run_is_also_observation_safe(self) -> None:
        config = SimulationConfig(width=10, height=10, initial_population=25)
        scenario = Scenario.default(config)
        simulation = Simulation(config=config, seed=5, scenario=scenario)
        for _ in range(4):
            simulation.step()

        before = simulation.state_digest()
        simulation.measure()
        simulation.snapshot()
        simulation.validate_state()

        self.assertEqual(before, simulation.state_digest())


if __name__ == "__main__":
    unittest.main()
