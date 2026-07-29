"""Compare two or more configurations across the same seeds.

The question this answers is the only one that matters about a mechanism:
*does it change anything?* A mechanism that cannot be shown to change an
outcome is not a feature, and the honest response to that is either to find
the conditions under which it pays or to turn it off — which is what happened
to lifetime plasticity, and why it defaults to zero.

Runs are **paired by seed**. Arms differ only in the settings named on the
command line, so a seed produces the same world, the same founders, and the
same weather in every arm; the difference between arms on that seed is
attributable to the setting rather than to luck. Comparing unpaired means
across a handful of runs mostly measures which seeds happened to land where.

    python -m sims.experiment \\
        --arm off=neural_output_weight=0 \\
        --arm on \\
        --config configs/pressure.json --seeds 0,1,2,3,4,5 --years 300

Note the switch: ``neural_output_weight=0`` silences the network without
changing how much randomness is drawn while the world is built, so both arms
start from an identical world. ``neural_brains_enabled=false`` does not, and
the harness will say so.

What it cannot do is make six seeds into evidence for a small effect. The
summary says which differences clear seed-to-seed variation and refuses to
dress up the ones that do not.
"""

import argparse
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import fields, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sims.simple_sim import read_config, read_scenario
from src.simulation import Scenario, Simulation, SimulationConfig


#: Reported for every run, in this order, because these are the readings that
#: say whether a population survived, whether it was under any pressure, and
#: whether its inherited brains moved.
HEADLINE_METRICS = (
    "population",
    "mean_health_fraction",
    "mean_body_condition",
    "resource_fraction",
    "mean_network_magnitude",
    "policy_diversity",
    "action_entropy",
    "maximum_generation",
)


def parse_integer_list(value: str) -> List[int]:
    try:
        values = [int(item.strip()) for item in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "expected comma-separated integers"
        ) from error
    if not values or any(item < 0 for item in values):
        raise argparse.ArgumentTypeError(
            "values must be non-negative integers"
        )
    return values


def parse_arm(value: str) -> Tuple[str, Dict[str, Any]]:
    """``name=key=value[,key=value]`` — one arm of the comparison.

    Values are read as JSON, so ``true`` is a boolean and ``0.05`` is a
    number. An arm with no settings at all is legal and useful: it is the
    control, running the configuration exactly as the file left it.
    """

    name, _, assignments = value.partition("=")
    if not name:
        raise argparse.ArgumentTypeError("an arm needs a name")
    overrides: Dict[str, Any] = {}
    known = {field.name for field in fields(SimulationConfig)}
    for assignment in filter(None, assignments.split(",")):
        key, separator, raw = assignment.partition("=")
        key = key.strip()
        if not separator:
            raise argparse.ArgumentTypeError(
                f"{assignment!r} is not key=value"
            )
        if key not in known:
            raise argparse.ArgumentTypeError(
                f"{key!r} is not a SimulationConfig setting"
            )
        try:
            overrides[key] = json.loads(raw)
        except json.JSONDecodeError:
            overrides[key] = raw
    return name, overrides


def run_once(task: Dict[str, Any]) -> Dict[str, Any]:
    """One arm on one seed. Importable at module level so it can be forked."""

    config = SimulationConfig(**task["config"])
    config = replace(config, **task["overrides"])
    scenario = (
        None if task["scenario"] is None
        else Scenario.from_dict(task["scenario"])
    )
    simulation = Simulation(
        config=config,
        seed=task["seed"],
        scenario=scenario,
    )
    opening = simulation.measure().to_dict()

    ticks = task["ticks"]
    per_year = max(1, int(config.ticks_per_year))
    # A population at equilibrium is held there by the land, which can hide a
    # mechanism that only changes how fast it got there. Checkpoints keep the
    # transient, where a difference in foraging or foresight should show
    # before carrying capacity flattens everything out.
    checkpoints = {
        year: None for year in task.get("checkpoint_years", ())
    }
    extinct_at = None
    for tick in range(ticks):
        simulation.step()
        if simulation.tick % per_year == 0:
            year = simulation.tick // per_year
            if year in checkpoints:
                checkpoints[year] = len(simulation.agents)
        if not simulation.agents:
            # Nothing further can happen, and the remaining ticks would only
            # be spent confirming it.
            extinct_at = tick + 1
            break
    closing = simulation.measure().to_dict()

    record = {
        "arm": task["arm"],
        "seed": task["seed"],
        "ticks_requested": ticks,
        "ticks_run": simulation.tick,
        "extinct_at_tick": extinct_at,
        "overrides": task["overrides"],
        "opening": opening,
        "final": closing,
    }
    for year, population in checkpoints.items():
        # A run that ended before the checkpoint reports zero, which is what
        # it had: leaving it absent would drop that seed from the pairing and
        # quietly compare only the survivors.
        record[f"population_at_{year}"] = (
            0 if population is None else population
        )
    for cause, count in closing.get("deaths_by_cause", {}).items():
        record[f"deaths_{cause}"] = count
    return record


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def deviation(values: Sequence[float]) -> float:
    """Sample standard deviation; zero for fewer than two values."""

    if len(values) < 2:
        return 0.0
    average = mean(values)
    total = sum((value - average) ** 2 for value in values)
    return math.sqrt(total / (len(values) - 1))


def sign_test(differences: Sequence[float]) -> Tuple[int, int, float]:
    """How many seeds moved which way, and how surprising that split is.

    A sign test rather than a t-test: with a handful of seeds, whether every
    seed agrees is a claim the data can support, and the size of the average
    difference mostly is not. Ties count against the result, because a seed
    that saw no change is not evidence of one. The p-value is the exact
    two-sided binomial probability of a split this lopsided under "the arms
    are the same".
    """

    wins = sum(1 for value in differences if value > 0)
    losses = sum(1 for value in differences if value < 0)
    decided = wins + losses
    if decided == 0:
        return 0, 0, 1.0
    extreme = max(wins, losses)
    tail = sum(
        math.comb(decided, count)
        for count in range(extreme, decided + 1)
    )
    probability = min(1.0, 2 * tail / (2 ** decided))
    return wins, losses, probability


def compare(
    records: Sequence[Dict[str, Any]],
    arms: Sequence[str],
    metric: str,
    threshold: float,
) -> List[str]:
    """The scoreboard: every arm against the first one, paired by seed."""

    by_arm: Dict[str, Dict[int, float]] = {name: {} for name in arms}
    for record in records:
        # Falling back to the run record itself is what lets survival be
        # compared — `ticks_run` is the honest metric when the interesting
        # outcome is dying early rather than ending small.
        value = record["final"].get(metric, record.get(metric))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            by_arm[record["arm"]][record["seed"]] = float(value)

    paired = len(by_arm[arms[0]])
    lines = [f"Metric: {metric}   (paired by seed, n={paired})", ""]
    for name in arms:
        values = list(by_arm[name].values())
        lines.append(
            f"  {name:<12} mean {mean(values):>10.3f}"
            f"   sd {deviation(values):>9.3f}"
            f"   range {min(values, default=0):.3f} to"
            f" {max(values, default=0):.3f}"
        )
    if len(arms) < 2:
        return lines

    control = arms[0]
    lines.append("")
    for name in arms[1:]:
        shared = sorted(set(by_arm[control]) & set(by_arm[name]))
        differences = [by_arm[name][seed] - by_arm[control][seed]
                       for seed in shared]
        if not differences:
            lines.append(f"  {name} vs {control}: no seeds in common")
            continue
        average = mean(differences)
        spread = deviation(differences)
        wins, losses, probability = sign_test(differences)
        seeds = len(differences)
        control_mean = mean(list(by_arm[control].values()))
        relative = abs(average) / spread if spread > 0 else math.inf
        share = (
            abs(average) / abs(control_mean) * 100
            if control_mean else math.inf
        )
        # Unanimity is judged among the seeds that moved at all. A seed whose
        # two arms landed on exactly the same number is not a dissenting
        # vote, and counting it as one turned "five of five agree, 17% apart"
        # into "no difference this experiment can see".
        decided = wins + losses
        unanimous = decided > 0 and (wins == decided or losses == decided)

        lines.append(f"  {name} vs {control}")
        lines.append(
            f"    per-seed difference  mean {average:+.3f}"
            f"   sd {spread:.3f}"
        )
        # Detectability and importance are different questions, and a
        # scoreboard that answers only the first invites a perfectly
        # reproducible one-percent change to be read as a discovery.
        lines.append(
            f"    size against {control:<12} {share:.1f}% of its mean"
        )
        lines.append(
            f"    seeds favouring {name:<8} {wins} of {seeds}"
            f"   (sign test p = {probability:.3f})"
        )
        if probability <= threshold and relative >= 1.0:
            lines.append(
                f"    VERDICT: {name} differs from {control}"
                f" — every-seed agreement, {share:.1f}% of the {control} mean"
            )
        elif unanimous:
            # The sign test cannot reach the threshold at this many seeds no
            # matter how large the effect: with n seeds the best possible
            # two-sided p is 2/2^n. Reporting that as "no difference" would
            # blame the world for a shortage of runs.
            lines.append(
                f"    VERDICT: every seed that moved agrees ({share:.1f}% of"
                f" the {control} mean), but {seeds} seeds cannot reach"
                f" p <= {threshold:g} — the best possible with {decided}"
                f" seed{'' if decided == 1 else 's'} that moved is"
                f" {2 / 2 ** decided:.3f}. Run at least"
                f" {minimum_seeds(threshold)} seeds"
            )
        elif probability <= threshold:
            lines.append(
                f"    VERDICT: {name} moves the same way on most seeds, but"
                f" by less than the seeds vary among themselves"
            )
        else:
            lines.append(
                f"    VERDICT: no difference this experiment can see."
                f" With {seeds} seeds only a large, consistent"
                f" effect would show"
            )
        lines.append("")
    return lines


def pairing_warnings(
    records: Sequence[Dict[str, Any]],
    arms: Sequence[str],
) -> List[str]:
    """Check that every arm really did start from the same world.

    Pairing is the whole basis of the comparison, and it is quietly lost when
    a setting changes how much randomness is drawn while the world is being
    built. ``neural_brains_enabled=false`` does exactly that: skipping the
    weight draws shifts every later draw, so the arms get different founders
    in different places, and the difference between them is no longer
    attributable to the setting. ``neural_output_weight=0`` is the same
    experiment without the flaw — the networks are still built, they simply
    do not contribute.

    Rather than trust the author to know which settings are safe, this
    compares the opening measurement and says when they are not.
    """

    openings: Dict[int, Dict[str, Dict[str, Any]]] = {}
    for record in records:
        openings.setdefault(record["seed"], {})[record["arm"]] = (
            record.get("opening", {})
        )
    broken = sorted(
        seed
        for seed, by_arm in openings.items()
        if len({json.dumps(value, sort_keys=True)
                for value in by_arm.values()}) > 1
    )
    if not broken:
        return []
    return [
        "WARNING: the arms did not start from the same world on"
        f" seed{'s' if len(broken) > 1 else ''}"
        f" {', '.join(str(seed) for seed in broken)}.",
        "  A setting here changes how much randomness is drawn during"
        " construction, so the arms have different founders and this",
        "  comparison comes with the world attached. For brains, prefer"
        " neural_output_weight=0 over neural_brains_enabled=false.",
        "",
    ]


def minimum_seeds(threshold: float) -> int:
    """Fewest paired seeds at which unanimity can clear the threshold."""

    seeds = 1
    while 2 / 2 ** seeds > threshold and seeds < 64:
        seeds += 1
    return seeds


def report_as_they_arrive(
    results: Iterable[Dict[str, Any]],
    as_json: bool,
    out: Optional[Path] = None,
) -> Iterable[Dict[str, Any]]:
    """Print each run the moment it finishes, and keep it for the summary."""

    for record in results:
        if out is not None:
            with out.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        record,
                        sort_keys=True,
                        separators=(",", ":"),
                    ) + "\n"
                )
        if as_json:
            print(
                json.dumps(record, sort_keys=True, separators=(",", ":")),
                flush=True,
            )
        else:
            row = "  ".join(
                f"{record['final'].get(name, 0):>11.3f}"
                for name in HEADLINE_METRICS
            )
            note = "" if record["extinct_at_tick"] is None else "  EXTINCT"
            print(
                f"{record['arm']:<12} {record['seed']:>4}  {row}{note}",
                flush=True,
            )
        yield record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sims.experiment",
        description=(
            "Run the same seeds under two or more configurations and report "
            "whether the difference clears seed-to-seed variation."
        ),
    )
    parser.add_argument(
        "--arm",
        action="append",
        type=parse_arm,
        metavar="NAME=key=value[,key=value]",
        help=(
            "An arm of the comparison; repeat it. The first is the "
            "control. Example: --arm off=neural_brains_enabled=false"
        ),
    )
    parser.add_argument(
        "--seeds",
        type=parse_integer_list,
        default=[0, 1, 2, 3, 4, 5],
    )
    parser.add_argument(
        "--years",
        type=float,
        default=200.0,
        help="Simulated years per run (converted using ticks_per_year).",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--config", type=Path)
    source.add_argument("--scenario", type=Path)
    parser.add_argument(
        "--metric",
        action="append",
        help=(
            "Metric to judge, repeatable. Any field of the metrics record "
            "(e.g. mean_network_magnitude), plus ticks_run for survival and "
            "population_at_YEAR for the transient. Default: population."
        ),
    )
    parser.add_argument(
        "--checkpoint-years",
        type=parse_integer_list,
        default=[],
        help="Years at which to record population, for the transient.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.05,
        help="Sign-test p-value below which a difference is reported.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Runs to execute in parallel. Results are ordered regardless.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit one JSON record per run and nothing else.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help=(
            "Append each finished run to this file as JSON. A sweep left "
            "overnight and interrupted can still be summarised from it."
        ),
    )
    parser.add_argument(
        "--summarise",
        type=Path,
        help="Summarise a saved --out file without running anything.",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(None if argv is None else list(argv))

    if args.summarise is not None:
        # Reading back what a run managed to finish is the difference
        # between an interrupted overnight sweep being a partial result and
        # being nothing at all.
        records = [
            json.loads(line)
            for line in args.summarise.read_text().splitlines()
            if line.strip()
        ]
        if not records:
            print("no runs in that file", file=sys.stderr)
            return 1
        names: List[str] = []
        for record in records:
            if record["arm"] not in names:
                names.append(record["arm"])
        seeds_done = {
            name: sum(1 for r in records if r["arm"] == name)
            for name in names
        }
        print(
            f"{len(records)} runs read: "
            + ", ".join(f"{name} x{count}" for name, count in
                        seeds_done.items())
        )
        print()
        for line in pairing_warnings(records, names):
            print(line)
        for metric in (args.metric or ["population"]):
            for line in compare(records, names, metric, args.threshold):
                print(line)
            print()
        return 0

    if not args.arm:
        raise ValueError("at least one --arm is required")
    if args.years <= 0:
        raise ValueError("--years must be positive")
    if args.jobs < 1:
        raise ValueError("--jobs must be at least one")

    names = [name for name, _ in args.arm]
    if len(set(names)) != len(names):
        raise ValueError("arm names must be distinct")

    if args.scenario is not None:
        config, scenario = read_scenario(args.scenario)
        scenario_values: Optional[Dict[str, Any]] = scenario.to_dict()
    else:
        config = read_config(args.config)
        scenario_values = None

    ticks = max(1, round(args.years * config.ticks_per_year))
    metrics = args.metric or ["population"]
    checkpoints = [
        year for year in args.checkpoint_years if year * config.ticks_per_year
        <= ticks
    ]
    tasks = [
        {
            "arm": name,
            "seed": seed,
            "ticks": ticks,
            "overrides": overrides,
            "config": config.to_dict(),
            "scenario": scenario_values,
            "checkpoint_years": checkpoints,
        }
        for name, overrides in args.arm
        for seed in args.seeds
    ]

    if not args.json:
        print(
            f"{len(tasks)} runs: {len(names)} arms x {len(args.seeds)} seeds"
            f" x {ticks} ticks ({args.years:g} years)",
            file=sys.stderr,
        )

    if not args.json:
        print()
        header = "  ".join(f"{name[:11]:>11}" for name in HEADLINE_METRICS)
        print(f"{'arm':<12} {'seed':>4}  {header}", flush=True)

    # Results are reported as they arrive rather than at the end. A sweep of
    # this shape runs for hours, and one that loses everything it had done
    # when the machine is rebooted or the process is killed is a sweep nobody
    # dares start. Ordering is preserved either way.
    if args.jobs == 1:
        results: Iterable[Dict[str, Any]] = (
            run_once(task) for task in tasks
        )
        records = list(
            report_as_they_arrive(results, args.json, args.out)
        )
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            records = list(report_as_they_arrive(
                pool.map(run_once, tasks),
                args.json,
                args.out,
            ))

    if args.json:
        return 0

    print()
    for line in pairing_warnings(records, names):
        print(line)
    for metric in metrics:
        for line in compare(records, names, metric, args.threshold):
            print(line)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
