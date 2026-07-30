import { useMemo, useState } from "react";

import {
  ApiSimulationClient,
  type SimulationClient,
} from "./api/client";
import { DemoSimulationClient } from "./api/demoClient";
import type { CreateRunRequest } from "./api/contracts";
import { EventFeedPanel } from "./components/EventFeed";
import { ExperimentWorkspace } from "./components/ExperimentWorkspace";
import { Icon } from "./components/Icon";
import { LayerPanel } from "./components/LayerPanel";
import { MetricStrip } from "./components/MetricStrip";
import { MindTrace } from "./components/MindTrace";
import { PersonInspector } from "./components/PersonInspector";
import { RunToolbar } from "./components/RunToolbar";
import { ScenarioWorkspace } from "./components/ScenarioWorkspace";
import { Timeline } from "./components/Timeline";
import {
  WorldCanvas,
  type CanvasLayerSettings,
} from "./components/WorldCanvas";
import { useRunLab } from "./hooks/useRunLab";
import { scenarioName } from "./lib/format";
import { INITIAL_REQUEST } from "./lib/scenarios";

type WorkspaceView = "scenarios" | "run" | "experiments";

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
  view,
  onView,
}: {
  runId: string;
  source: "demo" | "service";
  view: WorkspaceView;
  onView(view: WorkspaceView): void;
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
        <button
          aria-current={view === "scenarios" ? "page" : undefined}
          className={view === "scenarios" ? "active" : ""}
          onClick={() => onView("scenarios")}
          type="button"
        >
          Scenarios
        </button>
        <button
          aria-current={view === "run" ? "page" : undefined}
          className={view === "run" ? "active" : ""}
          onClick={() => onView("run")}
          type="button"
        >
          Run Lab
        </button>
        <button
          aria-current={view === "experiments" ? "page" : undefined}
          className={view === "experiments" ? "active" : ""}
          onClick={() => onView("experiments")}
          type="button"
        >
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
  const { state, actions, plan, serverDriven, ticksPerYear } = useRunLab(
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
    fauna: true,
    vessels: true,
    colorMode: "country",
  });
  const [view, setView] = useState<WorkspaceView>("run");

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
      <AppHeader
        onView={setView}
        runId={manifest.run_id}
        source={client.source}
        view={view}
      />
      {client.source === "demo" ? (
        <div className="demo-notice" role="status">
          <Icon name="spark" size={14} />
          Synthetic interface fixture — useful for design, never a scientific
          simulation result.
        </div>
      ) : null}
      {view === "scenarios" ? (
        <ScenarioWorkspace
          baseRequest={{
            seed: manifest.seed,
            config: manifest.config,
            scenario: manifest.scenario,
          }}
          client={client}
          onLaunch={async (request: CreateRunRequest) => {
            const opened = await actions.createRun(request);
            if (opened) {
              setView("run");
            }
            return opened;
          }}
        />
      ) : null}
      {view === "experiments" ? (
        <ExperimentWorkspace client={client} manifest={manifest} />
      ) : null}
      {view === "run" ? (
        <>
      <RunToolbar
        enginePlayback={state.enginePlayback}
        exportUrl={exportUrl}
        frame={frame}
        manifest={manifest}
        mutating={state.loadState === "mutating"}
        onNewRun={() => void actions.newRun()}
        onPause={actions.pause}
        onPlay={actions.play}
        onReset={() => void actions.reset()}
        onSetPace={actions.setPace}
        onStep={() => void actions.step(1)}
        onStepYear={() => void actions.stepYear()}
        paceIndex={state.paceIndex}
        plan={plan}
        playing={state.playing}
        serverDriven={serverDriven}
        ticksPerYear={ticksPerYear}
      />

      {state.notice === null ? null : (
        <div className="inline-notice" role="status">
          <Icon name="spark" size={15} />
          {state.notice}
        </div>
      )}

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
          <div className="trace-column">
            <Timeline history={state.history} />
            <MindTrace
              frame={frame}
              manifest={manifest}
              yearly={state.yearly}
            />
          </div>
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
        </>
      ) : (
        <footer className="app-footer">
          <span>
            Model {manifest.model.model_version} · Protocol{" "}
            {manifest.protocol_version}
          </span>
          <span>
            Scenarios set initial conditions; experiments compare mechanisms.
          </span>
        </footer>
      )}
    </div>
  );
}
