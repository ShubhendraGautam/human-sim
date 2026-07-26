import unittest
from dataclasses import replace

from src.simulation import ReproductiveRole, Simulation, SimulationConfig


class DeterminismRegressionTests(unittest.TestCase):
    def test_agent_dictionary_order_does_not_change_resolution(self) -> None:
        config = SimulationConfig(
            width=6,
            height=6,
            initial_population=24,
            initial_exposed_fraction=0.0,
            baseline_mortality_rate_per_year=0.0,
        )
        first = Simulation(config, seed=90210)
        second = Simulation(config, seed=90210)
        second.agents = dict(reversed(tuple(second.agents.items())))

        self.assertEqual(first.state_digest(), second.state_digest())
        first.step()
        second.step()

        self.assertEqual(first.state_digest(), second.state_digest())

    def test_pregnancy_dictionary_order_does_not_change_birth_ids(self) -> None:
        config = SimulationConfig(
            width=1,
            height=1,
            initial_population=4,
            initial_energy_minimum=100.0,
            initial_energy_maximum=100.0,
            reproduction_energy=10.0,
            reproduction_cost=1.0,
            maximum_conception_probability=1.0,
            gestation_years=1.0 / 12.0,
            pregnancy_loss_base_rate_per_year=0.0,
            pregnancy_loss_condition_rate_per_year=0.0,
            baseline_mortality_rate_per_year=0.0,
        )
        first = Simulation(config, seed=31415)
        second = Simulation(config, seed=31415)
        for simulation in (first, second):
            agents = tuple(simulation.agents.values())
            for index, agent in enumerate(agents):
                agent.age = 30.0
                agent.body_condition = 1.0
                agent.development_index = 1.0
                agent.reproductive_role = (
                    ReproductiveRole.OVA
                    if index % 2 == 0
                    else ReproductiveRole.SPERM
                )
                agent.traits = replace(
                    agent.traits,
                    fertility=1.0,
                    maturity_age=16.0,
                )
            self.assertTrue(
                simulation._reproduce(agents[0], agents[1].id, set())
            )
            self.assertTrue(
                simulation._reproduce(agents[2], agents[3].id, set())
            )

        second.pregnancies = dict(
            reversed(tuple(second.pregnancies.items()))
        )
        due_tick = max(
            pregnancy.due_tick
            for pregnancy in first.pregnancies.values()
        )
        first.tick = due_tick
        second.tick = due_tick
        first._advance_pregnancies()
        second._advance_pregnancies()

        self.assertEqual(first.state_digest(), second.state_digest())


if __name__ == "__main__":
    unittest.main()
