"""Versioned, JSON-ready projections exposed by the simulation service.

These contracts deliberately contain plain JSON values.  They form a stable
boundary between a simulation backend and transports such as HTTP, WebSocket,
or an in-process test harness.
"""

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple


PROTOCOL_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
FRAME_SCHEMA_VERSION = 1
AGENT_DETAIL_SCHEMA_VERSION = 2
EVENT_FEED_SCHEMA_VERSION = 1

RUN_MANIFEST_KIND = "run_manifest"
RENDER_FRAME_KIND = "render_frame"
AGENT_DETAIL_KIND = "agent_detail"
EVENT_FEED_KIND = "event_feed"

RUN_STATUS_PAUSED = "paused"
RUN_STATUS_STEPPING = "stepping"
RUN_STATUS_FAILED = "failed"
RUN_STATUSES = frozenset(
    (RUN_STATUS_PAUSED, RUN_STATUS_STEPPING, RUN_STATUS_FAILED)
)


_CONTAINERS = frozenset((dict, list, tuple))


def _copy_json(value: object) -> object:
    """Copy a JSON-shaped tree without ``deepcopy`` bookkeeping.

    Projections are dicts, lists, and scalars only. Scalars are immutable and
    can be shared, so only the containers are rebuilt. ``deepcopy`` maintains a
    memo table and dispatches per element, which dominates manifest cost once
    world layers reach tens of thousands of cells.
    """

    kind = type(value)
    if kind is dict:
        return {key: _copy_json(item) for key, item in value.items()}
    if kind is list or kind is tuple:
        # World layers and agent columns are flat numeric lists. Detecting
        # that with cheap type checks beats a recursive call per cell.
        for item in value:
            if type(item) in _CONTAINERS:
                return [_copy_json(item) for item in value]
        return list(value)
    return value


def _copy_mapping(values: Mapping[str, object]) -> Dict[str, object]:
    """Return an owned JSON tree rather than leaking mutable backend data."""

    return {key: _copy_json(item) for key, item in values.items()}


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


@dataclass(frozen=True, slots=True)
class EventFeed:
    """Recent causal events, newest first.

    This is an observation like any other projection: the log is written by
    the engine as things happen and read here, never the other way round.
    """

    run_id: str
    sequence: int
    status: str
    tick: int
    year: float
    events: Tuple[Mapping[str, object], ...]
    oldest_retained_tick: int
    dropped: bool

    def __post_init__(self) -> None:
        _validate_envelope(self.run_id, self.sequence, self.status)

    def to_dict(self) -> Dict[str, object]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "schema_version": EVENT_FEED_SCHEMA_VERSION,
            "kind": EVENT_FEED_KIND,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "status": self.status,
            "tick": self.tick,
            "year": self.year,
            "events": [_copy_mapping(event) for event in self.events],
            "oldest_retained_tick": self.oldest_retained_tick,
            "dropped": self.dropped,
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
