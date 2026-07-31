"""Material objects are causal state, not scenery or engine-side labels."""

import hashlib
import unittest

from src.simulation import Simulation, SimulationConfig
from src.simulation.entities import EntityKind


def artifact_world(**overrides) -> Simulation:
    values = {
        "width": 1,
        "height": 1,
        "initial_population": 1,
        "initial_fauna_density": 0.0,
        "initial_exposed_fraction": 0.0,
        "environmental_exposure_rate_per_year": 0.0,
        "baseline_mortality_rate_per_year": 0.0,
        "frailty_mortality_rate_per_year": 0.0,
        "artifact_material_cost": 4.0,
        "artifact_energy_cost": 2.0,
    }
    values.update(overrides)
    return Simulation(SimulationConfig(**values), seed=17)


class ArtifactConstructionTests(unittest.TestCase):
    def test_building_spends_material_and_keeps_creator_provenance(
        self,
    ) -> None:
        simulation = artifact_world()
        builder = next(iter(simulation.agents.values()))
        builder.material_inventory = 5.0
        energy = builder.energy

        self.assertTrue(simulation._build_or_maintain_artifact(builder))

        artifact = next(iter(simulation.artifacts.values()))
        self.assertEqual(artifact.kind, EntityKind.ARTIFACT)
        self.assertEqual(
            simulation.entities.creator_of(artifact.id),
            builder.id,
        )
        self.assertEqual(builder.material_inventory, 1.0)
        self.assertEqual(builder.energy, energy - 2.0)
        self.assertEqual(simulation._last_material_consumed, 4.0)

        simulation._remove_agent(builder.id, cause="test")
        self.assertEqual(
            simulation.entities.creator_of(artifact.id),
            builder.id,
        )
        self.assertIn(artifact.id, simulation.artifacts)

    def test_only_one_object_is_built_per_cell_in_one_resolution(self) -> None:
        simulation = artifact_world(initial_population=2)
        first, second = simulation._ordered_agents()
        for agent in (first, second):
            agent.material_inventory = 5.0

        self.assertTrue(simulation._build_or_maintain_artifact(first))
        self.assertFalse(simulation._build_or_maintain_artifact(second))
        self.assertEqual(len(simulation.artifacts), 1)

    def test_maintenance_restores_condition_at_a_smaller_cost(self) -> None:
        simulation = artifact_world(
            artifact_maintenance_material_cost=1.0,
            artifact_maintenance_energy_cost=0.5,
            artifact_maintenance_restore=0.25,
        )
        builder = next(iter(simulation.agents.values()))
        builder.material_inventory = 5.0
        self.assertTrue(simulation._build_or_maintain_artifact(builder))
        artifact = next(iter(simulation.artifacts.values()))
        artifact.durability = 0.5
        builder.material_inventory = 2.0

        self.assertTrue(simulation._build_or_maintain_artifact(builder))

        self.assertEqual(artifact.durability, 0.75)
        self.assertEqual(builder.material_inventory, 1.0)
        self.assertEqual(simulation.total_artifact_maintenance, 1)


class ArtifactEffectTests(unittest.TestCase):
    def test_insulation_reduces_the_embodied_seasonal_cost(self) -> None:
        simulation = artifact_world(
            ticks_per_year=4,
            environmental_energy_cost_per_year=8.0,
            artifact_insulation=0.75,
        )
        agent = next(iter(simulation.agents.values()))
        agent.material_inventory = 5.0
        self.assertTrue(simulation._build_or_maintain_artifact(agent))
        simulation.world.rebuild_spatial_index(simulation.entities.placed())
        simulation.world.last_row_factors = [1.5]
        agent.energy = 50.0
        agent.age = 25.0
        simulation._last_environmental_energy_cost = 0.0

        simulation._apply_time_and_metabolism(ordered_agents=[agent])

        self.assertAlmostEqual(simulation._insulation_at(0, 0), 0.75)
        self.assertAlmostEqual(
            simulation._last_environmental_energy_cost,
            0.25,
        )

    def test_storage_accepts_harvest_overflow_and_supplies_eating(
        self,
    ) -> None:
        simulation = artifact_world(
            harvest_amount=3.0,
            artifact_storage_capacity=10.0,
        )
        agent = next(iter(simulation.agents.values()))
        agent.material_inventory = 5.0
        self.assertTrue(simulation._build_or_maintain_artifact(agent))
        artifact = next(iter(simulation.artifacts.values()))
        simulation.world.rebuild_spatial_index(simulation.entities.placed())
        agent.inventory = simulation.config.inventory_capacity - 1.0

        self.assertTrue(simulation._gather(agent))
        self.assertGreater(artifact.food_stored, 0.0)
        agent.inventory = 0.0
        agent.energy = 0.0
        stored = artifact.food_stored

        self.assertTrue(simulation._eat(agent))
        self.assertLess(artifact.food_stored, stored)
        self.assertGreater(agent.energy, 0.0)

    def test_decay_removes_object_and_accounts_for_stored_food(
        self,
    ) -> None:
        simulation = artifact_world(
            ticks_per_year=12,
            artifact_decay_rate_per_year=12.0,
            food_spoilage_rate_per_year=0.0,
        )
        agent = next(iter(simulation.agents.values()))
        agent.material_inventory = 5.0
        self.assertTrue(simulation._build_or_maintain_artifact(agent))
        artifact = next(iter(simulation.artifacts.values()))
        artifact.food_stored = 3.0

        simulation._advance_artifacts()

        self.assertEqual(len(simulation.artifacts), 0)
        self.assertEqual(simulation.total_artifacts_decayed, 1)
        self.assertEqual(simulation._last_food_lost_on_artifact_decay, 3.0)


class ArtifactOffSwitchTests(unittest.TestCase):
    BASELINES = {
        0: "7fbc48005b83852936497fbcc9ddbb038fdb21ac325664013ca721f69c427471",
        4: "79b40fb043435a862878757d3356f2d3cca3665829f97740c6d701c541fcaa26",
        19: "992c8dc48a7add59d7cb7ebce8ccb34599126b6d5dcfa8f9c2711d98f4f5d391",
    }

    def test_disabled_artifacts_reproduce_pre_change_digests(self) -> None:
        for seed, expected in self.BASELINES.items():
            with self.subTest(seed=seed):
                simulation = Simulation(
                    SimulationConfig(
                        width=12,
                        height=12,
                        initial_population=20,
                        artifacts_enabled=False,
                    ),
                    seed=seed,
                )
                simulation.run(24)
                actual = hashlib.sha256(
                    repr(simulation.state_digest()).encode()
                ).hexdigest()
                self.assertEqual(actual, expected)

    def test_arms_start_with_identical_people_and_legacy_policies(
        self,
    ) -> None:
        def founders(enabled: bool):
            simulation = Simulation(
                SimulationConfig(
                    width=12,
                    height=12,
                    initial_population=20,
                    artifacts_enabled=enabled,
                ),
                seed=31,
            )
            return [
                (
                    agent.id,
                    agent.x,
                    agent.y,
                    agent.age,
                    agent.energy,
                    agent.genome,
                    agent.traits,
                    agent.reproductive_role,
                    agent.network.hidden,
                    agent.network.output[:-1]
                    if enabled
                    else agent.network.output,
                )
                for agent in simulation._ordered_agents()
            ]

        self.assertEqual(founders(False), founders(True))


if __name__ == "__main__":
    unittest.main()
