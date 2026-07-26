import {
  assertAgentDetailEnvelope,
  assertFrameColumns,
  assertWorldManifest,
  type AgentDetailEnvelope,
  type CreateRunRequest,
  type RunFrame,
  type RunManifest,
  type RunSession,
  type RunSource,
  type StepRunRequest,
} from "./contracts";

export interface SimulationClient {
  readonly source: RunSource;
  createRun(request: CreateRunRequest): Promise<RunSession>;
  openRun(runId: string): Promise<RunSession>;
  step(runId: string, request: StepRunRequest): Promise<RunFrame>;
  reset(runId: string): Promise<RunSession>;
  getAgentDetail(
    runId: string,
    agentId: string,
  ): Promise<AgentDetailEnvelope>;
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
