"""Versioned, JSON-ready projections exposed by the simulation service.

These contracts deliberately contain plain JSON values.  They form a stable
boundary between a simulation backend and transports such as HTTP, WebSocket,
or an in-process test harness.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, Mapping, Optional


PROTOCOL_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
FRAME_SCHEMA_VERSION = 1
AGENT_DETAIL_SCHEMA_VERSION = 1

RUN_MANIFEST_KIND = "run_manifest"
RENDER_FRAME_KIND = "render_frame"
AGENT_DETAIL_KIND = "agent_detail"

RUN_STATUS_PAUSED = "paused"
RUN_STATUS_STEPPING = "stepping"
RUN_STATUS_FAILED = "failed"
RUN_STATUSES = frozenset(
    (RUN_STATUS_PAUSED, RUN_STATUS_STEPPING, RUN_STATUS_FAILED)
)


def _copy_mapping(values: Mapping[str, object]) -> Dict[str, object]:
    """Return an owned JSON tree rather than leaking mutable backend data."""

    return deepcopy(dict(values))


@dataclass(frozen=True, slots=True)
class RunManifest:
    """Static run metadata and world layers fetched once by a UI."""

    run_id: str
    sequence: int
    status: str
    seed: int
    tick: int
    year: float
    population: int
    model: Mapping[str, object]
    config: Mapping[str, object]
    scenario: Mapping[str, object]
    world: Mapping[str, object]
    capabilities: Mapping[str, object]

    def __post_init__(self) -> None:
        _validate_envelope(self.run_id, self.sequence, self.status)

    def to_dict(self) -> Dict[str, object]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "kind": RUN_MANIFEST_KIND,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "status": self.status,
            "seed": self.seed,
            "tick": self.tick,
            "year": self.year,
            "population": self.population,
            "model": _copy_mapping(self.model),
            "config": _copy_mapping(self.config),
            "scenario": _copy_mapping(self.scenario),
            "world": _copy_mapping(self.world),
            "capabilities": _copy_mapping(self.capabilities),
        }


@dataclass(frozen=True, slots=True)
class RenderFrame:
    """Small recurring projection used for rendering and live metrics."""

    run_id: str
    sequence: int
    status: str
    tick: int
    year: float
    metrics: Mapping[str, object]
    agents: Mapping[str, object]
    resources: Optional[Mapping[str, object]] = None

    def __post_init__(self) -> None:
        _validate_envelope(self.run_id, self.sequence, self.status)

    def to_dict(self) -> Dict[str, object]:
        result: Dict[str, object] = {
            "protocol_version": PROTOCOL_VERSION,
            "schema_version": FRAME_SCHEMA_VERSION,
            "kind": RENDER_FRAME_KIND,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "status": self.status,
            "tick": self.tick,
            "year": self.year,
            "metrics": _copy_mapping(self.metrics),
            "agents": _copy_mapping(self.agents),
        }
        if self.resources is not None:
            result["resources"] = _copy_mapping(self.resources)
        return result


@dataclass(frozen=True, slots=True)
class AgentDetail:
    """On-demand deep projection for one living agent."""

    run_id: str
    sequence: int
    status: str
    tick: int
    agent: Mapping[str, object]

    def __post_init__(self) -> None:
        _validate_envelope(self.run_id, self.sequence, self.status)

    def to_dict(self) -> Dict[str, object]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "schema_version": AGENT_DETAIL_SCHEMA_VERSION,
            "kind": AGENT_DETAIL_KIND,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "status": self.status,
            "tick": self.tick,
            "agent": _copy_mapping(self.agent),
        }


def _validate_envelope(run_id: str, sequence: int, status: str) -> None:
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a nonempty string")
    if (
        not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or sequence < 0
    ):
        raise ValueError("sequence must be a nonnegative integer")
    if status not in RUN_STATUSES:
        raise ValueError(f"unknown run status: {status!r}")
