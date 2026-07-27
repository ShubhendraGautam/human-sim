import { useMemo, useState } from "react";

import {
  ApiSimulationClient,
  type SimulationClient,
} from "./api/client";
import { DemoSimulationClient } from "./api/demoClient";
import type { CreateRunRequest } from "./api/contracts";
import { EventFeedPanel } from "./components/EventFeed";
import { Icon } from "./components/Icon";
import { LayerPanel } from "./components/LayerPanel";
import { MetricStrip } from "./components/MetricStrip";
import { PersonInspector } from "./components/PersonInspector";
import { RunToolbar } from "./components/RunToolbar";
import { Timeline } from "./components/Timeline";
import {
  WorldCanvas,
  type CanvasLayerSettings,
} from "./components/WorldCanvas";
import { useRunLab } from "./hooks/useRunLab";
import { scenarioName } from "./lib/format";

// A straight channel of constant width reads as a canal, not a sea, and a
// rectangular coast makes the whole world look like a chart rather than a
// place. Scenario geometry is rectangles — that is the map format — but
// several overlapping ones cut headlands and bays into the shoreline, which
// is enough for the eye to stop seeing a diagram.
const STRAIT: [number, number, number, number][] = [
  [23, 0, 10, 30],
  [20, 2, 3, 9],
  [21, 21, 3, 7],
  [19, 12, 2, 5],
  [33, 5, 3, 6],
  [32, 17, 4, 9],
  [36, 25, 2, 5],
];

const INITIAL_REQUEST: CreateRunRequest = {
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

function makeClient(): SimulationClient {
  const demoRequested =
    new URLSearchParams(window.location.search).get("demo") === "1";
  if (demoRequested) {
    return new DemoSimulationClient();
  }
  const apiUrl = import.meta.env.VITE_SIM_API_URL;
  return new ApiSimulationClient(apiUrl ?? "");
}

function LoadingShell() {
  return (
    <main className="loading-shell" aria-live="polite">
      <span className="brand-symbol">
        <i />
        <i />
        <i />
        <i />
      </span>
      <h1>Preparing the Run Lab</h1>
      <p>Loading a versioned world observation…</p>
      <span className="loading-bar">
        <i />
      </span>
    </main>
  );
}

function AppHeader({
  runId,
  source,
}: {
  runId: string;
  source: "demo" | "service";
}) {
  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand-symbol">
          <i />
          <i />
          <i />
          <i />
        </span>
        <span>
          <strong>HUMAN</strong>
          <i>SIM</i>
        </span>
      </div>
      <nav aria-label="Primary">
        <button disabled type="button">
          Scenarios
        </button>
        <button aria-current="page" className="active" type="button">
          Run Lab
        </button>
        <button disabled type="button">
          Experiments
        </button>
      </nav>
      <div className="header-run-meta">
        <span className={`source-badge source-${source}`}>
          <span />
          {source === "demo" ? "Synthetic demo" : "Engine service"}
        </span>
        <span className="run-id">
          Run <strong>{runId}</strong>
        </span>
      </div>
    </header>
  );
}

export default function App() {
  const client = useMemo(makeClient, []);
  const { state, actions, plan, ticksPerYear } = useRunLab(
    client,
    INITIAL_REQUEST,
    import.meta.env.VITE_SIM_RUN_ID,
  );
  const [layers, setLayers] = useState<CanvasLayerSettings>({
    terrain: true,
    countries: true,
    food: true,
    materials: false,
    disease: true,
    agents: true,
    vessels: true,
    colorMode: "country",
  });

  if (
    state.loadState === "loading" ||
    state.manifest === null ||
    state.frame === null
  ) {
    if (state.loadState === "error") {
      return (
        <main className="error-shell">
          <span className="error-icon">
            <Icon name="activity" size={24} />
          </span>
          <span className="eyebrow">Connection failed</span>
          <h1>The Run Lab could not open</h1>
          <p>{state.error}</p>
          <button onClick={() => window.location.reload()} type="button">
            Try again
          </button>
        </main>
      );
    }
    return <LoadingShell />;
  }

  const { manifest, frame } = state;
  const exportUrl = manifest.capabilities.full_snapshot_export
    ? client.getExportUrl(manifest.run_id)
    : null;

  return (
    <div className="app-shell">
      <AppHeader runId={manifest.run_id} source={client.source} />
      {client.source === "demo" ? (
        <div className="demo-notice" role="status">
          <Icon name="spark" size={14} />
          Synthetic interface fixture — useful for design, never a scientific
          simulation result.
        </div>
      ) : null}
      <RunToolbar
        exportUrl={exportUrl}
        frame={frame}
        manifest={manifest}
        mutating={state.loadState === "mutating"}
        onPause={actions.pause}
        onPlay={actions.play}
        onReset={() => void actions.reset()}
        onSetPace={actions.setPace}
        onStep={() => void actions.step(1)}
        onStepYear={() => void actions.stepYear()}
        paceIndex={state.paceIndex}
        plan={plan}
        playing={state.playing}
        ticksPerYear={ticksPerYear}
      />

      {state.error === null ? null : (
        <div className="inline-error" role="alert">
          <Icon name="activity" size={15} />
          {state.error}
        </div>
      )}

      <main className="run-lab">
        <MetricStrip frame={frame} />

        <div className="lab-grid">
          <LayerPanel
            frame={frame}
            layers={layers}
            manifest={manifest}
            onColorMode={(colorMode) =>
              setLayers((current) => ({ ...current, colorMode }))
            }
            onToggle={(layer, visible) =>
              setLayers((current) => ({
                ...current,
                [layer]: visible,
              }))
            }
          />
          <section className="world-panel" aria-label="World viewport">
            <div className="world-heading">
              <div>
                <span className="eyebrow">Live observation</span>
                <h1>{scenarioName(manifest)}</h1>
              </div>
              <div className="world-heading-meta">
                <span>
                  <Icon name="waves" size={14} />
                  Sea is impassable without technology
                </span>
                <span>
                  <Icon name="seed" size={14} />
                  Deterministic seed {manifest.seed}
                </span>
              </div>
            </div>
            <WorldCanvas
              frame={frame}
              intervalMs={plan.intervalMs}
              layers={layers}
              manifest={manifest}
              onSelectAgent={actions.selectAgent}
              selectedAgentId={state.selectedAgentId}
            />
          </section>
          <PersonInspector
            detail={state.detail}
            frame={frame}
            loading={state.detailLoading}
            manifest={manifest}
            onClose={() => actions.selectAgent(null)}
            onSelectAgent={actions.selectAgent}
            selectedAgentId={state.selectedAgentId}
          />
        </div>

        <div className="lower-grid">
          <Timeline history={state.history} />
          <EventFeedPanel
            dropped={state.eventsDropped}
            events={state.events}
            onSelectAgent={actions.selectAgent}
            year={frame.year}
          />
        </div>
      </main>

      <footer className="app-footer">
        <span>
          Model {manifest.model.model_version} · Protocol{" "}
          {manifest.protocol_version}
        </span>
        <span>
          Interface controls time and starting conditions—not agent behaviour.
        </span>
      </footer>
    </div>
  );
}
