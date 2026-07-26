import type { CSSProperties } from "react";

import type { RunFrame } from "../api/contracts";
import { compact, percent, precise } from "../lib/format";
import { Icon, type IconName } from "./Icon";

interface MetricCardProps {
  accent: string;
  detail: string;
  icon: IconName;
  label: string;
  value: string;
}

function MetricCard({
  accent,
  detail,
  icon,
  label,
  value,
}: MetricCardProps) {
  return (
    <article
      className="metric-card"
      style={{ "--accent": accent } as CSSProperties}
    >
      <span className="metric-icon">
        <Icon name={icon} size={17} />
      </span>
      <div>
        <span className="metric-label">{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </article>
  );
}

export function MetricStrip({ frame }: { frame: RunFrame }) {
  const { metrics } = frame;
  const netPopulation = metrics.births - metrics.deaths;
  const infectious = metrics.disease_population.infectious ?? 0;
  return (
    <section className="metric-strip" aria-label="Current run metrics">
      <MetricCard
        accent="#f4bd68"
        detail={`${netPopulation >= 0 ? "+" : ""}${compact(netPopulation)} net`}
        icon="users"
        label="Population"
        value={compact(metrics.population)}
      />
      <MetricCard
        accent="#76c984"
        detail={`${precise(metrics.food_per_capita)} per person`}
        icon="food"
        label="Food stock"
        value={percent(metrics.resource_fraction)}
      />
      <MetricCard
        accent="#e99184"
        detail={`${compact(metrics.isolated_population)} socially isolated`}
        icon="health"
        label="Mean health"
        value={percent(metrics.mean_health_fraction)}
      />
      <MetricCard
        accent="#77b9cf"
        detail={`${compact(metrics.recoveries)} cumulative recoveries`}
        icon="activity"
        label="Infectious"
        value={compact(infectious)}
      />
      <MetricCard
        accent="#b89ce8"
        detail={`${percent(metrics.mean_heterozygosity)} heterozygosity`}
        icon="brain"
        label="Diversity"
        value={percent(metrics.genetic_diversity)}
      />
    </section>
  );
}
