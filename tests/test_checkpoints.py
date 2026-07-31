"""Resumable state is exact, versioned, and distinct from visualization."""

import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from src.human_sim_service.sessions import RunManager
from src.simulation import Simulation, SimulationConfig
from src.simulation.models import ReproductiveRole
from src.simulation.versions import CHECKPOINT_SCHEMA_VERSION


def exercised_run() -> Simulation:
    simulation = Simulation(
        SimulationConfig(
            width=12,
            height=8,
            initial_population=28,
            initial_fauna_density=0.08,
            neural_recurrence_weight=0.8,
            plasticity_rate=0.03,
            language_enabled=True,
            metrics_interval=1,
        ),
        seed=19,
    )
    simulation.run(40)
    return simulation


class CheckpointTests(unittest.TestCase):
    def test_checkpoint_round_trip_retains_state_and_future(self) -> None:
        original = exercised_run()
        payload = json.loads(json.dumps(original.checkpoint()))

        restored = Simulation.from_checkpoint(payload)

        self.assertEqual(
            json.loads(json.dumps(restored.checkpoint())),
            payload,
        )
        self.assertEqual(restored.state_digest(), original.state_digest())
        original.run(30)
        restored.run(30)
        self.assertEqual(restored.state_digest(), original.state_digest())

    def test_checkpoint_retains_taught_policy_lineage(self) -> None:
        simulation = Simulation(
            SimulationConfig(
                width=8,
                height=8,
                initial_population=8,
                initial_fauna_density=0.0,
                policy_teaching_rate=1.0,
            ),
            seed=9,
        )
        teacher, learner = (
            simulation.agents[agent_id]
            for agent_id in sorted(simulation.agents)[:2]
        )
        learner.x, learner.y = teacher.x, teacher.y
        teacher.known_techniques = learner.known_techniques = 0
        teacher.network.output[0][0] = 0.8
        learner.network.output[0][0] = -0.4
        self.assertTrue(simulation._teach(teacher, learner.id))

        restored = Simulation.from_checkpoint(simulation.checkpoint())
        restored_learner = restored.agents[learner.id]

        self.assertEqual(restored_learner.brain.policy_teacher_id, teacher.id)
        self.assertEqual(restored_learner.brain.policy_origin_id, teacher.id)
        self.assertEqual(restored_learner.brain.policy_generation, 1)
        self.assertEqual(restored.total_policy_transmissions, 1)
        self.assertEqual(restored.state_digest(), simulation.state_digest())

    def test_checkpoint_is_not_a_visualization_snapshot(self) -> None:
        simulation = exercised_run()

        checkpoint = simulation.checkpoint()
        snapshot = simulation.snapshot()

        self.assertEqual(checkpoint["checkpoint_kind"], "resumable")
        self.assertEqual(
            checkpoint["schema_version"],
            CHECKPOINT_SCHEMA_VERSION,
        )
        self.assertIn("rng", checkpoint["state"])
        self.assertEqual(snapshot["snapshot_kind"], "visualization")
        with self.assertRaisesRegex(ValueError, "not a resumable"):
            Simulation.from_checkpoint(snapshot)

    def test_incompatible_checkpoint_is_refused(self) -> None:
        payload = exercised_run().checkpoint()
        incompatible = copy.deepcopy(payload)
        incompatible["schema_version"] = CHECKPOINT_SCHEMA_VERSION + 1

        with self.assertRaisesRegex(ValueError, "incompatible"):
            Simulation.from_checkpoint(incompatible)

    def test_unborn_children_and_recent_dead_survive_restore(self) -> None:
        simulation = Simulation(
            SimulationConfig(
                width=5,
                height=5,
                initial_population=2,
                initial_energy_minimum=100.0,
                initial_energy_maximum=100.0,
                reproduction_energy=10.0,
                reproduction_cost=2.0,
                maximum_conception_probability=1.0,
            ),
            seed=13,
        )
        gestational_parent, other_parent = simulation.agents.values()
        gestational_parent.reproductive_role = ReproductiveRole.OVA
        other_parent.reproductive_role = ReproductiveRole.SPERM
        gestational_parent.age = other_parent.age = 20.0
        gestational_parent.x = other_parent.x = 0
        gestational_parent.y = other_parent.y = 0
        gestational_parent.traits = replace(
            gestational_parent.traits,
            fertility=1.0,
            maturity_age=1.0,
        )
        other_parent.traits = replace(
            other_parent.traits,
            fertility=1.0,
            maturity_age=1.0,
        )
        self.assertTrue(
            simulation._reproduce(
                gestational_parent,
                other_parent.id,
                set(),
            )
        )
        simulation._remove_agent(other_parent.id, cause="test")

        restored = Simulation.from_checkpoint(
            json.loads(json.dumps(simulation.checkpoint()))
        )

        self.assertIn(gestational_parent.id, restored.pregnancies)
        self.assertIn(other_parent.id, restored.deaths)
        self.assertEqual(
            restored.state_digest(),
            simulation.state_digest(),
        )
        simulation.run(15)
        restored.run(15)
        self.assertEqual(
            restored.state_digest(),
            simulation.state_digest(),
        )

    def test_manager_restores_a_paused_independent_run(self) -> None:
        source = RunManager(id_factory=lambda: "source")
        source.create(
            config={
                "width": 8,
                "height": 6,
                "initial_population": 14,
            },
            seed=31,
        )
        source.step("source", ticks=12)
        checkpoint = json.loads(
            json.dumps(source.export_checkpoint("source"))
        )

        target = RunManager(id_factory=lambda: "restored")
        manifest = target.restore(checkpoint)

        self.assertEqual(manifest["run_id"], "restored")
        self.assertEqual(manifest["status"], "paused")
        self.assertEqual(manifest["tick"], 12)
        source.step("source", ticks=10)
        target.step("restored", ticks=10)
        self.assertEqual(
            source.export_checkpoint("source")["state"],
            target.export_checkpoint("restored")["state"],
        )

    def test_autosave_recovers_runs_after_a_service_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            first = RunManager(
                checkpoint_directory=path,
                autosave_ticks=5,
                id_factory=lambda: "durable",
            )
            first.create(
                config={
                    "width": 8,
                    "height": 6,
                    "initial_population": 14,
                },
                seed=41,
            )
            first.step("durable", ticks=7)

            restarted = RunManager(
                checkpoint_directory=path,
                autosave_ticks=5,
            )

            manifest = restarted.manifest("durable")
            self.assertEqual(manifest["status"], "paused")
            self.assertEqual(manifest["tick"], 7)
            first.step("durable", ticks=6)
            restarted.step("durable", ticks=6)
            self.assertEqual(
                first.export_checkpoint("durable")["state"],
                restarted.export_checkpoint("durable")["state"],
            )
            restarted.delete("durable")
            empty_restart = RunManager(checkpoint_directory=path)
            self.assertEqual(empty_restart.list_manifests(), [])


if __name__ == "__main__":
    unittest.main()
