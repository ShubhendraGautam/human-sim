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
const fineNumber = new Intl.NumberFormat("en", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

export function compact(value: number): string {
  return compactNumber.format(value);
}

export function precise(value: number): string {
  return preciseNumber.format(value);
}

/** For quantities that live near zero, where one decimal says nothing. */
export function fine(value: number): string {
  return fineNumber.format(value);
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/**
 * A change, with its direction stated rather than implied by colour.
 *
 * Returns null when there is nothing to compare against or the baseline was
 * zero, because "infinite growth" is not a reading anyone can use.
 */
export function changePercent(
  from: number,
  to: number,
): string | null {
  if (!Number.isFinite(from) || !Number.isFinite(to) || from === 0) {
    return null;
  }
  const change = ((to - from) / Math.abs(from)) * 100;
  if (Math.abs(change) < 0.05) {
    return "no change";
  }
  return `${change > 0 ? "+" : "−"}${preciseNumber.format(Math.abs(change))}%`;
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

/** A positive numeric field from the run's configuration, or a fallback. */
export function configNumber(
  manifest: RunManifest,
  name: string,
  fallback: number,
): number {
  const value = manifest.config[name];
  return typeof value === "number" && value > 0 ? value : fallback;
}

/**
 * A configured number exactly as set, including zero.
 *
 * `configNumber` treats zero as absent, which is right for a capacity but
 * wrong for a rate: a rate of zero is a switch that has been turned off, and
 * that is something a reader needs told rather than defaulted away.
 */
export function configuredNumber(
  manifest: RunManifest,
  name: string,
): number | null {
  const value = manifest.config[name];
  return typeof value === "number" ? value : null;
}
