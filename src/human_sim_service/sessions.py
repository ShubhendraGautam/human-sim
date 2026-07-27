"""Thread-safe run lifecycle independent of any web framework."""

import threading
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional, Union

from src.simulation import Scenario, SimulationConfig

from .backend import (
    SimulationBackend,
    SimulationBackendFactory,
    python_backend_factory,
)
from .contracts import (
    AgentDetail,
    RenderFrame,
    RunManifest,
    RUN_STATUS_FAILED,
    RUN_STATUS_PAUSED,
    RUN_STATUS_STEPPING,
)


ConfigValue = Optional[Union[SimulationConfig, Mapping[str, object]]]
ScenarioValue = Optional[Union[Scenario, Mapping[str, object]]]


class RunServiceError(Exception):
    """Base class for stable service-layer errors."""


class RunNotFoundError(RunServiceError, KeyError):
    pass


class DuplicateRunError(RunServiceError, ValueError):
    pass


class AgentNotFoundError(RunServiceError, KeyError):
    pass


class RunFailedError(RunServiceError, RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RunDefinition:
    """Immutable inputs used to recreate a deterministic run."""

    config: SimulationConfig
    seed: int
    scenario: Scenario

    @classmethod
    def from_values(
        cls,
        *,
        config: ConfigValue = None,
        seed: int = 0,
        scenario: ScenarioValue = None,
    ) -> "RunDefinition":
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise ValueError("seed must be an integer")
        resolved_config = _coerce_config(config)
        resolved_scenario = _coerce_scenario(
            scenario,
            resolved_config,
        )
        resolved_scenario.validate(resolved_config)
        return cls(
            config=resolved_config,
            seed=seed,
            scenario=resolved_scenario,
        )


class RunSession:
    """Own one backend instance and serialize all access to its state."""

    def __init__(
        self,
        run_id: str,
        definition: RunDefinition,
        *,
        backend_factory: SimulationBackendFactory = python_backend_factory,
    ) -> None:
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id must be a nonempty string")
        self.run_id = run_id
        self.definition = definition
        self._backend_factory = backend_factory
        self._lock = threading.RLock()
        self._backend = self._new_backend()
        self._sequence = 0
        self._status = RUN_STATUS_PAUSED
        self._last_error: Optional[str] = None

    @property
    def sequence(self) -> int:
        with self._lock:
            return self._sequence

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def manifest(self) -> Dict[str, object]:
        with self._lock:
            source = self._backend.manifest()
            return RunManifest(
                run_id=self.run_id,
                sequence=self._sequence,
                status=self._status,
                seed=source.seed,
                tick=source.tick,
                year=source.year,
                population=source.population,
                model=source.model,
                config=source.config,
                scenario=source.scenario,
                world=source.world,
                capabilities={
                    "step": True,
                    "reset": True,
                    "agent_detail": True,
                    "resource_layers": True,
                    "full_snapshot_export": True,
                },
            ).to_dict()

    def frame(
        self,
        *,
        include_resources: bool = False,
    ) -> Dict[str, object]:
        _require_boolean(include_resources, "include_resources")
        with self._lock:
            return self._frame_locked(include_resources)

    def agent_detail(
        self,
        agent_id: Union[int, str],
    ) -> Dict[str, object]:
        resolved_id = _coerce_agent_id(agent_id)
        with self._lock:
            try:
                source = self._backend.agent(resolved_id)
            except KeyError:
                # The dead are answerable while the engine still remembers
                # them, so reaching here means never seen or long forgotten.
                raise AgentNotFoundError(
                    f"run {self.run_id!r} has no record of agent "
                    f"{resolved_id}"
                ) from None
            return AgentDetail(
                run_id=self.run_id,
                sequence=self._sequence,
                status=self._status,
                tick=source.tick,
                agent=source.agent,
            ).to_dict()

    def step(
        self,
        ticks: int = 1,
        *,
        include_resources: bool = False,
    ) -> Dict[str, object]:
        _require_positive_integer(ticks, "ticks")
        _require_boolean(include_resources, "include_resources")
        with self._lock:
            if self._status == RUN_STATUS_FAILED:
                raise RunFailedError(
                    f"run {self.run_id!r} failed; reset it before stepping"
                )
            self._status = RUN_STATUS_STEPPING
            try:
                self._backend.advance(ticks)
            except Exception as error:
                self._sequence += 1
                self._status = RUN_STATUS_FAILED
                self._last_error = f"{type(error).__name__}: {error}"
                raise
            self._sequence += 1
            self._status = RUN_STATUS_PAUSED
            self._last_error = None
            return self._frame_locked(include_resources)

    def reset(
        self,
        *,
        include_resources: bool = False,
    ) -> Dict[str, object]:
        _require_boolean(include_resources, "include_resources")
        with self._lock:
            self._status = RUN_STATUS_STEPPING
            try:
                replacement = self._new_backend()
            except Exception as error:
                self._sequence += 1
                self._status = RUN_STATUS_FAILED
                self._last_error = f"{type(error).__name__}: {error}"
                raise
            self._backend = replacement
            self._sequence += 1
            self._status = RUN_STATUS_PAUSED
            self._last_error = None
            return self._frame_locked(include_resources)

    def export_snapshot(self) -> Dict[str, object]:
        with self._lock:
            return self._backend.export_snapshot()

    def _frame_locked(self, include_resources: bool) -> Dict[str, object]:
        source = self._backend.frame(include_resources=include_resources)
        return RenderFrame(
            run_id=self.run_id,
            sequence=self._sequence,
            status=self._status,
            tick=source.tick,
            year=source.year,
            metrics=source.metrics,
            agents=source.agents,
            resources=source.resources,
        ).to_dict()

    def _new_backend(self) -> SimulationBackend:
        return self._backend_factory(
            config=self.definition.config,
            seed=self.definition.seed,
            scenario=self.definition.scenario,
        )


class RunManager:
    """Thread-safe registry and facade for independent run sessions."""

    def __init__(
        self,
        *,
        backend_factory: SimulationBackendFactory = python_backend_factory,
        id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._backend_factory = backend_factory
        self._id_factory = id_factory
        self._lock = threading.RLock()
        self._sessions: Dict[str, RunSession] = {}

    def create(
        self,
        *,
        config: ConfigValue = None,
        seed: int = 0,
        scenario: ScenarioValue = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, object]:
        definition = RunDefinition.from_values(
            config=config,
            seed=seed,
            scenario=scenario,
        )
        resolved_id = run_id if run_id is not None else self._id_factory()
        if not isinstance(resolved_id, str) or not resolved_id:
            raise ValueError("run_id must be a nonempty string")
        session = RunSession(
            resolved_id,
            definition,
            backend_factory=self._backend_factory,
        )
        with self._lock:
            if resolved_id in self._sessions:
                raise DuplicateRunError(
                    f"run {resolved_id!r} already exists"
                )
            self._sessions[resolved_id] = session
        return session.manifest()

    def list_manifests(self) -> List[Dict[str, object]]:
        with self._lock:
            sessions = tuple(
                self._sessions[key] for key in sorted(self._sessions)
            )
        return [session.manifest() for session in sessions]

    def manifest(self, run_id: str) -> Dict[str, object]:
        return self._session(run_id).manifest()

    def frame(
        self,
        run_id: str,
        *,
        include_resources: bool = False,
    ) -> Dict[str, object]:
        return self._session(run_id).frame(
            include_resources=include_resources,
        )

    def agent_detail(
        self,
        run_id: str,
        agent_id: Union[int, str],
    ) -> Dict[str, object]:
        return self._session(run_id).agent_detail(agent_id)

    def step(
        self,
        run_id: str,
        ticks: int = 1,
        *,
        include_resources: bool = False,
    ) -> Dict[str, object]:
        return self._session(run_id).step(
            ticks,
            include_resources=include_resources,
        )

    def reset(
        self,
        run_id: str,
        *,
        include_resources: bool = False,
    ) -> Dict[str, object]:
        return self._session(run_id).reset(
            include_resources=include_resources,
        )

    def export_snapshot(self, run_id: str) -> Dict[str, object]:
        return self._session(run_id).export_snapshot()

    def _session(self, run_id: str) -> RunSession:
        with self._lock:
            try:
                return self._sessions[run_id]
            except KeyError:
                raise RunNotFoundError(
                    f"run {run_id!r} does not exist"
                ) from None


def _coerce_config(config: ConfigValue) -> SimulationConfig:
    if config is None:
        return SimulationConfig()
    if isinstance(config, SimulationConfig):
        return config
    if isinstance(config, Mapping):
        return SimulationConfig(**dict(config))
    raise TypeError("config must be SimulationConfig, a mapping, or None")


def _coerce_scenario(
    scenario: ScenarioValue,
    config: SimulationConfig,
) -> Scenario:
    if scenario is None:
        return Scenario.default(config)
    if isinstance(scenario, Scenario):
        return scenario
    if isinstance(scenario, Mapping):
        return Scenario.from_dict(scenario)
    raise TypeError("scenario must be Scenario, a mapping, or None")


def _coerce_agent_id(agent_id: Union[int, str]) -> int:
    if isinstance(agent_id, bool):
        raise ValueError("agent_id must be a nonnegative integer string")
    if isinstance(agent_id, int):
        resolved = agent_id
    elif isinstance(agent_id, str) and agent_id:
        try:
            resolved = int(agent_id)
        except ValueError:
            raise ValueError(
                "agent_id must be a nonnegative integer string"
            ) from None
    else:
        raise ValueError("agent_id must be a nonnegative integer string")
    if resolved < 0:
        raise ValueError("agent_id must be a nonnegative integer string")
    return resolved


def _require_positive_integer(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_boolean(value: bool, name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
