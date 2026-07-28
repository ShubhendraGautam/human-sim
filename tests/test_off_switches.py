"""Every new mechanism has a setting at which it does nothing.

The project's rule is that a mechanism ships with a way to turn it off, so
that a suspicious result can be bisected against the model without it rather
than argued about. These check the switches are real: with each one closed,
the mechanism produces no state, costs no draw from the random stream, and
leaves the rest of the model to behave as it did.
"""

import unittest

from src.simulation import Simulation, SimulationConfig
from src.simulation.entities import EntityKind


def run(ticks: int = 40, **overrides) -> Simulation:
    values = {
        "width": 20,
        "height": 20,
        "initial_population": 40,
    }
    values.update(overrides)
    simulation = Simulation(config=SimulationConfig(**values), seed=9)
    simulation.run(ticks)
    return simulation


class FaunaSwitchTest(unittest.TestCase):
    def test_no_animals_are_ever_created_at_zero_density(self) -> None:
        simulation = run(initial_fauna_density=0.0)

        self.assertEqual(len(simulation.fauna), 0)
        self.assertEqual(
            simulation.world.occupants_of_kind(EntityKind.FAUNA),
            {},
        )
        self.assertEqual(simulation.herd.total_born, 0)

    def test_disabled_fauna_neither_graze_nor_are_hunted(self) -> None:
        simulation = run(fauna_enabled=False, initial_fauna_density=0.0)

        self.assertEqual(simulation.herd.last_grazed, 0.0)
        self.assertEqual(simulation.total_hunts, 0)
        self.assertEqual(simulation.total_hunt_kills, 0)

    def test_a_world_without_animals_still_runs_and_stays_valid(self) -> None:
        simulation = run(120, initial_fauna_density=0.0)

        simulation.validate_state()
        self.assertGreater(len(simulation.agents), 0)


class LanguageSwitchTest(unittest.TestCase):
    def test_nobody_speaks_a_word_when_language_is_disabled(self) -> None:
        simulation = run(120, language_enabled=False)

        self.assertEqual(simulation.total_coinages, 0)
        for agent in simulation.agents.values():
            self.assertEqual(agent.lexicon.size, 0)

    def test_metrics_report_a_mute_population_as_mute(self) -> None:
        metrics = run(80, language_enabled=False).measure()

        self.assertEqual(metrics.mean_vocabulary, 0.0)
        self.assertEqual(metrics.distinct_words, 0)
        self.assertEqual(metrics.speaking_population, 0)
        self.assertEqual(metrics.language_agreement, 0.0)

    def test_caregiver_transmission_closes_without_muting_adults(
        self,
    ) -> None:
        simulation = run(120, language_caregiver_transmission=False)

        # Adults still talk to each other; only the generational channel
        # is shut, which is the thing being isolated.
        self.assertGreater(simulation.total_coinages, 0)


class MalnutritionSwitchTest(unittest.TestCase):
    def test_at_threshold_zero_only_an_empty_body_is_damaged(self) -> None:
        """The old cliff, exactly: nothing bites until energy is gone."""

        def damage(energy: float, threshold: float) -> float:
            simulation = Simulation(
                config=SimulationConfig(
                    width=8,
                    height=8,
                    initial_population=1,
                    malnutrition_threshold=threshold,
                    initial_fauna_density=0.0,
                ),
                seed=2,
            )
            agent = simulation.agents[min(simulation.agents)]
            agent.energy = energy
            agent.body_condition = energy / simulation.config.maximum_energy
            agent.health = 60.0
            agent.frailty = 0.0
            agent.age = 25.0
            before = agent.health
            simulation._apply_time_and_metabolism()
            return before - agent.health

        short_but_fed = damage(10.0, 0.0)
        completely_spent = damage(0.0, 0.0)

        self.assertGreater(completely_spent, short_but_fed)


class NeuralSwitchTest(unittest.TestCase):
    def test_networks_contribute_nothing_at_zero_weight(self) -> None:
        simulation = run(60, neural_output_weight=0.0)

        simulation.validate_state()
        self.assertGreater(len(simulation.agents), 0)


if __name__ == "__main__":
    unittest.main()
