import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";

import type { SimulationClient } from "../api/client";
import type {
  CreateRunRequest,
  RunSession,
} from "../api/contracts";
import {
  paceIndexFor,
  paceStep,
  planPlayback,
  ticksPerYearOf,
} from "../lib/pace";
import {
  initialRunLabState,
  runLabReducer,
} from "../state/runLabReducer";

/**
 * How often the playback loop wakes to ask whether the next tick is due. It
 * is deliberately unrelated to the pace: waking on a short fixed cadence lets
 * a pace change take effect promptly without either stepping early or waiting
 * out an interval that may be half an hour long.
 */
const PLAYBACK_POLL_MS = 250;

/** Bounds on how often a server-driven run is re-read for display. */
const MINIMUM_OBSERVE_MS = 500;
const MAXIMUM_OBSERVE_MS = 2_000;

/** Where the last run watched in this browser is remembered. */
const RUN_STORAGE_KEY = "human-sim.run-id";

function rememberRun(runId: string): void {
  try {
    window.localStorage.setItem(RUN_STORAGE_KEY, runId);
  } catch {
    // Private modes and disabled storage are not failures worth reporting;
    // the run is still identified by the URL below.
  }
  const url = new URL(window.location.href);
  if (url.searchParams.get("run") !== runId) {
    url.searchParams.set("run", runId);
    window.history.replaceState(null, "", url);
  }
}

/**
 * Which run this tab should be looking at.
 *
 * A run outlives the page watching it — the engine holds it and advances it
 * on its own — so opening the Run Lab should be an act of *attaching* to a
 * world, not of creating one. The URL wins because it is the shareable,
 * explicit answer; the remembered id is what makes an ordinary reload
 * continue rather than restart.
 */
function preferredRunId(fallback?: string): string | null {
  const fromUrl = new URLSearchParams(window.location.search).get("run");
  if (fromUrl !== null && fromUrl !== "") {
    return fromUrl;
  }
  try {
    const stored = window.localStorage.getItem(RUN_STORAGE_KEY);
    if (stored !== null && stored !== "") {
      return stored;
    }
  } catch {
    // Fall through to the configured run, if any.
  }
  return fallback ?? null;
}

interface Attachment {
  session: RunSession;
  /** Why this is not the run that was asked for, when it is not. */
  notice: string | null;
}

function fresh(session: RunSession): Attachment {
  return { session, notice: null };
}

export function useRunLab(
  client: SimulationClient,
  initialRequest: CreateRunRequest,
  existingRunId?: string,
) {
  const [state, dispatch] = useReducer(
    runLabReducer,
    initialRunLabState,
  );
  const steppingRef = useRef(false);
  const bootstrapRef = useRef<Promise<Attachment> | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    let active = true;
    dispatch({ kind: "load_started" });
    // Attach to the run this browser was last watching; only make a world if
    // there is none to attach to. A run the engine has since forgotten — or
    // one lost to a service restart — falls back to a new run with the
    // reason said out loud, because silently starting a different world is
    // indistinguishable from the old one having reset itself.
    const wanted = preferredRunId(existingRunId);
    const request = (bootstrapRef.current ??=
      wanted === null
        ? client.createRun(initialRequest).then(fresh)
        : client
            .openRun(wanted)
            .then((session) => ({ session, notice: null }))
            .catch(() =>
              client.createRun(initialRequest).then((session) => ({
                session,
                notice:
                  `Run ${wanted} is no longer held by the engine — ` +
                  "it was started here instead.",
              })),
            ));
    void request
      .then(({ session, notice }) => {
        rememberRun(session.manifest.run_id);
        if (active) {
          dispatch({ kind: "session_received", ...session, notice });
        }
      })
      .catch((error: unknown) => {
        if (active) {
          dispatch({
            kind: "failed",
            message:
              error instanceof Error
                ? error.message
                : "The run could not be loaded.",
          });
        }
      });
    return () => {
      active = false;
    };
  }, [client, existingRunId, initialRequest]);

  const step = useCallback(
    async (ticks = 1): Promise<void> => {
      const snapshot = stateRef.current;
      if (
        steppingRef.current ||
        snapshot.manifest === null ||
        snapshot.loadState === "loading"
      ) {
        return;
      }
      steppingRef.current = true;
      dispatch({ kind: "mutation_started" });
      try {
        const frame = await client.step(snapshot.manifest.run_id, {
          ticks,
          include_resources: true,
        });
        dispatch({ kind: "frame_received", frame });
      } catch (error: unknown) {
        dispatch({
          kind: "failed",
          message:
            error instanceof Error
              ? error.message
              : "The simulation could not advance.",
        });
      } finally {
        steppingRef.current = false;
      }
    },
    [client],
  );

  const ticksPerYear = ticksPerYearOf(state.manifest);
  const plan = useMemo(
    () => planPlayback(paceStep(state.paceIndex).secondsPerYear, ticksPerYear),
    [state.paceIndex, ticksPerYear],
  );
  const planRef = useRef(plan);
  planRef.current = plan;

  const serverDriven =
    state.manifest?.capabilities.playback === true;

  // Ask the engine to drive, or to stop driving. Sending the pace on every
  // change is what lets the slider move a run that this tab did not start.
  //
  // What must not happen is sending anything on arrival: a run found already
  // going at a pace set from a terminal would be re-paced to this tab's
  // default just for being looked at. So the state the run was found in is
  // recorded as already applied, and only a difference is transmitted.
  const paceSeconds = paceStep(state.paceIndex).secondsPerYear;
  const appliedRef = useRef<string | null>(null);
  const attachedRunId = state.manifest?.run_id;
  const foundPlaying = state.manifest?.playback?.playing === true;
  const foundPaceIndex = paceIndexFor(
    state.manifest?.playback?.seconds_per_year,
  );
  useEffect(() => {
    // Recorded as the pace *this tab would send* for the run's own pace, not
    // as the run's exact figure. A run set to an hour a year sits between
    // rungs of the ladder; treating the nearest rung as unsent would push a
    // pace change the reader never asked for, purely by arriving.
    appliedRef.current =
      attachedRunId === undefined || foundPaceIndex === null
        ? null
        : `${attachedRunId}|${foundPlaying}|${
            paceStep(foundPaceIndex).secondsPerYear
          }`;
  }, [attachedRunId, foundPaceIndex, foundPlaying]);

  useEffect(() => {
    const runId = state.manifest?.run_id;
    if (!serverDriven || runId === undefined) {
      return;
    }
    const wanted = `${runId}|${state.playing}|${paceSeconds}`;
    if (appliedRef.current === wanted) {
      return;
    }
    appliedRef.current = wanted;
    let active = true;
    void client
      .setPlayback(runId, state.playing, paceSeconds)
      .then((envelope) => {
        if (active) {
          dispatch({
            kind: "playback_observed",
            playback: envelope.playback,
          });
        }
      })
      .catch((error: unknown) => {
        if (active) {
          dispatch({
            kind: "failed",
            message:
              error instanceof Error
                ? error.message
                : "The engine would not change playback.",
          });
        }
      });
    return () => {
      active = false;
    };
  }, [client, paceSeconds, serverDriven, state.manifest?.run_id, state.playing]);

  // While the engine drives, this tab is a window rather than a clock: it
  // re-reads the run often enough to look alive and never asks it to advance.
  // Reading is what makes the same world watchable from two browsers at once,
  // and what makes closing one of them change nothing.
  useEffect(() => {
    const runId = state.manifest?.run_id;
    if (!serverDriven || !state.playing || runId === undefined) {
      return;
    }
    let active = true;
    let timer: number | undefined;
    const period = Math.min(
      MAXIMUM_OBSERVE_MS,
      Math.max(MINIMUM_OBSERVE_MS, planRef.current.intervalMs),
    );
    const look = () => {
      void client
        .observe(runId)
        .then((frame) => {
          if (active) {
            dispatch({ kind: "frame_received", frame });
          }
        })
        .catch(() => {
          // A dropped reading is not a broken run. The next one will say
          // where the world got to; reporting each miss would turn a blink
          // in the network into an alarm about the simulation.
        })
        .finally(() => {
          if (active) {
            timer = window.setTimeout(look, period);
          }
        });
    };
    look();
    return () => {
      active = false;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [client, serverDriven, state.manifest?.run_id, state.playing, plan.intervalMs]);

  // Playback advances the run at the chosen pace. The loop measures from the
  // moment a step was requested rather than from when it answered, so service
  // latency is absorbed by the wait instead of being added to it: a run set to
  // ten minutes a year keeps that pace whether a step costs 5 ms or 200 ms.
  //
  // This is the fallback for a backend that cannot hold its own clock: the
  // browser is the thing making time pass, and closing it stops the world.
  useEffect(() => {
    if (serverDriven || !state.playing || state.manifest === null) {
      return;
    }
    let active = true;
    let timeout: number | undefined;
    // The first tick after pressing Run is immediate; only later ones wait,
    // otherwise a slow pace looks like a broken control.
    let dueAt = performance.now();

    const wake = () => {
      if (!active) {
        return;
      }
      const now = performance.now();
      const remaining = dueAt - now;
      if (remaining > 0) {
        timeout = window.setTimeout(
          wake,
          Math.min(PLAYBACK_POLL_MS, remaining),
        );
        return;
      }
      dueAt = now + planRef.current.intervalMs;
      void step(planRef.current.ticks).finally(() => {
        if (active && stateRef.current.playing) {
          wake();
        }
      });
    };

    wake();
    return () => {
      active = false;
      if (timeout !== undefined) {
        window.clearTimeout(timeout);
      }
    };
  }, [serverDriven, state.manifest, state.playing, step]);

  useEffect(() => {
    const agentId = state.selectedAgentId;
    const runId = state.manifest?.run_id;
    if (agentId === null || runId === undefined) {
      return;
    }
    let active = true;
    dispatch({ kind: "detail_started", agentId });
    void client
      .getAgentDetail(runId, agentId)
      .then((detail) => {
        if (active) {
          dispatch({ kind: "detail_received", detail });
        }
      })
      .catch(() => {
        if (active) {
          dispatch({ kind: "detail_failed", agentId });
        }
      });
    return () => {
      active = false;
    };
  }, [
    client,
    state.manifest?.run_id,
    state.selectedAgentId,
    Math.floor((state.frame?.tick ?? 0) / 12),
  ]);

  // Events are fetched after each frame rather than inside it. Frames are
  // latest-wins and may be skipped; the event log is a record that should not
  // be, so it is asked for separately and by tick rather than by frame.
  const eventTick = state.frame?.tick ?? -1;
  useEffect(() => {
    const runId = state.manifest?.run_id;
    if (runId === undefined || eventTick < 0) {
      return;
    }
    let active = true;
    void client
      .getEvents(runId, stateRef.current.lastEventTick)
      .then((feed) => {
        if (active) {
          dispatch({
            kind: "events_received",
            events: feed.events,
            dropped: feed.dropped,
            tick: feed.tick,
          });
        }
      })
      .catch(() => {
        // A missing notification must never break the run it describes.
      });
    return () => {
      active = false;
    };
  }, [client, state.manifest?.run_id, eventTick]);

  // A deliberate second world, rather than the accident a reload used to be.
  // The run left behind keeps going if the engine was driving it; it is
  // found again through `sims.lab list`.
  const newRun = useCallback(async (): Promise<void> => {
    if (steppingRef.current) {
      return;
    }
    dispatch({ kind: "playing_changed", playing: false });
    dispatch({ kind: "mutation_started" });
    try {
      const session = await client.createRun(initialRequest);
      rememberRun(session.manifest.run_id);
      dispatch({ kind: "session_received", ...session });
    } catch (error: unknown) {
      dispatch({
        kind: "failed",
        message:
          error instanceof Error
            ? error.message
            : "A new run could not be created.",
      });
    }
  }, [client, initialRequest]);

  const reset = useCallback(async (): Promise<void> => {
    const manifest = stateRef.current.manifest;
    if (manifest === null || steppingRef.current) {
      return;
    }
    dispatch({ kind: "playing_changed", playing: false });
    steppingRef.current = true;
    dispatch({ kind: "mutation_started" });
    try {
      const session = await client.reset(manifest.run_id);
      dispatch({ kind: "session_received", ...session });
    } catch (error: unknown) {
      dispatch({
        kind: "failed",
        message:
          error instanceof Error
            ? error.message
            : "The run could not be reset.",
      });
    } finally {
      steppingRef.current = false;
    }
  }, [client]);

  return {
    state,
    ticksPerYear,
    plan,
    /** Whether the engine, rather than this tab, is making time pass. */
    serverDriven,
    actions: {
      newRun,
      play: () => dispatch({ kind: "playing_changed", playing: true }),
      pause: () =>
        dispatch({ kind: "playing_changed", playing: false }),
      step,
      stepYear: () => step(ticksPerYear),
      reset,
      setPace: (paceIndex: number) =>
        dispatch({ kind: "pace_changed", paceIndex }),
      selectAgent: (agentId: string | null) =>
        dispatch({ kind: "agent_selected", agentId }),
    },
  };
}
