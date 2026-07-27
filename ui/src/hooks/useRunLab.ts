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
  const bootstrapRef = useRef<Promise<RunSession> | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    let active = true;
    dispatch({ kind: "load_started" });
    const request = (bootstrapRef.current ??=
      existingRunId === undefined
        ? client.createRun(initialRequest)
        : client.openRun(existingRunId));
    void request
      .then((session) => {
        if (active) {
          dispatch({ kind: "session_received", ...session });
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

  // Playback advances the run at the chosen pace. The loop measures from the
  // moment a step was requested rather than from when it answered, so service
  // latency is absorbed by the wait instead of being added to it: a run set to
  // ten minutes a year keeps that pace whether a step costs 5 ms or 200 ms.
  useEffect(() => {
    if (!state.playing || state.manifest === null) {
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
  }, [state.manifest, state.playing, step]);

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
    actions: {
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
