import unittest
from dataclasses import replace

from src.simulation import ReproductiveRole, Simulation, SimulationConfig


class SimulationTests(unittest.TestCase):
    def test_same_seed_and_config_are_reproducible(self) -> None:
        config = SimulationConfig(
            width=10,
            height=10,
            initial_population=30,
            metrics_interval=5,
        )
        first = Simulation(config, seed=8128)
        second = Simulation(config, seed=8128)

        first.run(25)
        second.run(25)

        self.assertEqual(first.state_digest(), second.state_digest())
        self.assertEqual(first.measure().to_dict(), second.measure().to_dict())

    def test_different_seeds_create_different_worlds(self) -> None:
        config = SimulationConfig(
            width=8,
            height=8,
            initial_population=10,
        )

        first = Simulation(config, seed=1)
        second = Simulation(config, seed=2)

        self.assertNotEqual(first.state_digest(), second.state_digest())

    def test_resource_levels_never_exceed_local_capacity(self) -> None:
        config = SimulationConfig(
            width=6,
            height=6,
            initial_population=25,
            resource_regeneration=20.0,
        )
        simulation = Simulation(config, seed=3)
        simulation.run(30)

        for resource, capacity in zip(
            simulation.world.resources,
            simulation.world.capacity,
        ):
            self.assertGreaterEqual(resource, 0.0)
            self.assertLessEqual(resource, capacity)
        for material, capacity in zip(
            simulation.world.materials,
            simulation.world.material_capacity,
        ):
            self.assertGreaterEqual(material, 0.0)
            self.assertLessEqual(material, capacity)

    def test_starvation_can_end_a_population_without_scripted_death(self) -> None:
        config = SimulationConfig(
            width=4,
            height=4,
            initial_population=12,
            initial_resource_fraction=0.0,
            resource_regeneration=0.0,
            initial_inventory=0.0,
            initial_energy_minimum=1.0,
            initial_energy_maximum=1.0,
            base_metabolism_minimum=1.0,
            base_metabolism_maximum=1.0,
            starvation_damage=200.0,
        )
        simulation = Simulation(config, seed=4)

        simulation.step()

        self.assertEqual(len(simulation.agents), 0)
        self.assertEqual(simulation.total_deaths, 12)

    def test_reproduction_creates_inherited_generation(self) -> None:
        config = SimulationConfig(
            width=2,
            height=2,
            initial_population=10,
            initial_energy_minimum=100.0,
            initial_energy_maximum=100.0,
            base_metabolism_minimum=0.01,
            base_metabolism_maximum=0.01,
            reproduction_energy=10.0,
            reproduction_cost=1.0,
            reproduction_weight=1_000.0,
            hunger_weight=0.0,
            gather_weight=0.0,
            sharing_weight=0.0,
            movement_weight=0.0,
            decision_noise=0.0,
            maximum_conception_probability=1.0,
            gestation_years=1.0 / 12.0,
        )
        simulation = Simulation(config, seed=5)
        for index, agent in enumerate(simulation.agents.values()):
            agent.reproductive_role = (
                ReproductiveRole.OVA
                if index % 2 == 0
                else ReproductiveRole.SPERM
            )
            agent.traits = replace(agent.traits, fertility=1.0)

        simulation.run(2)

        children = [
            agent
            for agent in simulation.agents.values()
            if agent.generation == 1
        ]
        self.assertGreater(len(children), 0)
        self.assertTrue(all(child.parents is not None for child in children))
        self.assertEqual(simulation.total_births, len(children))

    def test_metrics_are_sampled_at_configured_interval(self) -> None:
        streamed = []
        config = SimulationConfig(
            initial_population=5,
            metrics_interval=3,
            metrics_history_capacity=2,
        )
        simulation = Simulation(config, seed=6, metrics_sink=streamed.append)

        simulation.run(7)

        self.assertEqual(
            [metrics.tick for metrics in simulation.metrics_history],
            [3, 6],
        )
        self.assertEqual([metrics.tick for metrics in streamed], [0, 3, 6])

    def test_event_log_is_bounded(self) -> None:
        config = SimulationConfig(
            width=2,
            height=2,
            initial_population=20,
            initial_energy_minimum=100.0,
            initial_energy_maximum=100.0,
            base_metabolism_minimum=0.01,
            base_metabolism_maximum=0.01,
            reproduction_energy=10.0,
            reproduction_cost=1.0,
            reproduction_weight=1_000.0,
            hunger_weight=0.0,
            gather_weight=0.0,
            sharing_weight=0.0,
            movement_weight=0.0,
            decision_noise=0.0,
            event_log_capacity=3,
            maximum_conception_probability=1.0,
        )
        simulation = Simulation(config, seed=7)
        for index, agent in enumerate(simulation.agents.values()):
            agent.reproductive_role = (
                ReproductiveRole.OVA
                if index % 2 == 0
                else ReproductiveRole.SPERM
            )
            agent.traits = replace(agent.traits, fertility=1.0)

        simulation.run(2)

        self.assertLessEqual(len(simulation.events), 3)

    def test_invalid_configuration_fails_early(self) -> None:
        with self.assertRaises(ValueError):
            SimulationConfig(width=0)
        with self.assertRaises(ValueError):
            SimulationConfig(initial_population=-1)
        with self.assertRaises(ValueError):
            SimulationConfig(gene_mutation_probability=1.1)
        with self.assertRaises(ValueError):
            SimulationConfig(gene_crossover_probability=-0.1)
        with self.assertRaises(ValueError):
            SimulationConfig(initial_age_minimum=-1.0)
        with self.assertRaises(ValueError):
            SimulationConfig(width=4.5)
        with self.assertRaises(ValueError):
            SimulationConfig(harvest_amount=-1.0)

    def test_seeded_stress_run_preserves_invariants(self) -> None:
        simulation = Simulation(
            SimulationConfig(
                width=12,
                height=12,
                initial_population=80,
            ),
            seed=15,
        )

        simulation.run(60)

        simulation.validate_state()
        metrics = simulation.measure()
        self.assertGreaterEqual(metrics.genetic_diversity, 0.0)
        self.assertLessEqual(metrics.genetic_diversity, 0.5)
        self.assertGreaterEqual(metrics.action_entropy, 0.0)
        self.assertLessEqual(metrics.action_entropy, 1.0)


if __name__ == "__main__":
    unittest.main()
