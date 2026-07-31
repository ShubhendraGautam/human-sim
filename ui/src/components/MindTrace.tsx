import { useMemo, useState, type PointerEvent } from "react";

import type { RunFrame, RunManifest, TimelinePoint } from "../api/contracts";
import {
  changePercent,
  compact,
  configuredNumber,
  fine,
  percent,
  precise,
} from "../lib/format";
import { Icon } from "./Icon";

interface MindTraceProps {
  frame: RunFrame;
  manifest: RunManifest;
  /** One point per simulated year, oldest first. */
  yearly: TimelinePoint[];
}

const WIDTH = 1000;
const HEIGHT = 148;
const PADDING_X = 20;
const PADDING_TOP = 14;
const PADDING_BOTTOM = 24;
const PLOT_HEIGHT = HEIGHT - PADDING_TOP - PADDING_BOTTOM;

interface Scale {
  minimum: number;
  maximum: number;
  x: (year: number) => number;
  y: (value: number) => number;
}

function buildScale(points: TimelinePoint[]): Scale {
  const values = points.map((point) => point.mind);
  const low = Math.min(...values);
  const high = Math.max(...values);
  // A flat line is a real answer — nothing changed — and it should sit in
  // the middle of the plot rather than being stretched to fill it, which
  // would turn rounding noise into a dramatic climb.
  const span = Math.max(high - low, Math.max(high, 0.001) * 0.2);
  const middle = (high + low) / 2;
  const minimum = Math.max(0, middle - span * 0.75);
  const maximum = middle + span * 0.75;
  const firstYear = points[0]?.year ?? 0;
  const lastYear = points.at(-1)?.year ?? firstYear;
  const yearSpan = Math.max(0.0001, lastYear - firstYear);
  return {
    minimum,
    maximum,
    x: (year) =>
      PADDING_X + ((year - firstYear) / yearSpan) * (WIDTH - PADDING_X * 2),
    y: (value) =>
      PADDING_TOP +
      (1 - (value - minimum) / Math.max(0.0001, maximum - minimum)) *
        PLOT_HEIGHT,
  };
}

/**
 * How strong the population's inherited brains have become, over the run.
 *
 * The single measure plotted is the mean absolute weight of the inherited
 * network — what the engine actually records about a brain. It is not a
 * score of intelligence and nothing in the simulation reads it; a rising
 * line says having a strong opinion started paying off in this world, and a
 * falling one says it stopped. Because it is one measure it gets one axis
 * and one colour, and everything else in the panel is stated as a number
 * rather than crowded onto the same scale.
 *
 * The series is sampled once per simulated year and starts when this
 * interface opened the run, not when the run began — an observation cannot
 * report years nobody was watching, so the panel says which year it starts
 * from instead of implying it has the whole history.
 */
export function MindTrace({ frame, manifest, yearly }: MindTraceProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const points = useMemo(
    () => yearly.filter((point) => Number.isFinite(point.mind)),
    [yearly],
  );
  const scale = useMemo(() => buildScale(points), [points]);

  const path = useMemo(() => {
    if (points.length < 2) {
      return null;
    }
    const line = points
      .map(
        (point, index) =>
          `${index === 0 ? "M" : "L"}${scale.x(point.year).toFixed(2)},${scale
            .y(point.mind)
            .toFixed(2)}`,
      )
      .join(" ");
    const lastX = scale.x(points.at(-1)?.year ?? 0).toFixed(2);
    const firstX = scale.x(points[0]?.year ?? 0).toFixed(2);
    const base = (HEIGHT - PADDING_BOTTOM).toFixed(2);
    return {
      line,
      area: `${line} L${lastX},${base} L${firstX},${base} Z`,
    };
  }, [points, scale]);

  const first = points[0];
  const last = points.at(-1);
  const hovered =
    hoverIndex === null ? undefined : points[hoverIndex];
  const shown = hovered ?? last;
  const growth =
    first === undefined || last === undefined
      ? null
      : changePercent(first.mind, last.mind);
  const plasticityRate = configuredNumber(manifest, "plasticity_rate");
  const learningOff = plasticityRate !== null && plasticityRate <= 0;
  const policyTeachingRate = configuredNumber(
    manifest,
    "policy_teaching_rate",
  );
  const policyTeachingOn =
    policyTeachingRate !== null && policyTeachingRate > 0;

  const readPointer = (event: PointerEvent<SVGSVGElement>): void => {
    if (points.length === 0) {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / Math.max(1, rect.width);
    const target =
      (first?.year ?? 0) +
      ratio * ((last?.year ?? 0) - (first?.year ?? 0));
    let closest = 0;
    for (let index = 1; index < points.length; index += 1) {
      const candidate = points[index];
      const best = points[closest];
      if (
        candidate !== undefined &&
        best !== undefined &&
        Math.abs(candidate.year - target) < Math.abs(best.year - target)
      ) {
        closest = index;
      }
    }
    setHoverIndex(closest);
  };

  return (
    <section className="timeline-panel mind-panel" aria-label="Minds over time">
      <div className="timeline-heading">
        <div>
          <span className="eyebrow">
            {first === undefined
              ? "Observed from this run"
              : `Observed from year ${precise(first.year)} · one point a year`}
          </span>
          <h2>Minds</h2>
        </div>
        <div className="mind-readout">
          <strong>{fine(shown?.mind ?? frame.metrics.mean_network_magnitude)}</strong>
          <small>
            {hovered === undefined
              ? "mean inherited weight"
              : `mean weight in year ${precise(hovered.year)}`}
          </small>
        </div>
      </div>

      <p className="mind-sentence">
        {growth === null || first === undefined || last === undefined ? (
          <>
            Not enough of the run has been watched yet to say whether minds
            are getting stronger.
          </>
        ) : (
          <>
            Inherited brains are{" "}
            <strong>{growth}</strong> over{" "}
            {precise(Math.max(0, last.year - first.year))} years watched —
            mean absolute network weight, which is what the engine measures of
            a brain, not a score of intelligence.
          </>
        )}
      </p>

      <div className="timeline-chart">
        <svg
          aria-label={
            first === undefined || last === undefined
              ? "Mean inherited network weight; no years observed yet"
              : `Mean inherited network weight from year ${precise(first.year)} to ${precise(last.year)}, ${fine(first.mind)} to ${fine(last.mind)}`
          }
          onPointerLeave={() => setHoverIndex(null)}
          onPointerMove={readPointer}
          preserveAspectRatio="none"
          role="img"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        >
          <defs>
            <linearGradient id="mind-area" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#bb9ee3" stopOpacity="0.2" />
              <stop offset="100%" stopColor="#bb9ee3" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0, 0.5, 1].map((fraction) => (
            <line
              className="chart-gridline"
              key={fraction}
              x1={PADDING_X}
              x2={WIDTH - PADDING_X}
              y1={PADDING_TOP + fraction * PLOT_HEIGHT}
              y2={PADDING_TOP + fraction * PLOT_HEIGHT}
            />
          ))}
          {path === null ? null : (
            <>
              <path className="mind-area" d={path.area} />
              <path className="mind-line" d={path.line} />
            </>
          )}
          {hovered === undefined ? null : (
            <>
              <line
                className="chart-crosshair"
                x1={scale.x(hovered.year)}
                x2={scale.x(hovered.year)}
                y1={PADDING_TOP}
                y2={HEIGHT - PADDING_BOTTOM}
              />
              <circle
                className="mind-dot"
                cx={scale.x(hovered.year)}
                cy={scale.y(hovered.mind)}
                r="4"
              />
            </>
          )}
          {last === undefined || hovered !== undefined ? null : (
            <circle
              className="mind-dot"
              cx={scale.x(last.year)}
              cy={scale.y(last.mind)}
              r="3.5"
            />
          )}
          <text className="axis-label" x={PADDING_X} y={HEIGHT - 6}>
            {first === undefined ? "Year 0" : `Year ${precise(first.year)}`}
          </text>
          <text
            className="axis-label axis-label-end"
            x={WIDTH - PADDING_X}
            y={HEIGHT - 6}
          >
            {last === undefined ? "Year 0" : `Year ${precise(last.year)}`}
          </text>
          <text className="axis-label" x={PADDING_X} y={PADDING_TOP - 3}>
            {fine(scale.maximum)}
          </text>
        </svg>
      </div>

      <div className="timeline-footer">
        <span>
          <Icon name="brain" size={13} />
          {learningOff
            ? "Lifetime learning off"
            : `${fine(frame.metrics.mean_plasticity)} learned in life`}
        </span>
        <span>
          <Icon name="spark" size={13} />
          {fine(frame.metrics.policy_diversity)} policy spread
        </span>
        <span>
          <Icon name="users" size={13} />
          {precise(frame.metrics.mean_vocabulary)} words ·{" "}
          {compact(frame.metrics.inventions)} inventions
        </span>
        {policyTeachingOn ? (
          <span>
            <Icon name="users" size={13} />
            {compact(frame.metrics.taught_policy_population)} taught ·{" "}
            {compact(frame.metrics.taught_policy_lineages)} policy lineages
          </span>
        ) : null}
        <span className="timeline-buffer">
          {percent(frame.metrics.action_entropy)} action variety
        </span>
      </div>

      {learningOff ? (
        <p className="mind-note">
          <Icon name="spark" size={13} />
          This run has <code>plasticity_rate</code> at zero, so nobody learns
          within their own lifetime. Anything the line does is inheritance and
          selection between generations, not practice.
        </p>
      ) : null}
    </section>
  );
}
