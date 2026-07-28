import json
import unittest
from unittest.mock import patch

from src.human_sim_service.contracts import RenderFrame, _copy_mapping
from src.human_sim_service import (
    AGENT_DETAIL_SCHEMA_VERSION,
    FRAME_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    PROTOCOL_VERSION,
    AgentNotFoundError,
    PythonSimulationBackend,
    RunManager,
)
from src.simulation import (
    CountrySpec,
    Rectangle,
    Scenario,
    SimulationConfig,
)


def small_definition():
    config = SimulationConfig(
        width=5,
        height=2,
        initial_population=0,
        initial_exposed_fraction=0.0,
    )
    scenario = Scenario(
        countries=(
            CountrySpec(
                id=0,
                name="West",
                region=Rectangle(0, 0, 2, 2),
                population=3,
                religion="sun",
            ),
            CountrySpec(
                id=1,
                name="East",
                region=Rectangle(3, 0, 2, 2),
                population=1,
                religion="stars",
            ),
        ),
        seas=(Rectangle(2, 0, 1, 2),),
    )
    return config, scenario


class ServiceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        config, scenario = small_definition()
        self.manager = RunManager(id_factory=lambda: "contract-run")
        self.manifest = self.manager.create(
            config=config,
            seed=42,
            scenario=scenario,
        )

    def test_manifest_contains_static_versioned_contract(self) -> None:
        manifest = self.manifest

        json.dumps(manifest)
        self.assertEqual(manifest["protocol_version"], PROTOCOL_VERSION)
        self.assertEqual(
            manifest["schema_version"],
            MANIFEST_SCHEMA_VERSION,
        )
        self.assertEqual(manifest["kind"], "run_manifest")
        self.assertEqual(manifest["run_id"], "contract-run")
        self.assertEqual(manifest["sequence"], 0)
        self.assertEqual(manifest["status"], "paused")
        self.assertEqual(manifest["seed"], 42)
        self.assertEqual(manifest["population"], 4)
        self.assertEqual(manifest["world"]["width"], 5)
        self.assertEqual(len(manifest["world"]["terrain"]), 10)
        self.assertEqual(len(manifest["world"]["country"]), 10)
        self.assertEqual(len(manifest["world"]["food_productivity"]), 10)
        self.assertEqual(len(manifest["world"]["seasonal_amplitude"]), 10)
        self.assertEqual(len(manifest["world"]["seasonal_phase"]), 10)
        self.assertEqual(
            len(manifest["world"]["material_productivity"]),
            10,
        )
        self.assertIn("config_schema_version", manifest["model"])
        self.assertIn("genome_schema_version", manifest["model"])
        self.assertTrue(manifest["capabilities"]["resource_layers"])

    def test_frame_has_only_compact_render_columns_by_default(self) -> None:
        frame = self.manager.frame("contract-run")

        json.dumps(frame)
        self.assertEqual(frame["protocol_version"], PROTOCOL_VERSION)
        self.assertEqual(frame["schema_version"], FRAME_SCHEMA_VERSION)
        self.assertEqual(frame["kind"], "render_frame")
        self.assertNotIn("resources", frame)
        self.assertNotIn("config", frame)
        self.assertNotIn("scenario", frame)
        self.assertNotIn("relationships", frame)
        expected_columns = {
            "id",
            "x",
            "y",
            "birth_country",
            "belief",
            "age",
            "energy_fraction",
            "health_fraction",
            "body_condition",
            "frailty",
            "brain_kind",
            "last_action",
            "last_action_success",
            "infection_stage",
            "knows_seafaring",
            "known_techniques",
            "vessel_durability",
        }
        self.assertEqual(set(frame["agents"]), expected_columns)
        self.assertEqual(len(frame["agents"]["id"]), 4)
        self.assertTrue(
            all(isinstance(value, str) for value in frame["agents"]["id"])
        )
        for values in frame["agents"].values():
            self.assertEqual(len(values), 4)
        for value in frame["agents"]["energy_fraction"]:
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
        for value in frame["agents"]["health_fraction"]:
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_frame_carries_the_herd_a_renderer_has_to_draw(self) -> None:
        """Animals reach the wire, or nothing can draw one.

        The backend has always built these columns; the frame projection
        dropped them on the way out, so every renderer saw a world with no
        animals in it while the engine was simulating a herd.
        """

        frame = self.manager.frame("contract-run")

        self.assertEqual(
            set(frame["fauna"]),
            {"id", "x", "y", "energy", "vigilance"},
        )
        herd = len(frame["fauna"]["id"])
        self.assertEqual(herd, frame["metrics"]["fauna_population"])
        for values in frame["fauna"].values():
            self.assertEqual(len(values), herd)

    def test_frame_without_a_herd_reports_an_empty_one(self) -> None:
        """Absent animals are an answer, not a missing key."""

        frame = RenderFrame(
            run_id="contract-run",
            sequence=1,
            status="paused",
            tick=0,
            year=0.0,
            metrics={},
            agents={"id": []},
        ).to_dict()

        self.assertEqual(
            frame["fauna"],
            {"id": [], "x": [], "y": [], "energy": [], "vigilance": []},
        )

    def test_resource_layers_are_opt_in(self) -> None:
        frame = self.manager.frame(
            "contract-run",
            include_resources=True,
        )

        self.assertEqual(len(frame["resources"]["food"]), 10)
        self.assertEqual(len(frame["resources"]["materials"]), 10)

    def test_frame_reuses_metrics_already_sampled_for_current_tick(
        self,
    ) -> None:
        config, scenario = small_definition()
        backend = PythonSimulationBackend(
            config=config,
            seed=42,
            scenario=scenario,
        )

        with patch.object(
            backend._simulation,
            "measure",
            side_effect=AssertionError("current metrics were recomputed"),
        ):
            frame = backend.frame()

        self.assertEqual(frame.tick, 0)
        self.assertEqual(frame.metrics["tick"], 0)

    def test_agent_detail_is_deep_json_projection_with_string_ids(
        self,
    ) -> None:
        agent_id = self.manager.frame("contract-run")["agents"]["id"][0]

        detail = self.manager.agent_detail("contract-run", agent_id)

        json.dumps(detail)
        self.assertEqual(detail["protocol_version"], PROTOCOL_VERSION)
        self.assertEqual(
            detail["schema_version"],
            AGENT_DETAIL_SCHEMA_VERSION,
        )
        self.assertEqual(detail["kind"], "agent_detail")
        self.assertEqual(detail["agent"]["id"], agent_id)
        self.assertIn("genome", detail["agent"]["biology"])
        self.assertIn("traits", detail["agent"]["biology"])
        self.assertIn("preferences", detail["agent"]["brain"])
        self.assertIn("relationships", detail["agent"])
        for relationship in detail["agent"]["relationships"]:
            self.assertIsInstance(relationship["agent_id"], str)

    def test_missing_agent_has_service_level_error(self) -> None:
        with self.assertRaises(AgentNotFoundError):
            self.manager.agent_detail("contract-run", "999999")

    def test_full_export_retains_existing_snapshot_contract(self) -> None:
        snapshot = self.manager.export_snapshot("contract-run")

        json.dumps(snapshot)
        self.assertEqual(snapshot["snapshot_kind"], "visualization")
        self.assertIn("world", snapshot)
        self.assertIn("agents", snapshot)
        self.assertIn("relationships", snapshot)
        self.assertIn("genome_a", snapshot["agents"])


class ProjectionOwnershipTests(unittest.TestCase):
    """A projection must never alias mutable backend or engine state."""

    def test_nested_containers_are_rebuilt(self) -> None:
        source = {
            "layer": [1.0, 2.0, 3.0],
            "nested": {"inner": [{"deep": [4.0]}]},
            "scalar": 7,
        }

        copied = _copy_mapping(source)

        self.assertEqual(copied, source)
        self.assertIsNot(copied["layer"], source["layer"])
        self.assertIsNot(copied["nested"], source["nested"])
        self.assertIsNot(copied["nested"]["inner"], source["nested"]["inner"])
        self.assertIsNot(
            copied["nested"]["inner"][0]["deep"],
            source["nested"]["inner"][0]["deep"],
        )

    def test_mutating_a_copy_leaves_the_source_untouched(self) -> None:
        source = {"layer": [1.0, 2.0], "nested": {"inner": [{"deep": [4.0]}]}}

        copied = _copy_mapping(source)
        copied["layer"].append(99.0)
        copied["nested"]["inner"][0]["deep"][0] = -1.0

        self.assertEqual(source["layer"], [1.0, 2.0])
        self.assertEqual(source["nested"]["inner"][0]["deep"], [4.0])

    def test_frame_payload_does_not_alias_engine_arrays(self) -> None:
        config, scenario = small_definition()
        manager = RunManager(id_factory=lambda: "ownership-run")
        manager.create(config=config, seed=5, scenario=scenario)
        frame = manager.frame("ownership-run", include_resources=True)

        food = frame["resources"]["food"]
        original = list(food)
        food[0] = 12345.0
        refetched = manager.frame("ownership-run", include_resources=True)

        self.assertEqual(refetched["resources"]["food"], original)


if __name__ == "__main__":
    unittest.main()
