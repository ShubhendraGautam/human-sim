"""Measure engine and projection cost across population sizes.

This harness exists so the performance claims in ``docs/architecture.md`` are
reproducible rather than asserted. It reports wall-clock cost only; it never
feeds timing back into the simulation, and it does not change causal state.
"""

import argparse
import cProfile
import json
import pstats
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sims.scaling_experiment import config_for_population, parse_integer_list
from sims.simple_sim import read_config
from src.human_sim_service.backend import PythonSimulationBackend
from src.simulation import Scenario, Simulation, SimulationConfig


def code_revision() -> Optional[str]:
    """Return the current git revision, or ``None`` outside a checkout."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent.parent,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def measure_run(
    config: SimulationConfig,
    seed: int,
    ticks: int,
    include_projection: bool,
) -> Dict[str, object]:
    """Time construction, stepping, measurement, and optional projection."""
    started = time.perf_counter()
    simulation = Simulation(config=config, seed=seed)
    build_seconds = time.perf_counter() - started

    tick_seconds: List[float] = []
    for _ in range(ticks):
        started = time.perf_counter()
        simulation.step()
        tick_seconds.append(time.perf_counter() - started)

    started = time.perf_counter()
    simulation.measure()
    measure_seconds = time.perf_counter() - started

    record: Dict[str, object] = {
        "seed": seed,
        "ticks": ticks,
        "config": config.to_dict(),
        "final_population": len(simulation.agents),
        "build_ms": build_seconds * 1000.0,
        "measure_ms": measure_seconds * 1000.0,
    }
    if tick_seconds:
        mean_seconds = statistics.fmean(tick_seconds)
        record["tick_mean_ms"] = mean_seconds * 1000.0
        record["tick_median_ms"] = statistics.median(tick_seconds) * 1000.0
        record["tick_max_ms"] = max(tick_seconds) * 1000.0
        record["ticks_per_second"] = (
            1.0 / mean_seconds if mean_seconds > 0.0 else float("inf")
        )

    if include_projection:
        record.update(_measure_projection(config, seed, ticks))
    return record


def _measure_projection(
    config: SimulationConfig,
    seed: int,
    ticks: int,
) -> Dict[str, object]:
    """Time the service projection on an equivalently advanced backend."""
    backend = PythonSimulationBackend(
        config=config,
        seed=seed,
        scenario=Scenario.default(config),
    )
    backend.advance(ticks)

    started = time.perf_counter()
    manifest = backend.manifest()
    manifest_ms = (time.perf_counter() - started) * 1000.0

    results: Dict[str, object] = {
        "manifest_ms": manifest_ms,
        "manifest_bytes": _encoded_size(
            {"world": manifest.world, "config": manifest.config}
        ),
    }
    for include_resources in (True, False):
        started = time.perf_counter()
        frame = backend.frame(include_resources=include_resources)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        suffix = "with_resources" if include_resources else "agents_only"
        results[f"frame_{suffix}_ms"] = elapsed_ms
        results[f"frame_{suffix}_bytes"] = _encoded_size(
            {
                "metrics": frame.metrics,
                "agents": frame.agents,
                "resources": frame.resources,
            }
        )
    return results


def _encoded_size(payload: object) -> int:
    return len(json.dumps(payload, separators=(",", ":"), default=str))


def profile_run(
    config: SimulationConfig,
    seed: int,
    ticks: int,
    limit: int,
) -> None:
    """Print a ``tottime`` profile of the stepped engine to stderr."""
    simulation = Simulation(config=config, seed=seed)
    simulation.step()  # Exclude first-tick warmup from the profile.

    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(ticks):
        simulation.step()
    profiler.disable()

    print(
        f"\n=== profile: population={config.initial_population} "
        f"cells={config.width * config.height} ticks={ticks} ===",
        file=sys.stderr,
    )
    stats = pstats.Stats(profiler, stream=sys.stderr)
    stats.sort_stats("tottime").print_stats(limit)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure engine tick cost and service projection cost across "
            "population sizes, emitting one JSON record per run."
        )
    )
    parser.add_argument(
        "--populations",
        type=parse_integer_list,
        default=[1000, 5000, 10000],
        help="Comma-separated founder populations.",
    )
    parser.add_argument(
        "--seeds",
        type=parse_integer_list,
        default=[0],
        help="Comma-separated random seeds.",
    )
    parser.add_argument("--ticks", type=int, default=10)
    parser.add_argument(
        "--constant-density",
        type=float,
        default=0.25,
        help=(
            "Founders per grid cell. World area scales with population so "
            "cost changes reflect scale rather than crowding."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="JSON file containing SimulationConfig fields.",
    )
    parser.add_argument(
        "--no-projection",
        action="store_true",
        help="Skip service manifest and frame timing.",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Emit a cProfile tottime table per run on stderr.",
    )
    parser.add_argument(
        "--profile-limit",
        type=int,
        default=20,
        help="Rows to print in each profile table.",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.ticks < 0:
        raise ValueError("--ticks cannot be negative")
    if args.constant_density is not None and args.constant_density <= 0.0:
        raise ValueError("--constant-density must be positive")

    base_config = read_config(args.config)
    revision = code_revision()

    for population in args.populations:
        config = config_for_population(
            base_config,
            population,
            args.constant_density,
        )
        for seed in args.seeds:
            record = measure_run(
                config,
                seed,
                args.ticks,
                include_projection=not args.no_projection,
            )
            record["code_revision"] = revision
            print(json.dumps(record, sort_keys=True, separators=(",", ":")))
            if args.profile:
                profile_run(config, seed, args.ticks, args.profile_limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
