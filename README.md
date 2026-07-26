# Human-Sim

Human-Sim is a deterministic agent-based simulation for investigating how new
population-level behavior appears as a society grows.

The project does not script stories, institutions, or historical events. It
defines a small substrate—space, finite resources, metabolism, local
perception, action costs, reproduction, inheritance, and mutation—and lets
outcomes arise from repeated local interactions.

## Current model

Every run contains:

- A bounded, optionally wrapping resource grid with heterogeneous carrying
  capacity, regeneration, and user-defined land and sea.
- User-defined countries that place founders in distinct regions with different
  religions, cultural trait distributions, resources, and starting energy.
- Persistent agents with energy, health, food inventory, age, position, and
  inherited traits.
- Local perception: agents can inspect nearby cells and interact only with
  nearby agents.
- Utility-based choices between eating, gathering, sharing, reproduction,
  movement, research, teaching, construction, and rest.
- Birth, trait inheritance and mutation, aging, starvation, and death.
- Material gathering and an embodied seafaring path: curious coastal agents
  experiment at a cost, knowledge spreads locally, vessels require materials,
  and sea movement consumes energy and durability.
- Aggregate metrics and a bounded diagnostic event log.
- Seeded randomness. The same configuration, seed, and number of ticks produce
  exactly the same state.

Religion is currently a transmissible identity label, not a source of scripted
behavior. Traditions influence founder trait distributions and can change
through inheritance and contact. Wealth, markets, borders, and government
remain intentionally absent until lower-level mechanics can produce them.

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

Export a complete versioned UI snapshot:

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

Install an optional command-line entry point:

```bash
python3 -m pip install -e .
human-sim --ticks 120 --seed 42
```

## Test

The test suite uses the Python standard library:

```bash
python3 -m unittest discover -v
```

It checks deterministic replay, seed variation, resource bounds, inherited
generations, metrics sampling, bounded event storage, and extinction caused by
the simulated constraints rather than a scripted event.

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
columnar, JSON-serializable state for a future web or desktop UI. The engine
owns its clock and random generator; it does not depend on wall-clock time.

The spatial index avoids all-pairs interaction. Per-tick work grows with the
population and each agent's bounded perception area, rather than with the
square of the population. Detailed design and extension rules are documented
in [docs/architecture.md](docs/architecture.md).

## Experimental discipline

Do not infer emergence from one visually interesting run. Compare repeated
seeds across increasing population sizes while holding density and other
conditions constant. A candidate emergent behavior should be measurable,
repeatable as a distribution, and absent or qualitatively different below some
scale or interaction regime.

All model constants live in `SimulationConfig`. Changing them creates a new
experimental condition. Recorded results should always include the complete
configuration, seed, and code revision.
