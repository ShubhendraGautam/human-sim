# Human-Sim Run Lab

The Run Lab is the browser instrument for observing one deterministic
Human-Sim run. React owns controls and view state; one Canvas 2D renderer paints
the world and every person without creating a DOM node per agent.

The UI can choose initial conditions and control time. It never chooses agent
actions or writes into causal simulation state.

## Stack

- React 19 with strict TypeScript
- Vite 8
- Native `fetch`, Canvas 2D, and SVG
- React reducer/hooks for local state
- Vitest for contract, reducer, and geometry tests

React and React DOM are the only runtime dependencies. There is no router,
state framework, chart package, UI kit, or renderer dependency.

Node 24 or newer is required.

## Run against the simulation service

From the repository root, install the optional Python transport dependencies
and launch the API:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-api.txt
.venv/bin/python -m uvicorn \
  src.human_sim_service.api:create_app --factory --reload
```

In another terminal:

```bash
cd ui
npm ci
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`. The UI creates the included
two-islands scenario at seed `42`, then advances the real Python engine with
the versioned REST service.

Set `VITE_SIM_API_URL` when the API is hosted elsewhere. Set
`VITE_SIM_RUN_ID` to open an existing run instead of creating one.

## Explicit synthetic mode

Open `http://localhost:5173/?demo=1` to use the deterministic UI fixture. It is
visibly labelled **Synthetic demo**, is not exportable, and is never presented
as a scientific simulation result. There is no automatic fallback from a
failed service connection to synthetic data.

## Commands

```bash
npm run dev
npm run typecheck
npm test
npm run build
npm run preview
```

## Source boundaries

```text
src/api/contracts.ts       versioned service payloads
src/api/client.ts          real HTTP client boundary
src/api/demoClient.ts      explicitly selected synthetic fixture
src/state/                 ordered-frame reducer
src/hooks/                 lifecycle and local playback scheduling
src/components/            Run Lab views and Canvas renderer
src/lib/                   formatting and testable world geometry
```

`RunManifest` caches static scenario and world layers. Repeated `RunFrame`
payloads contain compact columnar people, metrics, and optional dynamic
resources. Selecting a person fetches `AgentDetail` separately, keeping genome,
relationship, and preference data out of routine render frames.

The bounded client timeline is an observation convenience, not an experiment
record. Exact experiment output belongs in a simulation metrics sink.
