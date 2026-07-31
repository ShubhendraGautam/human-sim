# UI and service architecture

## Purpose

The UI is an experimental instrument for Human-Sim. It should make a run
observable, reproducible, and comparable without becoming a second source of
simulation rules.

The central rule is:

> The UI may choose starting conditions and control the clock; it must never
> choose an agent's action or write directly into causal agent state.

Scenario editing therefore creates a new set of initial conditions. Run
controls start, pause, step, reset, or stop an engine. Everything displayed
during a run is an observation produced by the engine.

This document describes the target architecture and the contracts that the
current foundations are being built around. A listed contract or milestone is
not, by itself, a claim that its HTTP endpoint, streaming path, persistence, or
large-world optimization is already implemented.

The repository currently contains the synchronous service/session foundation,
its optional REST adapter, autonomous playback, safe resumable checkpoints,
and a frontend foundation with both service and explicitly synthetic demo
clients. WebSocket streaming, worker processes, viewport aggregation, and a
browser experiment workspace remain milestones.

## Technology choices

| Area | Choice | Reason |
| --- | --- | --- |
| Simulation | Python 3.10+ reference engine | Keeps the model readable, deterministic, and covered by the existing invariant tests. |
| Service core | Pure-standard-library `human_sim_service` package | Run ownership, validation, and projections remain usable from tests, a CLI, or any transport without requiring a web framework. |
| Service transport | Versioned REST, with FastAPI 0.139 and Uvicorn as an optional thin adapter | Provides typed request validation and a later WebSocket route without coupling either dependency to the simulation. |
| Browser application | React 19.2.8 and strict TypeScript 7.0.2 | Gives explicit component boundaries and compile-time checking of the service contract. |
| Build tooling | Vite 8.1.5 | Keeps the client a conventional static application with a fast local build. |
| World renderer | Native Canvas 2D behind a small renderer interface | Avoids one DOM node per cell or person and leaves room for an OffscreenCanvas or WebGL implementation without rewriting React components. |
| Client state | React reducer and focused hooks | Run state transitions remain explicit without introducing a second general-purpose state system. |
| Network | Native `fetch` and `WebSocket` | The protocol is small enough that an additional data-fetching library would add more policy than value in the first milestones. |
| Charts | Small SVG components initially | Current charts are simple bounded time series; a chart framework can be selected later from demonstrated needs. |
| Frontend tests | TypeScript checks and Vitest | Contract, reducer, projection, and renderer tests can run without a browser-driven end-to-end suite. |

There is intentionally no router, UI kit, chart framework, or global state
framework in the first Run Lab. Those are reversible additions. The service
contract, engine boundary, and renderer boundary are the long-lived choices.

Server-side rendering is not needed: this is an interactive simulation lab,
not an indexable content site. The built frontend can be served as static
files independently of the simulation service.

## Ownership boundaries

```text
React views
    |
    v
run reducer + hooks -----> Canvas2D renderer
    |
    v
SimulationClient
    |                    local development
    +---- HTTP / WS ------------------------------+
    |                                             |
    +---- synthetic DemoClient                    v
                                      transport adapter
                                                 |
                                                 v
                                      RunManager / RunSession
                                                 |
                                                 v
                                         SimulationBackend
                                           |           |
                                           v           v
                                    Python reference  future native
                                       Simulation       backend
```

The boundaries have deliberately narrow responsibilities:

- `src.simulation` owns all causal state, the random generator, tick ordering,
  and model validation. It knows nothing about HTTP, React, frame rates, or
  wall-clock time.
- `human_sim_service` owns run identity, serialized commands, lifecycle state,
  backend selection, and UI projections. Its core does not require FastAPI.
- The transport adapter maps HTTP or WebSocket messages to service operations.
  It contains no model formulas and does not reach into `Simulation.agents`.
- `SimulationClient` is the browser's only data source. React components do
  not parse engine snapshots or construct URLs.
- The reducer owns browser application state. Camera position, selected layer,
  selected person, and open panels are view state and never enter the engine.
- The Canvas renderer receives already-normalized render columns. It does not
  own the run or issue simulation commands.

The browser may use a clearly labelled synthetic demo client while frontend
work proceeds independently. Demo data is not a scientific result and must
never be exportable or presented as a real run.

## Data flow

1. The browser creates a run from a complete scenario, configuration, and
   explicit integer seed.
2. The service validates those inputs and constructs one backend instance.
3. The browser receives a run manifest. Static world layers are cached for the
   life of that run.
4. A step command is serialized with every other mutating command for the same
   run. The backend advances a requested number of ticks synchronously.
5. The service projects the new engine state into a compact render frame.
6. React updates metrics and controls; the renderer paints the latest accepted
   frame without turning agents into React elements.
7. Selecting a person triggers a separate detail request. Relationship and
   biological detail are not part of routine render frames.
8. Full schema-3 `Simulation.snapshot()` output is available as an explicit
   export, not as the live transport format.

Commands and observations must carry a `run_id`. Streaming observations also
carry a monotonically increasing `sequence`; a client discards a response from
an older run or an older sequence. A detail response carries its source tick,
so the inspector can mark it stale rather than silently combining states from
different ticks.

## Who owns the clock

A run may be advanced by whoever is watching it, or by the engine itself.
Both are supported, and which one is in force is a property of the run rather
than of the client: `capabilities.playback` says the engine can hold the
clock, and `playback.playing` says whether it currently is.

Engine-driven is the mode that matters for anything long. A run set going
through `POST /runs/{id}/playback` advances in a driver thread inside the
service, paced by wall-clock seconds per simulated year, and keeps advancing
with no client attached at all — which is the only arrangement in which a
world can be left evolving for days and looked at afterwards. A client then
*reads* frames rather than requesting steps, so two browsers can watch one
world and closing either changes nothing.

Client-driven playback remains for backends that cannot hold a clock, such as
the synthetic fixture. There the browser timer is what makes time pass, and
the world stops when the tab does.

Three rules keep the two honest:

- **The engine's account wins.** A client shows Pause for a run it finds
  already running, and adopts that run's pace instead of imposing its own —
  attaching to a world must not change it.
- **Stopping is synchronous.** `playing: false` returns once the batch in
  flight has finished, so the tick it reports is the tick the run is on and a
  subsequent manual step lands where the caller expects.
- **One clock at a time.** Stepping by hand is refused while the engine is
  driving, rather than interleaving two sources of time on one world.

Active runs are held in memory and periodically written as atomic resumable
checkpoints. A clean shutdown saves once more; startup restores every saved
run paused. Reattaching therefore survives UI and engine restarts without
silently starting the simulation clock. `GET /snapshot` remains an analysis
export and must not be used for rehydration.

## Versioned UI contracts

The UI protocol has its own `protocol_version` and projection
`schema_version`. It also reports the engine's model, snapshot, checkpoint,
configuration, and genome versions. These numbers answer different
compatibility questions and must not be collapsed into one value. Manifest,
frame, and agent-detail schemas are versioned independently, and they have
already diverged: the manifest is at 2, the event feed at 1, the frame started
carrying the herd at 2 and is now at 5 after environmental, artifact, and
policy-transmission metrics, while agent detail is at 3 (it carries both a
biography for the dead and cultural policy lineage).

A client therefore states which versions of each kind it can read, not one
version for everything. Collapsing them into a single constant makes an
ordinary additive change to one message reject every message of another kind —
which is how a UI ends up reporting that every person it asks about no longer
exists.

All envelopes have this common identity:

```ts
interface ProtocolEnvelope {
  protocol_version: number;
  schema_version: number;
  kind: string;
  run_id: string;
  sequence: number;
  status: "paused" | "stepping" | "running" | "stopped" | "failed";
}
```

Unknown fields should be ignored within a supported schema version. A breaking
rename, type change, or semantic change increments `schema_version`. An
unsupported version fails visibly; it must not be guessed at by the client.

### Run manifest

A manifest is sent once when a run is loaded and again after a reset. It
contains:

- Run identity, lifecycle status, seed, tick, year, and population.
- `model_version`, `snapshot_schema_version`, `config_schema_version`, and
  `genome_schema_version`.
- The complete normalized configuration and scenario.
- Capabilities such as stepping, reset, agent detail, dynamic resource layers,
  and full snapshot export.
- Static row-major world arrays: dimensions, wrapping, terrain, country,
  capacity, productivity, and seasonal layers.

Static layers do not belong in every frame. For a world of width `w` and height
`h`, every world array must contain exactly `w * h` values, with cell
`(x, y)` at `y * w + x`. Terrain uses the engine values `0` for land and `1`
for sea. A cell not assigned to a country uses `-1`.

The manifest is a description of an instantiated run, not a resumable
checkpoint.

### Render frame

A frame is optimized for repeated observation:

```ts
interface RunFrame extends ProtocolEnvelope {
  kind: "render_frame";
  tick: number;
  year: number;
  metrics: SimulationMetrics;
  agents: AgentColumns;
  /** Always present from frame schema 2; absent in schema 1. */
  fauna: FaunaColumns;
  resources?: {
    food: number[];
    materials: number[];
  };
}
```

`AgentColumns` is a structure of arrays. Every column has the same length as
`id`; columns include render-relevant values such as position, birth country,
belief, age, normalized energy and health, body condition, frailty, brain
kind, last action, infection stage, learned techniques, and seafaring/vessel
state. IDs are strings at the service boundary so a future native or
partitioned backend is not restricted by JavaScript's safe-integer range.

`FaunaColumns` is the same arrangement for animals, and deliberately separate
rather than more agent columns. Animals are a different kind of thing, they
turn over far faster than people, and a client that only draws people should
not have to receive a herd to discover that. It carries position, energy and
vigilance only — an animal has no identity worth inspecting the way a person
does, so there is no per-animal detail endpoint.

Dynamic food and material layers are optional. The client requests them only
while a resource layer is visible or at a lower sampling cadence. Metrics are
aggregate observer results from the engine. Map-like metric keys are JSON
strings even when the underlying country or belief ID is numeric.

A frame is complete for its tick; it is not a delta that depends on receiving
every previous frame. This makes dropping intermediate frames safe.

### Agent detail

Agent detail is fetched on selection and contains:

- Identity and lineage: birth country, belief, reproductive role, generation,
  parents, and guardian.
- Location and life state: age, absolute and normalized energy and health,
  inventories, body condition, development, and frailty.
- Expressed biology, brain kind and learned preferences, culture, disease, and
  technology state.
- The selected agent's bounded directed relationship records: other ID, trust,
  reciprocity balance, encounter count, and last-seen tick.

It is an observation at a stated tick. If the person dies before a later
request, the service returns a normal not-found/gone result and the UI keeps
only a labelled historical selection. Detail has no update operation.

### Full snapshot export

The existing schema-5 visualization snapshot remains useful for recording,
offline analysis, and bug reports. It is larger than a frame and may contain
the entire world, every causal agent column, pregnancies, and all retained
relationship edges.

It is explicitly `snapshot_kind: "visualization"`. It lacks resolver random
state and allocation details, so neither service nor UI may advertise it as a
save game. The separate checkpoint contract includes the RNG, identity
high-water mark, raw relationship slot order, mutable layers, causal entity
state, and bounded histories. JSON round-trip and future-trajectory tests are
the acceptance boundary.

## Run lifecycle and command semantics

The public states are:

- `paused`: the backend exists and accepts `step` or `reset`; no autonomous
  clock is advancing it.
- `stepping`: a synchronous mutation owns the per-run lock. A successful step
  or reset returns to `paused`.
- `failed`: the worker or backend failed. The error is observable, and no
  implicit reset hides it.
- `running`: an autonomous runner may schedule batches. It is reserved for the
  worker/streaming milestone.
- `stopped`: the run no longer advances. It is also reserved for that
  milestone; whether its observations remain readable will be a service
  retention policy.

Creation produces a paused run at tick zero. `step(n)` is atomic from another
command's perspective: ticks `1..n` execute in order, then one resulting frame
is published. `n` must be positive; the current REST adapter caps one request
at 10,000 ticks.

`reset` reconstructs the backend from the run's original normalized
configuration, scenario, and seed. Reset is not mutation in reverse, and it
must reproduce the original tick-zero state. It increments the observation
sequence, invalidating outstanding detail requests and cached frames.

Mutating commands for a run are serialized. Duplicate network retries must not
silently step twice; the HTTP layer should add an idempotency key or reject
ambiguous retries before remote multi-user deployment. Different runs may
advance concurrently. A failed run rejects further steps until an explicit
reset successfully reconstructs it.

The synchronous `/api/v1` adapter maps these operations as follows:

| Method and path | Result |
| --- | --- |
| `GET /health` | Protocol version and service health. |
| `GET /catalog/config` | Configuration schema version and engine defaults. |
| `POST /scenarios/validate` | Engine-validated, normalized configuration and scenario. |
| `GET /runs` | Current in-memory run manifests. |
| `POST /runs` | Create a paused run and return its manifest. |
| `GET /runs/{run_id}/manifest` | Fetch static run metadata and world layers. |
| `GET /runs/{run_id}/frame` | Fetch the latest frame, optionally with resources. |
| `POST /runs/{run_id}/steps` | Advance a bounded positive tick count and return one frame. |
| `POST /runs/{run_id}/reset` | Reconstruct the run and return its tick-zero frame. |
| `GET /runs/{run_id}/agents/{agent_id}` | Fetch current detail for one living person. |
| `GET /runs/{run_id}/snapshot` | Export the full visualization snapshot. |

The health path above, for example, means `/api/v1/health`. The adapter is
optional; the service package itself stays independent of FastAPI. There is no
WebSocket route or autonomous server-side clock yet. Its run registry is
in-memory and unauthenticated, so the current server is a local-development
surface rather than a public multi-user deployment.

## Information architecture

The product navigation has three stable areas:

- **Scenarios** — presets and a visual editor cover validated dimensions,
  rectangular countries/seas, founder populations, cultural distributions,
  and resource multipliers. Validation creates a new immutable run; editing
  never changes a live one. JSON import/export and scenario comparison remain
  later additions.
- **Run Lab** — operate and inspect one reproducible run.
- **Experiments** — the first connected bench runs paired control/treatment
  seeds on the current scenario, reports raw end-metric deltas and directional
  agreement, and deletes its temporary runs. Population/scale sweeps, series
  export, revision metadata, and a durable result store remain later work.

The Run Lab desktop layout is:

```text
+--------------------------------------------------------------------------+
| Human-Sim | Scenarios | Run Lab | Experiments       run/seed/status      |
+--------------------------------------------------------------------------+
| scenario | seed | reset | tick | year | play/pause | pace | tick / year  |
+--------------------------------------------------------------------------+
| population | food | health | births/deaths | infection | diversity      |
+-------------+--------------------------------------+---------------------+
| Layers      |                                      | Person              |
|             |          Canvas world                | identity / life     |
| Terrain     |          pan / zoom                  | biology / brain     |
| Countries   |          hover / select              | culture / disease   |
| Resources   |                                      | relationships       |
| Disease     |                                      |                     |
| Actions     |                                      |                     |
+-------------+--------------------------------------+---------------------+
| bounded timeline: population / resources / health / disease | events     |
| minds: inherited network weight, one point a year           |            |
+--------------------------------------------------------------------------+
```

Two time scales sit below the world, because the questions asked of a run have
two scales. The bounded timeline is a frame buffer a few minutes deep and
answers what is happening now. Anything that moves over generations — how
strong inherited brains have become, whether policies are still diverse — is
invisible in that window, so it is sampled once per simulated year and kept
for the whole session. Each chart carries one scale; a second measure of a
different magnitude gets its own chart rather than a second axis.

On narrower screens, layers and person detail become drawers while the world
remains primary. Keyboard and pointer interaction must both support layer
selection and run controls. Color is never the only encoding for sea, disease,
or selection, and legends always show units or normalization.

The toolbar always displays seed, tick, year, and status. A reset or scenario
change requires a clear run boundary in the timeline.

Playback is paced in real time per simulated year rather than in ticks per
second, because the quantity a viewer cares about is how long a year takes to
watch, not how often the browser polls. The control spans thirty real minutes
per simulated year to unpaced, defaulting to ten minutes; the pace determines
both the request size and the delay between requests, and slow paces always
request one tick at a time so no causal round is hidden inside a batch. Pacing
is local: it changes when the browser asks the engine to advance, never how
the engine advances, so every pace produces the same history. Because a single
tick can then last a minute, playback shows how much of the current interval
has elapsed rather than leaving the screen apparently frozen. Controls are disabled
while a synchronous mutation is in flight. The inspector distinguishes
genetic potential, development, current condition, and culture rather than
combining them into a misleading "fitness" score.

The first scenario UI should edit only validated starting conditions already
represented by `SimulationConfig` and `Scenario`: dimensions, seed, countries,
rectangular land/sea layout, founder populations, cultural distributions, and
resource multipliers. It must not invent professions, historical events, or
country behavior.

## Scaling, rendering, and backpressure

Simulation speed and display cadence are independent. A fast run may advance
hundreds of ticks while the browser displays only a few observations per
second.

- Each subscriber has a capacity-one render queue. Publishing a new frame
  replaces an unconsumed older frame: **latest frame wins**.
- Dropped render frames never drop causal ticks. Exact metric or event streams,
  when required for an experiment, use a separate bounded persistence sink.
- Frames are self-contained, sequence-numbered observations. No delta protocol
  is introduced until reconnection and loss recovery are designed.
- Static map data is cached from the manifest. Relationships, genomes, learned
  preference vectors, and pregnancy records stay out of routine frames.
- React never renders a component per cell or person. One imperative Canvas
  renderer paints typed render columns and schedules at most one paint per
  animation frame.
- Panning and zooming are local view operations and do not step the engine.
  Detail requests are cancelled or ignored when the selected run, person, or
  sequence changes.

The first JSON frame may contain every rendered person and both dynamic
resource grids. The next scale step is a viewport request containing world
bounds, zoom level, requested layers, and a point budget. The service then
returns:

- Exact agents inside a detailed viewport up to the budget.
- Deterministic spatial bins—count, dominant category, and aggregate
  health/resource values—when zoomed out or over budget.
- Only the dynamic layers that are currently visible.

Aggregation is an observer projection and must not affect simulation
resolution. The UI should expose when it is showing bins rather than
individuals.

### Events and life summaries

The engine has always written a bounded causal event log; until now nothing
outside the engine could read it. `GET /runs/{id}/events` serves a window onto
it, newest first, with `since_tick` for a reader following along.

Two admissions of ignorance are part of the contract rather than polish. A
feed reports `dropped` when the caller asks for everything after a tick the
log no longer reaches back to, because silence and a gap must not look the
same in a notification list. A dead person's biography reports
`moments_complete: false` when the log no longer reaches back to their birth,
so a fragment is never presented as a whole life.

Events are fetched separately from frames, and deliberately. Frames are
latest-wins and may be skipped; a record of what happened should not be, so it
is requested by tick rather than carried on a frame that might be dropped.

Wording is a translation of the record and never an embellishment of it:
`communicate` becomes "spoke with", not a conversation topic the model never
had. Routine events from the same tick are grouped with a count, since forty
conversations in one tick is a true record and a useless list; landmarks are
never grouped, so a first landfall cannot be buried under small talk.

A biography contains only what the engine still knows. Two of its figures are
about survivors rather than the person — how many children and grandchildren
outlived them — because those are the only marks a life leaves that the model
can still see afterwards. The person's own social memory returned to the
relationship store when they died.

### Detail tiers and what a sprite is allowed to mean

How a cell is drawn follows from how many pixels it occupies, not from the
world's size: density below roughly one pixel per cell, dots to four, plain
glyphs to eleven, sprites above that. Since a sprite-sized cell is large, few
of them fit on screen, so sprite cost is bounded by the viewport rather than
by the map. Below that tier a draw budget samples every nth cell, because zoom
multiplies fit-to-screen and a large world therefore starts fully visible with
more cells in front of the viewer than there are pixels to show them in.

Off-screen cells are skipped outright. Everything drawn per cell is derived
from the coordinates — placement, variation, which plant appears — so scenery
holds still between frames. Anything that moved from frame to frame would read
as an event, and on this map an event means something happened.

**A sprite is a reading of a measurable quantity, never a stored type.**
Greenery is drawn from the food layer and stone from the material layer;
both are quantities the engine already keeps. Nothing has sprouted or been
built, so no glyph claims otherwise, and there is deliberately no dwelling
sprite. When artifacts and flora become real entities the renderer should read
the entity register instead — the change is which measurement is consulted,
not a new category in the engine. If a renderer ever needs a field like
`type: "house"`, a label has been pushed into the model and the design is
wrong.

Glyphs are vector paths rendered once into an offscreen atlas and blitted with
`drawImage` — the same hot path a bitmap atlas uses, so a licensed CC0 tile
set can replace the painting functions without touching a call site. Drawing
them keeps the bundle free of binary assets, allows a person to be tinted to
any palette colour without a second image, and renders identically offline.

Four things make small shapes read as objects rather than as symbols, and all
four are worth preserving in any replacement art: a contact shadow, so things
stand on the ground instead of floating; one consistent light from the upper
left, matching the page, giving every glyph a lit face, a shaded face and a
thin rim; bold silhouettes, because these are drawn at sixteen pixels as often
as sixty and internal detail is lost long before outline is; and variation in
species, size and placement, because identical trees on a grid read as
wallpaper. People are drawn in painter's order — whoever is lower on the map
is nearer the reader and overlaps whoever is behind them.

Foliage is tinted by the season the engine is actually in. The growth wave's
phase flips across the equator, so reading that same phase puts one hemisphere
in autumn while the other is in spring, and summer is centred on peak growth
rather than guessed at. Deciduous species stand bare in winter and conifers
take snow. Children are drawn shorter with a larger head, read from the age
column. None of this is invented: every visual difference on the map traces to
a number the engine keeps.

Measure serialized frame bytes, projection time, transport latency, paint
time, and dropped-frame count before changing formats. Binary frames,
compression, Web Workers, OffscreenCanvas, or WebGL are later optimizations
behind existing boundaries, not competing data models.

## Worker-process target

The synchronous in-process session adapter is deliberately transitional. CPU
work must not remain on an async web server's event loop.

The target deployment uses one worker process for each active run, subject to a
bounded global worker limit:

```text
API supervisor
  - run metadata
  - command serialization
  - capacity-one subscriber queues
  - worker admission / failure state
             |
             | create, step batch, reset, project, export
             v
run worker process
  - one SimulationBackend
  - one causal clock and RNG owner
  - no HTTP or browser concerns
```

There is never one process per agent. If a single run later exceeds one
process, spatial partitioning should use a modest number of workers and
exchange boundary actions between explicit tick phases.

Worker commands and results use the same serializable service contracts. A
worker crash transitions the run to `failed`; a supervisor may restore the
last resumable checkpoint, never a visualization snapshot. Idle-run unloading
can use the same checkpoint boundary when it is implemented.

## Native-code seam

`SimulationBackend` is the only service dependency on an engine
implementation. The Python `Simulation` adapter remains the behavioral
reference. A future C, Cython, Rust, or array-backed implementation can replace
measured hot loops behind that interface without changing scenarios, REST
routes, manifests, frames, detail responses, or the React application.

The current backend surface is deliberately small:
`advance(ticks)`, `manifest()`, `frame(include_resources)`, `agent(id)`, and
`export_snapshot()`. Reset constructs a replacement backend from the immutable
run definition rather than requiring every backend to implement reverse
mutation.

Native work should begin only after profiling identifies a stable bottleneck.
Likely candidates are bounded neighborhood evaluation and action scoring;
scenario parsing, lifecycle orchestration, HTTP, and UI projection should stay
outside C.

A native backend must:

- Preserve tick-phase semantics and authoritative resolution checks.
- Pass deterministic replay, parity, invariant, resource-conservation, and
  schema-contract tests against the Python reference.
- Keep IDs and flat arrays as the interchange form rather than exposing native
  pointers.
- Report the same model/config/genome versions for equivalent mechanics, and a
  new model version when mechanics change.
- Avoid maintaining a second set of behavioral rules.

Process isolation remains useful with a native backend for fault containment
and run-level concurrency even if native code releases the GIL.

## Delivery milestones

1. **Foundations** — define TypeScript contracts and client interface; add the
   standard-library run manager, backend protocol, Python adapter, projections,
   and contract tests; render a clearly labelled local synthetic demo.
2. **Connected Run Lab** — connect the existing optional REST adapter to the
   Run Lab's create, manifest, bounded step, reset, latest frame, agent detail,
   and snapshot-export operations. Verify a two-islands run against direct
   engine output.
3. **Clock and streaming** — add play/pause, bounded tick batches, capacity-one
   WebSocket delivery, sequence/reconnect behavior, and service telemetry.
4. **Scenario workspace** — presets, service validation, visual rectangle
   editing, and immutable run creation are connected. Add JSON import/export
   and scenario comparison next.
5. **Experiments** — paired repeated seeds and comparable end metrics are
   connected. Add constant-density scale sweeps, metric series, result export,
   revision metadata, and durable server-side jobs next.
6. **Large-world projections** — add viewport queries, deterministic bins,
   resource-layer cadence, renderer profiling, and only then worker rendering
   or a binary transport if measurements justify it.
7. **Durability and acceleration** — resumable checkpoints are done; move run
   execution to bounded worker processes and port only demonstrated hot
   kernels behind `SimulationBackend`.

Each milestone keeps a headless path. A browser feature is complete only when
the underlying experiment remains reproducible from its scenario,
configuration, seed, model versions, and code revision.

## Local development

Run the simulation and its tests independently of the UI:

```bash
python3 -m unittest discover -v
python3 -m sims.simple_sim --scenario scenarios/two_islands.json --ticks 20
```

Install and run the optional local REST service:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-api.txt
.venv/bin/python -m src.human_sim_service.api
```

It listens on `127.0.0.1:8000`; interactive API documentation is available at
`/api/docs`.

The frontend requires Node.js 24 or newer. Install and run it in a second
terminal:

```bash
cd ui
npm install
npm run dev
```

Frontend verification:

```bash
cd ui
npm run typecheck
npm test
npm run build
```

The initial browser experience runs against its explicitly labelled demo
client until the Run Lab selects `ApiSimulationClient`. Before that connection
is enabled, the Vite development server should proxy `/api/v1` to the local
service so components do not depend on environment-specific URLs. A WebSocket
proxy is added only with the streaming milestone.
