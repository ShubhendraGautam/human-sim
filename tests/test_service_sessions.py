import threading
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
    plan_playback,
)
from src.human_sim_service.sessions import PlaybackPlan
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
            fauna={"id": [], "x": [], "y": [], "energy": [],
                   "vigilance": []},
            artifacts={
                "id": [], "x": [], "y": [], "durability": [],
                "insulation": [], "storage_capacity": [],
                "food_stored": [], "occupancy_capacity": [],
                "occupancy": [],
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

    def test_playback_plan_reads_a_pace_as_batches_and_waits(self) -> None:
        """A pace is wall-clock time per simulated year, not ticks/second."""

        # Slow enough to see every tick: one at a time, waiting between.
        self.assertEqual(plan_playback(120.0, 12), PlaybackPlan(1, 10.0))
        # Too fast for per-tick bookkeeping to be worth it: batch them.
        fast = plan_playback(1.2, 12)
        self.assertGreater(fast.ticks, 1)
        self.assertAlmostEqual(fast.interval, fast.ticks * 0.1)
        # A batch never hides more than a year of change.
        self.assertEqual(plan_playback(0.0001, 12).ticks, 12)
        # No pace, and zero, both mean "as fast as this machine manages".
        for pace in (None, 0.0):
            with self.subTest(pace=pace):
                self.assertEqual(plan_playback(pace, 12).interval, 0.0)

    def test_engine_advances_a_run_with_nobody_asking(self) -> None:
        """The point of the whole arrangement: no client, still moving."""

        manager = RunManager(id_factory=lambda: "unattended")
        manager.create(config=SimulationConfig(initial_population=0))
        self.addCleanup(manager.close)

        manager.set_playback("unattended", True, seconds_per_year=0.0)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if manager.manifest("unattended")["tick"] > 0:
                break
            time.sleep(0.02)

        running = manager.manifest("unattended")
        self.assertGreater(running["tick"], 0)
        self.assertEqual(running["status"], "running")
        self.assertTrue(running["playback"]["playing"])

        manager.set_playback("unattended", False)
        settled = manager.manifest("unattended")["tick"]
        time.sleep(0.2)
        stopped = manager.manifest("unattended")
        self.assertEqual(stopped["tick"], settled)
        self.assertEqual(stopped["status"], "paused")
        self.assertFalse(stopped["playback"]["playing"])

    def test_a_driven_run_can_still_be_read(self) -> None:
        """Observation must not have to wait for the world to stop."""

        manager = RunManager(id_factory=lambda: "readable")
        manager.create(config=SimulationConfig(initial_population=0))
        self.addCleanup(manager.close)
        manager.set_playback("readable", True, seconds_per_year=0.0)

        for _ in range(20):
            frame = manager.frame("readable")
            self.assertEqual(frame["kind"], "render_frame")
            self.assertIn(frame["status"], {"running", "stepping"})

        manager.set_playback("readable", False)

    def test_an_unpaced_run_does_not_lock_observers_out(self) -> None:
        """A world going flat out must still be watchable.

        Regression: an unpaced driver stepped a whole simulated year per
        batch and re-took the lock the instant it let go. On a populated
        world that meant a reader waited through batch after batch — a
        manifest request measured at 98 seconds, which is a Run Lab that
        never finishes loading. The batch is now sized by how long a tick
        actually costs, and the driver stands back between batches.
        """

        manager = RunManager(id_factory=lambda: "busy")
        # Populated enough that a tick is real work — tens of milliseconds —
        # but not so dense that one tick alone outlasts the budget. A reader
        # can never be let in mid-tick, so a world whose ticks cost seconds
        # would measure the engine rather than the scheduling.
        manager.create(
            config=SimulationConfig(
                width=40,
                height=20,
                initial_population=60,
                ticks_per_year=12,
            ),
            seed=3,
        )
        self.addCleanup(manager.close)
        manager.set_playback("busy", True, seconds_per_year=0.0)
        # Let the driver measure a tick or two before timing anything.
        time.sleep(0.5)

        worst = 0.0
        for _ in range(10):
            started = time.monotonic()
            manager.frame("busy")
            worst = max(worst, time.monotonic() - started)

        manager.set_playback("busy", False)
        self.assertGreater(manager.manifest("busy")["tick"], 0)
        # Roughly: one batch of about a quarter second, plus the read itself.
        # The old behaviour queued a reader behind batch after batch instead.
        self.assertLess(worst, 1.5, f"worst read waited {worst:.1f}s")

    def test_deleting_a_run_stops_it_driving_itself(self) -> None:
        manager = RunManager(id_factory=lambda: "doomed")
        manager.create(config=SimulationConfig(initial_population=0))
        manager.set_playback("doomed", True, seconds_per_year=0.0)

        manager.delete("doomed")

        self.assertEqual(manager.list_manifests(), [])
        with self.assertRaises(RunNotFoundError):
            manager.manifest("doomed")
        with self.assertRaises(RunNotFoundError):
            manager.delete("doomed")
        # Every driver thread it started has actually gone, not just been
        # forgotten about: a leaked one would keep stepping a dead world.
        self.assertEqual(
            [
                thread
                for thread in threading.enumerate()
                if thread.name == "playback-doomed"
            ],
            [],
        )

    def test_a_failed_run_stops_driving_and_refuses_to_restart(self) -> None:
        factory = FailFirstFactory()
        manager = RunManager(
            backend_factory=factory,
            id_factory=lambda: "broken",
        )
        manager.create(config=SimulationConfig(initial_population=0))
        self.addCleanup(manager.close)

        manager.set_playback("broken", True, seconds_per_year=0.0)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if manager.manifest("broken")["status"] == "failed":
                break
            time.sleep(0.02)

        self.assertEqual(manager.manifest("broken")["status"], "failed")
        self.assertFalse(manager.playback("broken")["playing"])
        with self.assertRaises(RunFailedError):
            manager.set_playback("broken", True, seconds_per_year=0.0)

    def test_pace_arguments_are_strict(self) -> None:
        manager = RunManager(id_factory=lambda: "paced")
        manager.create(config=SimulationConfig(initial_population=0))
        self.addCleanup(manager.close)

        with self.assertRaises(ValueError):
            manager.set_playback("paced", True, seconds_per_year=-1.0)
        with self.assertRaises(TypeError):
            manager.set_playback("paced", True, seconds_per_year="fast")
        with self.assertRaises(ValueError):
            manager.set_playback("paced", "yes")

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
