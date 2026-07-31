"""The comparison harness has to be trustworthy before its answers are."""

import argparse
import unittest

from sims.experiment import (
    compare,
    deviation,
    pairing_warnings,
    parse_arm,
    run_once,
    sign_test,
)
from src.simulation import SimulationConfig


def small_config() -> dict:
    return SimulationConfig(
        width=12,
        height=12,
        initial_population=30,
        ticks_per_year=12,
    ).to_dict()


def task(arm: str, seed: int, overrides: dict, ticks: int = 24) -> dict:
    return {
        "arm": arm,
        "seed": seed,
        "ticks": ticks,
        "overrides": overrides,
        "config": small_config(),
        "scenario": None,
    }


class ArmParsingTests(unittest.TestCase):
    def test_settings_keep_their_json_types(self) -> None:
        name, overrides = parse_arm(
            "off=neural_brains_enabled=false,plasticity_rate=0.05"
        )

        self.assertEqual(name, "off")
        self.assertIs(overrides["neural_brains_enabled"], False)
        self.assertEqual(overrides["plasticity_rate"], 0.05)

    def test_an_arm_may_change_nothing(self) -> None:
        """The control is a real arm, not a special case."""

        self.assertEqual(parse_arm("control"), ("control", {}))

    def test_a_setting_that_does_not_exist_is_refused(self) -> None:
        # Silently ignoring it would run the control twice and report the
        # difference between a configuration and itself as a finding.
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_arm("bad=no_such_setting=1")
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_arm("bad=neural_brains_enabled")


class StatisticsTests(unittest.TestCase):
    def test_unanimous_seeds_are_as_surprising_as_they_can_be(self) -> None:
        wins, losses, probability = sign_test([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

        self.assertEqual((wins, losses), (6, 0))
        # Two-sided exact binomial: 2 * (1/64).
        self.assertAlmostEqual(probability, 0.03125)

    def test_an_even_split_is_no_evidence(self) -> None:
        _, _, probability = sign_test([1.0, -1.0, 2.0, -2.0])

        self.assertEqual(probability, 1.0)

    def test_seeds_that_saw_nothing_count_against_a_finding(self) -> None:
        """A tie is not half a win; it is the absence of an effect."""

        wins, losses, probability = sign_test([1.0, 1.0, 0.0, 0.0])

        self.assertEqual((wins, losses), (2, 0))
        self.assertAlmostEqual(probability, 0.5)

    def test_deviation_is_the_sample_spread(self) -> None:
        self.assertAlmostEqual(deviation([2.0, 4.0, 4.0, 4.0, 5.0]), 1.0954, 3)
        self.assertEqual(deviation([7.0]), 0.0)


class VerdictTests(unittest.TestCase):
    def records(self, values: dict) -> list:
        return [
            {
                "arm": arm,
                "seed": seed,
                "extinct_at_tick": None,
                "final": {"population": value},
            }
            for arm, seeds in values.items()
            for seed, value in seeds.items()
        ]

    def test_a_large_consistent_difference_is_reported(self) -> None:
        report = "\n".join(compare(
            self.records({
                "on": {0: 100.0, 1: 102.0, 2: 98.0, 3: 101.0, 4: 99.0,
                       5: 100.0},
                "off": {0: 40.0, 1: 41.0, 2: 39.0, 3: 40.0, 4: 41.0,
                        5: 39.0},
            }),
            ["on", "off"],
            "population",
            0.05,
        ))

        self.assertIn("VERDICT: off differs from on", report)

    def test_a_real_but_trivial_difference_states_its_size(self) -> None:
        """Detectable and important are different questions.

        A change of one person, reproduced exactly on every seed, is real.
        Whether it matters is for the reader to judge, so the size is put
        beside the verdict rather than left implied.
        """

        report = "\n".join(compare(
            self.records({
                "on": {0: 100.0, 1: 60.0, 2: 140.0, 3: 20.0, 4: 180.0,
                       5: 90.0},
                "off": {0: 101.0, 1: 61.0, 2: 141.0, 3: 21.0, 4: 181.0,
                        5: 91.0},
            }),
            ["on", "off"],
            "population",
            0.05,
        ))

        self.assertIn("1.0% of its mean", report)
        self.assertIn("VERDICT: off differs from on", report)

    def test_too_few_seeds_is_not_reported_as_no_effect(self) -> None:
        """Four unanimous seeds cannot reach p <= 0.05; say so.

        The sign test's floor at n seeds is 2/2**n, so a 60% drop seen on
        every one of four seeds still lands at p = 0.125. Calling that "no
        difference" blames the world for a shortage of runs.
        """

        report = "\n".join(compare(
            self.records({
                "on": {0: 100.0, 1: 102.0, 2: 98.0, 3: 101.0},
                "off": {0: 40.0, 1: 41.0, 2: 39.0, 3: 40.0},
            }),
            ["on", "off"],
            "population",
            0.05,
        ))

        self.assertIn("every seed that moved agrees", report)
        self.assertIn("Run at least 6 seeds", report)
        self.assertNotIn("no difference this experiment can see", report)

    def test_a_tie_does_not_count_as_disagreement(self) -> None:
        """One seed landing on the same number is not a dissenting vote.

        Counting it as one turned "five of five agree, 17% apart" into "no
        difference this experiment can see" on a real result.
        """

        report = "\n".join(compare(
            self.records({
                "on": {0: 148.0, 1: 206.0, 2: 184.0, 3: 185.0, 4: 180.0,
                       5: 185.0},
                "off": {0: 148.0, 1: 146.0, 2: 155.0, 3: 156.0, 4: 143.0,
                        5: 158.0},
            }),
            ["on", "off"],
            "population",
            0.05,
        ))

        self.assertIn("every seed that moved agrees", report)
        self.assertNotIn("no difference this experiment can see", report)

    def test_noise_is_reported_as_noise(self) -> None:
        report = "\n".join(compare(
            self.records({
                "on": {0: 100.0, 1: 100.0, 2: 100.0, 3: 100.0},
                "off": {0: 130.0, 1: 70.0, 2: 120.0, 3: 80.0},
            }),
            ["on", "off"],
            "population",
            0.05,
        ))

        self.assertIn("no difference this experiment can see", report)

    def test_survival_can_be_the_metric(self) -> None:
        """When the outcome is dying early, ticks survived is the reading."""

        records = [
            {"arm": "on", "seed": 0, "ticks_run": 900, "final": {}},
            {"arm": "off", "seed": 0, "ticks_run": 300, "final": {}},
        ]

        report = "\n".join(compare(records, ["on", "off"], "ticks_run", 0.05))

        self.assertIn("mean    900.000", report)
        self.assertIn("mean    300.000", report)


class TransientTests(unittest.TestCase):
    def test_each_record_names_the_code_that_produced_it(self) -> None:
        request = task("on", 2, {}, ticks=1)
        request["code_revision"] = "abc123-dirty"

        record = run_once(request)

        self.assertEqual(record["code_revision"], "abc123-dirty")
        self.assertEqual(record["config"], request["config"])
        self.assertIsNone(record["scenario"])
        self.assertEqual(len(record["construction_fingerprint"]), 64)

    def test_checkpoints_record_the_population_on_the_way(self) -> None:
        """Equilibrium is set by the land; the transient is where a
        mechanism that only changes the rate of growth can still show."""

        request = task("on", 2, {}, ticks=48)
        request["checkpoint_years"] = [1, 2, 3]

        record = run_once(request)

        self.assertIn("population_at_1", record)
        self.assertIn("population_at_3", record)
        self.assertGreater(record["population_at_1"], 0)

    def test_a_checkpoint_after_extinction_is_zero_not_absent(self) -> None:
        """An absent reading would drop that seed from the pairing and
        quietly compare only the arms that survived."""

        request = task(
            "doomed",
            1,
            {"initial_resource_fraction": 0.0, "resource_regeneration": 0.0},
            ticks=600,
        )
        request["checkpoint_years"] = [40]

        record = run_once(request)

        self.assertEqual(record["population_at_40"], 0)
        self.assertIsNotNone(record["extinct_at_tick"])

    def test_deaths_are_broken_out_by_cause(self) -> None:
        record = run_once(task("on", 4, {}, ticks=240))

        causes = [key for key in record if key.startswith("deaths_")]
        self.assertTrue(causes, "no death causes were recorded")


class PairingTests(unittest.TestCase):
    def test_the_same_seed_builds_the_same_world_in_every_arm(self) -> None:
        """The claim the whole method rests on.

        If arms differed in their starting conditions, the per-seed
        difference would be measuring the world rather than the setting.
        Nullifying the network by weight leaves construction untouched.
        """

        control = run_once(task("on", 7, {}))
        switched = run_once(task("off", 7, {"neural_output_weight": 0.0}))

        self.assertEqual(control["opening"], switched["opening"])
        self.assertEqual(pairing_warnings([control, switched], ["on", "off"]),
                         [])

    def test_a_switch_that_moves_the_world_is_called_out(self) -> None:
        """Skipping the weight draws shifts every later draw.

        `neural_brains_enabled=false` builds a different world from the same
        seed, so the arms differ by founders as well as by brains. The
        comparison is confounded, and saying so is the harness's job rather
        than the reader's.
        """

        control = run_once(task("on", 7, {}))
        switched = run_once(
            task("off", 7, {"neural_brains_enabled": False})
        )

        self.assertNotEqual(control["opening"], switched["opening"])
        report = "\n".join(
            pairing_warnings([control, switched], ["on", "off"])
        )
        self.assertIn("did not start from the same world", report)
        self.assertIn("neural_output_weight=0", report)

    def test_an_independent_action_row_is_not_a_pairing_failure(self) -> None:
        """Artifact output weights use a keyed stream, not founder draws."""

        control = run_once(task("on", 7, {}, ticks=0))
        switched = run_once(
            task("off", 7, {"artifacts_enabled": False}, ticks=0)
        )

        self.assertNotEqual(control["opening"], switched["opening"])
        self.assertEqual(
            control["construction_fingerprint"],
            switched["construction_fingerprint"],
        )
        self.assertEqual(
            pairing_warnings([control, switched], ["on", "off"]),
            [],
        )

    def test_a_run_is_reproducible(self) -> None:
        first = run_once(task("on", 3, {}))
        second = run_once(task("on", 3, {}))

        self.assertEqual(first["final"], second["final"])

    def test_the_switch_reaches_the_engine(self) -> None:
        """An override that did nothing would silently duplicate the arm."""

        control = run_once(task("on", 5, {}))
        switched = run_once(task("off", 5, {"neural_brains_enabled": False}))

        self.assertGreater(control["final"]["mean_network_magnitude"], 0.0)
        self.assertEqual(switched["final"]["mean_network_magnitude"], 0.0)


if __name__ == "__main__":
    unittest.main()
