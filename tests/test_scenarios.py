import json
import unittest

from src.simulation import (
    CountrySpec,
    Rectangle,
    Scenario,
    Simulation,
    SimulationConfig,
    Terrain,
)


def island_scenario(population: int = 1) -> Scenario:
    return Scenario(
        countries=(
            CountrySpec(
                id=0,
                name="West",
                region=Rectangle(0, 0, 2, 2),
                population=population,
                religion="sun",
                generosity_mean=0.8,
                exploration_mean=0.7,
                curiosity_mean=1.0,
                conformity_mean=0.6,
            ),
            CountrySpec(
                id=1,
                name="East",
                region=Rectangle(3, 0, 2, 2),
                population=0,
                religion="stars",
            ),
        ),
        seas=(Rectangle(2, 0, 1, 2),),
    )


class ScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = SimulationConfig(
            width=5,
            height=2,
            initial_population=0,
            cultural_trait_variation=0.0,
            initial_energy_minimum=100.0,
            initial_energy_maximum=100.0,
            research_material_cost=0.1,
            research_energy_cost=0.1,
            discovery_threshold=0.01,
            vessel_material_cost=1.0,
            vessel_energy_cost=1.0,
            vessel_durability=5.0,
        )

    def test_country_founders_use_region_and_cultural_start(self) -> None:
        simulation = Simulation(
            self.config,
            seed=1,
            scenario=island_scenario(population=8),
        )

        for agent in simulation.agents.values():
            self.assertEqual(agent.birth_country_id, 0)
            self.assertEqual(agent.belief_id, 0)
            self.assertIn(agent.x, (0, 1))
            self.assertEqual(agent.culture.generosity, 0.8)
            self.assertEqual(agent.culture.curiosity, 1.0)

    def test_sea_requires_discovery_material_and_vessel(self) -> None:
        simulation = Simulation(
            self.config,
            seed=2,
            scenario=island_scenario(),
        )
        agent = next(iter(simulation.agents.values()))
        agent.x, agent.y = 1, 0
        agent.material_inventory = 5.0

        self.assertFalse(simulation._move(agent, (2, 0)))
        self.assertTrue(simulation._research(agent))
        self.assertTrue(agent.knows_seafaring)
        self.assertEqual(simulation.total_inventions, 1)
        self.assertTrue(simulation._build_vessel(agent))
        self.assertTrue(simulation._move(agent, (2, 0)))
        self.assertEqual(
            simulation.world.terrain[
                simulation.world.cell_index(agent.x, agent.y)
            ],
            Terrain.SEA,
        )
        self.assertTrue(simulation._move(agent, (3, 0)))
        self.assertEqual(simulation.world.country_at(agent.x, agent.y), 1)
        self.assertEqual(simulation.total_sea_crossings, 1)

    def test_snapshot_is_json_serializable_and_columnar(self) -> None:
        simulation = Simulation(
            self.config,
            seed=3,
            scenario=island_scenario(population=3),
        )

        snapshot = simulation.snapshot()

        json.dumps(snapshot)
        self.assertEqual(snapshot["schema_version"], 7)
        self.assertEqual(snapshot["snapshot_kind"], "visualization")
        self.assertIn("config", snapshot)
        self.assertIn("config_schema_version", snapshot)
        self.assertIn("genome_schema_version", snapshot)
        self.assertEqual(
            len(snapshot["action_preference_order"]),
            len(snapshot["agents"]["learned_preferences"][0]),
        )
        self.assertEqual(snapshot["world"]["width"], 5)
        self.assertEqual(len(snapshot["agents"]["id"]), 3)
        for field in (
            "metabolism",
            "harvest_skill",
            "inherited_generosity",
            "inherited_exploration",
            "inherited_curiosity",
            "inherited_conformity",
            "risk_tolerance",
            "vision",
        ):
            self.assertEqual(len(snapshot["agents"][field]), 3)
        self.assertEqual(
            snapshot["world"]["terrain"][
                simulation.world.cell_index(2, 0)
            ],
            Terrain.SEA,
        )

    def test_overlapping_country_land_is_rejected(self) -> None:
        scenario = Scenario(
            countries=(
                CountrySpec(0, "A", Rectangle(0, 0, 3, 2), 1),
                CountrySpec(1, "B", Rectangle(1, 0, 3, 2), 1),
            )
        )

        with self.assertRaises(ValueError):
            Simulation(self.config, scenario=scenario)

    def test_country_labels_must_be_safe_strings(self) -> None:
        scenario = Scenario(
            countries=(
                CountrySpec(
                    0,
                    "A",
                    Rectangle(0, 0, 2, 2),
                    1,
                    religion=[],
                ),
            )
        )

        with self.assertRaises(ValueError):
            Simulation(self.config, scenario=scenario)


if __name__ == "__main__":
    unittest.main()
