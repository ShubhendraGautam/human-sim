import { describe, expect, it } from "vitest";

import {
  PROTOCOL_VERSION,
  assertAgentDetailEnvelope,
  assertFrameColumns,
  type AgentDetailEnvelope,
  type RunFrame,
} from "./contracts";

function detail(schemaVersion: number): AgentDetailEnvelope {
  return {
    protocol_version: PROTOCOL_VERSION,
    schema_version: schemaVersion,
    kind: "agent_detail",
    run_id: "run-a",
    sequence: 3,
    status: "paused",
    tick: 12,
    agent: { id: "57" },
  } as unknown as AgentDetailEnvelope;
}

function frame(fauna: Record<string, number[]> | undefined): RunFrame {
  return {
    protocol_version: PROTOCOL_VERSION,
    schema_version: fauna === undefined ? 1 : 2,
    kind: "render_frame",
    run_id: "run-a",
    sequence: 3,
    status: "paused",
    tick: 12,
    year: 1,
    agents: { id: ["1", "2"], x: [0, 1], y: [2, 3] },
    ...(fauna === undefined ? {} : { fauna }),
  } as unknown as RunFrame;
}

describe("protocol envelopes", () => {
  it("reads every schema version of a kind it knows", () => {
    // Agent detail moved to 2 when biographies were added while frames
    // stayed where they were. A single shared version constant made that
    // ordinary change reject every person the inspector asked for.
    expect(() => assertAgentDetailEnvelope(detail(2))).not.toThrow();
    expect(() => assertAgentDetailEnvelope(detail(1))).not.toThrow();
  });

  it("refuses a schema version it has never seen", () => {
    expect(() => assertAgentDetailEnvelope(detail(99))).toThrow(
      /schema version 99/,
    );
  });

  it("accepts a frame from a service too old to send animals", () => {
    expect(() => assertFrameColumns(frame(undefined))).not.toThrow();
  });

  it("rejects a herd whose columns disagree on length", () => {
    expect(() =>
      assertFrameColumns(
        frame({ id: [1, 2], x: [4, 5], y: [6], energy: [1, 1], vigilance: [0, 0] }),
      ),
    ).toThrow(/fauna\.y/);
  });
});
