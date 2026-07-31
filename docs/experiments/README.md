# Experiment queue

This is the ordered evidence queue for mechanisms that exist but are not yet
settled. Run one sweep at a time. The simulations are deterministic, but
running several CPU-bound sweeps together makes their timing measurements
meaningless and slows the result that should decide what lands next.

Every comparison uses six paired seeds, records complete run definitions and
the code revision, and writes each completed run immediately. An interrupted
sweep is therefore a partial result rather than no result.

Experiment summaries are observer evidence, never causal input. A result may
justify leaving a mechanism off, changing its generic cost, or designing a new
experiment; it is never compiled back into a lineage bonus, preferred policy,
target population trajectory, or biome-specific strategy.

## 1. Artifacts over 300 years

**Question:** Do effect-defined artifacts improve survival or condition after
the ten-year construction burst, once decay, maintenance, storage, and
environmental exposure have had time to interact?

```bash
setsid nohup ./run.sh experiment \
  --arm off=artifacts_enabled=false --arm base \
  --config configs/pressure.json --seeds 0,1,2,3,4,5 --years 300 \
  --checkpoint-years 10,50,100 \
  --out .run/experiments/artifacts-300-years.jsonl \
  --metric population --metric population_at_10 \
  --metric population_at_50 --metric population_at_100 \
  --metric mean_energy --metric mean_body_condition \
  --metric artifact_count --metric sheltered_population \
  --metric artifact_food_stored --jobs 2 \
  > .run/experiments/artifacts-300-years.txt 2>&1 &
```

Promotion criterion: a direct physical effect such as shelter or stored food
must persist across seeds. Population is allowed to be a trade-off, but it
must be reported rather than hidden behind the physical effect.

**Result:** the persistence criterion failed. Treatment seeds built and then
lost 116.8 artifacts on average, and all six ended with no artifacts or
material. Population was 14.7% lower at year 50 in every treatment seed and
mixed by year 300. See `docs/findings.md`; B3's renewal regimes now precede
another durability claim.

## 2. D2 world-area and population matrix

**Question:** Which effects come from a larger canvas, which come from lower
founder density, and which come from scaling the population with the area?

Measure cost first:

```bash
python3 -m sims.profile_engine --config configs/pressure.json \
  --world-sizes 24x24,48x48 --populations 80,320 \
  --seeds 0,1 --ticks 20 --no-projection \
  > .run/experiments/d2-cost-matrix.jsonl
```

Then measure demographic consequences:

```bash
python3 -u -m sims.scaling_experiment --config configs/pressure.json \
  --world-sizes 24x24,48x48 --populations 80,320 \
  --seeds 0,1,2,3,4,5 --ticks 1200 \
  > .run/experiments/d2-demographic-matrix.jsonl
```

The four cells separate the comparisons: 80/48x48 isolates sparsity;
320/48x48 restores the pressure-world founder density; 320/24x24 exposes
crowding. `baseline.json` is intentionally excluded: its approximately
13,000-person ceiling is an abundance and runtime test, not a selective D2
ecology.
Read population beside births, isolation, remembered/social connections,
infections, body condition, and resource fraction. Promotion criterion: B3
uses the smallest world/population scale that creates persistent spatially
distinct populations without making local interaction vanish.

## 3. Cultural policy transmission over 300 years

**Question:** Do local policy lineages spread, and does a lineage that spreads
improve survival rather than merely make nearby people more alike?

```bash
setsid nohup ./run.sh experiment \
  --arm off --arm taught=policy_teaching_rate=0.15 \
  --config configs/pressure.json --seeds 0,1,2,3,4,5 --years 300 \
  --checkpoint-years 10,50,100 \
  --out .run/experiments/policy-teaching-300-years.jsonl \
  --metric population --metric population_at_50 \
  --metric population_at_100 --metric taught_policy_population \
  --metric taught_policy_lineages --metric policy_transmissions \
  --metric policy_diversity --jobs 2 \
  > .run/experiments/policy-teaching-300-years.txt 2>&1 &
```

Promotion criterion: transmission must occur across seeds and its lineage
metrics must be interpretable beside survival. Spread alone does not justify
enabling it; a copied bad policy is still a successful transmission.

## 4. Neural maintenance over 1,500 years

**Question:** Does charging for inherited network magnitude turn the observed
mutation ratchet into a selectable trade-off, or merely reduce population?

The cost of `4.0` is the already-tested physiological scale: at the observed
long-run network magnitude of roughly `0.15`, it charges about `0.6` energy per
person-year.

```bash
setsid nohup ./run.sh experiment \
  --arm free --arm upkeep=neural_maintenance_cost=4.0 \
  --config configs/pressure.json --seeds 0,1,2,3,4,5 --years 1500 \
  --checkpoint-years 50,300,1000 \
  --out .run/experiments/neural-upkeep-1500-years.jsonl \
  --metric population --metric population_at_50 \
  --metric population_at_1000 --metric mean_network_magnitude \
  --metric policy_diversity --metric mean_body_condition --jobs 2 \
  > .run/experiments/neural-upkeep-1500-years.txt 2>&1 &
```

Promotion criterion: upkeep must change the magnitude trajectory, not only
charge energy. If magnitude is unchanged and population falls, it stays off.

## 5. Recurrent memory over 1,500 years

**Question:** Can inherited temporal memory improve outcomes or retain a
distinct policy after enough generations for selection to act?

```bash
setsid nohup ./run.sh experiment \
  --arm feedforward --arm recurrent=neural_recurrence_weight=0.8 \
  --config configs/pressure.json --seeds 0,1,2,3,4,5 --years 1500 \
  --checkpoint-years 50,300,1000 \
  --out .run/experiments/recurrence-1500-years.jsonl \
  --metric population --metric population_at_1000 \
  --metric mean_recurrent_magnitude --metric policy_diversity \
  --metric mean_body_condition --jobs 2 \
  > .run/experiments/recurrence-1500-years.txt 2>&1 &
```

Promotion criterion: recurrence must produce a repeatable outcome or policy
difference that clears its measured runtime cost. Capability alone is not a
result.

## 6. Lifetime plasticity over 3,000 years

**Question:** Was plasticity rejected because its noisy update rule is harmful,
or because the earlier experiment ended before evolved brains began to pay?

```bash
setsid nohup ./run.sh experiment \
  --arm off=neural_output_weight=0 --arm base \
  --arm plastic=plasticity_rate=0.05 \
  --config configs/pressure.json --seeds 0,1,2,3,4,5 --years 3000 \
  --checkpoint-years 50,300,1000,2000 \
  --out .run/experiments/plasticity-3000-years.jsonl \
  --metric population --metric population_at_1000 \
  --metric mean_plasticity --metric policy_diversity --jobs 2 \
  > .run/experiments/plasticity-3000-years.txt 2>&1 &
```

Promotion criterion: the plastic arm must beat inherited-only brains across
paired seeds at a long horizon. Merely beating the silenced arm is evidence
for brains, not for lifetime learning.

## Reading progress

Count completed runs with `wc -l` on the JSONL file. Rebuild a summary without
simulating again:

```bash
./run.sh experiment --summarise .run/experiments/NAME.jsonl \
  --metric population --metric ANOTHER_METRIC
```
