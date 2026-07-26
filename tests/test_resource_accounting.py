import unittest

from src.simulation import Simulation, SimulationConfig


class ResourceAccountingTests(unittest.TestCase):
    def test_food_stock_change_is_explained_by_recorded_flows(self) -> None:
        simulation = Simulation(
            SimulationConfig(
                width=1,
                height=1,
                initial_population=1,
                initial_exposed_fraction=0.0,
                food_spoilage_rate_per_year=0.5,
                baseline_mortality_rate_per_year=0.0,
                frailty_mortality_rate_per_year=0.0,
                aging_damage_per_year=0.0,
            ),
            seed=990,
        )
        before = (
            simulation.world.total_resources()
            + sum(agent.inventory for agent in simulation.agents.values())
        )

        simulation.step()
        metrics = simulation.measure()
        after = (
            simulation.world.total_resources()
            + metrics.total_food_inventory
        )

        self.assertAlmostEqual(
            after - before,
            metrics.food_regenerated
            - metrics.food_consumed
            - metrics.food_spoiled
            - metrics.food_lost_on_death,
            places=9,
        )

    def test_material_use_and_death_losses_are_observable(self) -> None:
        simulation = Simulation(
            SimulationConfig(
                width=1,
                height=1,
                initial_population=1,
                initial_exposed_fraction=0.0,
                vessel_material_cost=2.0,
                vessel_energy_cost=1.0,
            ),
            seed=991,
        )
        agent = next(iter(simulation.agents.values()))
        agent.knows_seafaring = True
        agent.material_inventory = 5.0
        agent.inventory = 3.0
        before_material = (
            simulation.world.total_materials()
            + agent.material_inventory
        )

        self.assertTrue(simulation._build_vessel(agent))
        after_build = (
            simulation.world.total_materials()
            + agent.material_inventory
        )
        self.assertAlmostEqual(
            before_material - after_build,
            simulation._last_material_consumed,
        )

        simulation._remove_agent(agent.id, cause="test")
        metrics = simulation.measure()
        self.assertEqual(metrics.food_lost_on_death, 3.0)
        self.assertEqual(metrics.material_lost_on_death, 3.0)
        self.assertAlmostEqual(
            before_material
            - (
                simulation.world.total_materials()
                + metrics.total_material_inventory
            ),
            metrics.material_consumed
            + metrics.material_lost_on_death,
        )


if __name__ == "__main__":
    unittest.main()
