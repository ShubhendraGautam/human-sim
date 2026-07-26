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

### `src.simulation.life_history` and `src.simulation.health`

These modules contain pure scalar formulas for development, age capability,
fecundity, frailty, mortality hazards, infection susceptibility, and disease
severity. They use explicit simulated-year units, consume no global state, and
form a small parity surface for a future C backend.

### `src.simulation.relationships`

Social memory is a central fixed-width structure-of-arrays store. Agents keep
only a numeric row handle. Directed trust, reciprocity balance, encounters, and
timestamps use numeric arrays; released rows are recycled deterministically.
Reads apply decay without changing stored state, and a full row evicts contacts
deterministically. Total memory is bounded by population times configured
contacts rather than by all possible pairs.

### `src.simulation.world`

The world stores resources in flat arrays and maps occupied cells to agent IDs.
Neighborhood queries therefore depend on perception radius and local density,
not total population.

World layers store terrain, country, food capacity, annual productivity,
seasonal amplitude/phase, material capacity, and occupancy separately. Food
renewal scales with carrying capacity, remaining ecological room, elapsed
years, and the current latitude season. Materials are nonrenewable by default.
Harvest and renewal flows are per-tick observer metrics. Agent-held stocks,
consumption, spoilage, construction/research use, and inventory lost on death
are also recorded, allowing per-tick stock-flow balance checks without feeding
those measurements back into behavior. The default world is bounded; wrapping
remains a configurable experiment.

Sea cells cannot be entered by ordinary movement. Seafaring is not globally
unlocked: an individual must experiment at a coast, spend energy and material,
accumulate enough research, and construct a vessel. Knowledge can then spread
through local teaching. Vessels have durability and sea movement has a higher
energy cost.

### `src.simulation.engine`

One `Simulation` owns all mutable state, including its pseudorandom generator.
A tick has seven phases:

1. Reset interval flow counters and advance local infection stages/exposure.
2. Advance body condition, development, metabolism, gestation, frailty, and
   mortality; remove deaths through indexed cleanup.
3. Advance pregnancies and births, then rebuild the spatial index.
4. Let each living agent select one action from bounded local information.
5. Match disjoint pairs among local agents who independently chose
   reproductive intent, then resolve all actions with authoritative locality
   and resource checks.
6. Regenerate environmental resources from productivity and season.
7. Rebuild occupancy and sample observer metrics when configured.

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
- Relationship memory is a central fixed-width numeric store.
- Cross-agent effects occur during an explicit resolution phase.
- Spatial interaction and attention are bounded and partitionable.
- Disease uses an ephemeral cell-pressure layer rather than pairwise contact
  objects.
- Guardian cleanup uses a reverse dependent index rather than scanning the
  population for every death.
- Rendering and event persistence are optional consumers.
- The simulation never uses wall-clock time for causal state.
- The in-memory event and metrics histories are bounded; a caller can stream
  either through a sink.
- UI snapshots are versioned and columnar, avoiding an API tied to Python
  objects.
- Decision random streams are keyed per tick and agent, so brain evaluation can
  later be parallelized without changing unrelated decisions.

Snapshot schema 3 declares `snapshot_kind: visualization` and includes the
configuration, seed, model/genome versions, action preference order, ecology
layers, expressed phenotype and causal agent columns, pregnancies, and
relationship edges. It is not a resumable checkpoint: the global resolver RNG
state and some allocation details remain intentionally absent. Large UI
consumers can omit world, agent, or relationship payloads instead of
serializing every edge on every frame.

Do not assign one operating-system process or container to every agent. If a
single process becomes insufficient, partition spatial regions into a modest
number of workers and exchange boundary actions between ticks.

### Native-code boundary

C is useful at a measured, stable hot loop. Current profiling at ten thousand
agents identifies bounded neighbor evaluation and action scoring—not scenario
parsing or the UI API—as the dominant Python work. Packed genomes are two
integers per agent; terrain, resources, and relationships already use flat
numeric storage; cross-agent effects use IDs and explicit phases. A C, Cython,
Rust, or NumPy-backed decision kernel can therefore sit behind `Simulation`
while the readable Python engine remains the behavioral reference.

Every future native backend must pass the same deterministic, parity, and
invariant tests as the reference engine. Native acceleration should preserve
the scenario JSON and snapshot schema rather than create a second model.

## Measuring emergence

Scaling population alone also changes density unless world area is scaled with
it. Experiments should distinguish:

- Population scaling at constant world size.
- Population scaling at constant density.
- Increasing interaction radius at constant population.
- Resource abundance and regeneration changes.
- Trait diversity and mutation changes.

Metrics currently include population, age bands, births, deaths by cause,
world and agent-held food/material stock, transfer/source/sink flows, seasonal
productivity, energy, body condition,
development, health fraction, frailty, disease compartments, action
attempt/success/failure and entropy, remembered and recently active
relationship degree/trust, beliefs,
country occupancy, brain mechanisms, population genetic diversity,
pregnancies, seafaring knowledge, vessels, inventions, and landfalls. New
hypotheses should normally add an observer metric before adding a new agent
rule.

Stock values are instantaneous; flow values describe the most recently
completed tick. A run that needs a continuous conservation ledger should set
`metrics_interval=1` or call `measure()` after every step. Sparse metrics
history does not silently reinterpret one sampled tick as the whole sampling
interval.

Useful future observer metrics include network clustering, spatial
segregation, lineage diversity, trait distributions, resource inequality,
specialization, mobility, and survival curves.

## Near-term extension order

1. Add a UI/service adapter around scenario loading, stepping, viewport
   snapshots, and parameter validation.
2. Separate lightweight visualization snapshots from full resumable
   checkpoints and persist experiment streams with the code revision.
3. Add spatially coherent climate/biome layers and additional resource types
   only where they create distinct ecological niches.
4. Introduce production and exchange from physical inventories.
5. Add resource-grounded taking or conflict only after relationship harm,
   reputation, and injury consequences exist.
6. Derive groups and institutions from persistent relationships and collective
   action.

This order builds causal layers. Markets should follow production and exchange;
institutions should follow relationships and collective decisions; country
statistics should be measurements of those structures rather than initial
conditions.
