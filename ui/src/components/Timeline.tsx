import { useMemo } from "react";

import type { TimelinePoint } from "../api/contracts";
import { compact, precise } from "../lib/format";
import { Icon } from "./Icon";

interface TimelineProps {
  history: TimelinePoint[];
}

const WIDTH = 1000;
const HEIGHT = 130;
const PADDING_X = 18;
const PADDING_TOP = 12;
const PADDING_BOTTOM = 23;

function linePath(
  values: number[],
  minimum: number,
  maximum: number,
): string {
  const range = Math.max(0.0001, maximum - minimum);
  return values
    .map((value, index) => {
      const x =
        PADDING_X +
        (index / Math.max(1, values.length - 1)) *
          (WIDTH - PADDING_X * 2);
      const y =
        PADDING_TOP +
        (1 - (value - minimum) / range) *
          (HEIGHT - PADDING_TOP - PADDING_BOTTOM);
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

export function Timeline({ history }: TimelineProps) {
  const paths = useMemo(() => {
    const population = history.map((point) => point.population);
    const minimumPopulation = Math.min(...population, 0);
    const maximumPopulation = Math.max(...population, 1);
    const populationPadding = Math.max(
      2,
      (maximumPopulation - minimumPopulation) * 0.15,
    );
    const populationLine = linePath(
      population,
      Math.max(0, minimumPopulation - populationPadding),
      maximumPopulation + populationPadding,
    );
    const area = `${populationLine} L${WIDTH - PADDING_X},${HEIGHT - PADDING_BOTTOM} L${PADDING_X},${HEIGHT - PADDING_BOTTOM} Z`;
    return {
      populationLine,
      populationArea: area,
      foodLine: linePath(
        history.map((point) => point.food),
        0,
        1,
      ),
      healthLine: linePath(
        history.map((point) => point.health),
        0,
        1,
      ),
    };
  }, [history]);

  const first = history[0];
  const last = history.at(-1);

  return (
    <section className="timeline-panel" aria-label="Run timeline">
      <div className="timeline-heading">
        <div>
          <span className="eyebrow">Local observation buffer</span>
          <h2>Run trace</h2>
        </div>
        {/*
          Each swatch carries the series colour and its dash pattern. The
          colour alone was doing all the work of telling three lines apart,
          which is exactly the reading a red-green colourblind viewer cannot
          make — gold against green is the closest pair on the chart.
        */}
        <div className="timeline-legend" aria-label="Chart legend">
          <span className="legend-population">
            <i />
            Population
          </span>
          <span className="legend-food">
            <i />
            Food
          </span>
          <span className="legend-health">
            <i />
            Health
          </span>
        </div>
      </div>
      <div className="timeline-chart">
        <svg
          aria-label="Population, food capacity, and mean health over observed frames"
          preserveAspectRatio="none"
          role="img"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        >
          <defs>
            <linearGradient id="population-area" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#efbb68" stopOpacity="0.22" />
              <stop offset="100%" stopColor="#efbb68" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0.25, 0.5, 0.75].map((fraction) => (
            <line
              className="chart-gridline"
              key={fraction}
              x1={PADDING_X}
              x2={WIDTH - PADDING_X}
              y1={
                PADDING_TOP +
                fraction * (HEIGHT - PADDING_TOP - PADDING_BOTTOM)
              }
              y2={
                PADDING_TOP +
                fraction * (HEIGHT - PADDING_TOP - PADDING_BOTTOM)
              }
            />
          ))}
          {history.length > 1 ? (
            <>
              <path
                className="population-area"
                d={paths.populationArea}
              />
              <path
                className="population-line"
                d={paths.populationLine}
              />
              <path className="food-line" d={paths.foodLine} />
              <path className="health-line" d={paths.healthLine} />
            </>
          ) : null}
          <line
            className="playhead-line"
            x1={WIDTH - PADDING_X}
            x2={WIDTH - PADDING_X}
            y1={PADDING_TOP}
            y2={HEIGHT - PADDING_BOTTOM}
          />
          <circle
            className="playhead-dot"
            cx={WIDTH - PADDING_X}
            cy={PADDING_TOP + 2}
            r="3.5"
          />
          <text className="axis-label" x={PADDING_X} y={HEIGHT - 5}>
            {first === undefined ? "Tick 0" : `Tick ${first.tick}`}
          </text>
          <text
            className="axis-label axis-label-end"
            x={WIDTH - PADDING_X}
            y={HEIGHT - 5}
          >
            {last === undefined ? "Tick 0" : `Tick ${last.tick}`}
          </text>
        </svg>
      </div>
      <div className="timeline-footer">
        <span>
          <Icon name="users" size={13} />
          {last === undefined ? "—" : compact(last.population)} living
        </span>
        <span>
          <Icon name="seed" size={13} />
          {last === undefined ? "—" : `Year ${precise(last.year)}`}
        </span>
        <span>
          <Icon name="activity" size={13} />
          {last === undefined ? "—" : compact(last.infectious)} infectious
        </span>
        <span className="timeline-buffer">
          {history.length} / 180 frames retained
        </span>
      </div>
    </section>
  );
}
