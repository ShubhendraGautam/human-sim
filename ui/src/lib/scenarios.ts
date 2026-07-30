import type { CreateRunRequest } from "../api/contracts";

export interface ScenarioPreset {
  id: string;
  name: string;
  summary: string;
  request: CreateRunRequest;
}

const STRAIT: [number, number, number, number][] = [
  [23, 0, 10, 30],
  [20, 2, 3, 9],
  [21, 21, 3, 7],
  [19, 12, 2, 5],
  [33, 5, 3, 6],
  [32, 17, 4, 9],
  [36, 25, 2, 5],
];

export const INITIAL_REQUEST: CreateRunRequest = {
  seed: 42,
  config: {
    width: 56,
    height: 30,
    wrap_world: false,
    initial_population: 0,
    ticks_per_year: 12,
    metrics_interval: 1,
  },
  scenario: {
    countries: [
      {
        id: 0,
        name: "Aster",
        region: [0, 0, 26, 30],
        population: 90,
        religion: "sun",
        generosity_mean: 0.75,
        exploration_mean: 0.3,
        curiosity_mean: 0.45,
        conformity_mean: 0.7,
        starting_energy_multiplier: 1,
        food_multiplier: 1.15,
        material_multiplier: 0.8,
      },
      {
        id: 1,
        name: "Boreal",
        region: [30, 0, 26, 30],
        population: 90,
        religion: "stars",
        generosity_mean: 0.35,
        exploration_mean: 0.75,
        curiosity_mean: 0.8,
        conformity_mean: 0.3,
        starting_energy_multiplier: 0.9,
        food_multiplier: 0.85,
        material_multiplier: 1.3,
      },
    ],
    seas: STRAIT,
  },
};

export const SCENARIO_PRESETS: ScenarioPreset[] = [
  {
    id: "twin-shores",
    name: "Twin Shores",
    summary: "Two cultures separated by a difficult, irregular strait.",
    request: INITIAL_REQUEST,
  },
  {
    id: "open-range",
    name: "Open Range",
    summary: "One connected population with no geographic isolation.",
    request: {
      seed: 17,
      config: {
        width: 48,
        height: 28,
        wrap_world: false,
        initial_population: 0,
        ticks_per_year: 12,
        metrics_interval: 1,
      },
      scenario: {
        countries: [
          {
            id: 0,
            name: "Commonweal",
            region: [0, 0, 48, 28],
            population: 180,
            religion: "earth",
            generosity_mean: 0.58,
            exploration_mean: 0.55,
            curiosity_mean: 0.62,
            conformity_mean: 0.45,
            food_multiplier: 1,
            material_multiplier: 1,
          },
        ],
        seas: [],
      },
    },
  },
  {
    id: "scarcity-divide",
    name: "Scarcity Divide",
    summary: "Matched neighbours begin with opposite food and material wealth.",
    request: {
      seed: 91,
      config: {
        width: 60,
        height: 30,
        wrap_world: false,
        initial_population: 0,
        ticks_per_year: 12,
        metrics_interval: 1,
      },
      scenario: {
        countries: [
          {
            id: 0,
            name: "Verdant",
            region: [0, 0, 30, 30],
            population: 90,
            religion: "grove",
            generosity_mean: 0.55,
            exploration_mean: 0.5,
            curiosity_mean: 0.55,
            conformity_mean: 0.5,
            food_multiplier: 1.35,
            material_multiplier: 0.65,
          },
          {
            id: 1,
            name: "Ferrum",
            region: [30, 0, 30, 30],
            population: 90,
            religion: "forge",
            generosity_mean: 0.55,
            exploration_mean: 0.5,
            curiosity_mean: 0.55,
            conformity_mean: 0.5,
            food_multiplier: 0.65,
            material_multiplier: 1.35,
          },
        ],
        seas: [],
      },
    },
  },
];

export function cloneRunRequest(request: CreateRunRequest): CreateRunRequest {
  return structuredClone(request);
}
