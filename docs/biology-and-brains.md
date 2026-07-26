# Biology, inheritance, and brains

This is an abstract evolutionary model, not a claim to reproduce the full
biology or psychology of real humans. Its purpose is to create causal,
heritable variation cheaply enough to study large populations.

## Four separate layers

Each person has four kinds of state:

1. **Genome** — inherited, recombined, and occasionally mutated.
2. **Phenotype** — biological potential expressed from that genome.
3. **Culture** — learned norms and religion, transmitted through families and
   contact.
4. **Brain state** — preferences learned during this person's lifetime.

Only the genome is genetically inherited. Children begin with empty learned
preferences and no acquired technology. This prevents knowledge such as
seafaring from appearing genetically in the next generation.

## Genome

The genome uses two packed 56-bit haplotypes. The bits are grouped into seven
synthetic chromosomes and fourteen modeled quantitative genes, with four loci
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
constitution, longevity, maturation, vision, learning, risk, and cognitive
style. Several advantages increase metabolism: greater sensory, learning,
constitution, and longevity potential all cost energy. Diversity is therefore
maintained through costs and environmental selection rather than quotas.

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
- Individual biological maturity.
- Adequate energy and health.
- Reproduction cooldown completion.
- No current pregnancy for an ova-role person.

Success is stochastic and depends on both partners' fertility and current
health. A successful conception creates a pregnancy rather than an instant
child. Gestation consumes energy every tick; low health or death can end it.
Birth occurs only at the due tick and has an additional energy cost. Newborn
energy is capped by the energy invested through conception, gestation, and
birth. Young children follow a guardian, have age-scaled metabolism, cannot
perform adult resource or social actions, and depend on caregivers to transfer
food until the configured independence age.

Detailed childhood development, pregnancy complications beyond health loss,
mate consent, kinship beyond parents/siblings, and more complete sex biology
are intentionally not modeled yet.

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
and failed actions update a fixed-size preference vector. The state is bounded
and never inherited. Social brains can inspect only a configured maximum
number of local neighbors.

Decision randomness comes from a deterministic stream keyed by seed, tick, and
agent ID. This keeps one brain's variable number of random choices from
changing every later person's decision and leaves a path to parallel or native
decision evaluation.

## What to measure

The observer reports brain-kind populations, action entropy, reproductive
roles, pregnancies, losses, within-person heterozygosity, and population
genetic diversity. These are measurements only; they do not feed back into
agent behavior.
