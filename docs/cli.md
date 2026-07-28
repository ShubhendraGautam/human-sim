# Command reference

Every way to start, steer, and measure a run. The [README](../README.md) has
the few commands most people need; this has the rest.

Human-Sim requires Python 3.10 or newer. The simulation core has no
third-party runtime dependencies — only the optional HTTP service does.

## Headless runs

A headless run happens inside the command that starts it. When the command
ends, so does the world. For runs meant to outlive the shell that started
them, see [Long-lived runs](#long-lived-runs) below.

Human-Sim requires Python 3.10 or newer and currently has no third-party runtime
dependencies.

```bash
python3 -m sims.simple_sim
```

Run a reproducible experiment:

```bash
python3 -m sims.simple_sim \
  --population 1000 \
  --width 64 \
  --height 64 \
  --ticks 240 \
  --seed 42
```

Watch a population outrun what its land can feed:

```bash
python3 -m sims.simple_sim --config configs/scarcity.json --ticks 400 --seed 42
```

The default world is deliberately abundant, and it helps to see why. The
food layer regrows a share of its *deficit* each year, so its sustainable
yield is `resource_regeneration x cell_capacity x cells` — about 17,700
food/year at the defaults. A person burns roughly 1.33 food/year. The default
world could therefore feed something like ten thousand people, which 200
founders growing at a couple of percent a year will not approach inside any
run you are likely to sit through. That is why nobody starves in a default
run: not because starvation is broken, but because the ceiling is nowhere
near. `configs/scarcity.json` puts the ceiling within reach. On seeds 42, 7 and 3
the population overshoots to around 400, starves back below 100 within about
25 to 35 years, and the land recovers behind it — resources climb from 6% of
capacity back past 35% while the survivors' body condition recovers from 0.5
to nearly 0.9. Starvation deaths stop accruing once density falls, which is
the feedback the old rule could not produce.

Two honest caveats about that run. The crash overshoots: the remnant keeps
declining slowly afterwards rather than settling at what the recovered land
could support, so this is boom and bust, not a steady state. And 400 people
on a 24x24 map hunt the herd out inside five years, so that configuration
shows overhunting rather than coexistence. The default world is where animals
and people persist together.

Emit only machine-readable final metrics:

```bash
python3 -m sims.simple_sim --config configs/baseline.json --seed 42 --json
```

Run the included two-country island scenario:

```bash
python3 -m sims.simple_sim \
  --scenario scenarios/two_islands.json \
  --ticks 240 \
  --seed 4
```

Scenario files contain the world configuration, rectangular country regions,
founder profiles, and sea regions. This is the same serializable contract a
future scenario editor can produce.

Export a versioned visualization snapshot:

```bash
python3 -m sims.simple_sim \
  --scenario scenarios/two_islands.json \
  --ticks 20 \
  --snapshot > snapshot.json
```

Compare population sizes across repeated seeds:

```bash
python3 -m sims.scaling_experiment \
  --populations 100,300,1000 \
  --seeds 0,1,2 \
  --ticks 120 \
  --constant-density 0.25
```

The experiment emits one JSON record per run, including its complete
configuration, seed, and final metrics. Omit `--constant-density` to study the
effect of increasing crowding in a fixed world; include it to isolate population
scale while keeping starting density approximately constant.

Measure engine and projection cost:

```bash
python3 -m sims.profile_engine \
  --populations 1000,5000,10000 \
  --ticks 10
```

Each record reports build time, per-tick cost, `measure()` cost, and service
manifest and frame cost with serialized byte counts, alongside the configuration
and code revision. Add `--profile` for a `cProfile` table identifying which
functions dominate. Wall-clock timing varies substantially on a loaded machine,
so compare alternating runs rather than one measurement.

Install an optional command-line entry point:

```bash
python3 -m pip install -e .
human-sim --ticks 120 --seed 42
```
## Long-lived runs

These talk to the engine service rather than simulating anything themselves,
so the run keeps advancing after the command returns. Start the service with
`./run.sh start --api-only` first.

```bash
./run.sh lab start --scenario scenarios/two_islands.json --seed 5 --pace fast
./run.sh lab list                      # every run the service holds
./run.sh lab show <id>                 # one run in detail
./run.sh lab watch <id> --every 60     # a metrics line a minute
./run.sh lab play <id> --pace 1h       # change pace, or resume
./run.sh lab pause <id>                # stop advancing; state is kept
./run.sh lab step <id> --ticks 12      # advance a paused run by hand
./run.sh lab snapshot <id> --out world.json
./run.sh lab delete <id> [<id>...]     # release the memory
./run.sh lab delete --all              # every idle run; --running takes those too
```

`--pace` is the wall-clock time one simulated year should take: `fast` for as
quickly as the machine manages, or a number with an `s`/`m`/`h`/`d` suffix.
Add `--json` to any subcommand for machine-readable output, and `--api URL`
(or `HUMAN_SIM_API`) to reach a service somewhere else.

Runs live in the service's memory. Stopping the API ends every run it held,
and a snapshot is an export for analysis rather than a resumable save.

## run.sh

```text
setup                 Create .venv, install Python and UI dependencies
start [opts]          Start the engine API and the Run Lab UI
stop [opts]           Stop services; --ui-only keeps the engine and its runs
restart [opts]        Stop, then start again
status                Show what is running
logs [api|ui|all]     Follow service logs
sim [args...]         Headless run: sims.simple_sim
scenario [file] [..]  Run a scenario file
lab <subcommand>      Long-lived runs held by the service
test [py|ui|all]      Run the test suites
lint                  flake8 + TypeScript typecheck
check                 lint, then test
build                 Production build of the UI
clean                 Stop services and remove generated files
```

`start` and `stop` accept `--api-only` and `--ui-only`; `start` also takes
`--logs`. Ports come from `API_PORT` and `UI_PORT`. Pid files and logs live
in `.run/`.

## Run Lab UI by hand

`./run.sh start` brings both halves up together. To run them separately,
start the optional API:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-api.txt
.venv/bin/python -m src.human_sim_service.api
```

In another terminal, using Node.js 24 or newer:

```bash
cd ui
npm ci
npm run dev
```

Then open <http://127.0.0.1:5173>. URL parameters:

- `?run=<id>` attaches to a particular run. Without it the lab reattaches to
  the run this browser last watched, and creates a world only when there is
  none to attach to.
- `?demo=1` loads an explicitly labelled synthetic fixture with no engine
  behind it. Useful for interface design, never a simulation result — and its
  playback stops with the tab, because nothing else is running it.

See [ui/README.md](../ui/README.md) for frontend commands and
[docs/ui-architecture.md](ui-architecture.md) for the service contracts.
