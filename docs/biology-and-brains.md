# Biology, inheritance, and brains

This is an abstract evolutionary model, not a claim to reproduce the full
biology or psychology of real humans. Its purpose is to create causal,
heritable variation cheaply enough to study large populations.

## Separate causal layers

Each person has six kinds of state:

1. **Genome** — inherited, recombined, and occasionally mutated.
2. **Genetic potential** — biological bounds expressed from that genome.
3. **Developed physiology** — prenatal condition, childhood nutrition, body
   condition, current health, infection, and frailty.
4. **Culture** — learned norms and religion, transmitted through families and
   contact.
5. **Brain state** — preferences learned during this person's lifetime.
6. **Relationships** — bounded, asymmetric memories of particular people.

Only the genome is genetically inherited. Children begin with empty learned
preferences, fresh relationship memory, and no acquired technology. Prenatal
condition can affect a newborn's realized health without changing its genome.
This prevents nutrition, trust, or knowledge such as seafaring from appearing
genetically in the next generation.

## Genome

The genome uses two packed 64-bit haplotypes. The bits are grouped into eight
synthetic chromosomes and sixteen modeled quantitative genes, with four loci
per gene.

At conception:

- Each parent creates one gamete.
- Each synthetic chromosome independently chooses a parental copy.
- A chromosome can undergo one crossover at a configured probability.
- Each transmitted locus can independently mutate by flipping.
- The child receives one gamete from each parent.

This preserves parental variation instead of averaging every child toward the
population mean. The mutation probability is an effective simulation
parameter, not a real human per-base mutation rate.

Modeled genetic potentials include metabolism, gathering ability, fertility,
constitution, longevity, maturation, vision, learning, risk, immune response,
affiliation, and cognitive style. Several advantages increase metabolism:
greater sensory, learning, constitution, longevity, immune, fertility, and
harvesting potential all cost energy. Diversity is therefore maintained
through costs and environmental selection rather than quotas.

Country cultural settings do not automatically change genomes. Scenario
authors can explicitly supply founder genetic centers, but the default is the
same broad biological distribution everywhere.

## Reproduction

The model currently has two complementary reproductive roles: `ova` and
`sperm`. These represent only the compatibility mechanism used for conception;
they are not gender identities and do not represent the full biological
variation of real sex development.

Conception requires:

- Distinct, local, non-close-relative partners.
- Complementary reproductive roles.
- Both agents independently choosing reproductive behavior during the same
  decision phase. A bounded resolver forms disjoint pairs from local
  proposals; selecting some other action is never treated as consent.
- Age-specific fecundity rather than a permanent fertile state after maturity.
- Adequate energy, developed capacity, body condition, and current health.
- Reproduction cooldown completion.
- No current pregnancy for an ova-role person.

This separates reciprocal intent from the brittle requirement that two people
independently choose the exact same pair. Success is stochastic and depends on
both partners' fertility and current
health, chronic condition, developmental history, and age curve. A successful
conception creates a pregnancy rather than an instant child. Gestation records
only energy that the gestational parent actually pays; scheduled costs cannot
create phantom newborn reserves. Prenatal condition is weighted by elapsed
simulated years rather than observation count. Loss is a stochastic hazard
shaped by health and nutrition, with a hard low-health safety boundary. Birth
occurs only at the due tick, costs energy and health, and begins a postpartum
cooldown without shortening any longer existing cooldown.

Newborn energy is capped by recorded conception, gestation, and birth
investment. Recent ancestry is stored through grandparents, preventing
parent/child, sibling, aunt/niece, grandparent, and first-cousin pairings
without an unbounded pedigree graph. Young children travel with a local
guardian, including as bounded vessel passengers, and either living parent can
provide care. Physical capability rises continuously between dependency and
maturity instead of changing from child to adult in one tick.

The external world does not change its reading to suit the observer. A person
and an animal at one cell receive the same objective local food, material,
terrain, and season. People turn that reading into bodily exposure and neural
senses; age, condition, inherited weights, memory, and learned overlays can
therefore make the response differ. Biological maturity limits feasible work
even with neural growth off. Optional neural growth changes processing
capacity by bringing inherited hidden units online over a lifetime; it does
not invent a different temperature or food stock for a younger brain.

## Nutrition, development, and aging

Energy is immediate fuel. Body condition is an exponential history of energy
adequacy, so one missed meal differs from long deprivation. Until maturity, a
time-weighted developmental index combines prenatal and childhood condition.
It permanently affects realized health reserve, physical production, and
fecundity, while the genome remains unchanged.

Genetic lifespan is an aging scale, not a scheduled death date. Frailty begins
late in that scale and accumulates faster with age. Constitution and nutrition
modify its rate. Frailty reduces current health capacity and healing, adds
health damage, and raises a deterministic-seed stochastic mortality hazard.
Only a separate absolute maximum age remains as a simulation safety boundary.
Healing depends on body condition, is suppressed by frailty, and consumes
energy. Acute damage is applied before healing, so a terminal infection cannot
recover later in the same tick. Mixed health damage is attributed to its
largest causal contributor; death causes are observer data, not scripted
outcomes.

All continuous lifecycle rates use simulated years. Some action opportunities
remain discrete per tick, so changing `ticks_per_year` is a different temporal
resolution experiment rather than a cosmetically neutral UI setting.

## Infection

The current disease layer is one generic, calibratable SEIR-style process:
susceptible, exposed, infectious, and temporarily recovered. It is not a model
of a named disease.

- Infection enters a population two ways: founders explicitly exposed through
  global configuration or a country's starting condition, and a small
  per-person environmental hazard. The second exists because the first is a
  one-time event: with contact as the only remaining route, an outbreak that
  burns out can never return, and a sparse population whose founding seed
  fails is permanently healthy no matter how crowded it later becomes. The
  hazard stands in for reservoirs the model does not contain — water, soil,
  and animals — and disappears when those are simulated directly.
- Introductions are per person, so contact with the reservoir grows with the
  population rather than arriving as a fixed quota.
- Whether an introduction fizzles or becomes a wave is left to density. The
  reservoir decides how often infection arrives, never how far it gets.
- Infectious agents deposit pressure into a bounded neighborhood layer.
- Transmission is a hazard of local pressure and current host susceptibility.
  The two routes are independent, so surviving one still leaves the other.
- Inherited immune potential, age, body condition, and frailty affect
  susceptibility or severity.
- Infection consumes energy and damages health; it never directly deletes an
  agent.
- Recovery grants temporary immunity. Gestational infection can transmit
  vertically at a configured probability; otherwise recent maternal immunity
  can protect a newborn temporarily.

The implementation is `O(population + occupied cells)` per tick and stores only
a numeric stage and timer per agent.

## Relationships and culture

Relationships are directed: one person can trust another without the feeling
being mutual. Each agent has a row in a central fixed-capacity
structure-of-arrays store containing contact ID, trust, reciprocity balance,
encounter count, and recency. Values decay lazily and deterministic eviction
keeps memory bounded.

Receiving concrete help can raise recipient-to-giver trust. Giving records a
cost in the giver's reciprocity balance but does not make the giver trust the
recipient automatically. Sharing, care, teaching, communication, and mate
choice can therefore diverge between strangers, relatives, and repeated
partners without a global friendship graph.

Communication is an explicit costly action. It exposes one cultural dimension
and can expose a belief; food sharing changes only observed generosity.
Cultural influence depends on the learner, conformity, familiarity, and trust.
A single food transfer no longer copies every hidden cultural value or flips a
religion label.

## Brain mechanisms

Brain kinds change how choices are evaluated; they do not grant different
actions or hidden world information.

- `deliberative` chooses the highest current utility.
- `exploratory` samples between plausible choices using a temperature affected
  by risk tolerance.
- `habitual` adds bounded values learned from previous outcomes.
- `social` biases choices toward recently observed neighbor actions.

Every person also has continuous curiosity, exploration, risk, learning,
generosity, and conformity tendencies. This means two people with the same
brain kind can still behave differently.

After resolution, a brain receives the outcome of its own action. Successful
and failed actions update a fixed-size preference vector plus a compact last
outcome record. The state is bounded and never inherited. Social brains weight
recent successful behavior by relationship confidence and trust rather than
copying every visible attempt equally.

The inherited network can optionally be recurrent. Its extra connections feed
the prior hidden activation into the next decision, giving evolution a bounded
one-step memory without exposing an event log or global history. Recurrent
weights recombine and mutate at conception like the other neural weights. The
activation they operate on is acquired lifetime state held by `BrainState`, so
it dies with the person and a newborn begins with no active thought from either
parent. `neural_recurrence_weight=0` is the feed-forward off switch and remains
the default until long-run comparisons show that temporal memory pays.

An optional cultural channel can move an effective output policy between
living people. A local teaching action blends the teacher's inherited output
plus lifetime overlay into the learner's lifetime overlay. Neither inherited
network is written, so teaching does not cross the Weismann barrier; a child
still receives only recombined parental networks fixed at conception. The
recipient records the immediate teacher, originating policy lineage, hop, and
tick. `policy_teaching_rate=0` removes the option and is the default until
paired runs connect policy spread to survival rather than spread alone.
Transfer itself is neutral: it records mutual contact but does not assume the
copied policy helped, alter trust or another cultural trait, or grant a fitness
bonus. Opposing policies use the same copy operation; only their later
consequences under local conditions can separate them at scale.

Attention is capped before neighbor objects are materialized. Dependents and
locally remembered contacts receive priority, and remaining capacity is
sampled from the local population. Each attended person becomes a separate
feasible share, care, teaching, communication, or mate candidate; the engine
no longer picks one universal “poorest” or “highest-energy” target before the
brain evaluates options.

Decision randomness comes from a deterministic stream keyed by seed, tick, and
agent ID. This keeps one brain's variable number of random choices from
changing every later person's decision and leaves a path to parallel or native
decision evaluation.

## What to measure

The observer reports age bands, body condition, development, frailty, health
fraction, death causes, disease compartments, incidence and recovery totals,
brain-kind populations, successful/attempted/failed actions, action entropy,
inherited and recurrent network magnitude, policy-teaching recipients,
lineages and transmissions,
remembered and recently active relationship degree and trust, reproductive
roles, pregnancies, losses, within-person heterozygosity, and population
genetic diversity. Food and material accounting separates world stocks,
agent-held stocks, harvest transfers, ecological renewal, consumption,
spoilage, construction/research use, and inventory lost with deaths. These are
measurements only; they do not feed back into agent behavior.

## Intentional limits

This is still not a clinical, demographic, or psychological prediction model.
It has no multiple nutrients, named pathogen strains, complete sex
development, detailed organs, injuries, explicit households, pair-bond
contracts, full pedigree, agriculture, economy, government, warfare, or
language. Those should be added only when they introduce a causal mechanism
that can be calibrated and measured without scripting an outcome.

Relationship trust is currently one general help/reliability signal rather
than separate expectations for care, safety, teaching, and partnership.
Social imitation observes a compact recent action/success record rather than a
rich theory of another person's motives. These are deliberate bounded-state
approximations and should not be interpreted as full human psychology.
