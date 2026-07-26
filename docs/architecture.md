# Architecture and modeling rules

## North star

Human-Sim hardcodes mechanisms, never outcomes.

Every simulation requires axioms. In this model they are resource conservation,
metabolic cost, spatial locality, possible actions, and lifecycle constraints.
Whether the population grows, collapses, cooperates, segregates, specializes,
or forms stable structures must follow from those axioms and agent experience.

An addition belongs in the engine when it answers all of these questions:

1. What information can an agent locally observe?
2. What does the action cost?
3. What state does it change?
4. Can the proposed outcome instead be derived as a metric?
5. Can its effect be compared across seeds and scales?

## Package boundaries

### `src.simulation.config`

`SimulationConfig` is the complete set of model parameters. It is immutable and
validated at construction. There should be no scenario-specific constants in
the engine or command-line interface.

### `src.simulation.scenario`

Scenarios are user-authored, serializable starting conditions. A country is a
named region, founder population, religion label, cultural distribution, and
resource/energy multipliers. It is not an omniscient agent and has no arbitrary
economy or culture score.

Sea is terrain rather than an event. Scenario rectangles are deliberately a
small first map format that a future UI can edit; richer raster or polygon
importers can compile down to the same world layers.

### `src.simulation.models`

The data plane consists of slotted dataclasses. Slots keep individual agents
compact enough for large populations. Agents contain causal state only; names,
biographies, display colors, and prose belong in visualization or reporting
layers.

Traits are continuous where possible. Founders receive variation, and children
receive one recombined, possibly mutated haplotype from each parent. Phenotypes,
culture, and learned brain state are separate. There is no explicit selection
score: reproductive success and survival provide selection pressure through
the environment.

### `src.simulation.world`

The world stores resources in flat arrays and maps occupied cells to agent IDs.
Neighborhood queries therefore depend on perception radius and local density,
not total population.

World layers store terrain, country, food, material, and occupancy separately.
The default world is bounded; wrapping remains a configurable experiment.

Sea cells cannot be entered by ordinary movement. Seafaring is not globally
unlocked: an individual must experiment at a coast, spend energy and material,
accumulate enough research, and construct a vessel. Knowledge can then spread
through local teaching. Vessels have durability and sea movement has a higher
energy cost.

### `src.simulation.engine`

One `Simulation` owns all mutable state, including its pseudorandom generator.
A tick has five phases:

1. Advance biological time, charge metabolism, apply aging, and remove deaths.
2. Rebuild the spatial index.
3. Let each living agent select one action from local information.
4. Resolve actions in a seeded random order.
5. Regenerate environmental resources and sample metrics.

Decisions are created from a consistent beginning-of-action-phase view.
Resolution order is randomized to prevent permanent low-ID priority while
remaining reproducible.

### `sims`

Scenarios and entry points assemble configurations and run engines. They must
not contain behavior unavailable to library users.

## Scaling contract

The current engine targets thousands to tens of thousands of agents in one
process. Its core data structures avoid an all-pairs social graph and unbounded
per-agent memory.

These rules preserve a future path to partitioning:

- Agents interact through IDs, not Python object graphs.
- Cross-agent effects occur during an explicit resolution phase.
- Spatial interaction is bounded and partitionable.
- Rendering and event persistence are optional consumers.
- The simulation never uses wall-clock time for causal state.
- The in-memory event and metrics histories are bounded; a caller can stream
  either through a sink.
- UI snapshots are versioned and columnar, avoiding an API tied to Python
  objects.
- Decision random streams are keyed per tick and agent, so brain evaluation can
  later be parallelized without changing unrelated decisions.

Do not assign one operating-system process or container to every agent. If a
single process becomes insufficient, partition spatial regions into a modest
number of workers and exchange boundary actions between ticks.

### Native-code boundary

C is useful only after profiling identifies a stable hot loop. Packed genomes
are two integers per agent, and the likely first ports are neighborhood
scoring, action scoring, genetics, and resource regeneration—not
the scenario parser or UI API. Terrain and resource data already use flat
numeric layers, agents interact through integer IDs, and ticks have explicit
phases. A C, Cython, Rust, or NumPy-backed implementation can therefore sit
behind `Simulation` while keeping scenario JSON and snapshot schema version 2.

Until populations make Python the measured bottleneck, native code would slow
model iteration and make correctness harder to inspect. Every future native
backend must pass the same deterministic and invariant tests as the reference
Python engine.

## Measuring emergence

Scaling population alone also changes density unless world area is scaled with
it. Experiments should distinguish:

- Population scaling at constant world size.
- Population scaling at constant density.
- Increasing interaction radius at constant population.
- Resource abundance and regeneration changes.
- Trait diversity and mutation changes.

Metrics currently include population, births, deaths, food/material stock, mean
energy/health/inventory/age, maximum generation, energy inequality, action
counts and entropy, beliefs, country occupancy, brain mechanisms, population
genetic diversity, pregnancies, seafaring knowledge, vessels, inventions, and
landfalls. New hypotheses should normally add an observer metric before adding
a new agent rule.

Useful future observer metrics include network clustering, spatial
segregation, lineage diversity, trait distributions, resource inequality,
specialization, mobility, and survival curves.

## Near-term extension order

1. Add a UI/service adapter around scenario loading, stepping, and snapshots.
2. Persist experiment streams together with the code revision.
3. Add bounded relationship memory based on repeated local encounters.
4. Allow learned action preferences while retaining explicit information and
   energy costs.
5. Introduce production and exchange from physical inventories.
6. Derive groups and institutions from persistent relationships and collective
   action.

This order builds causal layers. Markets should follow production and exchange;
institutions should follow relationships and collective decisions; country
statistics should be measurements of those structures rather than initial
conditions.
