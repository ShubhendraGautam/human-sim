"""Seasonal extremes are a physical pressure, not only a food modifier."""

import hashlib
import unittest

from src.simulation import Simulation, SimulationConfig
from src.simulation.exposure import (
    exposure_energy_cost,
    seasonal_exposure,
)


class ExposureFormulaTests(unittest.TestCase):
    def test_hot_and_cold_departures_cost_the_same(self) -> None:
        self.assertEqual(seasonal_exposure(-0.4), 0.4)
        self.assertEqual(seasonal_exposure(0.4), 0.4)

    def test_insulation_reduces_pressure_without_creating_energy(self) -> None:
        self.assertAlmostEqual(seasonal_exposure(-0.4, 0.25), 0.3)
        self.assertEqual(seasonal_exposure(0.4, 1.5), 0.0)
        self.assertEqual(seasonal_exposure(0.4, -1.0), 0.4)

    def test_cost_uses_explicit_years(self) -> None:
        self.assertAlmostEqual(
            exposure_energy_cost(-0.5, 8.0, 0.25),
            1.0,
        )


class ExposureIntegrationTests(unittest.TestCase):
    @staticmethod
    def simulation(cost: float) -> Simulation:
        return Simulation(
            SimulationConfig(
                width=1,
                height=2,
                initial_population=2,
                ticks_per_year=4,
                seasonality_strength=0.5,
                seasonal_equator_fraction=0.0,
                environmental_energy_cost_per_year=cost,
                artifacts_enabled=False,
                initial_fauna_density=0.0,
                initial_exposed_fraction=0.0,
                environmental_exposure_rate_per_year=0.0,
                baseline_mortality_rate_per_year=0.0,
                frailty_mortality_rate_per_year=0.0,
                health_recovery=0.0,
            ),
            seed=7,
        )

    def test_local_season_charges_energy_and_is_reported(self) -> None:
        simulation = self.simulation(8.0)
        agents = simulation._ordered_agents()
        agents[0].y = 0
        agents[1].y = 1
        for agent in agents:
            agent.energy = 50.0
            agent.age = 25.0
        # Opposite hemispheres, equally far from their midpoint.
        simulation.world.last_row_factors = [1.5, 0.5]

        before = sum(agent.energy for agent in agents)
        simulation._apply_time_and_metabolism(ordered_agents=agents)
        metrics = simulation.measure()
        paid = before - sum(agent.energy for agent in agents)
        metabolic = sum(agent.traits.metabolism for agent in agents) * 3.0

        self.assertAlmostEqual(
            metrics.environmental_energy_cost,
            paid - metabolic,
        )
        self.assertAlmostEqual(metrics.mean_environmental_exposure, 0.5)
        self.assertAlmostEqual(metrics.environmental_energy_cost, 2.0)

    def test_equable_conditions_add_no_cost(self) -> None:
        simulation = self.simulation(8.0)
        agent = simulation._ordered_agents()[0]
        simulation.world.last_row_factors = [1.0, 1.0]
        before = agent.energy

        simulation._apply_time_and_metabolism(
            ordered_agents=[agent],
        )

        self.assertAlmostEqual(
            before - agent.energy,
            agent.traits.metabolism * 3.0,
        )
        self.assertEqual(simulation._last_environmental_energy_cost, 0.0)


class ExposureOffSwitchTests(unittest.TestCase):
    # Captured from the model immediately before environmental energy costs
    # were added. These are deliberately golden: comparing two copies of the
    # new code would only prove determinism, not that the switch restores the
    # past.
    BASELINES = {
        0: "0fc47e729d63f1f7ef84b6609c7fc149b042848c7a49ad80da49dbdf770181a0",
        4: "5deb2989f4984d9c4c3f7a3603eb0bbe010b70736f155954300be6cb2be56658",
        19: "c1c86534908d4bf6bc7e5288ad519b895aef7367939abd676a15a4f405183359",
    }

    def test_zero_cost_reproduces_pre_change_digests(self) -> None:
        for seed, expected in self.BASELINES.items():
            with self.subTest(seed=seed):
                simulation = Simulation(
                    SimulationConfig(
                        width=12,
                        height=12,
                        initial_population=20,
                        environmental_energy_cost_per_year=0.0,
                        artifacts_enabled=False,
                    ),
                    seed=seed,
                )
                simulation.run(24)
                actual = hashlib.sha256(
                    repr(simulation.state_digest()).encode()
                ).hexdigest()
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
