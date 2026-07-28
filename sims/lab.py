"""Command-line control for long-lived runs held by the engine service.

``simple_sim`` runs a world inside the command that started it: when the
command ends, so does the world. This module is for the other case — a run
that is meant to outlive the thing that asked for it. The service holds the
run and steps it on its own clock; this is a thin client that configures one,
sets it going, and later asks how it is doing. Nothing here simulates
anything, which is what lets you start a run from a terminal, close the
terminal, and attach a browser to the same world a day later.

    python -m sims.lab start --scenario scenarios/two_islands.json --pace fast
    python -m sims.lab list
    python -m sims.lab watch <run-id> --every 60
    python -m sims.lab pause <run-id>

What this cannot do is survive the service process. Runs live in memory; if
the API is restarted the worlds it held are gone, and there is no rehydration
path yet. For anything you would be sad to lose, take a snapshot.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from sims.simple_sim import read_scenario


DEFAULT_API = os.environ.get("HUMAN_SIM_API", "http://127.0.0.1:8000")
DEFAULT_UI = os.environ.get("HUMAN_SIM_UI", "http://127.0.0.1:5173")


class ServiceError(RuntimeError):
    """The service answered, and the answer was no."""


def parse_pace(value: str) -> Optional[float]:
    """Seconds of wall clock one simulated year should take.

    ``fast`` (or zero) means as quickly as the machine manages, which is the
    usual choice for a run nobody is watching. Suffixes are allowed because
    the interesting paces for an unattended run are minutes and hours, and
    ``--pace 3600`` is a worse way to say an hour.
    """

    text = value.strip().lower()
    if text in {"fast", "max", "unbounded"}:
        return 0.0
    units = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
    multiplier = 1.0
    if text and text[-1] in units:
        multiplier = units[text[-1]]
        text = text[:-1]
    try:
        seconds = float(text) * multiplier
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"pace must be a number, optionally suffixed s/m/h/d, or "
            f"'fast'; got {value!r}"
        ) from None
    if seconds < 0:
        raise argparse.ArgumentTypeError("pace cannot be negative")
    return seconds


def describe_pace(seconds_per_year: Optional[float]) -> str:
    if seconds_per_year is None:
        return "no pace set"
    if seconds_per_year <= 0:
        return "as fast as possible"
    if seconds_per_year < 90:
        return f"{seconds_per_year:g}s a year"
    if seconds_per_year < 3600:
        return f"{seconds_per_year / 60:g}m a year"
    return f"{seconds_per_year / 3600:g}h a year"


def request(
    api: str,
    path: str,
    method: str = "GET",
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    call = urllib.request.Request(
        f"{api.rstrip('/')}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(call) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        try:
            payload = json.loads(detail)
            message = payload.get("error", {}).get("message") or detail
        except json.JSONDecodeError:
            message = detail or error.reason
        raise ServiceError(f"{error.code}: {message}") from None
    except urllib.error.URLError as error:
        raise ServiceError(
            f"no engine service at {api} ({error.reason}). "
            f"Start one with ./run.sh start --api-only"
        ) from None


def load_definition(
    args: argparse.Namespace,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Config and scenario as plain JSON, exactly as the service wants them."""

    if args.scenario is not None:
        # Read and validated locally first, so a typo in a scenario file is
        # reported here rather than as a rejected request.
        config, scenario = read_scenario(args.scenario)
        return config.to_dict(), scenario.to_dict()
    if args.config is not None:
        with args.config.open(encoding="utf-8") as handle:
            values = json.load(handle)
        if not isinstance(values, dict):
            raise ValueError("configuration JSON must contain an object")
        return values, None
    return {}, None


def command_start(args: argparse.Namespace) -> int:
    config, scenario = load_definition(args)
    for name, value in (
        ("width", args.width),
        ("height", args.height),
        ("initial_population", args.population),
    ):
        if value is not None:
            config[name] = value
    body: Dict[str, Any] = {"seed": args.seed}
    if config:
        body["config"] = config
    if scenario is not None:
        body["scenario"] = scenario

    manifest = request(args.api, "/api/v1/runs", "POST", body)
    run_id = manifest["run_id"]
    if not args.paused:
        request(
            args.api,
            f"/api/v1/runs/{run_id}/playback",
            "POST",
            {"playing": True, "seconds_per_year": args.pace},
        )
    if args.json:
        print(json.dumps(request(args.api, f"/api/v1/runs/{run_id}/playback")))
        return 0
    print(f"run       {run_id}")
    print(f"seed      {manifest['seed']}")
    print(
        f"world     {manifest['config']['width']}"
        f" x {manifest['config']['height']}"
        f", {manifest['population']} people"
    )
    print(
        "playing   "
        + ("no — start it with 'play'" if args.paused
           else describe_pace(args.pace))
    )
    print(f"watch     python -m sims.lab watch {run_id}")
    print(f"observe   {DEFAULT_UI}/?run={run_id}")
    return 0


def command_list(args: argparse.Namespace) -> int:
    payload = request(args.api, "/api/v1/runs")
    runs = payload["runs"]
    if args.json:
        print(json.dumps(payload))
        return 0
    if not runs:
        print("no runs; start one with 'python -m sims.lab start'")
        return 0
    print(
        f"{'run':34} {'status':9} {'tick':>9} {'year':>9} "
        f"{'people':>8}  pace"
    )
    for manifest in runs:
        playback = manifest.get("playback", {})
        print(
            f"{manifest['run_id']:34} {manifest['status']:9} "
            f"{manifest['tick']:>9} {manifest['year']:>9.1f} "
            f"{manifest['population']:>8}  "
            f"{describe_pace(playback.get('seconds_per_year'))}"
        )
    return 0


def command_play(args: argparse.Namespace) -> int:
    state = request(
        args.api,
        f"/api/v1/runs/{args.run_id}/playback",
        "POST",
        {"playing": True, "seconds_per_year": args.pace},
    )
    return _report_playback(state, args.json)


def command_pause(args: argparse.Namespace) -> int:
    state = request(
        args.api,
        f"/api/v1/runs/{args.run_id}/playback",
        "POST",
        {"playing": False},
    )
    return _report_playback(state, args.json)


def command_step(args: argparse.Namespace) -> int:
    frame = request(
        args.api,
        f"/api/v1/runs/{args.run_id}/steps",
        "POST",
        {"ticks": args.ticks, "include_resources": False},
    )
    if args.json:
        print(json.dumps(frame["metrics"]))
        return 0
    print(_metric_line(frame["metrics"]))
    return 0


def command_show(args: argparse.Namespace) -> int:
    manifest = request(args.api, f"/api/v1/runs/{args.run_id}/manifest")
    if args.json:
        print(json.dumps(manifest))
        return 0
    playback = manifest.get("playback", {})
    print(f"run       {manifest['run_id']}")
    print(f"status    {manifest['status']}")
    print(f"pace      {describe_pace(playback.get('seconds_per_year'))}")
    print(f"tick      {manifest['tick']}  (year {manifest['year']:.1f})")
    print(f"people    {manifest['population']}")
    print(f"model     {manifest['model']['model_version']}")
    return 0


def command_watch(args: argparse.Namespace) -> int:
    """Print a line every so often, for a run that outlives this command.

    This only observes. Stopping it with Ctrl-C leaves the run exactly as it
    was, still going, which is the whole point of the arrangement.
    """

    started = time.monotonic()
    try:
        while True:
            frame = request(args.api, f"/api/v1/runs/{args.run_id}/frame")
            if args.json:
                print(json.dumps(frame["metrics"]), flush=True)
            else:
                print(_metric_line(frame["metrics"]), flush=True)
            if frame["status"] == "failed":
                print("run failed; it is no longer advancing", file=sys.stderr)
                return 1
            if args.until is not None and frame["year"] >= args.until:
                return 0
            if args.duration is not None and (
                time.monotonic() - started >= args.duration
            ):
                return 0
            time.sleep(args.every)
    except KeyboardInterrupt:
        print("\nstopped watching; the run is still going", file=sys.stderr)
        return 0


def command_snapshot(args: argparse.Namespace) -> int:
    snapshot = request(args.api, f"/api/v1/runs/{args.run_id}/snapshot")
    text = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    if args.out is None:
        print(text)
        return 0
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out} ({len(text)} bytes)")
    return 0


def command_delete(args: argparse.Namespace) -> int:
    """Forget runs, which is the only way memory is ever given back.

    Deleting is irreversible — a run exists only in the service's memory, so
    there is nothing to restore it from. That is why ``--all`` names what it
    is about to destroy and asks, unless told not to.
    """

    if args.all:
        targets = [
            manifest["run_id"]
            for manifest in request(args.api, "/api/v1/runs")["runs"]
            # A run being driven is one somebody set going on purpose. Taking
            # those too needs saying out loud.
            if args.running or manifest["status"] != "running"
        ]
    else:
        targets = list(args.run_id)
    if not targets:
        print("nothing to delete")
        return 0

    if args.all and not args.yes:
        print("about to delete:")
        for run_id in targets:
            print(f"  {run_id}")
        answer = input(f"delete {len(targets)} run(s)? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("nothing deleted")
            return 0

    failures = 0
    for run_id in targets:
        try:
            request(args.api, f"/api/v1/runs/{run_id}", "DELETE")
        except ServiceError as error:
            print(f"error: {run_id}: {error}", file=sys.stderr)
            failures += 1
            continue
        print(f"deleted {run_id}")
    return 1 if failures else 0


def _report_playback(state: Dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(state))
        return 0
    playback = state["playback"]
    print(
        f"{state['run_id']}  {state['status']}  "
        f"tick {state['tick']} (year {state['year']:.1f})  "
        f"{describe_pace(playback['seconds_per_year'])}"
    )
    return 0


def _metric_line(metrics: Dict[str, Any]) -> str:
    return (
        f"year {metrics['year']:>8.1f}  "
        f"people {metrics['population']:>6}  "
        f"births {metrics['births']:>4}  "
        f"deaths {metrics['deaths']:>4}  "
        f"food {metrics['resource_fraction']:>5.2f}  "
        f"health {metrics['mean_health_fraction']:>5.2f}  "
        f"mind {metrics['mean_network_magnitude']:>6.4f}  "
        f"words {metrics['distinct_words']:>5}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sims.lab",
        description=(
            "Configure and control runs held by a long-lived engine service. "
            "Runs keep advancing after this command exits."
        ),
    )
    parser.add_argument(
        "--api",
        default=DEFAULT_API,
        help=f"engine service base URL (default {DEFAULT_API})",
    )
    # Accepted on either side of the subcommand. `lab start --json` is what
    # anybody types first, and having that fail on a flag the tool plainly
    # has is a poor way to meet a command line.
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable output",
    )
    shared.add_argument("--api", default=DEFAULT_API, help=argparse.SUPPRESS)
    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable output",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    start = subcommands.add_parser(
        "start",
        help="create a run and set it going",
        parents=[shared],
    )
    source = start.add_mutually_exclusive_group()
    source.add_argument("--config", type=Path)
    source.add_argument("--scenario", type=Path)
    start.add_argument("--seed", type=int, default=0)
    start.add_argument("--width", type=int)
    start.add_argument("--height", type=int)
    start.add_argument("--population", type=int)
    start.add_argument(
        "--pace",
        type=parse_pace,
        default=0.0,
        help=(
            "wall-clock time one simulated year takes: 'fast' (default), "
            "or a number with an optional s/m/h/d suffix, e.g. 30s or 1h"
        ),
    )
    start.add_argument(
        "--paused",
        action="store_true",
        help="create the run without starting it",
    )
    start.set_defaults(handler=command_start)

    listing = subcommands.add_parser(
        "list",
        help="every run the service holds",
        parents=[shared],
    )
    listing.set_defaults(handler=command_list)

    show = subcommands.add_parser(
        "show",
        help="one run in detail",
        parents=[shared],
    )
    show.add_argument("run_id")
    show.set_defaults(handler=command_show)

    play = subcommands.add_parser(
        "play",
        help="set a run going",
        parents=[shared],
    )
    play.add_argument("run_id")
    play.add_argument("--pace", type=parse_pace, default=None)
    play.set_defaults(handler=command_play)

    pause = subcommands.add_parser(
        "pause",
        help="stop advancing a run",
        parents=[shared],
    )
    pause.add_argument("run_id")
    pause.set_defaults(handler=command_pause)

    step = subcommands.add_parser(
        "step",
        help="advance a paused run by hand",
        parents=[shared],
    )
    step.add_argument("run_id")
    step.add_argument("--ticks", type=int, default=1)
    step.set_defaults(handler=command_step)

    watch = subcommands.add_parser(
        "watch",
        help="print metrics periodically without touching the run",
        parents=[shared],
    )
    watch.add_argument("run_id")
    watch.add_argument(
        "--every",
        type=float,
        default=10.0,
        help="seconds between readings (default 10)",
    )
    watch.add_argument(
        "--until",
        type=float,
        default=None,
        help="stop watching once the run reaches this simulated year",
    )
    watch.add_argument(
        "--duration",
        type=float,
        default=None,
        help="stop watching after this many real seconds",
    )
    watch.set_defaults(handler=command_watch)

    snapshot = subcommands.add_parser(
        "snapshot",
        help="export complete run state as JSON",
        parents=[shared],
    )
    snapshot.add_argument("run_id")
    snapshot.add_argument("--out", type=Path)
    snapshot.set_defaults(handler=command_snapshot)

    delete = subcommands.add_parser(
        "delete",
        help="stop runs and release their memory",
        parents=[shared],
    )
    delete.add_argument("run_id", nargs="*")
    delete.add_argument(
        "--all",
        action="store_true",
        help="every run that is not currently being driven",
    )
    delete.add_argument(
        "--running",
        action="store_true",
        help="with --all, take the runs that are still advancing too",
    )
    delete.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="skip the confirmation --all otherwise asks for",
    )
    delete.set_defaults(handler=command_delete)

    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(
        None if argv is None else list(argv)
    )
    if getattr(args, "all", False) and getattr(args, "run_id", None):
        print(
            "error: name runs or pass --all, not both",
            file=sys.stderr,
        )
        return 2
    if (
        args.handler is command_delete
        and not args.all
        and not args.run_id
    ):
        print("error: name a run to delete, or pass --all", file=sys.stderr)
        return 2
    try:
        return int(args.handler(args))
    except ServiceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
