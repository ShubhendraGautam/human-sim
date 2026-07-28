import {
  toTimelinePoint,
  type AgentDetailEnvelope,
  type PlaybackState,
  type RunFrame,
  type RunManifest,
  type TimelinePoint,
  type WorldEvent,
} from "../api/contracts";
import { DEFAULT_PACE_INDEX, PACE_LADDER, paceIndexFor } from "../lib/pace";

const HISTORY_LIMIT = 180;

/**
 * How many years of the run to keep beside the frame buffer.
 *
 * The frame buffer answers "what is happening now" and holds a few minutes of
 * ticks. Anything that changes over generations — how strong inherited
 * networks have become, whether policies are still diverse — is invisible in
 * that window, because at twelve ticks a year it spans about fifteen years of
 * a run that goes on for hundreds. One sample a simulated year is cheap
 * enough to keep for the whole run and is the scale those questions are
 * actually asked at.
 */
const YEARLY_LIMIT = 600;

export type LoadState = "loading" | "ready" | "mutating" | "error";

export interface RunLabState {
  loadState: LoadState;
  manifest: RunManifest | null;
  frame: RunFrame | null;
  history: TimelinePoint[];
  /** One point per simulated year, oldest first; the long view. */
  yearly: TimelinePoint[];
  /**
   * What the engine last said about driving this run, when the engine is
   * the one driving it. Kept because the pace it holds may be one no rung
   * of the local ladder matches — a run started from a terminal at an hour
   * a year — and the reader should be told the real figure.
   */
  enginePlayback: PlaybackState | null;
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
  /**
   * Something true about how this session was established that the reader
   * would otherwise have no way to know — that the run they were watching
   * was gone, say. Not an error: the lab is working, just not on the world
   * they left.
   */
  notice: string | null;
}

const EVENT_LIMIT = 400;

export const initialRunLabState: RunLabState = {
  loadState: "loading",
  manifest: null,
  frame: null,
  history: [],
  yearly: [],
  enginePlayback: null,
  playing: false,
  paceIndex: DEFAULT_PACE_INDEX,
  selectedAgentId: null,
  detail: null,
  detailLoading: false,
  events: [],
  eventsDropped: false,
  lastEventTick: -1,
  error: null,
  notice: null,
};

export type RunLabAction =
  | { kind: "load_started" }
  | {
      kind: "session_received";
      manifest: RunManifest;
      frame: RunFrame;
      notice?: string | null;
    }
  | { kind: "playback_observed"; playback: PlaybackState }
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

/**
 * Keep the first frame seen in each simulated year.
 *
 * Playback may step a whole year at a time or skip frames under load, so the
 * series is sampled by the year a frame reports rather than by counting
 * frames. Years the reader was not watching are simply absent — the gap is
 * left as a gap rather than interpolated, because a line drawn through
 * nothing is a claim about a world nobody observed.
 */
function appendYearly(
  yearly: TimelinePoint[],
  frame: RunFrame,
): TimelinePoint[] {
  const latest = yearly.at(-1);
  const year = Math.floor(frame.year);
  if (latest !== undefined && Math.floor(latest.year) === year) {
    return yearly;
  }
  return [...yearly, toTimelinePoint(frame)].slice(-YEARLY_LIMIT);
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
        yearly: [toTimelinePoint(action.frame)],
        // A run the engine is already driving is playing whether or not this
        // tab asked it to. Showing "Run" over a world that is visibly moving
        // would make the button a lie.
        playing: action.manifest.playback?.playing === true,
        // Adopt the run's pace rather than imposing this tab's default,
        // which would re-pace a world on the way to observing it.
        paceIndex:
          paceIndexFor(action.manifest.playback?.seconds_per_year) ??
          state.paceIndex,
        enginePlayback: action.manifest.playback ?? null,
        notice: action.notice ?? null,
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
        yearly: appendYearly(state.yearly, action.frame),
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
    case "playback_observed":
      // What the engine says it is doing wins over what this tab asked for.
      return {
        ...state,
        playing: action.playback.playing,
        enginePlayback: action.playback,
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
