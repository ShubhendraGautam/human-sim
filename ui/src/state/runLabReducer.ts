import {
  toTimelinePoint,
  type AgentDetailEnvelope,
  type RunFrame,
  type RunManifest,
  type TimelinePoint,
} from "../api/contracts";

const HISTORY_LIMIT = 180;

export type LoadState = "loading" | "ready" | "mutating" | "error";

export interface RunLabState {
  loadState: LoadState;
  manifest: RunManifest | null;
  frame: RunFrame | null;
  history: TimelinePoint[];
  playing: boolean;
  speed: number;
  selectedAgentId: string | null;
  detail: AgentDetailEnvelope | null;
  detailLoading: boolean;
  error: string | null;
}

export const initialRunLabState: RunLabState = {
  loadState: "loading",
  manifest: null,
  frame: null,
  history: [],
  playing: false,
  speed: 1,
  selectedAgentId: null,
  detail: null,
  detailLoading: false,
  error: null,
};

export type RunLabAction =
  | { kind: "load_started" }
  | { kind: "session_received"; manifest: RunManifest; frame: RunFrame }
  | { kind: "mutation_started" }
  | { kind: "frame_received"; frame: RunFrame }
  | { kind: "failed"; message: string }
  | { kind: "playing_changed"; playing: boolean }
  | { kind: "speed_changed"; speed: number }
  | { kind: "agent_selected"; agentId: string | null }
  | { kind: "detail_started"; agentId: string }
  | { kind: "detail_received"; detail: AgentDetailEnvelope }
  | { kind: "detail_failed"; agentId: string };

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
        speed: state.speed,
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
    case "speed_changed":
      return {
        ...state,
        speed: action.speed,
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
      return {
        ...state,
        detailLoading: false,
      };
  }
}
