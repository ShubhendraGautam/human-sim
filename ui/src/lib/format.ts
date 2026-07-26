import type {
  RunManifest,
  RunStatus,
  ScenarioContract,
} from "../api/contracts";

const compactNumber = new Intl.NumberFormat("en", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const preciseNumber = new Intl.NumberFormat("en", {
  maximumFractionDigits: 1,
});

export function compact(value: number): string {
  return compactNumber.format(value);
}

export function precise(value: number): string {
  return preciseNumber.format(value);
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function countryName(
  scenario: ScenarioContract,
  countryId: number,
): string {
  return (
    scenario.countries.find((country) => country.id === countryId)?.name ??
    "Unclaimed"
  );
}

export function beliefName(
  scenario: ScenarioContract,
  beliefId: number,
): string {
  return (
    scenario.beliefs?.find((belief) => belief.id === beliefId)?.name ??
    `Belief ${beliefId}`
  );
}

export function statusLabel(
  status: RunStatus,
  playing: boolean,
): string {
  if (status === "failed") {
    return "Failed";
  }
  if (playing) {
    return "Running locally";
  }
  if (status === "stepping") {
    return "Stepping";
  }
  if (status === "stopped") {
    return "Stopped";
  }
  return "Paused";
}

export function scenarioName(manifest: RunManifest): string {
  const names = manifest.scenario.countries.map((country) => country.name);
  return names.length === 2 ? `${names[0]} · ${names[1]}` : "Custom world";
}
