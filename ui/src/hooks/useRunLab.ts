import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
} from "react";

import type { SimulationClient } from "../api/client";
import type {
  CreateRunRequest,
  RunSession,
} from "../api/contracts";
import {
  initialRunLabState,
  runLabReducer,
} from "../state/runLabReducer";

const PLAYBACK_INTERVAL_MS = 420;

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

  useEffect(() => {
    if (!state.playing || state.manifest === null) {
      return;
    }
    let active = true;
    let timeout: number | undefined;
    const schedule = () => {
      timeout = window.setTimeout(() => {
        if (!active) {
          return;
        }
        void step(stateRef.current.speed).finally(() => {
          if (active && stateRef.current.playing) {
            schedule();
          }
        });
      }, PLAYBACK_INTERVAL_MS);
    };
    schedule();
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
    actions: {
      play: () => dispatch({ kind: "playing_changed", playing: true }),
      pause: () =>
        dispatch({ kind: "playing_changed", playing: false }),
      step,
      reset,
      setSpeed: (speed: number) =>
        dispatch({ kind: "speed_changed", speed }),
      selectAgent: (agentId: string | null) =>
        dispatch({ kind: "agent_selected", agentId }),
    },
  };
}
