import type { ConfigValue, SimulationMetrics } from "../api/contracts";

export type ExperimentMetric =
  | "population"
  | "policy_diversity"
  | "mean_network_magnitude"
  | "mean_recurrent_magnitude"
  | "mean_brain_units"
  | "mean_plasticity"
  | "mean_health_fraction"
  | "mean_energy"
  | "mean_body_condition";

export interface ExperimentDefinition {
  id: string;
  name: string;
  question: string;
  controlLabel: string;
  treatmentLabel: string;
  control: Record<string, ConfigValue>;
  treatment: Record<string, ConfigValue>;
  suggestedMetric: ExperimentMetric;
}

export interface PairedResult {
  seed: number;
  control: number;
  treatment: number;
  delta: number;
}

export interface ExperimentSummary {
  controlMean: number;
  treatmentMean: number;
  meanDelta: number;
  treatmentHigher: number;
  controlHigher: number;
  ties: number;
}

export const EXPERIMENT_DEFINITIONS: ExperimentDefinition[] = [
  {
    id: "environmental-exposure",
    name: "Environmental exposure",
    question: "What does paying for local seasonal extremes change?",
    controlLabel: "No exposure cost",
    treatmentLabel: "Exposure cost 8",
    control: { environmental_energy_cost_per_year: 0 },
    treatment: { environmental_energy_cost_per_year: 8 },
    suggestedMetric: "mean_body_condition",
  },
  {
    id: "recurrence",
    name: "Recurrent memory",
    question: "Does carrying hidden state between decisions improve outcomes?",
    controlLabel: "Feed-forward",
    treatmentLabel: "Memory 0.8",
    control: { neural_recurrence_weight: 0 },
    treatment: { neural_recurrence_weight: 0.8 },
    suggestedMetric: "population",
  },
  {
    id: "plasticity",
    name: "Lifetime learning",
    question: "Does changing neural weights during life earn back its cost?",
    controlLabel: "Inherited only",
    treatmentLabel: "Plasticity 0.05",
    control: { plasticity_rate: 0 },
    treatment: { plasticity_rate: 0.05 },
    suggestedMetric: "population",
  },
  {
    id: "growth",
    name: "Evolvable brain growth",
    question: "Does selection favour building more neural capacity over a life?",
    controlLabel: "Fixed brain",
    treatmentLabel: "Growing brain",
    control: {
      neural_growth_enabled: false,
      neural_maintenance_cost: 1,
    },
    treatment: {
      neural_growth_enabled: true,
      neural_maintenance_cost: 1,
    },
    suggestedMetric: "mean_brain_units",
  },
  {
    id: "influence",
    name: "Brain influence",
    question: "Does letting the inherited network affect decisions change fitness?",
    controlLabel: "Silent network",
    treatmentLabel: "Audible network",
    control: { neural_output_weight: 0 },
    treatment: { neural_output_weight: 1.2 },
    suggestedMetric: "population",
  },
  {
    id: "maintenance",
    name: "Brain maintenance cost",
    question: "Does charging for neural tissue suppress unsupported complexity?",
    controlLabel: "Free brain",
    treatmentLabel: "Cost 1.0",
    control: { neural_maintenance_cost: 0 },
    treatment: { neural_maintenance_cost: 1 },
    suggestedMetric: "mean_network_magnitude",
  },
];

export const EXPERIMENT_METRICS: {
  id: ExperimentMetric;
  label: string;
}[] = [
  { id: "population", label: "Population" },
  { id: "policy_diversity", label: "Policy diversity" },
  { id: "mean_network_magnitude", label: "Network magnitude" },
  { id: "mean_recurrent_magnitude", label: "Recurrent magnitude" },
  { id: "mean_brain_units", label: "Active brain units" },
  { id: "mean_plasticity", label: "Lifetime plasticity" },
  { id: "mean_health_fraction", label: "Health fraction" },
  { id: "mean_energy", label: "Mean energy" },
  { id: "mean_body_condition", label: "Body condition" },
];

export function parseSeeds(input: string, maximum = 12): number[] {
  const tokens = input
    .split(/[\s,]+/)
    .map((token) => token.trim())
    .filter(Boolean);
  if (tokens.length === 0) {
    throw new Error("Enter at least one integer seed.");
  }
  const seeds = tokens.map((token) => Number(token));
  if (seeds.some((seed) => !Number.isSafeInteger(seed))) {
    throw new Error("Seeds must be whole, safe integers separated by commas.");
  }
  const unique = [...new Set(seeds)];
  if (unique.length > maximum) {
    throw new Error(`Run at most ${maximum} paired seeds from the browser.`);
  }
  return unique;
}

export function metricValue(
  metrics: SimulationMetrics,
  metric: ExperimentMetric,
): number {
  return metrics[metric];
}

export function summarizeExperiment(
  results: PairedResult[],
): ExperimentSummary {
  if (results.length === 0) {
    throw new Error("An experiment summary needs at least one pair.");
  }
  const total = (key: "control" | "treatment" | "delta") =>
    results.reduce((sum, result) => sum + result[key], 0);
  const epsilon = 1e-12;
  return {
    controlMean: total("control") / results.length,
    treatmentMean: total("treatment") / results.length,
    meanDelta: total("delta") / results.length,
    treatmentHigher: results.filter((result) => result.delta > epsilon).length,
    controlHigher: results.filter((result) => result.delta < -epsilon).length,
    ties: results.filter((result) => Math.abs(result.delta) <= epsilon).length,
  };
}

export function formatExperimentValue(
  metric: ExperimentMetric,
  value: number,
): string {
  if (metric === "population") {
    return Math.round(value).toLocaleString();
  }
  if (
    metric === "mean_health_fraction"
    || metric === "mean_body_condition"
  ) {
    return `${(value * 100).toFixed(1)}%`;
  }
  return Math.abs(value) < 0.01 ? value.toFixed(4) : value.toFixed(3);
}
