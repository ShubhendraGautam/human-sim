# Design checklist

Four directions are open at once: make the world legible, put more than
people in it, let minds change themselves, and make the world large enough to
contain distinct niches. Each is large enough to wander in. This document is
the map — what each one means concretely, what has to be true before it is
allowed in, and the single order they land in.

It is a living plan. When an item ships, check it and record what was
measured. When an item is rejected, leave it here with the reason.

Mechanisms that are built but not yet settled run through the ordered,
reproducible queue in [experiments/README.md](experiments/README.md). Evidence
from an earlier item decides whether the next mechanism stays off, changes, or
becomes the next implementation dependency.

## Gates every item clears

These are not ceremony. Each one is a way a previous change could have gone
wrong and did not.

- [ ] **The five questions.** What can an agent locally observe, what does the
  action cost, what state does it change, could the outcome be a metric
  instead, and can its effect be compared across seeds and scales?
  (`docs/architecture.md`.) An item that fails question four is a metric.
- [ ] **An off switch that reproduces the past.** Every mechanism ships with a
  config value at which `state_digest()` matches the pre-change baseline
  byte-for-byte across a spread of seeds. This proved the entity registry and
  death records were mechanically inert, and it is what makes a suspicious
  result debuggable rather than a mystery.
- [ ] **A named cost before building, a measured cost after.** Alternate the
  two arms and prefer the minimum; this machine varies by up to 2x between
  identical runs. Reference point: 2,000 people is ~250 ms/tick, `_decide` is
  ~70% of it.
- [ ] **Observation never feeds back.** New state is readable by
  `src.simulation.observation` and by nothing that decides.
- [ ] **A metric before a rule.** If the hypothesis can be tested by measuring
  the existing model, measure first.
- [ ] **Dependencies.** The simulation core stays free of third-party runtime
  dependencies; CI enforces this. UI additions are vendored into the repo with
  a permissive licence — never fetched at runtime.
- [ ] **Versions.** `MODEL_VERSION` when mechanics change at the default
  config, `CONFIG_SCHEMA_VERSION` for new parameters,
  `SNAPSHOT_SCHEMA_VERSION` for frame shape.

## Track A — Legibility

The map currently shows coloured cells and dots. That is honest but unreadable:
nothing tells you at a glance that a place is wooded, quarried, or built on.

**A0 is the rule the whole track hangs on.** A sprite is a *reading* of
measurable properties, never a stored type. The registry knows something is an
artifact; it must never learn that the artifact is a house. The renderer maps
`(kind, measurable properties) → glyph`: something with high insulation and
occupancy draws as a dwelling because that is what it does. The moment the
renderer wants a `type: "house"` field, the engine has been asked to hardcode a
label and the design is wrong.

- [x] **A1 Asset sourcing.** *(done — but not as written.)* The plan said CC0
  tiles from a pack; the glyphs are instead vector paths painted once into an
  offscreen atlas at startup. Three reasons decided it: a person has to be
  tinted to a palette colour that carries meaning, which a raster tile cannot
  do without a second image per colour; the atlas costs about 7 kB of code
  and no binary assets; and it renders identically offline with no attribution
  ledger. The seam is kept honest — the atlas is blitted with `drawImage`
  exactly as a bitmap sheet would be, so swapping in a licensed CC0 pack means
  replacing the painting functions and nothing else. **Revisit if the drawn
  glyphs do not look good enough**; that is a judgement about appearance, and
  appearance is the point of this track.
- [x] **A2 Draw path.** *(done.)* One atlas, `drawImage` onto the existing
  canvas, no DOM node per entity. People are bucketed by colour so each tint
  is one cached sprite.
- [x] **A3 Level of detail.** *(done — four tiers.)* Density below ~1.6 px per
  cell, dots to 4.5, plain glyphs to 11, sprites above.

  One correction to what this document previously claimed. I wrote that
  "sprite cost is bounded by screen area, not world size" as though culling
  delivered it. Culling does not: zoom multiplies fit-to-screen, so a
  4096-cell world at rest is *entirely* visible with over a million cells in
  front of the viewer. What actually bounds sprite cost is the tier — sprites
  need an 11 px cell, and few of those fit on a screen. Below sprite tier a
  draw budget samples every nth cell instead. Both are pinned by tests, since
  the reasoning was wrong once already.
- [x] **A4 Drawable today, without any engine change.** *(done.)* Textured
  terrain with a marked coastline, greenery from the food layer, stone from
  the material layer, people as figures, hulls as boats, disease and selection
  rings that follow whatever tier a person is drawn at.
- [x] **A5 Drawable only after Track B.** *Shipped for structures and fauna.*
  Animals read the fauna register. Built objects read the artifact register,
  and their cached glyph variants are selected from insulation, stored food,
  occupancy, and durability. There is still no `house` field: a roof-like
  glyph is the renderer's reading of high insulation, not an engine label.

  Greenery moved out of this item and into A4 on a distinction worth keeping:
  drawing the *food layer* as plants is a reading of a quantity the engine
  already has, not an invented entity. When flora become real the renderer
  reads the register instead — a change of source, not of category.
- [x] **A5b Say what happened, not just what is.** *(done, unplanned.)* The
  map showed a world's state and nothing of its history, so a run read as
  drifting dots. The engine's event log is now served and shown as a filtered
  notification feed, and a dead person gets a life summary. This was missing
  from the original checklist entirely: most of what makes a world legible is
  not what gets drawn but what gets *narrated*, and nearly all of it was
  already recorded and simply never read.
- [x] **A6 The legend stays authoritative.** *(done.)* The layer panel names
  what each glyph is drawn from and states plainly that nothing has been
  planted or built.
- [ ] **A7 Tests.** *(partly done — 17 new UI tests.)* Detail tiers, draw
  budget, cell noise stability and culling bounds are pinned as pure
  functions. Still missing: an atlas coverage test and a build assertion that
  no asset is fetched from a remote host — both need a DOM/canvas test
  environment, which this UI does not yet have.

## Track B — A world with more than people

The substrate is already in: one identity space, `EntityKind` of `PERSON`,
`FAUNA`, `FLORA`, `ARTIFACT`, a kind-bucketed spatial index, and provenance
that outlives a creator. What is missing is that only `PERSON` has behaviour.

Each new kind answers the same five questions as any other addition. A kind
that cannot answer them is scenery.

- [x] **B1 Environmental exposure.** *Shipped.* The season an agent already
  senses now has a physical cost as well as an ecological one. Distance from
  the local annual midpoint costs energy for thermoregulation, symmetrically
  in hot and cold extremes. This is a local scalar read, changes embodied
  energy, and creates no prescribed response: moving, eating the cost, and
  eventually building insulation can compete through the existing utility
  machinery.

  The formula takes insulation as a measurable fraction and knows no structure
  labels. It clamps overlapping protection so insulation cannot create energy;
  B2 now supplies that fraction through one narrow seam:
  `(local season, insulation) -> energy cost`. With
  `environmental_energy_cost_per_year=0`, golden pre-change
  `state_digest()` hashes match byte-for-byte across three seeds.

  **Measured.** At the default strength, the first simulated year charged
  1.02 energy per person, about 8.5% of mean basal metabolism. Six paired
  seeds after 20 years finished at 330.2 people without the cost and 331.2
  with it — no population effect distinguishable from seed noise — while
  mean energy moved 89.39 to 88.77 and body condition 0.881 to 0.875. The
  direct physiological signal is present without claiming an unsupported
  demographic outcome. Alternating the arms measured 105.41 versus
  106.03 ms/tick (1.006x); the cost is below ordinary timing noise and far
  inside the 2x Track B budget.
- [x] **B2 Artifacts.** *Shipped.* A build action competes in the existing
  utility machinery, spends held material and energy, and registers an inert
  object with creator provenance that survives its maker. Objects carry only
  measurable properties: condition, insulation, food capacity, and occupancy
  capacity. Local occupants share insulation; overcrowding dilutes it. Gather
  can put overflow into local capacity and eat can draw it back out.

  Condition falls each year. The same build action repairs the most damaged
  local object at a smaller material and energy price; without repair the
  object deregisters and any food it held is recorded as a loss. Current
  occupancy is derived from the person index and never stored on the object.

  The action was appended without invalidating the control. With
  `artifacts_enabled=false`, brains retain the old output width and golden
  pre-change digests match across three seeds. In the treatment, the new
  founder output row uses an independent keyed stream, so both arms begin
  with identical bodies, positions, roles, genomes, and all legacy neural
  weights.

  **Measured.** Six paired seeds, 60 founders on 24x24 land after ten years:
  the artifact arm held 31.7 objects and sheltered 9.8 current occupants on
  average. Mean energy moved 88.62 to 89.15 and body condition 0.873 to 0.877;
  population moved 88.8 to 85.7, a mixed short-horizon trade rather than an
  asserted benefit. At equal starting population the arm adds 120 profiler
  calls per tick (0.46%); alternating wall-clock arms could not resolve a
  slowdown (35.94 vs 34.81 ms median), well inside the Track B budget.
- [ ] **B3 Climate and biome layers.** Spatially coherent, and added only
  where they create distinct ecological niches. A second resource that behaves
  like the first is a rename. Resources are distinguished by **renewal
  regime** rather than by name: renewing at a rate tied to ecological room
  (food today), renewing far more slowly than a lifetime, or not at all
  (materials today). A resource earns its place by making somewhere worth
  going and somewhere worth leaving.

  **Entry slice after D2:** add deterministic, spatially coherent temperature
  and moisture layers, then derive local seasonal exposure and food renewal
  from those physical values. A biome name may be an observer label, never an
  engine branch. Agents initially sense only the consequences they already
  can observe — season, resource yield, and embodied cost. The disabled path
  must reproduce the current world arrays and digest exactly. A second carried
  resource waits until it has a renewal regime and action trade-off that food
  and material do not already express.
- [ ] **B4 Flora.** Plants must *replace* the food renewal formula, not sit
  beside it. Acceptance: with flora off, food renews as it does today; with
  flora on, food exists where plants are, and clearing an area has
  consequences that outlast the tick. Anything less makes a tree decoration.
- [x] **B5 Fauna.** *Shipped.* `src.simulation.fauna` holds grazing animals
  as registered `FAUNA` entities on a cheap fixed policy — each reads only its
  own cell and four neighbours, never `_decide`. They draw on the same food
  layer people harvest, and carry energy that a hunter recovers as food, so a
  herd is competition and larder without either being a rule about people.
  Vigilance and fecundity are heritable and mutate.

  Measured: intake had to fall away as a patch empties. Without that response
  the herd flattened the world to 3% of capacity and held it there — growth
  in `world` is a share of the *deficit*, so bare ground regrows fastest and
  an unrestrained grazer sits on top of maximum regrowth taking all of it.
  With the response, two seeds ran 600 ticks with the herd oscillating
  between roughly 1,500 and 3,500, resources holding at 45–78%, and the human
  population growing alongside it.

  **Not done:** fauna do *not* yet retire `environmental_exposure_rate_per_year`.
  Animals exist but are not disease reservoirs, so the standing hazard is
  still doing that job and this item is only half discharged.

  **Not done:** there is no spawner and none is wanted. Overhunting to
  extinction is reachable and observed: `configs/scarcity.json` puts 400
  people on a 24x24 map and the herd is gone inside five years. Whether the
  same happens eventually under the *default* configuration is not settled —
  runs to tick 900 show the herd suppressed from ~900 to ~400 as the human
  population passes 1,000, which is a trend and not yet an answer.

- [ ] **B6 The update budget.** The keystone of this track. **Not every
  registered entity gets a per-tick decision.** Three tiers: per-cell
  aggregate (flora), cheap fixed policy (fauna), full decision (people).
  Plants and animals could outnumber people ten to one; if they enter through
  `_decide` the tick dies. Budget: all of Track B stays within 2x the
  person-only tick at equal population, or it becomes a native-kernel
  conversation rather than more Python.

  *Fauna arm measured.* Animals run on a fixed policy and never enter
  `_decide`. At 1,225 people, a ~300-animal herd cost 1.17x the person-only
  tick. Absolute per-tick numbers from that run are not comparable to the
  reference in `architecture.md` — the machine was running several
  simulations at once — but both arms paid the same tax and the ratio is
  what the gate asks for. The item stays open until flora are in, since the
  budget is for all of Track B rather than one kind of it.
- [ ] **B7 Invariants and digest.** *Complete for fauna and artifacts; waits
  for flora.* Artifact identity, provenance, placement, physical bounds,
  storage bounds, action width, digest, checkpoint, and stock flows are
  pinned. The item remains open because B4 has not supplied the final kind.

## Track C — Minds that change themselves

Today `BrainKind` is genetic and `BrainState` is a bounded per-lifetime
preference vector that is never inherited. So *how you think* is inherited and
*what you learned* dies with you. Nothing a person works out can outlive them
except through culture labels and teaching.

For "societies thinking how to go above and beyond" to mean anything, a mind
has to be able to change data it holds, pass that change on, and be measurably
better for it.

Four failure modes to design against, named now so they are not discovered as
disappointments later:

1. **Free lunch.** Self-modification with no cost is strictly dominant.
   Changing your own mind must cost energy and time and compete with eating.
2. **Outcome hardcoding.** "Unlock planning at tech level 5" is the exact
   thing this project refuses. A brain change is a mutation of data the agent
   already holds, or it is not a brain change.
3. **Convergence.** If everyone finds the same policy, the world has one
   problem, not many. That is a Track B deficiency surfacing as a Track C
   result — diagnose it there.
4. **Unbounded cost and lost determinism.** Fixed opcode set, fixed node
   budget, evaluation on the existing per-agent keyed random stream.

Level 2 is the committed destination. Level 1 is therefore built as its
substrate rather than as a place to stop.

- [x] **C1a Inherited networks.** *(done — neuroevolution, not training.)*
  Every person carries a small network — twenty-one local senses, a handful of
  hidden units, one score per action — whose output shifts action preference.
  It is never trained: there is no loss, no gradient and no target behaviour
  anywhere in it. Children get a per-weight recombination of their parents'
  weights, fixed at conception like the genome, with bounded mutation. What
  survives is whatever was survived with.

  This is the C1 substrate arriving as a network rather than a flat vector,
  which is strictly more general and keeps the same guarantees: deterministic,
  no third-party dependency, fixed cost per decision. Measured cost is +27%
  per tick at ~890 people (185 ms to 236 ms), which is the population trade
  accepted up front.

  Two things it deliberately cannot do. It never invents, hides, or forces an
  action — it biases scores, and the world's locality and resource checks
  still refuse whatever they would have refused. And it sees only the senses
  in `brain.sense`; a network that could read the population total would be
  consulting the observer's notes instead of its own body.

  **Not yet demonstrated: that it evolves anything.** Over 60 simulated years
  a run reaches only 4 generations, and mean weight magnitude moved 0.0953 to
  0.0970 — a drift indistinguishable from noise. Neuroevolution needs
  generations, not years, and the honest state is that the mechanism is in
  place and the selection signal is unmeasured. What it needs is either far
  longer runs or a scenario with sharper mortality, and a metric for weight
  magnitude and policy diversity over lineages.

- [x] **C1b Lifetime plasticity.** *Built, measured, and shipped **off**.*
  A reward-modulated update on the output layer, using the outcome signal
  `BrainState` already receives, credited to the hidden units that were
  active when the choice was made. It costs energy, so changing your own
  mind competes with eating and failure mode 1 is closed by construction.

  The learned overlay lives on `BrainState`, not on the network. That is
  the Weismann barrier for minds: `BrainState` is created fresh for every
  child and is never an input to `neural.inherit`, so lifetime experience
  cannot become heritable by accident. A test maxes out a parent's overlay
  and asserts the identical recombination comes out unchanged.

  **The signal had to be an advantage, not a reward.** Reinforcing the raw
  outcome sounds equivalent and is not. Almost every action returns
  something, so raw reward pushes every frequently-taken action upward and
  the brain entrenches whatever it already did most — self-confirmation
  rather than learning. Measured over six seeds in a scarce world that arm
  finished at 73.7 people against 82.0 for inherited weights alone and 75.3
  for no brain at all: worse than having no brain. Subtracting the running
  average the habit vector already keeps restores it to learning.

  **C5 is not satisfied, and this is recorded rather than tuned away.**
  With the advantage signal, six seeds x 400 ticks in the scarce world:

  | arm | population | sd |
  | --- | --- | --- |
  | no brain | 75.3 | 7.2 |
  | inherited only | 82.0 | 6.1 |
  | + plasticity | 79.0 | 6.8 |
  | + place memory | 81.2 | 3.8 |

  The gain over having no brain at all is real and belongs to **perception
  and audibility** (C1c), not to lifetime learning. Plasticity and place
  memory together land at 81.2 against 82.0 for inherited weights alone —
  indistinguishable, which is exactly the condition C5 says makes a feature
  decoration. Place memory does halve the between-seed spread (6.1 to 3.8),
  which is a real effect on reliability rather than on the mean, and is the
  one thing here worth following up.

  **Cost, attributed.** At ~700 people, against minds fully off:

  | arm | ms/tick | ratio |
  | --- | --- | --- |
  | minds off | 164.4 | — |
  | perception only | 199.7 | 1.21x |
  | + place memory | 197.5 | 1.20x |
  | + plasticity | 202.2 | 1.23x |

  Nearly the whole price is perception — seven extra senses widen the hidden
  layer by half again, and two of them are bounded spatial queries per agent
  per tick. Place memory is free within measurement noise and plasticity
  costs about two percent. So the expensive part is the part that pays and
  the cheap part is the part that does not, which is an awkward result but
  the one the numbers give.

  (`is_coast` was recomputing four neighbour lookups per asking. Terrain
  never changes during a run, so it is now a mask built once at world
  construction; that alone took the total from 1.31x to 1.23x.)

  **Is it the price or the rule?** Both, and the rule more. Six seeds at 600
  ticks:

  | arm | population |
  | --- | --- |
  | no learning | 23.7 |
  | learning, costed (rate 0.5) | 17.8 |
  | learning, free (rate 0.5) | 21.7 |
  | learning, free (rate 1.0) | 18.8 |

  Waiving the price recovers about half the loss and still does not beat not
  learning. The energy cost cannot explain the rest — 0.02 per action over a
  life is about two percent of lifetime energy, not a quarter of the
  population — so the remainder is behavioural.

  The last row is the informative one: **doubling the learning rate makes it
  worse**, a dose-response in the wrong direction. That is the signature of
  a mechanism adding variance rather than signal. A single-sample advantage
  estimate in a world this stochastic is mostly noise, and
  `neural_output_weight` faithfully amplifies it into the decision. Fixing
  that means averaging evidence over more than one outcome before acting on
  it — eligibility traces, or a slower second-order estimate — which is a
  design change rather than a tuning pass and is not attempted here.

  **Decision: `plasticity_rate` defaults to 0.0.** The mechanism, its off
  switch and its twenty-five tests stay. C5 says a feature that cannot be
  distinguished from its absence is decoration and gets removed rather than
  tuned; this one *could* be distinguished, in the wrong direction, which is
  a stronger reason not to ship it on.

  Two readings remain open and are not settled by this data. C4 says a
  better brain in a world with thirteen actions and no artifacts just
  performs the same thirteen actions slightly better — so this may be a
  Track B deficiency surfacing as a Track C result, which is failure mode 3
  and is diagnosed *there*, not here. And 400 ticks is about 33 years, so
  the horizon may simply be short. Neither is accepted as a reason to ship
  the feature on, and the useful next question is what has to become true
  about the world before lifetime learning starts paying.

- [x] **C1c Perception.** *Shipped.* Thirteen of the network's fourteen
  senses were the body reporting on itself; the only outward one was a
  neighbour count. A brain could feel hungry but could not perceive that the
  ground was bare, that it was better one step over, that winter was coming,
  or that an animal was within reach — so every one of those judgements had
  to be supplied by a constant in the config, which is precisely the
  hardcoding this project refuses. Seven world senses were added, all values
  the deciding code already computes and passes in.

  Related and measured: the network was inaudible. Its whole output came to
  about 0.05 utility units against a `decision_noise` of 0.20 and a
  `gather_weight` of 2.4 — quieter than the dice. On/off runs over five
  seeds were indistinguishable (438.6 against 447.8, brains-off nominally
  ahead), which is C5's kill criterion being met by the *old* arrangement.
  `neural_output_weight` was raised so a brain that has learned something
  can be heard.

- [x] **C1d Place memory.** *Shipped.* A bounded, fading store of cells that
  paid out, written only where the agent stood and took something from the
  ground. It feeds both a sense and a movement option, so returning to a
  remembered place is a choice weighed against the others rather than a
  behaviour. Before it, movement was pure local gradient: an agent could not
  hold the thought that there was food over the ridge last spring.

- [x] **C1e Recurrent neural memory.** *Built; experimental and off by
  default.* The inherited network now has an optional hidden-to-hidden matrix,
  so its previous activation can change its next response to otherwise
  identical senses. This is a real increase in representational power rather
  than more copies of the same unit: lineages can evolve history-dependent
  policies while evaluation remains bounded by the configured unit ceiling.

  Recurrent weights are inherited, recombined, and mutated. Recurrent state is
  held on `BrainState`, is never passed to `neural.inherit`, and starts empty
  in every child. Founder recurrent weights use a deterministic stream keyed
  independently of founder construction, so a `neural_recurrence_weight=0`
  control and a recurrent arm begin with the same genomes, positions, bodies,
  and reproductive roles. The default is zero until a long-horizon run shows
  that temporal memory improves something selection can retain.

- [ ] **C1 Level 1 — a weight vector that is heritable, learnable, and
  teachable.** *Transmission substrate built; evidence remains.* Inheritance
  is supplied by the network and lifetime change by its plastic output
  overlay. Cultural transmission is now present behind an off switch.

  A teaching action blends the teacher's effective output policy into the
  learner's lifetime overlay; it never rewrites the learner's inherited
  network, so cultural transmission cannot become genetic inheritance by
  accident. Policy copying is neutral at the moment of transfer: unlike
  receiving a concrete technique, it grants no fixed social benefit, trust,
  welfare, cultural-trait, reproductive, or survival bonus. The same operation
  copies opposing weight vectors without judging either one. The mechanism
  starts off. Its zero-rate switch must preserve the current digest and action
  options exactly, including for people who can already teach techniques.

  The transmission record carries the immediate teacher, the originating
  policy lineage, its hop count, and the tick. Observer metrics count living
  recipients, distinct lineages, and transmissions; the event feed records
  each transfer. This is the path C2 reuses, so C2 changes what a policy is,
  never how it moves between people.

  Acceptance: a policy can spread only through a local teaching action, all
  weights remain bounded, checkpoint restore preserves both the policy and its
  lineage, and paired runs can relate lineage spread to survival. A policy that
  spreads without improving anything is culture, but not an enabled default.
  Lineage and aggregate metrics are observer outputs only and must never enter
  scoring, copying, survival, or reproduction.
- [ ] **C2 Level 2 — small bounded programs.** Condition-to-action rules over
  local observations: fixed opcode set, a hard node budget, mutable, copyable
  by teaching, and storable in an artifact so an idea can outlive the person
  who had it. This is the real answer to going beyond, because a program can
  express something the fixed utility function cannot.
- [ ] **C2b Room to grow, without a rewrite.** The opcode set is versioned and
  extensible: adding an opcode is a `MODEL_VERSION` bump and a new
  experimental condition, never a schema migration. The node budget is
  configuration, so "how much mind can a person afford" is a question the
  model can be asked rather than a constant baked into it. Programs are stored
  and digested as data, so a later evaluator — including a native one — can
  replace the interpreter without invalidating a single saved run.
- [ ] **C3 Level 3 — a language model inside the tick. Rejected.** It ends
  determinism, scale, and the zero-dependency core in one move. The only
  acceptable form is offline and outside the simulation: a tool that helps
  author Level 2 programs a human then commits and version-controls.
- [ ] **C4 Sequencing dependency.** Ships after B2 at the earliest. With
  thirteen actions and no artifacts, a better brain just performs the same
  thirteen actions slightly better, and nothing on screen looks like progress.
  Give minds a world worth thinking about first.
- [ ] **C5 Acceptance, including the kill criterion.** Metrics for policy
  diversity, for the lineage of a policy — who taught whom — and for whether a
  policy that spread actually improved survival. If runs with self-
  modification on and off are statistically indistinguishable across seeds,
  the feature is decoration and gets removed rather than tuned.

## Track D — A world big enough to have somewhere else

A bigger world is not cosmetic. It is what keeps policies from converging:
with one climate and one resource gradient there is one best way to live, and
every mind finds it. Distinct niches are the raw material Track C needs.

The cost does not fall where intuition puts it. Drawing is safe — A3 bounds
sprite cost by screen area rather than world size. The tick is not, because
several sweeps are `O(cells)` and run every tick **whether or not anyone is
alive**. Measured on `World.regenerate` alone, population zero:

| World | Cells | Before | After D1 |
| --- | --- | --- | --- |
| 48 × 24 (today) | 1,152 | 0.75 ms | 0.21 ms |
| 160 × 120 | 19,200 | 14.1 ms | 3.1 ms |
| 512 × 512 | 262,144 | 182 ms | 42 ms |
| 1024 × 1024 | 1,048,576 | 708 ms | 164 ms |

Linear in area either way. Before D1, a 512 × 512 world spent ~150–180 ms per
tick growing food for nobody, against a whole tick of ~250 ms at 2,000 people.
Area, not population, was the budget.

`docs/architecture.md` records that NumPy was evaluated and rejected because
the decision loop is scalar-read bound, while noting vectorization stays
attractive for *large, sparsely populated worlds*. Growing the world is
exactly the condition that was named. This is the decision being revisited on
purpose, not a contradiction.

- [x] **D1 A cheaper sweep.** *(done — 3.6–4.6x at every size above.)*
  Growth is a share of the remaining deficit, so a full cell grows by nothing
  without needing a special case and a cell with no capacity stays at zero on
  its own. Sweeping by row hoists the season out of the inner expression and
  lets a row be read, grown, and written as bulk operations. Which cells are
  productive is fixed when the world is built, so the seasonal average is a
  weighted sum over rows rather than a sweep of the map.

  Verified identical: the same digests as the previous implementation across
  five configurations, including 60 simulated years at 632 people. The
  arithmetic is reassociated, so that parity is measured rather than
  structural — `tests/test_regeneration.py` keeps the old formula as a
  second opinion and checks the two agree cell by cell.

- [ ] **D1b Make the sweep track population, not area.** Still outstanding,
  and the reason it was not attempted first: the obvious fix does not work.
  An active set of cells below capacity never shrinks, because regrowth is
  asymptotic — at the default 0.18/year a cell harvested once takes roughly
  200 simulated years to come back within a float of full, so every cell a
  person has ever touched stays in the set for the length of most runs.
  Sublinear regeneration needs deferred evaluation: cells caught up on access
  rather than every tick. That is exact for the cells themselves, but the
  flow ledger wants a world total every tick, which is what makes it real
  work rather than a tweak.
- [ ] **D2 Scale population with area, deliberately.** A larger world at the
  same population is a sparser one: fewer encounters, failed mating, disease
  that cannot sustain itself. Growing the map without growing the people is a
  different experiment, not the same one bigger. Both arms get measured.

  **Size is the caller's choice and is not capped.** Anyone running a model
  is responsible for knowing what their machine can do, and a guard rail that
  refuses a large world is worse than a run that fails: it substitutes our
  guess about someone else's hardware for their own. The obligation this
  creates is to make the cost *visible* — a world's per-tick cost should be
  reportable before a long run is committed to — not to prevent the choice.

  **Prepared.** Both outcome and timing harnesses accept an explicit world
  matrix. The first comparison crosses 200 and 800 founders with 64x64 and
  128x128 worlds: 200/128x128 isolates sparsity, while 800/128x128 restores
  the current founder density. B3 starts only after this reports encounter,
  reproduction, disease, population, and per-tick consequences rather than
  assuming that a larger canvas is the same simulation enlarged.
- [ ] **D3 Then, and only then, the native kernel.** D2 pushes on `_decide`,
  which is ~70% of a tick and the thing pure-Python tuning has already given
  up about 1.15x on. This is where a C, Rust, or array-backed decision kernel
  behind `Simulation` earns its complexity — against the same determinism,
  parity, and invariant tests as the reference engine.
- [ ] **D4 Renewable and finite, together.** Limited land with some renewing
  resources and some not is what makes a place worth settling and worth
  exhausting. The regimes already exist in embryo — food renews against
  ecological room, materials do not by default. B3 makes the distinction
  deliberate rather than incidental.

## The order

The four tracks interleave into one sequence. Dependencies, not preference,
decide it.

1. ~~**D1** a cheaper per-cell sweep.~~ **Done.** 3.6–4.6x, digest-identical.
2. ~~Separate lightweight visualization snapshots from resumable checkpoints,
   and persist experiment streams with the code revision.~~ **Done.** The
   checkpoint is a safe JSON causal-state contract, not a renamed visual
   projection: RNG state, entity identity allocation, relationship slots,
   mutable world layers, pregnancies, histories, and brain lifetime state all
   round-trip. A restored run matches the original digest and future
   trajectory. Service-owned files are replaced atomically, autosaved every
   120 ticks, written on clean shutdown, and restored paused. Experiment
   records carry the code revision.

   Measured at 199 people and 32 animals after one simulated year: 1.34 MB
   of JSON, about 8 ms to project causal state and 44 ms to serialize, fsync,
   and atomically replace it. At the default cadence that is roughly
   0.43 ms amortized per tick; the save itself remains an occasional
   observer pause rather than work charged every tick.
3. ~~**A1–A4, A6** — sprite substrate for what already exists.~~ **Done.**
   A7 is partly done; it needs a DOM test environment to finish.
4. ~~**B1** environmental exposure.~~ **Done.** Seasonal distance from a
   local annual midpoint now charges embodied energy, and artifact insulation
   reduces that pressure through an effect-defined interface.
5. ~~**B2** artifacts, with **A5** drawing them.~~ **Done.** Objects are
   effect-defined, maintained or decayed, checkpointed, and visible.
6. **C1** level 1 brains, built as C2's substrate.
7. **D2** grow the world and its population together; **B3** climate and biome
   layers give the new space distinct niches and renewal regimes.
8. **B4** flora, with **A5** drawing trees.
9. ~~**B5** fauna.~~ **Mechanics done; reservoir work remains.** Animals graze,
   reproduce, mutate, compete with people for food, and can be hunted. After
   flora lands, make living fauna the disease reservoir and retire the
   standing environmental hazard.
10. **D3** the native decision kernel, once D2 has proven where the tick
    actually goes.
11. **C2** and **C2b** level 2 brains.
12. Production and exchange from physical inventories.
13. Resource-grounded taking or conflict, only after relationship harm,
    reputation, and injury consequences exist.
14. Groups and institutions derived from persistent relationships and
    collective action.

## Decisions taken

- **Assets: CC0, and performance outranks appearance.** The licence question
  was settled by not mattering much; the binding constraint is that art must
  never cost a frame at full scale. A3's aggregate tier is what delivers that,
  and it means the map is mostly density and dots when the world is large —
  by design, not as a shortcoming.
- **Brains: committed to Level 2, with room beyond it.** C1 is a stepping
  stone, so its transmission machinery is designed for programs from the
  start. C2b keeps the opcode set extensible and the node budget configurable
  so later ambition costs a version bump rather than a rewrite.
- **World: grow it; limited land, some resources renewing.** This promoted
  scale from a caveat to Track D and revived the vectorization question that
  `architecture.md` had closed. D1 comes first because a 512 × 512 world
  currently spends 151 ms per tick growing food for nobody.

- **Sizing is the caller's, not ours.** No caps, no refusals; a world too big
  for the machine is allowed to fail. What we owe is a legible cost, so the
  choice is informed — see D2.

## Still open

- **Which niches?** B3 is only worth building if the biomes differ in ways a
  policy can exploit differently. The specific axes — temperature, water,
  growing season, material richness — are unchosen, and choosing badly gives a
  bigger world with one best way to live.
