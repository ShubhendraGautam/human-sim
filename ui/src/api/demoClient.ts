import type { SimulationClient } from "./client";
import {
  PROTOCOL_VERSION,
  SCHEMA_VERSION,
  assertFrameColumns,
  assertWorldManifest,
  type AgentColumns,
  type AgentDetail,
  type AgentDetailEnvelope,
  type BrainKind,
  type CreateRunRequest,
  type EventFeed,
  type FaunaColumns,
  type InfectionStage,
  type ResourceLayers,
  type RunFrame,
  type RunManifest,
  type RunSession,
  type SimulationMetrics,
  type StepRunRequest,
  type WorldManifest,
} from "./contracts";

const WORLD_WIDTH = 64;
const WORLD_HEIGHT = 36;
const DEMO_POPULATION = 420;
const ACTIONS = [
  "gather",
  "move",
  "communicate",
  "share",
  "eat",
  "research",
  "care",
] as const;
const BRAIN_KINDS: BrainKind[] = [
  "deliberative",
  "exploratory",
  "habitual",
  "social",
];

interface DemoAgentSeed {
  id: string;
  birthCountry: number;
  belief: number;
  baseX: number;
  baseY: number;
  age: number;
  energyBias: number;
  healthBias: number;
  bodyCondition: number;
  frailty: number;
  brainKind: BrainKind;
  knowsSeafaring: boolean;
}

function clamp(value: number, minimum = 0, maximum = 1): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function hash(seed: number, value: number): number {
  let state = (seed ^ Math.imul(value + 1, 0x9e3779b1)) >>> 0;
  state ^= state >>> 16;
  state = Math.imul(state, 0x21f0aaad);
  state ^= state >>> 15;
  state = Math.imul(state, 0x735a2d97);
  state ^= state >>> 15;
  return (state >>> 0) / 4_294_967_296;
}

function numericAt(values: number[], index: number): number {
  return values[index] ?? 0;
}

function stringAt(values: string[], index: number): string {
  return values[index] ?? "";
}

function brainAt(values: BrainKind[], index: number): BrainKind {
  return values[index] ?? "deliberative";
}

function infectionAt(
  values: InfectionStage[],
  index: number,
): InfectionStage {
  return values[index] ?? "susceptible";
}

function buildWorld(): WorldManifest {
  const terrain: number[] = [];
  const country: number[] = [];
  const foodCapacity: number[] = [];
  const foodProductivity: number[] = [];
  const seasonalAmplitude: number[] = [];
  const seasonalPhase: number[] = [];
  const materialCapacity: number[] = [];
  const materialProductivity: number[] = [];

  for (let y = 0; y < WORLD_HEIGHT; y += 1) {
    const westCoast = 24 + Math.round(Math.sin(y * 0.43) * 1.8);
    const eastCoast = 39 + Math.round(Math.cos(y * 0.37) * 1.6);
    for (let x = 0; x < WORLD_WIDTH; x += 1) {
      const edgeInset =
        (y < 2 || y > WORLD_HEIGHT - 3) &&
        (x > 20 && x < 44);
      const isWest = x < westCoast && !edgeInset;
      const isEast = x >= eastCoast && !edgeInset;
      const isLand = isWest || isEast;
      terrain.push(isLand ? 0 : 1);
      country.push(isWest ? 0 : isEast ? 1 : -1);

      if (!isLand) {
        foodCapacity.push(0);
        foodProductivity.push(0);
        seasonalAmplitude.push(0);
        seasonalPhase.push(0);
        materialCapacity.push(0);
        materialProductivity.push(0);
        continue;
      }
      const latitude = Math.abs(y / (WORLD_HEIGHT - 1) - 0.5) * 2;
      const variation = 0.82 + hash(91 + x, y * WORLD_WIDTH + x) * 0.36;
      const foodBase = isWest ? 9.4 : 7.6;
      const materialBase = isWest ? 4.2 : 7.4;
      foodCapacity.push(foodBase * (1 - latitude * 0.34) * variation);
      foodProductivity.push(0.78 + variation * 0.24);
      seasonalAmplitude.push(0.12 + latitude * 0.22);
      seasonalPhase.push(y < WORLD_HEIGHT / 2 ? 0 : 0.5);
      materialCapacity.push(materialBase * (0.88 + (1 - variation) * 0.3));
      materialProductivity.push(0);
    }
  }

  return {
    width: WORLD_WIDTH,
    height: WORLD_HEIGHT,
    wrap_world: false,
    terrain,
    country,
    food_capacity: foodCapacity,
    food_productivity: foodProductivity,
    seasonal_amplitude: seasonalAmplitude,
    seasonal_phase: seasonalPhase,
    material_capacity: materialCapacity,
    material_productivity: materialProductivity,
  };
}

function findLandCell(
  world: WorldManifest,
  countryId: number,
  x: number,
  y: number,
): [number, number] {
  let candidateX = Math.round(clamp(x, 0, world.width - 1));
  const candidateY = Math.round(clamp(y, 0, world.height - 1));
  const index = candidateY * world.width + candidateX;
  if (world.country[index] === countryId) {
    return [candidateX, candidateY];
  }

  const direction = countryId === 0 ? -1 : 1;
  for (let distance = 1; distance < world.width; distance += 1) {
    candidateX += direction;
    if (candidateX < 0 || candidateX >= world.width) {
      break;
    }
    if (world.country[candidateY * world.width + candidateX] === countryId) {
      return [candidateX, candidateY];
    }
  }
  return countryId === 0 ? [4, candidateY] : [world.width - 5, candidateY];
}

function buildAgentSeeds(seed: number, world: WorldManifest): DemoAgentSeed[] {
  return Array.from({ length: DEMO_POPULATION }, (_, index) => {
    const birthCountry = index < DEMO_POPULATION / 2 ? 0 : 1;
    const sideIndex = index % (DEMO_POPULATION / 2);
    const randomX = hash(seed + 11, index);
    const randomY = hash(seed + 29, index);
    const targetX =
      birthCountry === 0
        ? 2 + randomX * 20
        : world.width - 23 + randomX * 20;
    const targetY = 2 + randomY * (world.height - 5);
    const [baseX, baseY] = findLandCell(
      world,
      birthCountry,
      targetX,
      targetY,
    );
    const brainIndex = Math.floor(hash(seed + 47, index) * BRAIN_KINDS.length);
    return {
      id: String(1001 + index),
      birthCountry,
      belief: birthCountry,
      baseX,
      baseY,
      age: 2 + hash(seed + 61, index) * 58,
      energyBias: 0.44 + hash(seed + 73, index) * 0.46,
      healthBias: 0.62 + hash(seed + 83, index) * 0.36,
      bodyCondition: 0.58 + hash(seed + 97, index) * 0.4,
      frailty: hash(seed + 101, index) ** 3 * 0.55,
      brainKind: BRAIN_KINDS[brainIndex] ?? "deliberative",
      knowsSeafaring:
        sideIndex < 12 || hash(seed + 107, index) > 0.965,
    };
  });
}

function buildManifest(seed: number, sequence: number): RunManifest {
  const world = buildWorld();
  const manifest: RunManifest = {
    protocol_version: PROTOCOL_VERSION,
    schema_version: SCHEMA_VERSION.run_manifest,
    kind: "run_manifest",
    run_id: `demo-${seed}`,
    sequence,
    status: "paused",
    seed,
    tick: 0,
    year: 0,
    population: DEMO_POPULATION,
    model: {
      model_version: "demo-adapter",
      snapshot_schema_version: 3,
      config_schema_version: 1,
      genome_schema_version: 1,
    },
    config: {
      width: WORLD_WIDTH,
      height: WORLD_HEIGHT,
      ticks_per_year: 12,
      metrics_interval: 1,
      wrap_world: false,
    },
    scenario: {
      countries: [
        {
          id: 0,
          name: "Aster",
          region: [0, 0, 27, WORLD_HEIGHT],
          population: DEMO_POPULATION / 2,
          religion: "sun",
          generosity_mean: 0.75,
          exploration_mean: 0.3,
          curiosity_mean: 0.45,
          conformity_mean: 0.7,
        },
        {
          id: 1,
          name: "Boreal",
          region: [38, 0, 26, WORLD_HEIGHT],
          population: DEMO_POPULATION / 2,
          religion: "stars",
          generosity_mean: 0.35,
          exploration_mean: 0.75,
          curiosity_mean: 0.8,
          conformity_mean: 0.3,
        },
      ],
      seas: [[27, 0, 11, WORLD_HEIGHT]],
      beliefs: [
        { id: 0, name: "sun" },
        { id: 1, name: "stars" },
      ],
    },
    world,
    capabilities: {
      step: true,
      reset: true,
      agent_detail: true,
      resource_layers: true,
      full_snapshot_export: false,
      // Nothing is running behind this fixture, so playback is the browser's
      // own timer and stops when the tab does.
      playback: false,
    },
    playback: { playing: false, seconds_per_year: null },
  };
  assertWorldManifest(manifest);
  return manifest;
}

function buildMetrics(tick: number, agents: AgentColumns): SimulationMetrics {
  const year = tick / 12;
  const season = Math.sin((year % 1) * Math.PI * 2);
  const infections = agents.infection_stage.reduce(
    (count, stage) => count + (stage === "infectious" ? 1 : 0),
    0,
  );
  const exposed = agents.infection_stage.reduce(
    (count, stage) => count + (stage === "exposed" ? 1 : 0),
    0,
  );
  const recovered = agents.infection_stage.reduce(
    (count, stage) => count + (stage === "recovered" ? 1 : 0),
    0,
  );
  const mean = (values: number[]): number =>
    values.reduce((sum, value) => sum + value, 0) /
    Math.max(1, values.length);
  const brainPopulation = Object.fromEntries(
    BRAIN_KINDS.map((kind) => [
      kind,
      agents.brain_kind.filter((value) => value === kind).length,
    ]),
  );
  const actionCounts = Object.fromEntries(
    ACTIONS.map((action) => [
      action,
      agents.last_action.filter((value) => value === action).length,
    ]),
  );

  return {
    tick,
    year,
    population: agents.id.length,
    births: Math.floor(tick / 15),
    conceptions: Math.floor(tick / 13),
    pregnancies: 7 + Math.round(Math.sin(tick * 0.08) * 2),
    pregnancy_losses: Math.floor(tick / 90),
    deaths: Math.floor(tick / 15),
    total_resources: 5_320 + season * 420 - tick * 0.32,
    total_materials: 3_860 - tick * 0.48,
    mean_energy: mean(agents.energy_fraction) * 100,
    mean_health: mean(agents.health_fraction) * 100,
    mean_inventory: 3.8 + season * 0.35,
    mean_age: mean(agents.age),
    mean_health_fraction: mean(agents.health_fraction),
    mean_body_condition: mean(agents.body_condition),
    mean_development: 0.89,
    mean_frailty: mean(agents.frailty),
    juvenile_population: agents.age.filter((age) => age < 16).length,
    maximum_generation: Math.min(8, 2 + Math.floor(tick / 70)),
    energy_gini: 0.19 + Math.sin(tick * 0.025) * 0.025,
    resource_fraction: clamp(0.67 + season * 0.09 - tick * 0.00012),
    food_per_capita: 12.4 + season * 1.1,
    total_food_inventory: 1_420 + season * 80,
    total_material_inventory: 624 + tick * 0.3,
    food_harvested: 76 + season * 9,
    food_regenerated: 71 + season * 15,
    food_consumed: 68,
    food_spoiled: 4.2,
    food_lost_on_death: tick % 15 === 0 && tick > 0 ? 2.4 : 0,
    material_harvested: 21,
    material_regenerated: 0,
    material_consumed: 8.5,
    material_lost_on_death: tick % 15 === 0 && tick > 0 ? 0.8 : 0,
    seasonal_productivity: 1 + season * 0.18,
    seafaring_population: agents.knows_seafaring.filter(Boolean).length,
    vessels: agents.vessel_durability.filter((value) => value > 0).length,
    inventions: Math.floor(tick / 38),
    sea_crossings: Math.floor(tick / 54),
    mean_heterozygosity: 0.318,
    genetic_diversity: 0.412,
    action_entropy: 0.76 + Math.sin(tick * 0.07) * 0.04,
    infections,
    recoveries: Math.floor(tick / 24),
    mean_remembered_connections: 4.7,
    mean_social_connections: 2.3 + Math.sin(tick * 0.04) * 0.2,
    mean_trust: 0.61 + Math.sin(tick * 0.015) * 0.03,
    isolated_population: 18,
    mean_vocabulary: 3.4 + Math.sin(tick * 0.02) * 0.6,
    language_agreement: 0.72 + Math.sin(tick * 0.015) * 0.08,
    language_global_agreement: 0.24 + Math.sin(tick * 0.011) * 0.05,
    distinct_words: 60 + Math.floor(tick / 12),
    speaking_population: agents.id.length,
    coinages: 40 + Math.floor(tick / 9),
    fauna_population: 900 + Math.round(Math.sin(tick * 0.03) * 380),
    fauna_mean_energy: 13 + Math.sin(tick * 0.03 + 1) * 4,
    fauna_mean_vigilance: 0.5,
    fauna_mean_age: 4.2,
    fauna_born: 12,
    fauna_died: 11,
    fauna_grazed: 180,
    hunts: Math.floor(tick / 4),
    hunt_kills: Math.floor(tick / 9),
    meat_gained: 6.5,
    mean_network_magnitude: 0.1,
    mean_plasticity: 0.04 + Math.sin(tick * 0.02) * 0.01,
    policy_diversity: 0.12,
    mean_remembered_places: 3.1,
    age_bands: {
      juvenile: agents.age.filter((age) => age < 16).length,
      adult: agents.age.filter((age) => age >= 16 && age < 55).length,
      elder: agents.age.filter((age) => age >= 55).length,
    },
    country_population: {
      "0": agents.birth_country.filter((value) => value === 0).length,
      "1": agents.birth_country.filter((value) => value === 1).length,
    },
    belief_population: {
      "0": agents.belief.filter((value) => value === 0).length,
      "1": agents.belief.filter((value) => value === 1).length,
    },
    brain_population: brainPopulation,
    reproductive_roles: {
      ova: Math.floor(agents.id.length / 2),
      sperm: Math.ceil(agents.id.length / 2),
    },
    actions: actionCounts,
    attempted_actions: actionCounts,
    failed_actions: Object.fromEntries(
      ACTIONS.map((action, index) => [action, (tick + index) % 4]),
    ),
    deaths_by_cause: {
      senescence: Math.floor(tick / 45),
      starvation: Math.floor(tick / 75),
    },
    disease_population: {
      susceptible: agents.id.length - infections - exposed - recovered,
      exposed,
      infectious: infections,
      recovered,
    },
  };
}

function buildFrame(
  manifest: RunManifest,
  seeds: DemoAgentSeed[],
  tick: number,
  sequence: number,
  includeResources: boolean,
): RunFrame {
  const agents: AgentColumns = {
    id: [],
    x: [],
    y: [],
    birth_country: [],
    belief: [],
    age: [],
    energy_fraction: [],
    health_fraction: [],
    body_condition: [],
    frailty: [],
    brain_kind: [],
    last_action: [],
    last_action_success: [],
    infection_stage: [],
    knows_seafaring: [],
    known_techniques: [],
    vessel_durability: [],
  };

  for (let index = 0; index < seeds.length; index += 1) {
    const seed = seeds[index];
    if (seed === undefined) {
      continue;
    }
    const driftX = Math.sin(tick * 0.07 + index * 1.71) * 0.62;
    const driftY = Math.cos(tick * 0.06 + index * 0.93) * 0.62;
    const [x, y] = findLandCell(
      manifest.world,
      seed.birthCountry,
      seed.baseX + driftX,
      seed.baseY + driftY,
    );
    const action =
      ACTIONS[(index + Math.floor(tick / 3)) % ACTIONS.length] ?? "rest";
    const diseaseCycle = (tick + index * 17) % 286;
    const infectionStage: InfectionStage =
      diseaseCycle < 4
        ? "exposed"
        : diseaseCycle < 13
          ? "infectious"
          : diseaseCycle < 39
            ? "recovered"
            : "susceptible";

    agents.id.push(seed.id);
    agents.x.push(x + ((index % 5) - 2) * 0.075);
    agents.y.push(y + ((index % 7) - 3) * 0.065);
    agents.birth_country.push(seed.birthCountry);
    agents.belief.push(seed.belief);
    agents.age.push(seed.age + tick / 12);
    agents.energy_fraction.push(
      clamp(seed.energyBias + Math.sin(tick * 0.045 + index) * 0.11),
    );
    agents.health_fraction.push(
      clamp(seed.healthBias - seed.frailty * 0.12 + Math.sin(tick * 0.02) * 0.025),
    );
    agents.body_condition.push(seed.bodyCondition);
    agents.frailty.push(clamp(seed.frailty + tick * 0.00005));
    agents.brain_kind.push(seed.brainKind);
    agents.last_action.push(action);
    agents.last_action_success.push((tick + index) % 9 === 0 ? 0.25 : 1);
    agents.infection_stage.push(infectionStage);
    agents.knows_seafaring.push(seed.knowsSeafaring);
    agents.known_techniques.push(seed.knowsSeafaring ? 1 : 0);
    agents.vessel_durability.push(
      seed.knowsSeafaring && index % 3 === 0
        ? clamp(0.86 - (tick % 180) / 240)
        : 0,
    );
  }

  const resources: ResourceLayers = {
    food: manifest.world.food_capacity.map((capacity, index) =>
      Math.max(
        0,
        capacity *
          (0.56 +
            Math.sin(tick * 0.04 + index * 0.013) * 0.13 +
            hash(manifest.seed + tick, index) * 0.08),
      ),
    ),
    materials: manifest.world.material_capacity.map((capacity, index) =>
      Math.max(0, capacity * (0.82 - tick * 0.00016 - hash(19, index) * 0.08)),
    ),
  };
  const fauna = buildDemoFauna(manifest, tick);
  const frame: RunFrame = {
    protocol_version: PROTOCOL_VERSION,
    schema_version: SCHEMA_VERSION.render_frame,
    kind: "render_frame",
    run_id: manifest.run_id,
    sequence,
    status: "paused",
    tick,
    year: tick / 12,
    metrics: buildMetrics(tick, agents),
    agents,
    fauna,
    ...(includeResources ? { resources } : {}),
  };
  assertFrameColumns(frame);
  return frame;
}

/** A synthetic herd for the labelled interface preview. */
function buildDemoFauna(
  manifest: RunManifest,
  tick: number,
): FaunaColumns {
  const width = manifest.world.width;
  const height = manifest.world.height;
  const count = 220;
  const fauna: FaunaColumns = {
    id: [],
    x: [],
    y: [],
    energy: [],
    vigilance: [],
  };
  for (let index = 0; index < count; index += 1) {
    const drift = Math.round(Math.sin(tick * 0.05 + index) * 2);
    fauna.id.push(1_000_000 + index);
    fauna.x.push(
      Math.min(width - 1, Math.max(0,
        Math.floor(hash(index + 7, manifest.seed) * width) + drift)),
    );
    fauna.y.push(
      Math.min(height - 1, Math.max(0,
        Math.floor(hash(index + 23, manifest.seed) * height) - drift)),
    );
    fauna.energy.push(6 + hash(index + 41, tick) * 16);
    fauna.vigilance.push(hash(index + 59, manifest.seed));
  }
  return fauna;
}

function buildAgentDetail(
  manifest: RunManifest,
  frame: RunFrame,
  index: number,
): AgentDetail {
  const id = stringAt(frame.agents.id, index);
  const energyFraction = numericAt(frame.agents.energy_fraction, index);
  const healthFraction = numericAt(frame.agents.health_fraction, index);
  const generation = 1 + (index % 5);
  const relationshipCount = 2 + (index % 5);
  const relationships = Array.from(
    { length: relationshipCount },
    (_, relationIndex) => {
      const otherIndex =
        (index + relationIndex * 23 + 7) % frame.agents.id.length;
      return {
        agent_id: stringAt(frame.agents.id, otherIndex),
        trust: clamp(0.28 + hash(manifest.seed + index, relationIndex) * 0.68),
        balance: -0.4 + hash(manifest.seed + 8 + index, relationIndex) * 0.8,
        encounters: 2 + Math.floor(hash(index + 17, relationIndex) * 34),
        last_seen_tick: Math.max(0, frame.tick - relationIndex * 3 - 1),
      };
    },
  );
  return {
    id,
    // The fixture never kills anyone; death is only observable on real runs.
    status: "living",
    death: null,
    biography: null,
    location: {
      x: numericAt(frame.agents.x, index),
      y: numericAt(frame.agents.y, index),
      current_country: numericAt(frame.agents.birth_country, index),
    },
    identity: {
      birth_country: numericAt(frame.agents.birth_country, index),
      belief: numericAt(frame.agents.belief, index),
      reproductive_role: index % 2 === 0 ? "ova" : "sperm",
      generation,
      parents:
        generation > 1
          ? [String(1001 + ((index + 91) % DEMO_POPULATION)), String(1001 + ((index + 157) % DEMO_POPULATION))]
          : null,
      guardian_id:
        numericAt(frame.agents.age, index) < 16
          ? String(1001 + ((index + 83) % DEMO_POPULATION))
          : null,
      grandparents:
        generation > 2
          ? [
              String(1001 + ((index + 201) % DEMO_POPULATION)),
              String(1001 + ((index + 227) % DEMO_POPULATION)),
            ]
          : [],
      dependents:
        numericAt(frame.agents.age, index) > 24 && index % 6 === 0
          ? [String(1001 + ((index + 61) % DEMO_POPULATION))]
          : [],
    },
    life: {
      age: numericAt(frame.agents.age, index),
      birth_tick: Math.min(
        0,
        frame.tick - Math.round(numericAt(frame.agents.age, index) * 12),
      ),
      energy: energyFraction * 100,
      energy_fraction: energyFraction,
      health: healthFraction * 100,
      effective_maximum_health: 100,
      health_fraction: healthFraction,
      body_condition: numericAt(frame.agents.body_condition, index),
      development: 0.72 + hash(index + 12, frame.tick) * 0.27,
      development_exposure_years: Math.min(
        16,
        numericAt(frame.agents.age, index),
      ),
      frailty: numericAt(frame.agents.frailty, index),
    },
    inventories: {
      food: 1.8 + hash(index, frame.tick) * 5,
      materials: 0.4 + hash(index + 4, frame.tick) * 3,
    },
    biology: {
      genome: {
        schema_version: 1,
        haplotype_a: Math.floor(hash(index + 9, manifest.seed) * 2 ** 32)
          .toString(16)
          .padStart(16, "0"),
        haplotype_b: Math.floor(hash(index + 13, manifest.seed) * 2 ** 32)
          .toString(16)
          .padStart(16, "0"),
        heterozygosity: 0.22 + hash(index + 15, manifest.seed) * 0.26,
        expressed: {
          metabolism: hash(index + 17, manifest.seed),
          constitution: hash(index + 19, manifest.seed),
          curiosity: hash(index + 21, manifest.seed),
        },
      },
      traits: {
        metabolism: 0.36 + hash(index + 18, manifest.seed) * 0.5,
        fertility: 0.3 + hash(index + 22, manifest.seed) * 0.64,
        constitution: 0.42 + hash(index + 31, manifest.seed) * 0.54,
        immune_strength: 0.32 + hash(index + 38, manifest.seed) * 0.62,
        lifespan: 57 + hash(index + 44, manifest.seed) * 37,
        vision: 2 + Math.floor(hash(index + 51, manifest.seed) * 4),
      },
    },
    brain: {
      kind: brainAt(frame.agents.brain_kind, index),
      last_action: frame.agents.last_action[index] ?? "",
      last_success: frame.agents.last_action_success[index] ?? 0,
      last_target_id:
        index % 4 === 0
          ? String(1001 + ((index + 7) % DEMO_POPULATION))
          : null,
      last_action_tick: frame.tick,
      preferences: {
        gather: 0.35 + hash(index + 57, frame.tick) * 0.5,
        share: 0.2 + hash(index + 63, frame.tick) * 0.55,
        move: 0.18 + hash(index + 69, frame.tick) * 0.68,
      },
    },
    culture: {
      generosity: 0.24 + hash(index + 74, manifest.seed) * 0.66,
      exploration: 0.22 + hash(index + 81, manifest.seed) * 0.7,
      curiosity: 0.28 + hash(index + 87, manifest.seed) * 0.68,
      conformity: 0.25 + hash(index + 94, manifest.seed) * 0.65,
    },
    reproduction: {
      last_reproduction_tick: index % 5 === 0 ? Math.max(0, frame.tick - 34) : -1_000_000_000,
      next_reproduction_tick: Math.max(frame.tick, frame.tick + (index % 28)),
      pregnancy: null,
    },
    technology: {
      research_progress: hash(index + 101, frame.tick) * 0.95,
      knows_seafaring: frame.agents.knows_seafaring[index] ?? false,
      known_techniques: frame.agents.knows_seafaring[index]
        ? ["seafaring"]
        : [],
      vessel_durability: numericAt(
        frame.agents.vessel_durability,
        index,
      ),
      voyage_dx: 0,
      voyage_dy: 0,
    },
    disease: {
      stage: infectionAt(frame.agents.infection_stage, index),
      ticks_remaining:
        infectionAt(frame.agents.infection_stage, index) === "susceptible"
          ? 0
          : 2 + (index % 9),
    },
    relationships,
  };
}

/**
 * Deterministic UI fixture. It exercises the exact service client boundary but
 * does not claim to be a second simulation engine.
 */
export class DemoSimulationClient implements SimulationClient {
  readonly source = "demo" as const;
  #manifest: RunManifest | null = null;
  #frame: RunFrame | null = null;
  #agentSeeds: DemoAgentSeed[] = [];
  #sequence = 0;

  async createRun(request: CreateRunRequest): Promise<RunSession> {
    this.#sequence = 1;
    this.#manifest = buildManifest(request.seed, this.#sequence);
    this.#agentSeeds = buildAgentSeeds(request.seed, this.#manifest.world);
    this.#sequence += 1;
    this.#frame = buildFrame(
      this.#manifest,
      this.#agentSeeds,
      0,
      this.#sequence,
      true,
    );
    return Promise.resolve({
      manifest: this.#manifest,
      frame: this.#frame,
    });
  }

  async openRun(runId: string): Promise<RunSession> {
    if (
      this.#manifest === null ||
      this.#frame === null ||
      this.#manifest.run_id !== runId
    ) {
      const seed = Number(runId.replace(/^demo-/, "")) || 42;
      return this.createRun({ seed });
    }
    return Promise.resolve({
      manifest: this.#manifest,
      frame: this.#frame,
    });
  }

  async step(
    runId: string,
    request: StepRunRequest,
  ): Promise<RunFrame> {
    const session = this.#requireSession(runId);
    this.#sequence += 1;
    this.#frame = buildFrame(
      session.manifest,
      this.#agentSeeds,
      session.frame.tick + Math.max(1, Math.round(request.ticks)),
      this.#sequence,
      request.include_resources,
    );
    return Promise.resolve(this.#frame);
  }

  async observe(runId: string): Promise<RunFrame> {
    return Promise.resolve(this.#requireSession(runId).frame);
  }

  async setPlayback(): Promise<never> {
    // The fixture has no engine behind it to keep going, and its manifest
    // says so. Reaching here means a caller ignored the capability.
    return Promise.reject(
      new Error("The synthetic fixture cannot run without the interface."),
    );
  }

  async reset(runId: string): Promise<RunSession> {
    const { manifest } = this.#requireSession(runId);
    return this.createRun({
      seed: manifest.seed,
      scenario: manifest.scenario,
      config: manifest.config,
    });
  }

  async getAgentDetail(
    runId: string,
    agentId: string,
  ): Promise<AgentDetailEnvelope> {
    const session = this.#requireSession(runId);
    const index = session.frame.agents.id.indexOf(agentId);
    if (index < 0) {
      throw new Error(`Person ${agentId} is not present in this frame.`);
    }
    return Promise.resolve({
      protocol_version: PROTOCOL_VERSION,
      schema_version: SCHEMA_VERSION.agent_detail,
      kind: "agent_detail",
      run_id: runId,
      sequence: session.frame.sequence,
      status: session.frame.status,
      tick: session.frame.tick,
      agent: buildAgentDetail(session.manifest, session.frame, index),
    });
  }

  async getEvents(runId: string, sinceTick: number): Promise<EventFeed> {
    const session = this.#requireSession(runId);
    const { frame } = session;
    // The demo fixture has no causal history to report, and inventing one
    // would put fabricated events beside real ones in the same panel. An
    // empty feed is the honest fixture.
    return Promise.resolve({
      protocol_version: PROTOCOL_VERSION,
      schema_version: SCHEMA_VERSION.event_feed,
      kind: "event_feed",
      run_id: runId,
      sequence: frame.sequence,
      status: frame.status,
      tick: frame.tick,
      year: frame.year,
      events: [],
      oldest_retained_tick: Math.max(0, sinceTick),
      dropped: false,
    });
  }

  getExportUrl(_runId: string): null {
    return null;
  }

  dispose(): void {
    this.#manifest = null;
    this.#frame = null;
    this.#agentSeeds = [];
  }

  #requireSession(runId: string): RunSession {
    if (
      this.#manifest === null ||
      this.#frame === null ||
      this.#manifest.run_id !== runId
    ) {
      throw new Error("The demo run is not initialized.");
    }
    return { manifest: this.#manifest, frame: this.#frame };
  }
}
