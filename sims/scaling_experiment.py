"""Run comparable simulations across population sizes and random seeds."""

import argparse
import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from sims.simple_sim import read_config
from src.simulation import Simulation, SimulationConfig


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


def parse_world_sizes(value: str) -> List[Tuple[int, int]]:
    """Parse comma-separated ``WIDTHxHEIGHT`` pairs."""

    sizes = []
    for item in value.split(","):
        width_text, separator, height_text = item.strip().lower().partition(
            "x"
        )
        if not separator:
            raise argparse.ArgumentTypeError(
                "world sizes must be WIDTHxHEIGHT pairs"
            )
        try:
            width = int(width_text)
            height = int(height_text)
        except ValueError as error:
            raise argparse.ArgumentTypeError(
                "world sizes must be WIDTHxHEIGHT pairs"
            ) from error
        if width <= 0 or height <= 0:
            raise argparse.ArgumentTypeError(
                "world dimensions must be positive integers"
            )
        sizes.append((width, height))
    if not sizes:
        raise argparse.ArgumentTypeError("at least one world size is required")
    return sizes


def config_for_population(
    base: SimulationConfig,
    population: int,
    constant_density: Optional[float],
    world_size: Optional[Tuple[int, int]] = None,
) -> SimulationConfig:
    if world_size is not None:
        if constant_density is not None:
            raise ValueError(
                "explicit world size and constant density are alternatives"
            )
        width, height = world_size
        return replace(
            base,
            initial_population=population,
            width=width,
            height=height,
        )
    if constant_density is None:
        return replace(base, initial_population=population)
    if constant_density <= 0.0:
        raise ValueError("constant density must be positive")
    side = max(1, math.ceil(math.sqrt(population / constant_density)))
    return replace(
        base,
        initial_population=population,
        width=side,
        height=side,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a population-by-seed matrix and emit one JSON record per run."
        )
    )
    parser.add_argument(
        "--populations",
        type=parse_integer_list,
        default=[100, 300, 1000],
        help="Comma-separated founder populations.",
    )
    parser.add_argument(
        "--seeds",
        type=parse_integer_list,
        default=[0, 1, 2],
        help="Comma-separated random seeds.",
    )
    parser.add_argument("--ticks", type=int, default=120)
    parser.add_argument(
        "--constant-density",
        type=float,
        help=(
            "Founders per grid cell. When supplied, world area scales with "
            "population; otherwise the configured dimensions remain fixed."
        ),
    )
    parser.add_argument(
        "--world-sizes",
        type=parse_world_sizes,
        help=(
            "Comma-separated WIDTHxHEIGHT worlds. Each founder population "
            "is run on every size, exposing sparse and crowded cases."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="JSON file containing SimulationConfig fields.",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.ticks < 0:
        raise ValueError("--ticks cannot be negative")
    if args.constant_density is not None and args.constant_density <= 0.0:
        raise ValueError("--constant-density must be positive")
    if args.constant_density is not None and args.world_sizes is not None:
        raise ValueError(
            "--constant-density and --world-sizes cannot be combined"
        )

    base_config = read_config(args.config)

    for population in args.populations:
        for world_size in args.world_sizes or [None]:
            config = config_for_population(
                base_config,
                population,
                args.constant_density,
                world_size,
            )
            for seed in args.seeds:
                simulation = Simulation(config=config, seed=seed)
                simulation.run(args.ticks)
                record = {
                    "seed": seed,
                    "founders_per_cell": (
                        population / (config.width * config.height)
                    ),
                    "config": config.to_dict(),
                    "metrics": simulation.measure().to_dict(),
                }
                print(json.dumps(
                    record,
                    sort_keys=True,
                    separators=(",", ":"),
                ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
