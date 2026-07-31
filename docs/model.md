# What the model contains

Every mechanism Human-Sim simulates, and the limits on each. This is the
detail behind the summary in the [README](../README.md); it is kept here so
the README can stay short and this can stay complete.

## Current model

Every run contains:

- One identity space for everything that occupies the world. Living things
  register themselves and deregister when they die; inert things are
  registered by whatever made them and keep that provenance after the maker
  is gone. People and animals are both present in it.
- A bounded, optionally wrapping world with heterogeneous carrying capacity,
  capacity-scaled productivity, latitude-driven seasons, food spoilage,
  nonrenewable materials by default, and user-defined land and sea.
- Environmental exposure grounded in that same local season. Both hot and
  cold departures from a row's annual midpoint charge thermoregulation energy,
  so season affects bodies as well as food. The formula already accepts
  bounded insulation as a physical input for future artifacts without naming
  any structure. Set `environmental_energy_cost_per_year` to zero to reproduce
  the pre-exposure model exactly.
- Material-built inert objects whose engine state is condition, insulation,
  food capacity, occupancy capacity, and stored food—not a structure type.
  Construction and repair cost material and energy; condition decays, stored
  food spoils, and an object that reaches zero condition disappears with its
  remaining stock recorded as a loss. Current local occupancy determines how
  far insulation stretches. Set `artifacts_enabled=false` to restore the
  pre-artifact action space and trajectory exactly.
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
- Bounded recurrent neural memory, present and **off by default**
  (`neural_recurrence_weight`). When enabled, the hidden state from one
  decision feeds the next through inherited, recombined, mutable connections.
  This lets identical current surroundings produce different preferences
  after different recent experience. Only the weights are inherited; the
  activation state lives in `BrainState` and every child starts empty.
  Founder recurrent weights come from a separate deterministic stream, so an
  on/off comparison does not silently receive different bodies or locations.
- A bounded, fading memory of places that paid out, so foraging can be a
  return to somewhere known rather than a walk uphill. Recorded only where
  someone stood and took something from the ground.
- A metabolic price for a brain, present and **off by default**
  (`neural_maintenance_cost`). Energy per year per unit of mean absolute
  inherited weight, charged on what a person was born with rather than on
  what they learned, which pays its own price at the moment of learning. It
  exists because of a measurement: mean network magnitude climbs from 0.106
  to 0.148 over 1500 years *identically* whether or not the network is
  allowed to influence a decision, so mutation inflates it and nothing pushes
  back. A brain that is free has no reason to be small, and its size is a
  random walk rather than a trade-off. In living things neural tissue is
  among the most expensive to run, and that expense is what makes brain size
  something evolution decides. Whether charging for it helps a population is
  unmeasured; the default is zero until it is.
- Lifetime plasticity, present and **off by default**. A learned adjustment
  to the inherited network, moved by how much better an action went than that
  action usually goes, credited to the parts of the brain that were active
  when the choice was made, costing energy, and dying with the person rather
  than passing to their children. It is off because it measured worse than
  not learning—23.7 people against 17.8 over six seeds, and still 21.7 with
  the energy price removed. The mechanism is correct and tested; what is
  unproven is that this world rewards it. Raise `plasticity_rate` to
  experiment.
- Cultural policy teaching, present and **off by default**
  (`policy_teaching_rate`). A local teaching action blends the teacher's
  effective inherited-plus-learned output policy into the learner's bounded
  lifetime overlay. It never rewrites either inherited network, so culture
  cannot become genetic inheritance by accident. The state records immediate
  teacher, originating lineage, transmission hop, and tick; observer metrics
  count living recipients, represented lineages, and total transfers. At zero
  it adds no teaching options and preserves the previous trajectory exactly.
  Copying itself awards the policy no trust, welfare, or survival advantage;
  useful and harmful policies pass through the same local mechanism.
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
