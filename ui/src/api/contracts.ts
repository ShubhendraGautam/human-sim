/**
 * UI-facing service protocol.
 *
 * The engine's visualization snapshot is intentionally not imported directly
 * into components. The service normalizes it into this compact, versioned
 * contract so engine and renderer can evolve independently.
 */

export const PROTOCOL_VERSION = 1 as const;
export const SCHEMA_VERSION = 1 as const;

export type RunStatus =
  | "paused"
  | "stepping"
  | "running"
  | "stopped"
  | "failed";
export type RunSource = "demo" | "service";
export type BrainKind =
  | "deliberative"
  | "exploratory"
  | "habitual"
  | "social";
export type InfectionStage =
  | "susceptible"
  | "exposed"
  | "infectious"
  | "recovered";

export interface ProtocolEnvelope {
  protocol_version: typeof PROTOCOL_VERSION;
  schema_version: typeof SCHEMA_VERSION;
  kind: string;
  run_id: string;
  sequence: number;
  status: RunStatus;
}

export interface ModelVersions {
  model_version: string;
  snapshot_schema_version: number;
  config_schema_version: number;
  genome_schema_version: number;
}

export interface WorldManifest {
  width: number;
  height: number;
  wrap_world: boolean;
  /** Row-major; 0 is land and 1 is sea. */
  terrain: number[];
  /** Row-major country id; -1 marks cells outside a country. */
  country: number[];
  food_capacity: number[];
  food_productivity: number[];
  seasonal_amplitude: number[];
  seasonal_phase: number[];
  material_capacity: number[];
  material_productivity: number[];
}

export type ConfigValue =
  | boolean
  | number
  | string
  | null
  | ConfigValue[]
  | { readonly [key: string]: ConfigValue };

export interface CountryContract {
  id: number;
  name: string;
  region: [number, number, number, number];
  population: number;
  religion: string;
  [key: string]: ConfigValue;
}

export interface BeliefContract {
  id: number;
  name: string;
}

export interface ScenarioContract {
  countries: CountryContract[];
  seas: [number, number, number, number][];
  beliefs?: BeliefContract[];
}

export interface RunCapabilities {
  step: boolean;
  reset: boolean;
  agent_detail: boolean;
  resource_layers: boolean;
  full_snapshot_export: boolean;
}

export interface RunManifest extends ProtocolEnvelope {
  kind: "run_manifest";
  seed: number;
  tick: number;
  year: number;
  population: number;
  model: ModelVersions;
  config: Record<string, ConfigValue>;
  scenario: ScenarioContract;
  world: WorldManifest;
  capabilities: RunCapabilities;
}

/**
 * Structure-of-arrays render payload. All fields have the same length as id.
 * IDs are strings at the service boundary so native/partitioned backends are
 * not restricted by JavaScript's safe integer range.
 */
export interface AgentColumns {
  id: string[];
  x: number[];
  y: number[];
  birth_country: number[];
  belief: number[];
  age: number[];
  energy_fraction: number[];
  health_fraction: number[];
  body_condition: number[];
  frailty: number[];
  brain_kind: BrainKind[];
  /** Empty until the first action. */
  last_action: string[];
  /** Graded causal outcome in the inclusive range [0, 1]. */
  last_action_success: number[];
  infection_stage: InfectionStage[];
  knows_seafaring: boolean[];
  vessel_durability: number[];
}

export interface ResourceLayers {
  food: number[];
  materials: number[];
}

export interface SimulationMetrics {
  tick: number;
  year: number;
  population: number;
  births: number;
  conceptions: number;
  pregnancies: number;
  pregnancy_losses: number;
  deaths: number;
  total_resources: number;
  total_materials: number;
  mean_energy: number;
  mean_health: number;
  mean_inventory: number;
  mean_age: number;
  mean_health_fraction: number;
  mean_body_condition: number;
  mean_development: number;
  mean_frailty: number;
  juvenile_population: number;
  maximum_generation: number;
  energy_gini: number;
  resource_fraction: number;
  food_per_capita: number;
  total_food_inventory: number;
  total_material_inventory: number;
  food_harvested: number;
  food_regenerated: number;
  food_consumed: number;
  food_spoiled: number;
  food_lost_on_death: number;
  material_harvested: number;
  material_regenerated: number;
  material_consumed: number;
  material_lost_on_death: number;
  seasonal_productivity: number;
  seafaring_population: number;
  vessels: number;
  inventions: number;
  sea_crossings: number;
  mean_heterozygosity: number;
  genetic_diversity: number;
  action_entropy: number;
  infections: number;
  recoveries: number;
  mean_remembered_connections: number;
  mean_social_connections: number;
  mean_trust: number;
  isolated_population: number;
  age_bands: Record<string, number>;
  country_population: Record<string, number>;
  belief_population: Record<string, number>;
  brain_population: Record<string, number>;
  reproductive_roles: Record<string, number>;
  actions: Record<string, number>;
  attempted_actions: Record<string, number>;
  failed_actions: Record<string, number>;
  deaths_by_cause: Record<string, number>;
  disease_population: Record<string, number>;
}

export interface RunFrame extends ProtocolEnvelope {
  kind: "render_frame";
  tick: number;
  year: number;
  metrics: SimulationMetrics;
  agents: AgentColumns;
  resources?: ResourceLayers;
}

export interface RelationshipDetail {
  agent_id: string;
  trust: number;
  balance: number;
  encounters: number;
  last_seen_tick: number;
}

export interface AgentDetail {
  id: string;
  location: {
    x: number;
    y: number;
    current_country: number;
  };
  identity: {
    birth_country: number;
    belief: number;
    reproductive_role: string;
    generation: number;
    parents: string[] | null;
    guardian_id: string | null;
    grandparents: string[];
    dependents: string[];
  };
  life: {
    age: number;
    birth_tick: number;
    energy: number;
    energy_fraction: number;
    health: number;
    effective_maximum_health: number;
    health_fraction: number;
    body_condition: number;
    development: number;
    development_exposure_years: number;
    frailty: number;
  };
  inventories: {
    food: number;
    materials: number;
  };
  biology: {
    genome: {
      schema_version: number;
      haplotype_a: string;
      haplotype_b: string;
      heterozygosity: number;
      expressed: Record<string, number>;
    };
    traits: Record<string, number | string>;
  };
  brain: {
    kind: BrainKind;
    preferences: Record<string, number>;
    last_action: string;
    last_success: number;
    last_target_id: string | null;
    last_action_tick: number;
  };
  culture: Record<string, number>;
  reproduction: {
    last_reproduction_tick: number;
    next_reproduction_tick: number;
    pregnancy: {
      other_parent_id: string;
      conception_tick: number;
      due_tick: number;
      prenatal_condition: number;
      prenatal_exposure_years: number;
      invested_energy: number;
    } | null;
  };
  technology: {
    research_progress: number;
    knows_seafaring: boolean;
    vessel_durability: number;
    voyage_dx: number;
    voyage_dy: number;
  };
  disease: {
    stage: InfectionStage;
    ticks_remaining: number;
  };
  relationships: RelationshipDetail[];
}

export interface AgentDetailEnvelope extends ProtocolEnvelope {
  kind: "agent_detail";
  tick: number;
  agent: AgentDetail;
}

export interface CreateRunRequest {
  seed: number;
  scenario?: ScenarioContract;
  config?: Record<string, ConfigValue>;
}

export interface StepRunRequest {
  ticks: number;
  include_resources: boolean;
}

export interface RunSession {
  manifest: RunManifest;
  frame: RunFrame;
}

export interface TimelinePoint {
  tick: number;
  year: number;
  population: number;
  food: number;
  health: number;
  infectious: number;
  births: number;
  deaths: number;
}

export function toTimelinePoint(frame: RunFrame): TimelinePoint {
  const { metrics } = frame;
  return {
    tick: frame.tick,
    year: frame.year,
    population: metrics.population,
    food: metrics.resource_fraction,
    health: metrics.mean_health_fraction,
    infectious: metrics.disease_population.infectious ?? 0,
    births: metrics.births,
    deaths: metrics.deaths,
  };
}

export function assertFrameColumns(frame: RunFrame): void {
  assertEnvelope(frame, "render_frame");
  const expected = frame.agents.id.length;
  for (const [name, values] of Object.entries(frame.agents)) {
    if (values.length !== expected) {
      throw new Error(
        `Invalid render frame: agents.${name} has ${values.length} values; expected ${expected}.`,
      );
    }
  }
}

export function assertWorldManifest(manifest: RunManifest): void {
  assertEnvelope(manifest, "run_manifest");
  const expected = manifest.world.width * manifest.world.height;
  for (const name of [
    "terrain",
    "country",
    "food_capacity",
    "food_productivity",
    "seasonal_amplitude",
    "seasonal_phase",
    "material_capacity",
    "material_productivity",
  ] as const) {
    if (manifest.world[name].length !== expected) {
      throw new Error(
        `Invalid run manifest: world.${name} has ${manifest.world[name].length} cells; expected ${expected}.`,
      );
    }
  }
}

export function assertAgentDetailEnvelope(
  detail: AgentDetailEnvelope,
): void {
  assertEnvelope(detail, "agent_detail");
  if (detail.agent.id.length === 0) {
    throw new Error("Invalid agent detail: agent.id is empty.");
  }
}

function assertEnvelope(
  envelope: ProtocolEnvelope,
  expectedKind: string,
): void {
  if (envelope.protocol_version !== PROTOCOL_VERSION) {
    throw new Error(
      `Unsupported protocol version ${String(envelope.protocol_version)}; expected ${PROTOCOL_VERSION}.`,
    );
  }
  if (envelope.schema_version !== SCHEMA_VERSION) {
    throw new Error(
      `Unsupported ${expectedKind} schema version ${String(envelope.schema_version)}; expected ${SCHEMA_VERSION}.`,
    );
  }
  if (envelope.kind !== expectedKind) {
    throw new Error(
      `Invalid protocol message: expected ${expectedKind}, received ${String(envelope.kind)}.`,
    );
  }
}
