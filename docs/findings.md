# Measured findings

Results that changed what the project believes, with the raw output beside
them in [experiments/](experiments/). Everything here was produced by
[`sims.experiment`](cli.md) with arms paired by seed,
so each number is a comparison against the same worlds rather than against a
different run.

Reproduce any of them with the command quoted under it.

---

## Brains cost you early and pay off late

**The headline: an inherited neural brain is a handicap for the first few
dozen generations and an advantage after that.** The crossover is somewhere
between year 300 and year 1000.

`configs/pressure.json`, 6 paired seeds, `base` (the engine as configured)
against `off` (`neural_output_weight=0`, which silences the network while
leaving it inherited and mutated):

| | pop @50 | pop @300 | pop @1000 | pop @1500 |
|---|---|---|---|---|
| off (silenced) | 156.0 | 181.3 | 221.2 | 212.2 |
| base (brains) | 139.8 | 179.2 | 241.7 | 256.5 |
| difference | **−10.4%** | −1.2% | +9.3% | **+20.9%** |
| seeds agreeing | 6 of 6 | 2 of 6 | 5 of 6 | 6 of 6 |
| sign test p | 0.031 | 1.000 | 0.219 | 0.031 |

```bash
./run.sh experiment --arm off=neural_output_weight=0 --arm base \
  --config configs/pressure.json --seeds 0,1,2,3,4,5 --years 1500 \
  --checkpoint-years 50,100,300,600,1000 \
  --metric population --metric population_at_50 --metric population_at_1000 \
  --metric mean_network_magnitude --metric policy_diversity
```

Raw output: [experiments/brains-1500-years.txt](experiments/brains-1500-years.txt)

Two readings explain the shape:

- **Policy diversity ends *lower* with brains** — 0.147 against the silenced
  arm's 0.156, every seed agreeing, p = 0.031. In the silenced arm nothing
  can select on the weights, so they drift and stay diverse. Selection in the
  live arm is converging the population on something. That is the signature
  of directional selection, and it is the direct evidence that the world does
  select on brains once given the generations to do it.
- **Network magnitude is not the axis.** It rose from ~0.106 at 300 years to
  ~0.148 at 1500 in *both* arms, with no significant difference between them.
  Mutation drives magnitude; selection works on structure.

It is not a free win. The brained populations run hotter: about 21% more
people, but at mean health 0.87–0.92 against 0.98–0.99, lower body condition,
and land grazed harder (resource fraction 0.07 against 0.10). More people in
worse condition, pressed closer to what the land will bear.

### Why the early cost

Founder weights are random (`neural_founder_scale`), so a new brain is a
consistent but arbitrary preference. Decision noise is not the enemy of a good
policy here — it is what rescues an agent from a bad one. That predicts the
harm should scale with how much the network is heard, and it does. At 300
years, every arm against the same silenced control, all unanimous at
p = 0.031 on population at year 50:

| Arm | Setting | pop @50 | vs off |
|---|---|---|---|
| off | `neural_output_weight=0` | 156.0 | — |
| base | weight 1.2, noise 0.20 | 139.8 | −10.4% |
| loud | `neural_output_weight=3.0` | 104.2 | −33.2% |
| quiet | `decision_noise=0.05` | 98.8 | −36.6% |
| loud_quiet | both | 71.5 | −54.2% |

Louder is worse; less noise to hide behind is worse; both together is worst.
Body condition was identical across every arm, so this is how many survive,
not how well they eat.

Raw output:
[experiments/brain-volume-300-years.txt](experiments/brain-volume-300-years.txt)

**The practical consequence:** any experiment shorter than a few hundred years
will measure the handicap and miss the benefit, and will conclude the brain is
worthless or harmful. Judge cognition over generations or not at all.

---

## `configs/scarcity.json` cannot answer questions

Every seed goes extinct by about year 150, with brains or without: 12 runs,
12 extinctions, survival 1568–2264 ticks against 974–3024, three seeds each
way, p = 1.0. A world that kills everyone applies no differential pressure,
so any comparison run in it returns noise.

```bash
./run.sh experiment --arm on --arm off=neural_output_weight=0 \
  --config configs/scarcity.json --seeds 0,1,2,3,4,5 --years 300 \
  --metric ticks_run
```

Raw output:
[experiments/scarcity-300-years.txt](experiments/scarcity-300-years.txt)

This is why `configs/pressure.json` exists: the same land, started at 80
founders instead of 400, so the population grows *into* the ceiling instead of
crashing through it. It holds ~180 people for centuries with resources pinned
near 13% of capacity — persistently squeezed and still alive, which is the
only band where a mechanism that helps people eat can show up as more people.

---

## Finite materials make the current artifacts transient

Over 300 years in `configs/pressure.json`, the artifact arm built 116.8
objects per seed on average and performed 2,074 maintenance actions. Every
object nevertheless decayed in every seed, leaving zero shelter, stored food,
world material, or carried material at year 300. The mechanism is active, but
the current finite material regime cannot sustain its stock.

The demographic effect changed sign over time. At year 50 the artifact arm
had 115.0 people against 134.8 without artifacts, lower in all six paired seeds
(`p = 0.031`). By year 300 it had 172.5 against 159.3, but only four seeds
favored artifacts (`p = 0.688`). Final energy and body-condition differences
were likewise mixed. This does not clear the experiment queue's persistence
criterion: B3's renewal regimes must be explicit before artifact durability is
interpreted as an evolved long-run advantage.

The raw run's older pairing check warns because enabling artifacts adds one
brain output and therefore changes opening network-summary metrics. Direct
inspection found those were the only opening differences; founder bodies,
positions, genomes, legacy weights, and the engine construction stream match.
The harness now fingerprints that construction stream instead of treating an
intended mechanism metric as evidence of shifted random draws.

```bash
./run.sh experiment --arm off=artifacts_enabled=false --arm base \
  --config configs/pressure.json --seeds 0,1,2,3,4,5 --years 300 \
  --checkpoint-years 10,50,100 \
  --metric population --metric population_at_50 \
  --metric artifact_count --metric sheltered_population --jobs 2
```

---

## Method notes worth keeping

- **`neural_brains_enabled=false` is not a valid off switch for a comparison.**
  Skipping the network weight draws shifts every later random draw, so the
  arms get different founders in different places and the result comes with a
  different world attached. `neural_output_weight=0` leaves construction
  untouched. The harness fingerprints the engine random stream immediately
  after construction, so it detects shifted draws without mistaking an
  intended opening mechanism metric for a different world.
- **Six paired seeds is the floor.** The best possible two-sided sign-test
  p-value at `n` seeds is `2/2ⁿ`, so four unanimous seeds cap out at 0.125 no
  matter how large the effect.
- **Final population is a weak metric in a world at equilibrium.** The land
  decides how many people fit. Use `--checkpoint-years` and compare the
  transient, or the difference will be real and invisible.

---

## What the brain work is aimed at next

The 1500-year result says selection *does* act on brains, but two readings
from it point at things the model is missing rather than at cognition being
too simple.

**Magnitude is a ratchet, not a trade-off.** Mean network magnitude rose from
~0.106 to ~0.148 over 1500 years in the selected arm *and* in the silenced
control, with no significant difference between them. Mutation inflates it and
nothing pushes back, because a brain costs nothing to own. `neural_maintenance_cost`
(off by default) charges energy per year per unit of inherited weight, which
is what makes brain size something selection has to decide. Untested; it is an
arm to run, and if it costs population for nothing it stays at zero.

**Plasticity may have been judged on too short a run.** Lifetime learning is
off because it measured worse than not learning — 23.7 people against 17.8.
But that is the same shape as the inherited network, which also measured worse
early (−10% at year 50) and only became a +21% advantage past year 1000. The
plasticity verdict has not been retested at a horizon long enough to see a
crossover. The arm to run:

```bash
./run.sh experiment --arm off=neural_output_weight=0 --arm base \
  --arm plastic=plasticity_rate=0.05 \
  --config configs/pressure.json --seeds 0,1,2,3,4,5 --years 3000 \
  --checkpoint-years 50,300,1000,2000 \
  --out .run/experiments/overnight.jsonl \
  --metric population --metric population_at_1000 --metric mean_plasticity \
  --jobs 2
```

**Brain capacity cannot be tested this way.** `neural_hidden_units` changes
the number of weights drawn while the world is built, so the arms get
different founders — measured, and the harness warns about it. Comparing
brain sizes needs an unpaired design with enough seeds to average the founder
differences out.
