"""Tick throughput on a fixed workload, for judging optimisations.

Speed work needs a number that means the same thing before and after, so
this runs one named configuration for a fixed number of ticks after a warm-up
and reports the cost per tick. It deliberately does not scale populations or
worlds the way ``profile_engine`` does: the question here is not how cost
grows, it is whether a change made the same work cheaper.

Timing is **CPU time for this process**, not wall clock. On a shared laptop
the same unchanged code measured 42 and then 34 ticks per second an hour
apart — a 20% swing that would drown any honest optimisation and invent
several fake ones. Process CPU time ignores whatever else the machine is
doing, and repeats report the best rather than the mean, because
interference can only ever make a run slower.

The engine is deterministic, so a speed-up is only real if the state at the
end is bit-identical to what the slower code produced. The digest printed
alongside the timing is that check — if it moves, the optimisation changed
the simulation and the timing is beside the point.

    python -m sims.benchmark --config configs/pressure.json --ticks 600
"""

import argparse
import cProfile
import hashlib
import json
import pstats
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

from sims.simple_sim import read_config
from src.simulation import Simulation


def state_digest(simulation: Simulation) -> str:
    """A short fingerprint of everything the tick loop is allowed to change.

    Cheaper than a full snapshot and sensitive to the things an optimisation
    is most likely to break: who exists, where they are, and what condition
    they are in.
    """

    parts = [str(simulation.tick), str(len(simulation.agents))]
    for agent_id in sorted(simulation.agents):
        agent = simulation.agents[agent_id]
        parts.append(
            f"{agent_id}:{agent.x},{agent.y},"
            f"{agent.energy:.6f},{agent.health:.6f},{agent.age:.4f}"
        )
    digest = hashlib.blake2b(
        "|".join(parts).encode("utf-8"),
        digest_size=8,
    )
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sims.benchmark",
        description="Tick throughput on one fixed workload.",
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--warmup",
        type=int,
        default=240,
        help="Ticks to run before timing, so the population is settled.",
    )
    parser.add_argument("--ticks", type=int, default=600)
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Whole measurements to take; the best CPU time is reported.",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Print a cProfile table by total time instead of timing.",
    )
    parser.add_argument("--profile-limit", type=int, default=25)
    parser.add_argument(
        "--calls",
        action="store_true",
        help=(
            "Report Python function calls instead of time. Deterministic to "
            "the last call, so it resolves changes the clock cannot — but it "
            "counts call volume only, so a change that swaps one kind of "
            "call for another shows as no change at all."
        ),
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(None if argv is None else list(argv))
    if args.repeats < 1:
        raise ValueError("--repeats must be at least one")
    config = read_config(args.config)

    if args.profile:
        simulation = Simulation(config=config, seed=args.seed)
        for _ in range(args.warmup):
            simulation.step()
        profiler = cProfile.Profile()
        profiler.enable()
        for _ in range(args.ticks):
            simulation.step()
        profiler.disable()
        stats = pstats.Stats(profiler, stream=sys.stdout)
        stats.sort_stats("tottime").print_stats(args.profile_limit)
        return 0

    if args.calls:
        # A deterministic engine executes exactly the same calls every time,
        # so this number does not move between runs at all — where the same
        # unchanged code measured anywhere from 20 to 34 ticks a second on
        # this machine. It is a proxy for interpreter overhead rather than a
        # measure of time, and it is the only reliable signal available here
        # for a change worth a few percent.
        simulation = Simulation(config=config, seed=args.seed)
        for _ in range(args.warmup):
            simulation.step()
        profiler = cProfile.Profile()
        profiler.enable()
        for _ in range(args.ticks):
            simulation.step()
        profiler.disable()
        stats = pstats.Stats(profiler)
        record = {
            "config": str(args.config) if args.config else "defaults",
            "seed": args.seed,
            "timed_ticks": args.ticks,
            "function_calls": stats.total_calls,
            "calls_per_tick": round(stats.total_calls / args.ticks, 1),
            "digest": state_digest(simulation),
        }
        if args.json:
            print(json.dumps(record, sort_keys=True, separators=(",", ":")))
        else:
            print(
                f"{record['function_calls']:>12,} calls"
                f"   {record['calls_per_tick']:>9,.1f} per tick"
                f"   digest {record['digest']}"
            )
        return 0

    elapsed = None
    settled = 0
    for _ in range(args.repeats):
        simulation = Simulation(config=config, seed=args.seed)
        for _ in range(args.warmup):
            simulation.step()
        settled = len(simulation.agents)
        start = time.process_time()
        for _ in range(args.ticks):
            simulation.step()
        taken = time.process_time() - start
        elapsed = taken if elapsed is None else min(elapsed, taken)

    record = {
        "config": str(args.config) if args.config else "defaults",
        "seed": args.seed,
        "warmup_ticks": args.warmup,
        "timed_ticks": args.ticks,
        "population_at_start_of_timing": settled,
        "population_at_end": len(simulation.agents),
        "repeats": args.repeats,
        "cpu_seconds": round(elapsed, 3),
        "ms_per_tick": round(elapsed / args.ticks * 1000, 3),
        "ticks_per_second": round(args.ticks / elapsed, 2),
        "digest": state_digest(simulation),
    }
    if args.json:
        print(json.dumps(record, sort_keys=True, separators=(",", ":")))
    else:
        print(
            f"{record['ticks_per_second']:>8.2f} ticks/s"
            f"   {record['ms_per_tick']:>7.3f} ms/tick"
            f"   {settled} people"
            f"   digest {record['digest']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
