import time
import unittest

try:
    from fastapi.testclient import TestClient

    from src.human_sim_service.api import create_app
    from src.human_sim_service.sessions import RunManager
except ModuleNotFoundError:
    TestClient = None
    create_app = None
    RunManager = None


@unittest.skipIf(
    TestClient is None,
    "optional API dependencies are not installed",
)
class ServiceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        manager = RunManager(id_factory=lambda: "test-run")
        self.client = TestClient(create_app(manager))
        self.create_payload = {
            "seed": 23,
            "config": {
                "width": 5,
                "height": 4,
                "initial_population": 6,
                "initial_exposed_fraction": 0.0,
                "metrics_interval": 1,
            },
        }

    def test_health_and_config_catalog_are_versioned(self) -> None:
        health = self.client.get("/api/v1/health")
        catalog = self.client.get("/api/v1/catalog/config")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["protocol_version"], 1)
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.json()["defaults"]["width"], 64)

    def test_create_observe_step_inspect_reset_and_export(self) -> None:
        created = self.client.post(
            "/api/v1/runs",
            json=self.create_payload,
        )
        self.assertEqual(created.status_code, 201)
        manifest = created.json()
        self.assertEqual(manifest["kind"], "run_manifest")
        self.assertEqual(manifest["run_id"], "test-run")
        self.assertEqual(manifest["status"], "paused")
        self.assertEqual(len(manifest["world"]["terrain"]), 20)

        frame_response = self.client.get(
            "/api/v1/runs/test-run/frame",
            params={"include_resources": True},
        )
        frame = frame_response.json()
        self.assertEqual(frame_response.status_code, 200)
        self.assertEqual(frame["kind"], "render_frame")
        self.assertEqual(frame["tick"], 0)
        self.assertEqual(len(frame["agents"]["id"]), 6)
        self.assertIn("resources", frame)

        agent_id = frame["agents"]["id"][0]
        detail_response = self.client.get(
            f"/api/v1/runs/test-run/agents/{agent_id}"
        )
        detail = detail_response.json()
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail["kind"], "agent_detail")
        self.assertEqual(detail["agent"]["id"], agent_id)

        stepped = self.client.post(
            "/api/v1/runs/test-run/steps",
            json={"ticks": 2, "include_resources": False},
        )
        self.assertEqual(stepped.status_code, 200)
        self.assertEqual(stepped.json()["tick"], 2)
        self.assertNotIn("resources", stepped.json())

        reset = self.client.post(
            "/api/v1/runs/test-run/reset",
            json={"include_resources": True},
        )
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.json()["tick"], 0)

        exported = self.client.get(
            "/api/v1/runs/test-run/snapshot"
        )
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(
            exported.json()["snapshot_kind"],
            "visualization",
        )

    def test_a_run_can_be_left_advancing_and_then_found_again(self) -> None:
        """The unattended case: start it, walk away, reattach later."""

        self.client.post("/api/v1/runs", json=self.create_payload)

        started = self.client.post(
            "/api/v1/runs/test-run/playback",
            json={"playing": True, "seconds_per_year": 0},
        )
        self.assertEqual(started.status_code, 200)
        self.assertTrue(started.json()["playback"]["playing"])
        self.assertEqual(started.json()["status"], "running")

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self.client.get("/api/v1/runs/test-run/frame").json()["tick"]:
                break
            time.sleep(0.02)

        # A client that arrives later is told the world is already moving,
        # which is the one thing it cannot work out for itself.
        rejoined = self.client.get("/api/v1/runs/test-run/manifest").json()
        self.assertTrue(rejoined["capabilities"]["playback"])
        self.assertTrue(rejoined["playback"]["playing"])
        self.assertEqual(rejoined["playback"]["seconds_per_year"], 0)
        self.assertGreater(rejoined["tick"], 0)

        # Pausing without naming a pace keeps the pace for next time.
        paused = self.client.post(
            "/api/v1/runs/test-run/playback",
            json={"playing": False},
        )
        self.assertEqual(paused.status_code, 200)
        self.assertFalse(paused.json()["playback"]["playing"])
        self.assertEqual(paused.json()["playback"]["seconds_per_year"], 0)
        settled = paused.json()["tick"]
        time.sleep(0.2)
        self.assertEqual(
            self.client.get("/api/v1/runs/test-run/frame").json()["tick"],
            settled,
        )

        read_back = self.client.get("/api/v1/runs/test-run/playback")
        self.assertEqual(read_back.status_code, 200)
        self.assertFalse(read_back.json()["playback"]["playing"])

        deleted = self.client.delete("/api/v1/runs/test-run")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            self.client.get("/api/v1/runs/test-run/manifest").status_code,
            404,
        )
        self.assertEqual(
            self.client.delete("/api/v1/runs/test-run").status_code,
            404,
        )

    def test_checkpoint_can_be_downloaded_and_restored(self) -> None:
        self.client.post("/api/v1/runs", json=self.create_payload)
        self.client.post(
            "/api/v1/runs/test-run/steps",
            json={"ticks": 4},
        )

        exported = self.client.get(
            "/api/v1/runs/test-run/checkpoint"
        )
        restored = self.client.post(
            "/api/v1/checkpoints/restore",
            json={
                "run_id": "restored-run",
                "checkpoint": exported.json(),
            },
        )

        self.assertEqual(exported.status_code, 200)
        self.assertEqual(
            exported.json()["checkpoint_kind"],
            "resumable",
        )
        self.assertEqual(restored.status_code, 201)
        self.assertEqual(restored.json()["run_id"], "restored-run")
        self.assertEqual(restored.json()["status"], "paused")
        self.assertEqual(restored.json()["tick"], 4)

    def test_playback_requests_are_strict(self) -> None:
        self.client.post("/api/v1/runs", json=self.create_payload)

        for payload in (
            {"playing": True, "seconds_per_year": -1},
            {"playing": "yes"},
            {"playing": True, "unknown": 1},
            {},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/v1/runs/test-run/playback",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)

        self.assertEqual(
            self.client.post(
                "/api/v1/runs/absent/playback",
                json={"playing": False},
            ).status_code,
            404,
        )

    def test_validation_and_missing_resources_return_structured_errors(
        self,
    ) -> None:
        invalid = self.client.post(
            "/api/v1/scenarios/validate",
            json={
                "config": {"width": 2, "height": 2},
                "scenario": {
                    "countries": [{
                        "id": 0,
                        "name": "Outside",
                        "region": [0, 0, 3, 2],
                        "population": 1,
                    }],
                },
            },
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertIn("message", invalid.json()["error"])

        missing = self.client.get(
            "/api/v1/runs/does-not-exist/frame"
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["protocol_version"], 1)

    def test_request_models_reject_ambiguous_values(self) -> None:
        seed = self.client.post(
            "/api/v1/runs",
            json={"seed": True},
        )
        self.assertEqual(seed.status_code, 422)

        self.client.post("/api/v1/runs", json=self.create_payload)
        ticks = self.client.post(
            "/api/v1/runs/test-run/steps",
            json={"ticks": True},
        )
        self.assertEqual(ticks.status_code, 422)


if __name__ == "__main__":
    unittest.main()
