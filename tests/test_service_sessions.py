import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from src.human_sim_service import (
    BackendAgent,
    BackendFrame,
    BackendManifest,
    DuplicateRunError,
    RunDefinition,
    RunFailedError,
    RunManager,
    RunNotFoundError,
    RunSession,
)
from src.simulation import SimulationConfig


class RecordingBackend:
    """Intentionally unsynchronized backend for testing the session lock."""

    def __init__(self, *, config, seed, scenario) -> None:
        self.config = config
        self.seed = seed
        self.scenario = scenario
        self.tick = 0
        self.active_advances = 0
        self.maximum_active_advances = 0

    def advance(self, ticks: int) -> None:
        self.active_advances += 1
        self.maximum_active_advances = max(
            self.maximum_active_advances,
            self.active_advances,
        )
        time.sleep(0.001)
        self.tick += ticks
        self.active_advances -= 1

    def manifest(self) -> BackendManifest:
        return BackendManifest(
            seed=self.seed,
            tick=self.tick,
            year=float(self.tick),
            population=0,
            model={},
            config=self.config.to_dict(),
            scenario=self.scenario.to_dict(),
            world={
                "width": self.config.width,
                "height": self.config.height,
                "wrap_world": self.config.wrap_world,
                "terrain": [],
                "country": [],
                "food_capacity": [],
                "food_productivity": [],
                "seasonal_amplitude": [],
                "seasonal_phase": [],
                "material_capacity": [],
                "material_productivity": [],
            },
        )

    def frame(self, include_resources: bool = False) -> BackendFrame:
        resources = (
            {"food": [], "materials": []}
            if include_resources
            else None
        )
        return BackendFrame(
            tick=self.tick,
            year=float(self.tick),
            metrics={"tick": self.tick, "population": 0},
            agents={
                "id": [],
                "x": [],
                "y": [],
            },
            resources=resources,
        )

    def agent(self, agent_id: int) -> BackendAgent:
        raise KeyError(agent_id)

    def export_snapshot(self) -> Dict[str, object]:
        return {"tick": self.tick}


class RecordingFactory:
    def __init__(self) -> None:
        self.instances = []

    def __call__(self, *, config, seed, scenario):
        backend = RecordingBackend(
            config=config,
            seed=seed,
            scenario=scenario,
        )
        self.instances.append(backend)
        return backend


class FailFirstFactory(RecordingFactory):
    def __call__(self, *, config, seed, scenario):
        backend = super().__call__(
            config=config,
            seed=seed,
            scenario=scenario,
        )
        if len(self.instances) == 1:
            def fail(_ticks):
                raise RuntimeError("backend failure")

            backend.advance = fail
        return backend


class ServiceSessionTests(unittest.TestCase):
    def test_step_is_serialized_and_sequence_orders_responses(self) -> None:
        factory = RecordingFactory()
        definition = RunDefinition.from_values(
            config=SimulationConfig(
                width=2,
                height=2,
                initial_population=0,
            ),
            seed=9,
        )
        session = RunSession(
            "serialized",
            definition,
            backend_factory=factory,
        )

        with ThreadPoolExecutor(max_workers=8) as executor:
            responses = list(executor.map(lambda _: session.step(), range(20)))

        backend = factory.instances[0]
        self.assertEqual(backend.tick, 20)
        self.assertEqual(backend.maximum_active_advances, 1)
        self.assertEqual(
            sorted(response["sequence"] for response in responses),
            list(range(1, 21)),
        )
        self.assertTrue(
            all(response["status"] == "paused" for response in responses)
        )

    def test_reset_reconstructs_original_definition(self) -> None:
        manager = RunManager(id_factory=lambda: "resettable")
        manager.create(
            config={
                "width": 4,
                "height": 3,
                "initial_population": 5,
                "initial_exposed_fraction": 0.0,
            },
            seed=73,
        )
        initial = manager.frame(
            "resettable",
            include_resources=True,
        )
        advanced = manager.step("resettable", ticks=3)

        reset = manager.reset(
            "resettable",
            include_resources=True,
        )

        self.assertEqual(advanced["tick"], 3)
        self.assertEqual(reset["tick"], 0)
        self.assertEqual(reset["sequence"], 2)
        self.assertEqual(reset["agents"], initial["agents"])
        self.assertEqual(reset["resources"], initial["resources"])

    def test_failed_run_must_be_reset_before_it_can_step(self) -> None:
        factory = FailFirstFactory()
        session = RunSession(
            "recoverable",
            RunDefinition.from_values(
                config=SimulationConfig(initial_population=0),
            ),
            backend_factory=factory,
        )

        with self.assertRaisesRegex(RuntimeError, "backend failure"):
            session.step()

        self.assertEqual(session.status, "failed")
        self.assertEqual(session.sequence, 1)
        self.assertIn("RuntimeError", session.last_error)
        with self.assertRaises(RunFailedError):
            session.step()

        reset = session.reset()
        advanced = session.step()
        self.assertEqual(reset["status"], "paused")
        self.assertEqual(advanced["tick"], 1)
        self.assertEqual(advanced["sequence"], 3)

    def test_manager_accepts_json_mappings_for_config_and_scenario(
        self,
    ) -> None:
        manager = RunManager(id_factory=lambda: "mapped")
        manifest = manager.create(
            config={
                "width": 3,
                "height": 2,
                "initial_population": 0,
            },
            scenario={
                "countries": [{
                    "id": 4,
                    "name": "Mapped",
                    "region": [0, 0, 3, 2],
                    "population": 2,
                }],
                "seas": [],
            },
        )

        self.assertEqual(manifest["population"], 2)
        self.assertEqual(manifest["scenario"]["countries"][0]["id"], 4)

    def test_registry_rejects_duplicates_and_unknown_runs(self) -> None:
        manager = RunManager()
        manager.create(
            run_id="same",
            config=SimulationConfig(initial_population=0),
        )

        with self.assertRaises(DuplicateRunError):
            manager.create(
                run_id="same",
                config=SimulationConfig(initial_population=0),
            )
        with self.assertRaises(RunNotFoundError):
            manager.frame("absent")

    def test_step_arguments_are_strict(self) -> None:
        manager = RunManager(id_factory=lambda: "strict")
        manager.create(
            config=SimulationConfig(initial_population=0),
        )

        for ticks in (0, -1, True, 1.5):
            with self.subTest(ticks=ticks):
                with self.assertRaises(ValueError):
                    manager.step("strict", ticks=ticks)
        with self.assertRaises(ValueError):
            manager.frame("strict", include_resources=1)

    def test_list_manifests_is_stably_ordered(self) -> None:
        manager = RunManager()
        manager.create(
            run_id="zeta",
            config=SimulationConfig(initial_population=0),
        )
        manager.create(
            run_id="alpha",
            config=SimulationConfig(initial_population=0),
        )

        self.assertEqual(
            [
                manifest["run_id"]
                for manifest in manager.list_manifests()
            ],
            ["alpha", "zeta"],
        )


if __name__ == "__main__":
    unittest.main()
