"""Command-line entry point for a headless simulation run."""

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Optional

from src.simulation import Scenario, Simulation, SimulationConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a deterministic agent society simulation. "
            "The same configuration and seed produce the same result."
        )
    )
    parser.add_argument("--ticks", type=int, default=240)
    parser.add_argument("--population", type=int)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--seed", type=int, default=0)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--config",
        type=Path,
        help="JSON file containing SimulationConfig fields.",
    )
    source_group.add_argument(
        "--scenario",
        type=Path,
        help="JSON scenario containing config, countries, and sea regions.",
    )
    parser.add_argument(
        "--report-every",
        type=int,
        default=20,
        help="Print a compact progress record every N ticks; 0 disables it.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print only the final metrics as JSON.",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Emit the complete UI-ready final snapshot as JSON.",
    )
    return parser


def load_config(args: argparse.Namespace) -> SimulationConfig:
    config = read_config(args.config)

    overrides = {}
    if args.population is not None:
        overrides["initial_population"] = args.population
    if args.width is not None:
        overrides["width"] = args.width
    if args.height is not None:
        overrides["height"] = args.height
    return replace(config, **overrides)


def read_config(path: Optional[Path]) -> SimulationConfig:
    if path:
        with path.open(encoding="utf-8") as config_file:
            values = json.load(config_file)
        if not isinstance(values, dict):
            raise ValueError("configuration JSON must contain an object")
        return SimulationConfig(**values)
    return SimulationConfig()


def run_simulation(
    config: SimulationConfig,
    ticks: int,
    seed: int,
    report_every: int = 0,
    scenario: Optional[Scenario] = None,
) -> Simulation:
    simulation = Simulation(config=config, seed=seed, scenario=scenario)
    for _ in range(ticks):
        simulation.step()
        if report_every > 0 and simulation.tick % report_every == 0:
            metrics = simulation.measure()
            print(
                f"tick={metrics.tick} year={metrics.year:.2f} "
                f"population={metrics.population} "
                f"births={metrics.births} deaths={metrics.deaths} "
                f"resources={metrics.total_resources:.1f}"
            )
    return simulation


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.ticks < 0:
        raise ValueError("--ticks cannot be negative")
    if args.report_every < 0:
        raise ValueError("--report-every cannot be negative")

    if args.scenario:
        config, scenario = read_scenario(args.scenario)
        if args.population is not None:
            raise ValueError(
                "--population cannot override per-country scenario populations"
            )
        overrides = {
            name: value
            for name, value in (("width", args.width), ("height", args.height))
            if value is not None
        }
        if overrides:
            config = replace(config, **overrides)
            scenario.validate(config)
    else:
        config = load_config(args)
        scenario = None
    report_every = 0 if args.json or args.snapshot else args.report_every
    simulation = run_simulation(
        config=config,
        ticks=args.ticks,
        seed=args.seed,
        report_every=report_every,
        scenario=scenario,
    )
    output = (
        simulation.snapshot()
        if args.snapshot
        else simulation.measure().to_dict()
    )
    print(json.dumps(
        output,
        sort_keys=True,
        separators=(",", ":") if args.json or args.snapshot else None,
    ))
    return 0


def read_scenario(path: Path) -> tuple:
    with path.open(encoding="utf-8") as scenario_file:
        values = json.load(scenario_file)
    if not isinstance(values, dict):
        raise ValueError("scenario JSON must contain an object")
    config_values = values.get("config", {})
    scenario_values = values.get("scenario")
    if not isinstance(config_values, dict) or not isinstance(
        scenario_values, dict
    ):
        raise ValueError("scenario requires config and scenario objects")
    config = SimulationConfig(**config_values)
    scenario = Scenario.from_dict(scenario_values)
    scenario.validate(config)
    return config, scenario


if __name__ == "__main__":
    raise SystemExit(main())
