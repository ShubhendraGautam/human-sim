import {
  toTimelinePoint,
  type AgentDetailEnvelope,
  type RunFrame,
  type RunManifest,
  type TimelinePoint,
  type WorldEvent,
} from "../api/contracts";
import { DEFAULT_PACE_INDEX, PACE_LADDER } from "../lib/pace";

const HISTORY_LIMIT = 180;

export type LoadState = "loading" | "ready" | "mutating" | "error";

export interface RunLabState {
  loadState: LoadState;
  manifest: RunManifest | null;
  frame: RunFrame | null;
  history: TimelinePoint[];
  playing: boolean;
  /** Index into PACE_LADDER; real time a simulated year should take. */
  paceIndex: number;
  selectedAgentId: string | null;
  detail: AgentDetailEnvelope | null;
  detailLoading: boolean;
  /** Newest first, capped; the engine's own log is bounded too. */
  events: WorldEvent[];
  eventsDropped: boolean;
  lastEventTick: number;
  error: string | null;
}

const EVENT_LIMIT = 400;

export const initialRunLabState: RunLabState = {
  loadState: "loading",
  manifest: null,
  frame: null,
  history: [],
  playing: false,
  paceIndex: DEFAULT_PACE_INDEX,
  selectedAgentId: null,
  detail: null,
  detailLoading: false,
  events: [],
  eventsDropped: false,
  lastEventTick: -1,
  error: null,
};

export type RunLabAction =
  | { kind: "load_started" }
  | { kind: "session_received"; manifest: RunManifest; frame: RunFrame }
  | { kind: "mutation_started" }
  | { kind: "frame_received"; frame: RunFrame }
  | { kind: "failed"; message: string }
  | { kind: "playing_changed"; playing: boolean }
  | { kind: "pace_changed"; paceIndex: number }
  | { kind: "agent_selected"; agentId: string | null }
  | { kind: "detail_started"; agentId: string }
  | { kind: "detail_received"; detail: AgentDetailEnvelope }
  | { kind: "detail_failed"; agentId: string }
  | {
      kind: "events_received";
      events: WorldEvent[];
      dropped: boolean;
      tick: number;
    };

function appendHistory(
  history: TimelinePoint[],
  frame: RunFrame,
): TimelinePoint[] {
  const point = toTimelinePoint(frame);
  const withoutSameTick =
    history.at(-1)?.tick === point.tick ? history.slice(0, -1) : history;
  return [...withoutSameTick, point].slice(-HISTORY_LIMIT);
}

export function runLabReducer(
  state: RunLabState,
  action: RunLabAction,
): RunLabState {
  switch (action.kind) {
    case "load_started":
      return {
        ...initialRunLabState,
        paceIndex: state.paceIndex,
      };
    case "session_received":
      return {
        ...state,
        loadState: "ready",
        manifest: action.manifest,
        frame: action.frame,
        history: [toTimelinePoint(action.frame)],
        playing: false,
        selectedAgentId: null,
        detail: null,
        detailLoading: false,
        events: [],
        eventsDropped: false,
        lastEventTick: -1,
        error: null,
      };
    case "mutation_started":
      return {
        ...state,
        loadState: "mutating",
        error: null,
      };
    case "frame_received": {
      if (
        state.manifest === null ||
        action.frame.run_id !== state.manifest.run_id ||
        (state.frame !== null && action.frame.sequence < state.frame.sequence)
      ) {
        return state;
      }
      return {
        ...state,
        loadState: "ready",
        frame: action.frame,
        history: appendHistory(state.history, action.frame),
        error: null,
      };
    }
    case "failed":
      return {
        ...state,
        loadState: "error",
        playing: false,
        detailLoading: false,
        error: action.message,
      };
    case "playing_changed":
      return {
        ...state,
        playing: action.playing,
      };
    case "pace_changed":
      return {
        ...state,
        paceIndex: Math.min(
          PACE_LADDER.length - 1,
          Math.max(0, Math.round(action.paceIndex)),
        ),
      };
    case "agent_selected":
      return {
        ...state,
        selectedAgentId: action.agentId,
        detail: null,
        detailLoading: action.agentId !== null,
      };
    case "detail_started":
      if (action.agentId !== state.selectedAgentId) {
        return state;
      }
      return {
        ...state,
        detailLoading: true,
      };
    case "detail_received":
      if (
        action.detail.run_id !== state.manifest?.run_id ||
        action.detail.agent.id !== state.selectedAgentId
      ) {
        return state;
      }
      return {
        ...state,
        detail: action.detail,
        detailLoading: false,
      };
    case "detail_failed":
      if (action.agentId !== state.selectedAgentId) {
        return state;
      }
      // Keeping the last successful detail would leave a person on screen who
      // no longer exists, indistinguishable from a live reading. The engine
      // answers for its recent dead, so a failure here means genuinely gone.
      return {
        ...state,
        detail: null,
        detailLoading: false,
      };
    case "events_received": {
      if (action.events.length === 0) {
        return action.dropped === state.eventsDropped
          ? state
          : { ...state, eventsDropped: action.dropped };
      }
      // The feed is a window, not an archive: newest first, capped, and the
      // engine's own log is bounded behind it. Once dropped is set it stays
      // set, because the gap it reports never gets filled in later.
      return {
        ...state,
        events: [...action.events, ...state.events].slice(0, EVENT_LIMIT),
        eventsDropped: state.eventsDropped || action.dropped,
        lastEventTick: Math.max(state.lastEventTick, action.tick),
      };
    }
  }
}
