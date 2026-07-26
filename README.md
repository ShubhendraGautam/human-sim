# Human-Sim

Human-Sim is a deterministic agent-based simulation for investigating how new
population-level behavior appears as a society grows.

The project does not script stories, institutions, or historical events. It
defines a small substrate—space, finite resources, metabolism, local
perception, action costs, reproduction, inheritance, and mutation—and lets
outcomes arise from repeated local interactions.

## Current model

Every run contains:

- A bounded, optionally wrapping world with heterogeneous carrying capacity,
  capacity-scaled productivity, latitude-driven seasons, food spoilage,
  nonrenewable materials by default, and user-defined land and sea.
- User-defined countries that place founders in distinct regions with different
  religions, cultural trait distributions, resources, and starting energy.
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
- Strictly bounded local attention plus fixed-capacity, asymmetric memories of
  trust, reciprocity balance, encounter count, and recency.
- Utility-based choices between eating, gathering, sharing, reproduction,
  communication, movement, research, teaching, construction, and rest.
- Reciprocal reproductive intent with bounded local matching, age- and
  condition-dependent fecundity, costly gestation using actual paid energy,
  stochastic pregnancy loss, postpartum recovery, delayed birth, bounded
  recent ancestry, dependent children, caregiver food transfer, stochastic
  senescence, and causal death accounting.
- A generic local SEIR-style infection process. Outbreaks require seeded
  exposure and spread through local density; susceptibility and severity
  respond to inherited immune potential, age, nutrition, and frailty.
- Material gathering and an embodied seafaring path: curious coastal agents
  experiment at a cost, knowledge spreads locally, vessels require materials,
  and sea movement consumes energy and durability.
- Aggregate metrics—including world and held stocks plus per-tick harvest,
  renewal, consumption, spoilage, and death losses—and a bounded diagnostic
  event log.
- Seeded randomness. The same configuration, seed, and number of ticks produce
  exactly the same state.

Religion is currently a transmissible identity label, not a source of scripted
behavior. Culture and lifetime learning are separate from genetic inheritance.
Traditions initialize cultural tendencies and can change through family and
contact. Wealth, markets, borders, and government remain intentionally absent
until lower-level mechanics can produce them.

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

Start the optional API:

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

Open `http://127.0.0.1:5173`. Add `?demo=1` only when an explicitly labelled
synthetic interface preview is desired. The normal UI connects to the real
engine service.

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
  World      Agents
resource     local state
grid/index   inherited traits
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
[docs/biology-and-brains.md](docs/biology-and-brains.md).

## Experimental discipline

Do not infer emergence from one visually interesting run. Compare repeated
seeds across increasing population sizes while holding density and other
conditions constant. A candidate emergent behavior should be measurable,
repeatable as a distribution, and absent or qualitatively different below some
scale or interaction regime.

Experiment-facing model parameters live in `SimulationConfig`. Changing them
creates a new experimental condition. Recorded results should always include
the complete configuration, seed, and code revision.
