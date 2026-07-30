import {
  assertAgentDetailEnvelope,
  assertFrameColumns,
  assertWorldManifest,
  type AgentDetailEnvelope,
  type CreateRunRequest,
  type EventFeed,
  type PlaybackEnvelope,
  type RunFrame,
  type RunManifest,
  type RunSession,
  type RunSource,
  type StepRunRequest,
  type ValidateScenarioResponse,
} from "./contracts";

export interface SimulationClient {
  readonly source: RunSource;
  validateScenario(
    request: Pick<CreateRunRequest, "config" | "scenario">,
  ): Promise<ValidateScenarioResponse>;
  createRun(request: CreateRunRequest): Promise<RunSession>;
  openRun(runId: string): Promise<RunSession>;
  step(runId: string, request: StepRunRequest): Promise<RunFrame>;
  /** Read the current frame without advancing anything. */
  observe(runId: string): Promise<RunFrame>;
  /**
   * Hand the run to the engine's own clock, or take it back.
   *
   * Only meaningful where the manifest reports the `playback` capability.
   * A client without it drives the run itself and stops when it stops.
   */
  setPlayback(
    runId: string,
    playing: boolean,
    secondsPerYear: number | null,
  ): Promise<PlaybackEnvelope>;
  reset(runId: string): Promise<RunSession>;
  getAgentDetail(
    runId: string,
    agentId: string,
  ): Promise<AgentDetailEnvelope>;
  getEvents(runId: string, sinceTick: number): Promise<EventFeed>;
  /** Remove an experiment's temporary run from the engine registry. */
  deleteRun(runId: string): Promise<void>;
  getExportUrl(runId: string): string | null;
  dispose(): void;
}

interface ApiErrorPayload {
  detail?: string;
  message?: string;
  error?: {
    message?: string;
  };
}

export class ApiSimulationClient implements SimulationClient {
  readonly source = "service" as const;
  readonly #baseUrl: string;
  readonly #abortController = new AbortController();

  constructor(baseUrl: string) {
    this.#baseUrl = baseUrl.replace(/\/+$/, "");
  }

  async validateScenario(
    request: Pick<CreateRunRequest, "config" | "scenario">,
  ): Promise<ValidateScenarioResponse> {
    return this.#request<ValidateScenarioResponse>(
      "/api/v1/scenarios/validate",
      {
        method: "POST",
        body: JSON.stringify(request),
      },
    );
  }

  async createRun(request: CreateRunRequest): Promise<RunSession> {
    const manifest = await this.#request<RunManifest>("/api/v1/runs", {
      method: "POST",
      body: JSON.stringify(request),
    });
    return this.#loadSession(manifest);
  }

  async openRun(runId: string): Promise<RunSession> {
    const manifest = await this.#request<RunManifest>(
      `/api/v1/runs/${encodeURIComponent(runId)}/manifest`,
    );
    return this.#loadSession(manifest);
  }

  async step(
    runId: string,
    request: StepRunRequest,
  ): Promise<RunFrame> {
    const frame = await this.#request<RunFrame>(
      `/api/v1/runs/${encodeURIComponent(runId)}/steps`,
      {
        method: "POST",
        body: JSON.stringify(request),
      },
    );
    assertFrameColumns(frame);
    return frame;
  }

  async observe(runId: string): Promise<RunFrame> {
    const frame = await this.#request<RunFrame>(
      `/api/v1/runs/${encodeURIComponent(runId)}/frame?include_resources=true`,
    );
    assertFrameColumns(frame);
    return frame;
  }

  async setPlayback(
    runId: string,
    playing: boolean,
    secondsPerYear: number | null,
  ): Promise<PlaybackEnvelope> {
    return this.#request<PlaybackEnvelope>(
      `/api/v1/runs/${encodeURIComponent(runId)}/playback`,
      {
        method: "POST",
        body: JSON.stringify({
          playing,
          // Omitted rather than null, so pausing leaves the run's pace as
          // whoever set it left it.
          ...(secondsPerYear === null
            ? {}
            : { seconds_per_year: secondsPerYear }),
        }),
      },
    );
  }

  async reset(runId: string): Promise<RunSession> {
    const path = `/api/v1/runs/${encodeURIComponent(runId)}/reset`;
    const response = await this.#request<RunManifest | RunFrame>(path, {
      method: "POST",
      body: JSON.stringify({ include_resources: true }),
    });
    if (response.kind === "run_manifest") {
      return this.#loadSession(response);
    }
    const manifest = await this.#request<RunManifest>(
      `/api/v1/runs/${encodeURIComponent(runId)}/manifest`,
    );
    assertWorldManifest(manifest);
    assertFrameColumns(response);
    return { manifest, frame: response };
  }

  async getAgentDetail(
    runId: string,
    agentId: string,
  ): Promise<AgentDetailEnvelope> {
    const detail = await this.#request<AgentDetailEnvelope>(
      `/api/v1/runs/${encodeURIComponent(runId)}/agents/${encodeURIComponent(agentId)}`,
    );
    assertAgentDetailEnvelope(detail);
    return detail;
  }

  async getEvents(runId: string, sinceTick: number): Promise<EventFeed> {
    return this.#request<EventFeed>(
      `/api/v1/runs/${encodeURIComponent(runId)}/events` +
        `?since_tick=${Math.max(-1, Math.trunc(sinceTick))}&limit=120`,
    );
  }

  async deleteRun(runId: string): Promise<void> {
    await this.#request<unknown>(
      `/api/v1/runs/${encodeURIComponent(runId)}`,
      { method: "DELETE" },
    );
  }

  getExportUrl(runId: string): string {
    return `${this.#baseUrl}/api/v1/runs/${encodeURIComponent(runId)}/snapshot`;
  }

  dispose(): void {
    this.#abortController.abort();
  }

  async #loadSession(manifest: RunManifest): Promise<RunSession> {
    assertWorldManifest(manifest);
    const frame = await this.#request<RunFrame>(
      `/api/v1/runs/${encodeURIComponent(manifest.run_id)}/frame?include_resources=true`,
    );
    assertFrameColumns(frame);
    return { manifest, frame };
  }

  async #request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.#baseUrl}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body === undefined ? {} : { "Content-Type": "application/json" }),
        ...init.headers,
      },
      signal: this.#abortController.signal,
    });

    if (!response.ok) {
      let payload: ApiErrorPayload = {};
      try {
        payload = (await response.json()) as ApiErrorPayload;
      } catch {
        // An empty/non-JSON error response is still represented by its status.
      }
      throw new Error(
        payload.error?.message ??
          payload.detail ??
          payload.message ??
          `Simulation service returned ${response.status}.`,
      );
    }
    return (await response.json()) as T;
  }
}
