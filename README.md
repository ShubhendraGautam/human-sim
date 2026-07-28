# Human-Sim

Human-Sim is a deterministic agent-based simulation for investigating how new
population-level behavior appears as a society grows.

The project does not script stories, institutions, or historical events. It
defines a small substrate—space, finite resources, metabolism, local
perception, action costs, reproduction, inheritance, and mutation—and lets
outcomes arise from repeated local interactions.

## Current model

Every run contains:

- One identity space for everything that occupies the world. Living things
  register themselves and deregister when they die; inert things are
  registered by whatever made them and keep that provenance after the maker
  is gone. People and animals are both present in it.
- A bounded, optionally wrapping world with heterogeneous carrying capacity,
  capacity-scaled productivity, latitude-driven seasons, food spoilage,
  nonrenewable materials by default, and user-defined land and sea.
- User-defined countries that place founders in distinct regions with different
  religions, cultural trait distributions, resources, and starting energy.
- Grazing animals, seeded into every world and thereafter existing only
  because their parents did. They eat the same food layer people harvest, so
  a herd is competition; they carry energy in their bodies, so a herd is also
  food. Intake falls away as a patch empties, which is what stops a herd
  flattening the world and holding it flat, and produces boom and crash
  instead. Vigilance and fecundity are heritable and mutate, so hunting is
  selection rather than subtraction. Nothing replaces a herd that is hunted
  out. Set `initial_fauna_density` to zero for a world with no animals in it.
- Persistent agents with energy, health, food inventory, age, position, and
  inherited biology.
- Compact 64-locus diploid genomes with chromosome recombination, probabilistic
  mutation, individual health potential, fertility, metabolism, maturation,
  longevity, immunity, affiliation, sensory ability, and cognitive tendencies.
- Separate genetic potential, prenatal/childhood development, chronic body
  condition, current health, and accumulated frailty. Acquired condition never
  rewrites the genome.
- Four brain mechanisms—deliberative, exploratory, habitual learning, and
  social imitation—combined with continuous individual temperament.
- Minds that perceive the world rather than only their own bodies. Thirteen
  of a brain's fourteen senses used to be internal, so it could feel hunger
  but could not notice that the ground was bare, that it was better one step
  over, that winter was coming, or that an animal was within reach—every one
  of those judgements had to be supplied as a constant. It now senses those
  directly, and its opinion is loud enough to hear: the whole network used to
  contribute about 0.05 utility units against a decision noise of 0.20, which
  made brains-on and brains-off runs indistinguishable.
- A bounded, fading memory of places that paid out, so foraging can be a
  return to somewhere known rather than a walk uphill. Recorded only where
  someone stood and took something from the ground.
- Lifetime plasticity, present and **off by default**. A learned adjustment
  to the inherited network, moved by how much better an action went than that
  action usually goes, credited to the parts of the brain that were active
  when the choice was made, costing energy, and dying with the person rather
  than passing to their children. It is off because it measured worse than
  not learning—23.7 people against 17.8 over six seeds, and still 21.7 with
  the energy price removed. The mechanism is correct and tested; what is
  unproven is that this world rewards it. Raise `plasticity_rate` to
  experiment.
- Strictly bounded local attention plus fixed-capacity, asymmetric memories of
  trust, reciprocity balance, encounter count, and recency.
- Utility-based choices between eating, gathering, hunting, sharing,
  reproduction, communication, movement, research, teaching, construction,
  and rest. Hunting costs energy whether or not it succeeds, so it is a
  gamble against gathering rather than a better version of it.
- An open table of learnable techniques rather than one named skill. A
  technique is an affordance that makes it thinkable — a coast, materials to
  hand, animals within reach — an amount of work, and a change to what its
  carrier can do. Discovery and teaching are written against no technique in
  particular, so what a population works out is a table entry rather than a
  branch in the engine.
- Reciprocal reproductive intent with bounded local matching, age- and
  condition-dependent fecundity, costly gestation using actual paid energy,
  stochastic pregnancy loss, postpartum recovery, delayed birth, bounded
  recent ancestry, dependent children, caregiver food transfer, stochastic
  senescence, and causal death accounting.
- A generic local SEIR-style infection process with two ways in: local
  contact, and a small per-person environmental hazard standing in for the
  reservoirs this model does not contain yet. Without the second, an outbreak
  that ends ends forever, so a founding seed that fizzles in a sparse world
  leaves a world that can never be sick again. Susceptibility and severity
  respond to inherited immune potential, age, nutrition, and frailty, and
  whether an introduction fizzles or becomes a wave is decided by density
  rather than by a schedule. Set `environmental_exposure_rate_per_year` to
  zero to close the reservoir and reproduce earlier runs exactly.
- Material gathering and an embodied seafaring path: curious coastal agents
  experiment at a cost, knowledge spreads locally, and vessels require
  materials. A vessel is spent by time at sea rather than by distance, so
  nobody can wait out a voyage on open water; when a hull fails, a coast
  within reach can be waded to and open water cannot, which drowns whoever
  is in it along with any passengers aboard.
- Words, coined from nothing and passed on. A population starts mute. Speech
  is grounded in what both parties can see, children acquire from whoever
  feeds them, nobody invents a rival form for something they have heard
  others name, and a listener adopts the form they hear most rather than the
  one they heard last. Local agreement and population-wide agreement are
  reported separately: dialects that each agree internally are the expected
  outcome where contact is thin, and a single number cannot tell that apart
  from everyone babbling.
- Aggregate metrics—including world and held stocks plus per-tick harvest,
  renewal, consumption, spoilage, and death losses—a bounded diagnostic event
  log, and a bounded record of the recently dead holding the cause and the
  state each person died in, so death is observable as a state rather than as
  readings that stop arriving.
- Seeded randomness. The same configuration, seed, and number of ticks produce
  exactly the same state.

Religion is currently a transmissible identity label, not a source of scripted
behavior. Culture and lifetime learning are separate from genetic inheritance.
Traditions initialize cultural tendencies and can change through family and
contact. Wealth, markets, borders, and government remain intentionally absent
until lower-level mechanics can produce them.

## Quick start

`run.sh` is a single entry point for the common tasks: installing
dependencies, starting and stopping the engine service and the Run Lab UI
together, running a headless simulation, and running the checks CI runs.

```bash
./run.sh setup     # create .venv, install Python and UI dependencies
./run.sh start     # engine API on :8000, Run Lab UI on :5173
./run.sh status    # what is running
./run.sh logs      # follow both logs (Ctrl-C leaves services running)
./run.sh stop      # stop both
```

Other commands: `restart`, `sim [args]`, `scenario [file] [args]`,
`lab <subcommand>`, `test [py|ui|all]`, `lint`, `check`, `build`, `clean`. Run
`./run.sh help` for the full list. `start` and `stop` accept `--api-only` and
`--ui-only`; `start` also takes `--logs`. Ports come from `API_PORT` and
`UI_PORT`; pid files and logs live in `.run/`.

Everything the script does is also available as the direct commands below, and
the simulation core itself needs nothing but Python.

## Runs that outlive the thing that started them

There are two ways to run this simulation, and they answer different
questions.

`sims.simple_sim` runs a world *inside* the command that starts it: you say
how many ticks, it runs them, prints the result, and the world is gone. That
is the right tool for a reproducible experiment with a known length.

For a world meant to be left going — days of evolution, checked on now and
then — the engine service holds the run and advances it on its own clock.
Nothing needs to stay attached to it. No browser, no terminal:

```bash
./run.sh start --api-only
./run.sh lab start --scenario scenarios/two_islands.json --seed 5 --pace fast
#   run       c12fb6dceded4500b43c907ba4bf8035
#   observe   http://127.0.0.1:5173/?run=c12fb6dceded4500b43c907ba4bf8035

./run.sh lab list                  # every run the service holds
./run.sh lab watch <id> --every 60 # a metrics line a minute; Ctrl-C is safe
./run.sh lab pause <id>            # stop advancing; state is kept
./run.sh lab snapshot <id> --out world.json
./run.sh lab delete <id> [<id>...] # stop them and release the memory
./run.sh lab delete --all          # every idle run; --running takes those too
```

Runs accumulate: the service holds every one it is given until it is told
otherwise, and each keeps its whole population in memory. `lab list` is how
you notice, and `lab delete` is the only way to reclaim the space short of
stopping the service.

`--pace` is how much wall-clock time one simulated year should take: `fast`
(as quickly as the machine manages), or a number with an `s`/`m`/`h`/`d`
suffix — `--pace 1h` for a run you intend to watch over a week.

Opening the Run Lab attaches to the run rather than starting a new one: the
URL above names it explicitly, and an ordinary reload reattaches to whatever
this browser was last watching. Run and Pause then control the engine, so
closing the tab leaves the world going. The **New** button is how you ask for
a second world on purpose.

One limit to plan around: **runs live in the service's memory.** Stopping the
API — `./run.sh stop`, `restart`, a crash, a reboot — ends every run it held,
and there is no way to load one back. `./run.sh stop --ui-only` is the safe
half. Snapshots are an export for analysis, not a resumable save.

## Run

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

## Run Lab UI

The first web laboratory is available in `ui/`. It observes the simulation
through a separate, versioned service boundary; browser controls can advance
time and recreate starting conditions but cannot change an agent's decisions
or causal state.

`./run.sh start` brings both halves up together. To run them by hand instead,
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

Open `http://127.0.0.1:5173`. Add `?run=<id>` to attach to a particular run;
without it the lab reattaches to the run this browser last watched, and only
creates a world when there is none to attach to. Add `?demo=1` only when an
explicitly labelled synthetic interface preview is desired — that fixture has
no engine behind it, so its playback stops with the tab. The normal UI
connects to the real engine service.

See [ui/README.md](ui/README.md) for frontend commands and
[docs/ui-architecture.md](docs/ui-architecture.md) for the service contracts,
scaling strategy, worker-process milestone, and future native-backend seam.

## Test

The test suite uses the Python standard library:

```bash
python3 -m unittest discover -v
```

It checks deterministic replay, genome inheritance and mutation, resource
conservation and seasons, chronic development, frailty, reciprocal
reproduction, gestational investment, caregiver indexing, disease
transmission, bounded social memory, snapshot contracts, neighborhood and
tick-ordering invariants relied on by the optimized decision path, projection
ownership, and extinction caused by simulated constraints rather than a
scripted event.

Four tests skip unless the optional API dependencies are installed. Install
`requirements-api.txt` to run them.

Lint with the project style, configured in `setup.cfg`:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m flake8 src sims tests
```

## Continuous integration

`.github/workflows/ci.yml` runs four jobs on every push and pull request:

- **lint** — flake8 at the project's 79-column style.
- **core** — the suite on Python 3.10 through 3.14 with nothing installed, so
  the zero-dependency promise above is enforced rather than merely stated.
- **service** — the suite with the optional API dependencies present, after
  asserting they import, so the four guarded tests cannot silently skip.
- **ui** — typecheck, test, and build on the Node version in
  `ui/.node-version`.

## Architecture

```text
SimulationConfig (immutable rules)
          |
          v
Simulation engine -----> aggregate metrics / optional event sink
    |          |
    v          v
  World     EntityRegistry
resource    one id space
grid        people, fauna (today), flora, artifacts
  |              |
  +---> spatial index, one bucket per kind
```

The simulation is headless: rendering and analysis consume its outputs but
never control agent behavior. `Simulation.snapshot()` exposes a versioned,
columnar, JSON-serializable visualization state for a future web or desktop UI.
World and relationship payloads can be omitted when a UI needs a lighter
update; the complete agent payload can also be excluded. It is deliberately
not advertised as a resumable checkpoint. The engine owns its clock and random
generator; it does not depend on wall-clock time.

For example, a UI that already has the map and does not need network edges can
set `include_world=False` and `include_relationships=False`.

The spatial index avoids all-pairs interaction. Per-tick work grows with the
population, bounded attention, and local perception area rather than with the
square of the population. Relationships live in a fixed-width central
structure-of-arrays store instead of per-agent graphs. Detailed design and
extension rules are documented in
[docs/architecture.md](docs/architecture.md). The explicit limits and mechanics
of the biology model are in
[docs/biology-and-brains.md](docs/biology-and-brains.md). What is planned next,
and what each addition has to prove before it lands, is in
[docs/design-checklist.md](docs/design-checklist.md).

## Experimental discipline

Do not infer emergence from one visually interesting run. Compare repeated
seeds across increasing population sizes while holding density and other
conditions constant. A candidate emergent behavior should be measurable,
repeatable as a distribution, and absent or qualitatively different below some
scale or interaction regime.

Experiment-facing model parameters live in `SimulationConfig`. Changing them
creates a new experimental condition. Recorded results should always include
the complete configuration, seed, and code revision.
