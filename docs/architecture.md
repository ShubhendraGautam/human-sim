# Architecture and modeling rules

## North star

Human-Sim hardcodes mechanisms, never outcomes.

Every simulation requires axioms. In this model they are resource conservation,
metabolic cost, spatial locality, possible actions, and lifecycle constraints.
Whether the population grows, collapses, cooperates, segregates, specializes,
or forms stable structures must follow from those axioms and agent experience.

Scale supplies repeated trials; it is not itself a fitness rule. Evolution
requires variation, inheritance, and differential survival or reproduction,
all resolved through local physical and social interactions. The engine never
assigns a fitness score, rewards a lineage for becoming common, compares a
policy with a developer-authored ideal, or lets an aggregate observer metric
change an agent. Cultural copying follows the same boundary: it can move
bounded policy data between local people, but copying grants that policy no
trust, welfare, reproductive, or survival bonus. Useful, harmful, and neutral
policies are transmitted by the same mechanism; their population histories
emerge only after many carriers meet the world.

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

### `src.simulation.entities`

The world is a canvas, and everything standing on it shares one identity
space: a person, an animal, a plant, and a structure are all registered, and
an id names exactly one of them for the life of a run. Identity and placement
are common; behavior is not, and belongs with each kind.

Two rules define how something comes to exist, and are enforced at
registration rather than documented:

- A living thing registers itself and deregisters when it dies.
- An inert thing is registered by whatever made it and carries that creator's
  id for as long as it exists. Provenance outlives the creator: a structure
  still records the person who built it long after that person is dead.

Kinds are physical, never social. The registry knows something is an artifact;
it never knows the artifact is a house, a granary, or a hospital. Those are
labels a reader may apply to measurable effects — insulation, storage,
occupancy — not categories the engine simulates. A structure must therefore
earn its existence through the same utility machinery as any other action:
if nothing in the environment makes shelter pay for itself, nobody builds.

`Simulation.agents` is the registry's own person store rather than a copy of
it, so the population and the registry cannot drift apart. `Simulation.fauna`
is the same arrangement for animals. Registration and removal go through the
registry; `validate_state` checks that they did.

### `src.simulation.artifacts`

Inert objects made by people. The data model contains no social type: only
position, condition, insulation, food capacity, occupancy capacity, and held
food. Creator provenance lives in the entity registry and survives the
creator. Occupancy is a current spatial-index reading rather than stored
state; insulation is diluted when occupants exceed capacity.

Construction and maintenance share one action. Both spend embodied material
and energy; maintenance restores condition, and an unmaintained object
eventually deregisters. Gathering may place overflow into local storage and
eating may draw it back out, so capacity changes physical stock rather than a
display number. Stored food spoils under the same rule as carried food.

### `src.simulation.fauna`

Grazing animals, and the only kind besides people that the registry currently
holds. The module knows nothing about people: an animal eats, moves toward
food, breeds when fed and near another grown animal, ages, and dies. What
makes a herd matter to a population is that it draws on the same food layer
and that its bodies carry energy — both consequences of that behaviour rather
than rules about humans. Being hunted happens on the hunter's side, in the
engine.

Intake falls away as a patch empties. This is load-bearing rather than
decorative: growth in `world` is a share of the *deficit*, so bare ground is
where the world regrows fastest, and a grazer able to take the last blade
would sit on top of maximum regrowth and take all of it forever. With the
response, thin grass feeds fewer animals and the grass comes back.

Cost is the binding constraint here, because animals can outnumber people.
Every decision reads only the animal's own cell and its four neighbours, so
per-tick cost is constant per animal.

### `src.simulation.memory`

A bounded store of places a person found worth something, and when. Movement
was otherwise pure local gradient — an agent compared the cells it could see
and stepped toward the best, with no way to hold the thought that there was
food over the ridge last spring. Capacity is fixed and memories fade, because
an unbounded store would grow with how long someone lives and a memory that
never faded would send people confidently to places that no longer exist.

A place is only recorded where the agent stood and took something out of the
ground, so the store is its own experience rather than a readout of the map.
Arriving and finding it bare deletes the entry.

### `src.simulation.knowledge`

What can be learned, as a table rather than a branch. A technique is an
affordance that makes it thinkable, an amount of work, and a change to what
its carrier can do. The effects vocabulary is deliberately narrow —
multipliers on capacities the engine already has, plus one gate on open water
— so that adding a row cannot smuggle in scripted behaviour. Anything needing
genuinely new behaviour has to earn it in the engine, in the open.

Discovery and teaching in the engine are written against no technique in
particular. `Agent.knows_seafaring` survives as a view onto bit zero so the
service contract and UI keep working.

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

The world stores resources in flat arrays and maps occupied cells to entity
IDs. Neighborhood queries therefore depend on perception radius and local
density, not total population.

The index keeps one bucket per entity kind. A query for nearby people never
walks past plants or structures, so local perception costs what it costs today
however much else occupies the same cell, and a structure can never be
mistaken for a person standing there. The index is a snapshot rebuilt at fixed
points in the tick, not a live view: something that died since the last
rebuild may still be listed, and readers already tolerate that.

World layers store terrain, country, food capacity, annual productivity,
seasonal amplitude/phase, material capacity, and occupancy separately. Food
renewal scales with carrying capacity, remaining ecological room, elapsed
years, and the current latitude season. That same locally readable season has
an embodied effect: its absolute departure from the annual midpoint charges
thermoregulation energy. The formula accepts insulation as a bounded physical
input, not an artifact label, so a future structure can reduce the cost
without either layer learning what a house is. Materials are nonrenewable by
default.

`World.local_conditions()` is the organism-facing physical boundary. It
returns one immutable `LocalConditions` reading—terrain, food and capacity,
material and capacity, and season—with no species label or preferred action.
People translate it into physiology and bounded neural senses; fauna reads the
same food fraction through its cheap fixed policy. Future flora and B3 climate
fields extend this physical record rather than creating a parallel world per
kind. Equal coordinates therefore mean equal external conditions, not equal
experience or behavior.

Renewal is expressed as a share of the remaining deficit and swept a row at a
time. A full cell then grows by nothing without needing a special case, an
unproductive cell stays at zero on its own, and the season is hoisted out of
the inner expression so each row is read, grown, and written in bulk. Which
cells are productive is fixed when the world is built, so the reported
seasonal average is a weighted sum over rows rather than another sweep of the
map. The sweep remains linear in map area — cost is set by the size of the
world, not by how many people are alive in it — which is the binding
constraint on large worlds and is tracked in `docs/design-checklist.md`.
Harvest and renewal flows are per-tick observer metrics. Agent-held stocks,
consumption, spoilage, construction/research use, and inventory lost on death
are also recorded, allowing per-tick stock-flow balance checks without feeding
those measurements back into behavior. The default world is bounded; wrapping
remains a configurable experiment.

Sea cells cannot be entered by ordinary movement. Seafaring is not globally
unlocked: an individual must experiment at a coast, spend energy and material,
accumulate enough research, and construct a vessel. Knowledge can then spread
through local teaching. Sea movement has a higher energy cost.

A vessel is consumed by time at sea rather than by distance covered, because a
hull sitting on open water is as exposed as one being rowed. Nothing forbids
resting at sea; the sea is simply expensive, and the cost is what makes an
indefinite float impossible. When a hull fails, geography decides: a coast
within reach is waded to at a cost, and open water is not survivable.
Passengers ride on whoever holds the working vessel, so a dependent neither
drowns beside an intact hull nor survives one that has broken up.

### `src.simulation.engine`

One `Simulation` owns all mutable state, including its pseudorandom generator.
A tick has eight phases:

1. Reset interval flow counters and advance local infection stages/exposure.
2. Decay artifacts and their stored food; advance body condition,
   development, metabolism, insulated environmental energy cost, gestation,
   frailty, and mortality; remove deaths through indexed cleanup.
3. Advance pregnancies and births, then rebuild the spatial index.
4. Advance the herd — graze, move, breed, die — and rebuild the index again,
   so a hunter chooses against the herd as it actually stands rather than
   where it was last tick.
5. Let each living agent select one action from bounded local information.
6. Match disjoint pairs among local agents who independently chose
   reproductive intent, then resolve all actions with authoritative locality
   and resource checks.
7. Regenerate environmental resources from productivity and season.
8. Rebuild occupancy and sample observer metrics when configured.

Decisions are created from a consistent beginning-of-action-phase view.
Resolution order is randomized to prevent permanent low-ID priority while
remaining reproducible.

The engine module owns causal state only. Read-only projections live in
`src.simulation.observation`.

### Minds

Three separate things, deliberately not merged:

- **`Agent.network`** — what a person was born with. Recombined from both
  parents at conception, mutated, then fixed for life.
- **`BrainState.plastic`** — what they worked out for themselves. A learned
  adjustment to the network's output layer, moved by the outcome of each
  action and credited to the hidden units that were active when the choice
  was made, so it expresses "this action, in circumstances like these"
  rather than the context-free preference the habit vector already held.
- **`Agent.places`** — where they have been and what it was worth.

Keeping the learned overlay on `BrainState` rather than on the network is the
Weismann barrier for minds. `BrainState` is created fresh for every child and
is never an input to `neural.inherit`, so lifetime experience cannot become
heritable by accident. A test maxes out a parent's overlay and asserts the
same recombination comes out unchanged.

`brain.Surroundings` is what the world looks like from where someone is
standing. Every field is a value the deciding code already computes, passed
in rather than fetched, so a brain sees exactly what the utility rules see
and cannot acquire a spatial query nobody budgeted for. Before it existed,
thirteen of fourteen senses were the body reporting on itself: a brain could
feel hungry but could not perceive that the ground was bare, that it was
better one step over, or that winter was coming, so every one of those
judgements had to be made for it by a constant.

### `src.simulation.observation`

`measure`, `state_digest`, `snapshot`, and `validate_state` are free functions
taking a `Simulation`. `Simulation` keeps thin delegating methods, so callers
are unaffected.

Separating them makes the rule that observation never feeds back into behavior
structural rather than conventional: an observer that wanted to write state
would have to reach through its `simulation` argument, which is visible in
review. `tests/test_observation.py` pins the property directly, including the
strongest form—that observing a run cannot change its later trajectory.

This is also the seam a native or partitioned backend needs. Observation reads
broadly across agents, world, and relationships, whereas the tick phases mutate
them; keeping the two apart means an alternative backend can reimplement
stepping without reimplementing reporting.

### `src.simulation.versions`

`MODEL_VERSION` and `SNAPSHOT_SCHEMA_VERSION` live here so the engine and
observation can both declare them without importing each other. `engine`
re-exports both, so existing imports keep working.

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

### Measured cost

Performance claims here are reproducible with `sims/profile_engine.py`, which
reports build time, per-tick cost, `measure()` cost, and service projection
cost, and can emit a `cProfile` table with `--profile`.

Profiling five thousand agents confirms that bounded neighbor evaluation and
action scoring—not scenario parsing or the UI API—dominate. `_decide` accounts
for roughly 70% of a tick, `World.best_neighbor` for 13-16%, and per-agent
`random.Random` construction in `_decision_rng` for a further 8-9%.

Two caveats matter when repeating this. First, cost is spread across many small
interpreter operations rather than a single hot loop, so pure-Python tuning
yields modest gains: hoisting invariant lookups out of the neighbor loops,
caching neighborhood offsets, and sharing one per-tick agent ordering together
bought about 1.15x. Second, wall-clock measurement on a loaded machine varies by
up to 2x between identical runs; compare alternating arms and prefer the minimum
over the mean.

The remaining structural target is allocation: `_decide` constructs an `Action`
for every scored option and discards all but one. Deferring construction until
after scoring is the next profiled candidate.

Packed genomes are two integers per agent; terrain, resources, and relationships
already use flat numeric storage; cross-agent effects use IDs and explicit
phases. A C, Cython, Rust, or array-backed decision kernel can therefore sit
behind `Simulation` while the readable Python engine remains the behavioral
reference.

NumPy was evaluated for this seam and rejected for the engine. Scalar reads from
an `ndarray` cost about 3.5x an `array("d")` read, and the decision loop is
scalar-read bound, so array-backed world layers would slow the dominant path to
speed up the O(cells) sweeps that are only a few percent of a tick at typical
density. Vectorization remains attractive only for large, sparsely populated
worlds, and belongs with the native kernel rather than as a core dependency.

### Native-code boundary

C is useful at a measured, stable hot loop, and native work should begin only
after profiling identifies one.

Every future native backend must pass the same deterministic, parity, and
invariant tests as the reference engine. Native acceleration should preserve
the scenario JSON and snapshot schema rather than create a second model.

Optimization of the reference engine itself is held to a stricter rule: it must
not change results at all. A change that alters any agent decision is a new
model version and a new experimental condition, not a speedup. Verify by
capturing `state_digest()` across a spread of configurations and seeds before
the change and asserting equality afterwards; the existing determinism tests
compare one simulation against another and will not catch a uniform shift in
the random stream.

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

`docs/design-checklist.md` is the live plan: it holds this order interleaved
with interface and brain work, the acceptance gates each item must clear, and
the decisions still open. The list below is the engine-side sequence it draws
from.

1. ~~Separate lightweight visualization snapshots from full resumable
   checkpoints and persist experiment streams with the code revision.~~ Done.
2. ~~Add environmental exposure so seasons cost a body something and shelter
   has a physical pressure to answer.~~ Done.
3. ~~Add effect-defined, creator-attributed, maintained artifacts on the entity
   substrate.~~ Done.
4. Measure whether the teachable Level 1 policy substrate spreads useful
   policies and improves survival across lineages.
5. Grow world area and population together, then add spatially coherent
   climate/biome layers only where they create distinct ecological niches.
6. Add flora as the source of food renewal. Fauna mechanics already exist;
   after flora lands, make living organisms the disease reservoir and retire
   the standing environmental hazard.
7. Introduce production and exchange from physical inventories.
8. Add resource-grounded taking or conflict only after relationship harm,
   reputation, and injury consequences exist.
9. Derive groups and institutions from persistent relationships and collective
   action.

This order builds causal layers. Markets should follow production and exchange;
institutions should follow relationships and collective decisions; country
statistics should be measurements of those structures rather than initial
conditions.
