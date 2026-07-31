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

Use an explicit world matrix for D2's sparse-versus-density-matched question:

```bash
python3 -m sims.scaling_experiment \
  --config configs/pressure.json --world-sizes 24x24,48x48 \
  --populations 80,320 --seeds 0,1,2,3,4,5 --ticks 1200
```

This crosses every population with every world size. The `80 / 48x48` arm
isolates sparsity, while `320 / 48x48` restores the pressure-world founder
density.
Each record includes `founders_per_cell` so those cases remain explicit.

Measure engine and projection cost:

```bash
python3 -m sims.profile_engine \
  --populations 1000,5000,10000 \
  --ticks 10
```

`profile_engine` accepts the same `--world-sizes` matrix when area and
population costs need to be separated directly.

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
./run.sh lab snapshot <id> --out world.json       # analysis only
./run.sh lab checkpoint <id> --out run.json       # resumable
./run.sh lab restore run.json --pace fast          # move/restart
./run.sh lab delete <id> [<id>...]     # release the memory
./run.sh lab delete --all              # every idle run; --running takes those too
```

`--pace` is the wall-clock time one simulated year should take: `fast` for as
quickly as the machine manages, or a number with an `s`/`m`/`h`/`d` suffix.
Add `--json` to any subcommand for machine-readable output, and `--api URL`
(or `HUMAN_SIM_API`) to reach a service somewhere else.

The repository launcher keeps service-owned checkpoints in `.run/checkpoints`,
autosaves every 120 ticks, saves again on a clean shutdown, and restores runs
paused at startup. A crash can lose at most the unsaved interval. Override the
location with `HUMAN_SIM_CHECKPOINT_DIR` and the cadence with
`HUMAN_SIM_AUTOSAVE_TICKS`.

`lab checkpoint` writes through a temporary file and atomically replaces its
destination, so an interrupted write leaves the previous file intact.
`lab restore` accepts that JSON on another host. Checkpoint model and schema
versions must match exactly; incompatible state is refused rather than
guessed at. `lab snapshot` remains a visualization/analysis export and lacks
the random and allocation state required to resume.

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

## Comparing configurations

`sims.experiment` answers one question: *does this setting change anything?*
It runs two or more arms across the same seeds and reports whether the
difference clears seed-to-seed variation.

```bash
./run.sh experiment \
  --arm on \
  --arm off=neural_output_weight=0 \
  --config configs/scarcity.json \
  --seeds 0,1,2,3,4,5 --years 300 --metric population --jobs 2
```

- `--arm NAME=key=value[,key=value]` — repeat it; the first arm is the
  control. An arm with no settings runs the configuration as the file left
  it. Values are read as JSON, so `false` is a boolean and `0.05` is a number,
  and a key that is not a `SimulationConfig` field is refused rather than
  ignored.
- `--metric` — any field of the metrics record, plus `ticks_run` for
  survival. When a world kills everybody, final population is zero in every
  arm and only survival time distinguishes them.
- `--jobs` — runs in parallel; output stays ordered.
- `--json` — one record per run and nothing else, including the opening and
  final metrics for every run.

### Runs are paired by seed, and that has a trap

Each arm sees the same seed, so it should get the same world, the same
founders, and the same weather; the difference on that seed is then
attributable to the setting rather than to luck.

**A setting that changes how much randomness is drawn while the world is
being built breaks this.** `neural_brains_enabled=false` skips the weight
draws, which shifts every later draw, so the arms end up with different
founders standing in different places — and the comparison silently becomes
"brains plus a different world" against "brains". Use
`neural_output_weight=0` instead: the networks are still built, they simply
contribute nothing, and the two arms start from an identical world.

The harness checks this for you. It compares the opening measurement across
arms and prints a warning naming the seeds where they diverged, so a
confounded comparison announces itself instead of being read as a result.

### Choosing a world that can answer the question

An experiment can only see a difference the world allows to exist. Three
bands, measured:

| Config | Founders | Ceiling | What happens |
|---|---|---|---|
| `configs/baseline.json` | 200 | ~13,000 | No pressure. Nothing selects; every arm grows. |
| `configs/pressure.json` | 80 | ~350 | Grows into the ceiling and stays there: ~170 people, resources held near 13% of capacity, 14 generations in 300 years. |
| `configs/scarcity.json` | 400 | ~350 | Starts above the ceiling. Every seed goes extinct by about year 150, brains or no brains. |

The ceiling is `resource_regeneration x cell_capacity x cells` food per year
against roughly 1.33 food per person per year.

Both ends are useless for comparing a mechanism. Under abundance every arm
survives and the difference is noise; under `scarcity.json` every arm dies and
the difference is noise again. `pressure.json` is the band where a population
persists *and* is genuinely squeezed, which is the only place a mechanism that
helps people eat can show up as more people.

Measured results from this harness, with their raw output, are collected in
[findings.md](findings.md).

### Reading the verdict

The summary reports the per-seed difference, its spread, that difference as a
share of the control's mean, and an exact two-sided sign test. A difference is
only called real when the seeds agree *and* the effect is large next to how
much the seeds disagree among themselves.

Note the floor: with `n` paired seeds the best possible sign-test p-value is
`2/2ⁿ`, so **six seeds are the minimum** at the default threshold of 0.05, no
matter how large the effect. When every seed agrees but `n` is too small, the
summary says that rather than reporting "no difference" — a shortage of runs
is not evidence of absence.

### Metrics that survive an equilibrium

`--metric` is repeatable, so one expensive sweep can be read several ways:

```bash
./run.sh experiment --arm off=neural_output_weight=0 --arm on \
  --config configs/pressure.json --seeds 0,1,2,3,4,5 --years 300 \
  --checkpoint-years 25,50,100 \
  --metric population --metric population_at_50 \
  --metric mean_body_condition --metric mean_network_magnitude
```

Final population is a weak reading in a world that reaches equilibrium: the
land decides how many people fit, so a mechanism that only changes *how fast*
they got there leaves no trace in it. `--checkpoint-years` records population
at those years and exposes it as `population_at_YEAR`, which keeps the
transient. Death causes arrive as `deaths_<cause>`, and `ticks_run` is
survival.

One reading is worth singling out. Comparing `mean_network_magnitude` between
a live arm and a `neural_output_weight=0` arm is a **neutral-drift control**:
in the silenced arm the same networks are still inherited and mutated, but
nothing can select on them, because they cannot affect a decision. If the two
arms end up at the same magnitude, the networks in the live arm are drifting
too — whatever the world is selecting for, it is not brains.

### Leaving a sweep running overnight

```bash
setsid nohup ./run.sh experiment \
  --arm off=neural_output_weight=0 --arm base \
  --arm plastic=plasticity_rate=0.05 \
  --config configs/pressure.json --seeds 0,1,2,3,4,5 --years 3000 \
  --checkpoint-years 50,300,1000,2000 \
  --out .run/experiments/overnight.jsonl \
  --metric population --metric population_at_1000 --metric mean_plasticity \
  --jobs 2 > .run/experiments/overnight.txt 2>&1 &
```

`setsid nohup … &` detaches it, so closing the terminal or the editor leaves
it running. Each finished run is printed and appended to `--out` immediately,
so an interrupted sweep is still a partial result rather than nothing:

```bash
./run.sh experiment --summarise .run/experiments/overnight.jsonl \
  --metric population --metric mean_plasticity
```

That re-runs the comparison from whatever completed, without simulating
anything. Progress is `wc -l` on the same file.

**Not every setting can be an arm.** One that changes how much randomness is
drawn while the world is built gives the arms different founders — measured:
`neural_hidden_units` does this (a different network shape draws a different
number of weights), while `neural_output_weight` and `plasticity_rate` do
not. Testing brain *capacity* therefore needs a different design and more
seeds, because the founder differences have to be averaged out rather than
cancelled. The harness prints a warning naming the seeds when it happens, so
this is caught rather than believed.

## Measuring engine speed

```bash
python -m sims.benchmark --config configs/pressure.json --ticks 400 --repeats 3
python -m sims.benchmark --config configs/pressure.json --ticks 200 --calls
python -m sims.benchmark --config configs/pressure.json --ticks 300 --profile
```

Three readings, and the third is the one that matters:

- **ticks/s** — CPU time for this process, best of `--repeats`. Be careful
  with it: on a laptop this same unchanged code measured 42, 34 and 20 ticks
  per second within one session. Anything under about 20% is invisible here.
- **`--calls`** — Python function calls, which a deterministic engine repeats
  exactly. Zero variance, so it resolves what the clock cannot; but it counts
  call *volume*, so a change that swaps one kind of call for another reads as
  no change.
- **the digest** — a fingerprint of the final state. The engine is
  deterministic, so an optimisation that moves the digest changed the
  simulation and its timing is beside the point. Compare digests only between
  runs with identical config, seed, warmup and ticks.

The profile is flat: about 70,000 Python calls per tick spread across the
decision path, with no single function above 13% of self time. Two careful
micro-optimisations were written, measured, and reverted — the profile capped
each at roughly 1% overall. A real multiple has to come from a different
runtime or a native core, not from local edits.
