import { useEffect, useRef, useState } from "react";

import type { SimulationClient } from "../api/client";
import type {
  ConfigValue,
  CreateRunRequest,
  RunManifest,
} from "../api/contracts";
import {
  EXPERIMENT_DEFINITIONS,
  EXPERIMENT_METRICS,
  formatExperimentValue,
  metricValue,
  parseSeeds,
  type ExperimentDefinition,
  type ExperimentMetric,
  type PairedResult,
  summarizeExperiment,
} from "../lib/experiment";
import { scenarioName } from "../lib/format";
import { Icon } from "./Icon";

interface ExperimentWorkspaceProps {
  client: SimulationClient;
  manifest: RunManifest;
}

const MAX_STEP_TICKS = 10_000;

function overrideText(overrides: Record<string, ConfigValue>): string {
  return Object.entries(overrides)
    .map(([name, value]) => `${name}=${String(value)}`)
    .join(", ");
}

async function runArm(
  client: SimulationClient,
  base: RunManifest,
  seed: number,
  years: number,
  overrides: Record<string, ConfigValue>,
  metric: ExperimentMetric,
  cancelled: { current: boolean },
  onTicks: (ticks: number) => void,
): Promise<number> {
  const request: CreateRunRequest = {
    seed,
    scenario: base.scenario,
    config: {
      ...base.config,
      ...overrides,
    },
  };
  let runId: string | null = null;
  try {
    let session = await client.createRun(request);
    runId = session.manifest.run_id;
    const configuredTicks = session.manifest.config.ticks_per_year;
    const ticksPerYear =
      typeof configuredTicks === "number" && configuredTicks > 0
        ? configuredTicks
        : 12;
    let remaining = Math.max(1, Math.round(years * ticksPerYear));
    while (remaining > 0) {
      if (cancelled.current) {
        throw new Error("Experiment cancelled.");
      }
      const ticks = Math.min(MAX_STEP_TICKS, remaining);
      const frame = await client.step(runId, {
        ticks,
        include_resources: false,
      });
      session = { ...session, frame };
      remaining -= ticks;
      onTicks(ticks);
    }
    return metricValue(session.frame.metrics, metric);
  } finally {
    if (runId !== null) {
      try {
        await client.deleteRun(runId);
      } catch {
        // A cleanup failure must not replace the actual experiment result.
      }
    }
  }
}

export function ExperimentWorkspace({
  client,
  manifest,
}: ExperimentWorkspaceProps) {
  const [definitionId, setDefinitionId] = useState(
    EXPERIMENT_DEFINITIONS[0]?.id ?? "",
  );
  const definition =
    EXPERIMENT_DEFINITIONS.find((item) => item.id === definitionId) ??
    EXPERIMENT_DEFINITIONS[0]!;
  const [metric, setMetric] = useState<ExperimentMetric>(
    definition.suggestedMetric,
  );
  const [years, setYears] = useState(100);
  const [seedText, setSeedText] = useState("11, 23, 37");
  const [results, setResults] = useState<PairedResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ completed: 0, total: 0 });
  const cancelled = useRef(false);
  const serviceAvailable = client.source === "service";

  useEffect(
    () => () => {
      cancelled.current = true;
    },
    [],
  );

  const chooseDefinition = (next: ExperimentDefinition) => {
    setDefinitionId(next.id);
    setMetric(next.suggestedMetric);
    setResults([]);
    setError(null);
  };

  const run = async () => {
    if (!serviceAvailable || running) {
      return;
    }
    let seeds: number[];
    try {
      seeds = parseSeeds(seedText);
      if (!Number.isFinite(years) || years <= 0 || years > 10_000) {
        throw new Error("Duration must be between 1 and 10,000 years.");
      }
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Invalid experiment.");
      return;
    }

    const ticksPerYear =
      typeof manifest.config.ticks_per_year === "number"
        ? manifest.config.ticks_per_year
        : 12;
    setError(null);
    setResults([]);
    setRunning(true);
    cancelled.current = false;
    setProgress({
      completed: 0,
      total: seeds.length * 2 * years * ticksPerYear,
    });

    const nextResults: PairedResult[] = [];
    const addTicks = (ticks: number) =>
      setProgress((current) => ({
        ...current,
        completed: current.completed + ticks,
      }));

    try {
      for (const [index, seed] of seeds.entries()) {
        const controlFirst = index % 2 === 0;
        const firstOverrides = controlFirst
          ? definition.control
          : definition.treatment;
        const secondOverrides = controlFirst
          ? definition.treatment
          : definition.control;
        const first = await runArm(
          client,
          manifest,
          seed,
          years,
          firstOverrides,
          metric,
          cancelled,
          addTicks,
        );
        const second = await runArm(
          client,
          manifest,
          seed,
          years,
          secondOverrides,
          metric,
          cancelled,
          addTicks,
        );
        const control = controlFirst ? first : second;
        const treatment = controlFirst ? second : first;
        const pair = {
          seed,
          control,
          treatment,
          delta: treatment - control,
        };
        nextResults.push(pair);
        setResults([...nextResults]);
      }
    } catch (reason: unknown) {
      setError(
        reason instanceof Error ? reason.message : "The experiment stopped.",
      );
    } finally {
      setRunning(false);
    }
  };

  const summary = results.length > 0 ? summarizeExperiment(results) : null;
  let seedCount = 0;
  try {
    seedCount = parseSeeds(seedText).length;
  } catch {
    // The error is explained when the user asks to run it.
  }
  const simulatedYears = seedCount * years * 2;

  return (
    <main className="workspace experiment-workspace">
      <header className="workspace-hero">
        <div>
          <span className="eyebrow">Paired causal comparison</span>
          <h1>Experiment bench</h1>
          <p>
            Change one mechanism, hold the world and seeds constant, and see
            whether the difference repeats.
          </p>
        </div>
        <div className="workspace-hero-mark brain-mark">
          <Icon name="brain" size={26} />
        </div>
      </header>

      {!serviceAvailable ? (
        <div className="workspace-callout">
          <Icon name="spark" size={16} />
          The demo fixture cannot test hypotheses. Connect the engine service
          to run paired worlds.
        </div>
      ) : null}

      <div className="experiment-layout">
        <aside className="experiment-catalog" aria-label="Experiment catalog">
          <span className="eyebrow">Mechanism tests</span>
          <h2>Choose a question</h2>
          {EXPERIMENT_DEFINITIONS.map((item) => (
            <button
              className={item.id === definition.id ? "active" : ""}
              key={item.id}
              onClick={() => chooseDefinition(item)}
              type="button"
            >
              <Icon
                name={item.id === "maintenance" ? "activity" : "brain"}
                size={16}
              />
              <span>
                <strong>{item.name}</strong>
                <small>{item.question}</small>
              </span>
              <Icon name="chevron" size={14} />
            </button>
          ))}
        </aside>

        <section className="workspace-panel experiment-setup">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Protocol</span>
              <h2>{definition.name}</h2>
            </div>
            <span className="scenario-chip">
              <Icon name="globe" size={13} />
              {scenarioName(manifest)}
            </span>
          </div>
          <p className="experiment-question">{definition.question}</p>

          <div className="arm-grid">
            <article>
              <span>Control</span>
              <strong>{definition.controlLabel}</strong>
              <code>{overrideText(definition.control)}</code>
            </article>
            <span className="versus">vs</span>
            <article className="treatment-arm">
              <span>Treatment</span>
              <strong>{definition.treatmentLabel}</strong>
              <code>{overrideText(definition.treatment)}</code>
            </article>
          </div>

          <div className="experiment-fields">
            <label className="workspace-field">
              <span>Measure at finish</span>
              <select
                onChange={(event) =>
                  setMetric(event.target.value as ExperimentMetric)
                }
                value={metric}
              >
                {EXPERIMENT_METRICS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="workspace-field">
              <span>Years per arm</span>
              <input
                max={10_000}
                min={1}
                onChange={(event) => setYears(Number(event.target.value))}
                type="number"
                value={years}
              />
            </label>
            <label className="workspace-field seed-field">
              <span>Matched seeds</span>
              <input
                onChange={(event) => setSeedText(event.target.value)}
                placeholder="11, 23, 37"
                type="text"
                value={seedText}
              />
            </label>
          </div>

          <div className="experiment-cost">
            <Icon name="activity" size={15} />
            <span>
              {simulatedYears.toLocaleString()} total simulated years on this
              service. Three seeds are a scout; six or more are a more useful
              directional check.
            </span>
          </div>

          {running ? (
            <div className="experiment-progress" aria-live="polite">
              <span>
                Running paired worlds…{" "}
                {progress.total > 0
                  ? `${Math.min(
                      100,
                      Math.round((progress.completed / progress.total) * 100),
                    )}%`
                  : ""}
              </span>
              <div>
                <i
                  style={{
                    width: `${
                      progress.total > 0
                        ? Math.min(
                            100,
                            (progress.completed / progress.total) * 100,
                          )
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>
          ) : null}

          {error === null ? null : (
            <div className="experiment-error" role="alert">
              <Icon name="activity" size={15} />
              {error}
            </div>
          )}

          <div className="experiment-actions">
            <span>
              Temporary runs are removed after each arm. Your open Run Lab
              world is not changed.
            </span>
            {running ? (
              <button
                className="secondary-action"
                onClick={() => {
                  cancelled.current = true;
                }}
                type="button"
              >
                Cancel after step
              </button>
            ) : (
              <button
                className="primary-action"
                disabled={!serviceAvailable}
                onClick={() => void run()}
                type="button"
              >
                <Icon name="play" size={15} />
                Run experiment
              </button>
            )}
          </div>
        </section>
      </div>

      <section className="workspace-panel results-panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Evidence</span>
            <h2>Paired results</h2>
          </div>
          {summary === null ? null : (
            <span className="result-count">{results.length} matched seeds</span>
          )}
        </div>
        {summary === null ? (
          <div className="results-empty">
            <Icon name="activity" size={25} />
            <strong>No comparison yet</strong>
            <span>
              Results appear one seed-pair at a time. A mean alone is not
              treated as proof.
            </span>
          </div>
        ) : (
          <>
            <div className="result-summary">
              <article>
                <span>{definition.controlLabel}</span>
                <strong>
                  {formatExperimentValue(metric, summary.controlMean)}
                </strong>
                <small>mean control</small>
              </article>
              <article>
                <span>{definition.treatmentLabel}</span>
                <strong>
                  {formatExperimentValue(metric, summary.treatmentMean)}
                </strong>
                <small>mean treatment</small>
              </article>
              <article className={summary.meanDelta >= 0 ? "positive" : "negative"}>
                <span>Treatment delta</span>
                <strong>
                  {summary.meanDelta > 0 ? "+" : ""}
                  {formatExperimentValue(metric, summary.meanDelta)}
                </strong>
                <small>
                  higher in {summary.treatmentHigher}/{results.length}; lower
                  in {summary.controlHigher}; ties {summary.ties}
                </small>
              </article>
            </div>
            <div className="results-table-wrap">
              <table className="results-table">
                <thead>
                  <tr>
                    <th>Seed</th>
                    <th>{definition.controlLabel}</th>
                    <th>{definition.treatmentLabel}</th>
                    <th>Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((result) => (
                    <tr key={result.seed}>
                      <td>{result.seed}</td>
                      <td>{formatExperimentValue(metric, result.control)}</td>
                      <td>{formatExperimentValue(metric, result.treatment)}</td>
                      <td className={result.delta >= 0 ? "positive" : "negative"}>
                        {result.delta > 0 ? "+" : ""}
                        {formatExperimentValue(metric, result.delta)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="evidence-note">
              Direction is descriptive, not a significance claim. Extend the
              seed set and duration before changing model defaults.
            </p>
          </>
        )}
      </section>
    </main>
  );
}
