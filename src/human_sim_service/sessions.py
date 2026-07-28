"""Thread-safe run lifecycle independent of any web framework."""

import threading
import time
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
    EventFeed,
    RenderFrame,
    RunManifest,
    RUN_STATUS_FAILED,
    RUN_STATUS_PAUSED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_STEPPING,
)


#: A feed is a notification panel, not a transcript. Capping the window keeps
#: one request from serializing an entire event log.
MAXIMUM_EVENT_WINDOW = 500

#: Longest the driver holds the run's lock in one go.
#:
#: A batch of ticks is stepped without letting go, so a reader asking for a
#: frame waits for it. Keeping the batch short is what stops an unpaced run
#: from starving every observer; keeping it above one tick is what stops the
#: lock churn from costing more than the simulation.
MAXIMUM_BATCH_SECONDS = 0.25

#: How long the driver may sleep before it notices it was asked to stop.
MAXIMUM_SLEEP_SECONDS = 0.5

#: A moment of daylight between batches of an unpaced run.
#:
#: A lock is not a queue. A thread that releases one and immediately asks for
#: it again is usually handed it straight back, so an unpaced driver in a
#: tight loop can keep every reader waiting indefinitely — observed as a
#: 98-second wait for a manifest while a run advanced flat out. Standing back
#: for a moment costs a fraction of a percent of throughput and is the
#: difference between a run that can be watched and one that cannot.
YIELD_SECONDS = 0.004

#: How long to wait for a driver to finish the batch it is in the middle of.
#: Long enough for any sane batch, short enough that a wedged engine cannot
#: hold a request open indefinitely.
STOP_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class PlaybackPlan:
    """How many ticks to take at once, and how long to wait afterwards."""

    ticks: int
    interval: float


def plan_playback(
    seconds_per_year: Optional[float],
    ticks_per_year: int,
    seconds_per_batch: float = MAXIMUM_BATCH_SECONDS,
    measured_seconds_per_tick: float = 0.0,
) -> PlaybackPlan:
    """Turn a wall-clock pace into a batch size and a wait.

    The pace a person sets is *how long a simulated year should take to
    watch*, because that is the quantity they care about — not ticks per
    second, which means nothing without knowing how long a year is. A pace of
    zero or None is "as fast as this machine manages", which is what an
    unattended run left going for days usually wants.

    Batches exist so a fast run does not pay lock and bookkeeping costs per
    tick. They are bounded by *time*, not by count, because that is the thing
    a waiting reader actually experiences: a batch of twelve ticks is nothing
    on a world of forty people and several seconds on a world of two
    thousand, and it is the second case where a frame request goes unanswered
    long enough to look broken. An unpaced run therefore sizes its batch from
    how long a tick has recently taken, which is why the measurement is an
    argument rather than a guess.
    """

    per_year = max(1, int(ticks_per_year))
    if seconds_per_year is None or seconds_per_year <= 0:
        if measured_seconds_per_tick <= 0:
            # Nothing measured yet: start at one tick and learn from it.
            return PlaybackPlan(ticks=1, interval=0.0)
        ticks = max(
            1,
            min(
                per_year,
                int(seconds_per_batch / measured_seconds_per_tick),
            ),
        )
        return PlaybackPlan(ticks=ticks, interval=0.0)
    seconds_per_tick = seconds_per_year / per_year
    if seconds_per_tick >= seconds_per_batch:
        return PlaybackPlan(ticks=1, interval=seconds_per_tick)
    ticks = max(1, min(per_year, round(seconds_per_batch / seconds_per_tick)))
    return PlaybackPlan(ticks=ticks, interval=ticks * seconds_per_tick)


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
        # Playback state is deliberately separate from the run lock: the
        # driver has to be able to notice a stop request while the lock is
        # held by whatever is currently reading the run.
        self._playback_lock = threading.Lock()
        self._playing = False
        self._seconds_per_year: Optional[float] = None
        self._driver: Optional[threading.Thread] = None
        self._halt = threading.Event()

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
                    "playback": True,
                },
                playback=self.playback(),
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

    def events(
        self,
        since_tick: int = -1,
        limit: int = 200,
    ) -> Dict[str, object]:
        _require_integer(since_tick, "since_tick")
        _require_positive_integer(limit, "limit")
        with self._lock:
            source = self._backend.events(
                since_tick=since_tick,
                limit=min(limit, MAXIMUM_EVENT_WINDOW),
            )
            return EventFeed(
                run_id=self.run_id,
                sequence=self._sequence,
                status=self._status,
                tick=source.tick,
                year=source.year,
                events=source.events,
                oldest_retained_tick=source.oldest_retained_tick,
                dropped=source.dropped,
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
            self._advance_locked(ticks)
            return self._frame_locked(include_resources)

    def advance(self, ticks: int = 1) -> None:
        """Move the run on without projecting a frame for anybody.

        Rendering a frame means building a column per agent and copying the
        lot. That is worth doing for a caller who is going to look at it, and
        pure waste for the driver of an unattended run — which was doing it
        after every batch, under the lock, for a world nobody was watching.
        """

        _require_positive_integer(ticks, "ticks")
        with self._lock:
            self._advance_locked(ticks)

    def _advance_locked(self, ticks: int) -> None:
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
        self._status = self._resting_status()
        self._last_error = None

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
            self._status = self._resting_status()
            self._last_error = None
            return self._frame_locked(include_resources)

    def _resting_status(self) -> str:
        """What this run is between steps: still driving, or waiting."""

        with self._playback_lock:
            return RUN_STATUS_RUNNING if self._playing else RUN_STATUS_PAUSED

    def playback(self) -> Dict[str, object]:
        with self._playback_lock:
            return {
                "playing": self._playing,
                "seconds_per_year": self._seconds_per_year,
            }

    def set_playback(
        self,
        playing: bool,
        seconds_per_year: Optional[float] = None,
    ) -> Dict[str, object]:
        """Hand the run to the engine's own clock, or take it back.

        While playing, the run advances without anybody asking it to: the
        process holding it is the simulation, not the browser looking at it,
        so closing a window or restarting a UI leaves the world going. What
        this cannot survive is the service process itself ending — runs live
        in memory, and there is no rehydration path yet.
        """

        _require_boolean(playing, "playing")
        pace = _coerce_pace(seconds_per_year)
        if playing and self.status == RUN_STATUS_FAILED:
            raise RunFailedError(
                f"run {self.run_id!r} failed; reset it before playing"
            )

        driver: Optional[threading.Thread] = None
        with self._playback_lock:
            self._seconds_per_year = pace
            if playing and not self._playing:
                self._playing = True
                self._halt.clear()
                self._driver = threading.Thread(
                    target=self._drive,
                    name=f"playback-{self.run_id}",
                    daemon=True,
                )
                self._driver.start()
            elif not playing:
                self._playing = False
                self._halt.set()
                driver = self._driver
                self._driver = None

        if playing:
            # Say it is running now rather than once the first batch lands.
            # A reader who asks in between is looking at a run that is being
            # driven, and "paused" would be the wrong word for it.
            with self._lock:
                if self._status != RUN_STATUS_FAILED:
                    self._status = RUN_STATUS_RUNNING
        else:
            # Stopping waits for the batch already in flight, so that when
            # this returns the run really has stopped moving. Anything else
            # makes the tick reported here a number that was already stale,
            # and makes a step by hand land at an unpredictable point.
            # Joined outside the playback lock, which the driver's own exit
            # path needs to take.
            if driver is not None and driver is not threading.current_thread():
                driver.join(timeout=STOP_TIMEOUT_SECONDS)
            with self._lock:
                if self._status == RUN_STATUS_RUNNING:
                    self._status = RUN_STATUS_PAUSED

        return self.playback()

    def _drive(self) -> None:
        """Step the run on the engine's own clock until told to stop.

        Every batch is stepped through the same locked path a request uses,
        so an observer never sees a half-advanced world and a failure is
        recorded the same way whoever caused it. A failed run stops driving
        itself: continuing to hammer a broken engine would bury the error
        under thousands of identical ones.
        """

        ticks_per_year = max(1, int(self.definition.config.ticks_per_year))
        # How long a tick has been costing lately. Smoothed, because tick cost
        # drifts with population and a single slow tick should not resize
        # every batch after it.
        measured = 0.0
        while not self._halt.is_set():
            with self._playback_lock:
                pace = self._seconds_per_year
            plan = plan_playback(
                pace,
                ticks_per_year,
                measured_seconds_per_tick=measured,
            )
            started = time.monotonic()
            try:
                self.advance(plan.ticks)
            except Exception:
                # advance() has already recorded the failure and the status.
                break
            spent = time.monotonic() - started
            sample = spent / max(1, plan.ticks)
            measured = (
                sample
                if measured == 0.0
                else measured * 0.7 + sample * 0.3
            )
            if self._halt.is_set():
                break
            remaining = plan.interval - spent
            if remaining <= 0:
                # Always stand back, even flat out. See YIELD_SECONDS.
                self._halt.wait(YIELD_SECONDS)
                continue
            while remaining > 0 and not self._halt.is_set():
                self._halt.wait(min(MAXIMUM_SLEEP_SECONDS, remaining))
                remaining = plan.interval - (time.monotonic() - started)
        with self._playback_lock:
            self._playing = False
        with self._lock:
            if self._status == RUN_STATUS_RUNNING:
                self._status = RUN_STATUS_PAUSED

    def close(self) -> None:
        """Stop driving this run and wait for the driver to notice."""

        with self._playback_lock:
            self._playing = False
            driver = self._driver
            self._driver = None
        self._halt.set()
        if driver is not None and driver is not threading.current_thread():
            driver.join(timeout=STOP_TIMEOUT_SECONDS)

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
            fauna=source.fauna,
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

    def events(
        self,
        run_id: str,
        since_tick: int = -1,
        limit: int = 200,
    ) -> Dict[str, object]:
        return self._session(run_id).events(
            since_tick=since_tick,
            limit=limit,
        )

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

    def playback(self, run_id: str) -> Dict[str, object]:
        return self._session(run_id).playback()

    def set_playback(
        self,
        run_id: str,
        playing: bool,
        seconds_per_year: Optional[float] = None,
    ) -> Dict[str, object]:
        return self._session(run_id).set_playback(
            playing,
            seconds_per_year=seconds_per_year,
        )

    def delete(self, run_id: str) -> None:
        """Forget a run and stop whatever was driving it.

        Runs are held in memory for as long as the service lives, so a
        reattaching client that keeps making new ones instead of finding the
        old one leaves a world behind every time. Deleting is how that space
        is reclaimed; there is no other way back.
        """

        with self._lock:
            session = self._sessions.pop(run_id, None)
        if session is None:
            raise RunNotFoundError(f"run {run_id!r} does not exist")
        session.close()

    def close(self) -> None:
        """Stop every driver, for a service that is shutting down."""

        with self._lock:
            sessions = tuple(self._sessions.values())
        for session in sessions:
            session.close()

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


def _coerce_pace(seconds_per_year: object) -> Optional[float]:
    if seconds_per_year is None:
        return None
    if isinstance(seconds_per_year, bool) or not isinstance(
        seconds_per_year,
        (int, float),
    ):
        raise TypeError("seconds_per_year must be a number or null")
    value = float(seconds_per_year)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("seconds_per_year must be finite")
    if value < 0:
        raise ValueError("seconds_per_year cannot be negative")
    return value


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


def _require_integer(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")


def _require_positive_integer(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_boolean(value: bool, name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
