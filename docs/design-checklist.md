# Design checklist

Three directions are open at once: make the world legible, put more than
people in it, and let minds change themselves. Each is large enough to wander
in. This document is the map — what each one means concretely, what has to be
true before it is allowed in, and the single order they land in.

It is a living plan. When an item ships, check it and record what was
measured. When an item is rejected, leave it here with the reason.

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
- [ ] **A5 Drawable only after Track B.** Structures (needs artifacts) and
  animals (needs fauna). Do not fake these with decoration; a drawn house
  nobody built is exactly the block occupier this project is trying to stop
  building.

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

- [ ] **B1 Environmental exposure.** Seasons currently decide what grows, and
  nothing in the world costs a body anything for standing in it. Until it
  does, shelter cannot be necessary and any structure would be a rule invented
  to justify a sprite. This is why exposure comes first and everything
  physical waits behind it.
- [ ] **B2 Artifacts.** Built from materials by an identified creator, decay
  without maintenance, physical effects other entities read — insulation,
  storage, occupancy. No labels in the engine. A structure earns its existence
  through the same utility machinery as any other action: if nothing makes
  shelter pay for itself, nobody builds, and that is a valid result.
- [ ] **B3 Climate and biome layers.** Spatially coherent, and added only
  where they create distinct ecological niches. A second resource that behaves
  like the first is a rename. Resources are distinguished by **renewal
  regime** rather than by name: renewing at a rate tied to ecological room
  (food today), renewing far more slowly than a lifetime, or not at all
  (materials today). A resource earns its place by making somewhere worth
  going and somewhere worth leaving.
- [ ] **B4 Flora.** Plants must *replace* the food renewal formula, not sit
  beside it. Acceptance: with flora off, food renews as it does today; with
  flora on, food exists where plants are, and clearing an area has
  consequences that outlast the tick. Anything less makes a tree decoration.
- [ ] **B5 Fauna.** Cheap policies, not the human decision path. Fauna also
  retire the environmental disease hazard: that hazard exists only because the
  reservoirs — water, soil, animals — are not simulated, and it is meant to
  disappear when they are.
- [ ] **B6 The update budget.** The keystone of this track. **Not every
  registered entity gets a per-tick decision.** Three tiers: per-cell
  aggregate (flora), cheap fixed policy (fauna), full decision (people).
  Plants and animals could outnumber people ten to one; if they enter through
  `_decide` the tick dies. Budget: all of Track B stays within 2x the
  person-only tick at equal population, or it becomes a native-kernel
  conversation rather than more Python.
- [ ] **B7 Invariants and digest.** `state_digest()` covers the new kinds, and
  `validate_state` gains the invariants each kind makes possible.

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
  Every person carries a small network — fourteen local senses, a handful of
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

- [ ] **C1b Lifetime plasticity.** Inherited weights are the starting point,
  not self-modification. A brain that changes *within* a life — a
  reward-modulated update on the output layer, using the outcome signal
  `BrainState` already receives — is what makes this Track C rather than
  Track genetics. Deferred deliberately: inheritance had to be correct and
  measurable first.

- [ ] **C1 Level 1 — a weight vector that is heritable, learnable, and
  teachable.** Promote action scoring from config constants to per-agent data.
  A brain change becomes a change of weights, which can mutate at conception,
  drift with experience, and spread through the teaching and cultural channels
  that already exist. Because C2 is committed, the transmission path — how a
  policy mutates, how it is taught, how it is stored — is designed once here
  and reused, so that C2 changes only what a policy *is*, never how it moves
  between people.
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

The three tracks interleave into one sequence. Dependencies, not preference,
decide it.

1. ~~**D1** a cheaper per-cell sweep.~~ **Done.** 3.6–4.6x, digest-identical.
2. Separate lightweight visualization snapshots from resumable checkpoints,
   and persist experiment streams with the code revision. Long runs need this
   before they need anything else.
3. ~~**A1–A4, A6** — sprite substrate for what already exists.~~ **Done.**
   A7 is partly done; it needs a DOM test environment to finish.
4. **B1** environmental exposure.
5. **B2** artifacts, with **A5** drawing them.
6. **C1** level 1 brains, built as C2's substrate.
7. **D2** grow the world and its population together; **B3** climate and biome
   layers give the new space distinct niches and renewal regimes.
8. **B4** flora, with **A5** drawing trees.
9. **B5** fauna; retire the environmental disease hazard.
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
