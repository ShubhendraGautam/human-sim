"""Optional FastAPI transport for the framework-neutral run service.

Install ``requirements-api.txt`` to use this module.  The simulation package
itself remains dependency-free.
"""

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Annotated, Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.simulation import CONFIG_SCHEMA_VERSION, SimulationConfig

from .contracts import PROTOCOL_VERSION
from .sessions import (
    AgentNotFoundError,
    DuplicateRunError,
    RunDefinition,
    RunFailedError,
    RunManager,
    RunNotFoundError,
)


StrictSeed = Annotated[int, Field(strict=True)]
StepCount = Annotated[int, Field(strict=True, ge=1, le=10_000)]


class CreateRunRequest(BaseModel):
    """Serializable, immutable inputs for a new deterministic run."""

    model_config = ConfigDict(extra="forbid")

    seed: StrictSeed = 0
    config: Optional[Dict[str, Any]] = None
    scenario: Optional[Dict[str, Any]] = None


class StepRunRequest(BaseModel):
    """Advance a paused run and return its newest render frame."""

    model_config = ConfigDict(extra="forbid")

    ticks: StepCount = 1
    include_resources: bool = False


class PlaybackRequest(BaseModel):
    """Hand a run to the engine's own clock, or take it back.

    ``seconds_per_year`` is the wall-clock time one simulated year should
    take. Zero means as fast as the machine manages, which is the usual
    setting for a run left going unattended. Omitting it keeps whatever pace
    the run already had.
    """

    model_config = ConfigDict(extra="forbid")

    # Strict, like the other transport inputs: a client that sends "yes"
    # for playing is a client with a bug, and quietly reading it as true
    # would set a world going on the strength of a coercion.
    playing: Annotated[bool, Field(strict=True)]
    seconds_per_year: Optional[Annotated[float, Field(ge=0)]] = None


class ResetRunRequest(BaseModel):
    """Recreate a run from its original immutable definition."""

    model_config = ConfigDict(extra="forbid")

    include_resources: bool = False


class RestoreCheckpointRequest(BaseModel):
    """Create a paused run from complete causal state."""

    model_config = ConfigDict(extra="forbid")

    checkpoint: Dict[str, Any]
    run_id: Optional[str] = None


class ValidateScenarioRequest(BaseModel):
    """Validate scenario-editor input against the engine rules."""

    model_config = ConfigDict(extra="forbid")

    config: Optional[Dict[str, Any]] = None
    scenario: Optional[Dict[str, Any]] = None


def create_app(manager: Optional[RunManager] = None) -> FastAPI:
    """Build an app with an injectable run registry for tests."""

    runs = manager or _manager_from_environment()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        # Driver threads are daemons and would not hold the process open,
        # but leaving them stepping through interpreter teardown produces
        # failures that describe nothing.
        runs.close()

    app = FastAPI(
        title="Human-Sim service",
        summary="Versioned control and observation API for Human-Sim runs.",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.run_manager = runs

    @app.exception_handler(RunNotFoundError)
    async def handle_missing_run(
        _request: object,
        error: RunNotFoundError,
    ) -> JSONResponse:
        return _error_response(status.HTTP_404_NOT_FOUND, str(error))

    @app.exception_handler(AgentNotFoundError)
    async def handle_missing_agent(
        _request: object,
        error: AgentNotFoundError,
    ) -> JSONResponse:
        return _error_response(status.HTTP_404_NOT_FOUND, str(error))

    @app.exception_handler(DuplicateRunError)
    async def handle_duplicate_run(
        _request: object,
        error: DuplicateRunError,
    ) -> JSONResponse:
        return _error_response(status.HTTP_409_CONFLICT, str(error))

    @app.exception_handler(RunFailedError)
    async def handle_failed_run(
        _request: object,
        error: RunFailedError,
    ) -> JSONResponse:
        return _error_response(status.HTTP_409_CONFLICT, str(error))

    @app.exception_handler(ValueError)
    async def handle_invalid_value(
        _request: object,
        error: ValueError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            str(error),
        )

    @app.exception_handler(TypeError)
    async def handle_invalid_type(
        _request: object,
        error: TypeError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            str(error),
        )

    @app.get("/api/v1/health")
    def health() -> Dict[str, object]:
        return {
            "status": "ok",
            "protocol_version": PROTOCOL_VERSION,
        }

    @app.get("/api/v1/catalog/config")
    def config_catalog() -> Dict[str, object]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "config_schema_version": CONFIG_SCHEMA_VERSION,
            "defaults": SimulationConfig().to_dict(),
        }

    @app.post("/api/v1/scenarios/validate")
    def validate_scenario(
        request: ValidateScenarioRequest,
    ) -> Dict[str, object]:
        definition = RunDefinition.from_values(
            config=request.config,
            scenario=request.scenario,
        )
        return {
            "protocol_version": PROTOCOL_VERSION,
            "valid": True,
            "config": definition.config.to_dict(),
            "scenario": definition.scenario.to_dict(),
        }

    @app.get("/api/v1/runs")
    def list_runs() -> Dict[str, object]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "runs": runs.list_manifests(),
        }

    @app.post(
        "/api/v1/runs",
        status_code=status.HTTP_201_CREATED,
    )
    def create_run(request: CreateRunRequest) -> Dict[str, object]:
        return runs.create(
            config=request.config,
            seed=request.seed,
            scenario=request.scenario,
        )

    @app.post(
        "/api/v1/checkpoints/restore",
        status_code=status.HTTP_201_CREATED,
    )
    def restore_checkpoint(
        request: RestoreCheckpointRequest,
    ) -> Dict[str, object]:
        return runs.restore(
            request.checkpoint,
            run_id=request.run_id,
        )

    @app.get("/api/v1/runs/{run_id}/manifest")
    def run_manifest(run_id: str) -> Dict[str, object]:
        return runs.manifest(run_id)

    @app.get("/api/v1/runs/{run_id}/frame")
    def run_frame(
        run_id: str,
        include_resources: Annotated[bool, Query()] = False,
    ) -> Dict[str, object]:
        return runs.frame(
            run_id,
            include_resources=include_resources,
        )

    @app.post("/api/v1/runs/{run_id}/steps")
    def step_run(
        run_id: str,
        request: StepRunRequest,
    ) -> Dict[str, object]:
        return runs.step(
            run_id,
            request.ticks,
            include_resources=request.include_resources,
        )

    @app.post("/api/v1/runs/{run_id}/reset")
    def reset_run(
        run_id: str,
        request: ResetRunRequest,
    ) -> Dict[str, object]:
        return runs.reset(
            run_id,
            include_resources=request.include_resources,
        )

    @app.get("/api/v1/runs/{run_id}/playback")
    def playback(run_id: str) -> Dict[str, object]:
        return _playback_response(runs, run_id, runs.playback(run_id))

    @app.post("/api/v1/runs/{run_id}/playback")
    def set_playback(
        run_id: str,
        request: PlaybackRequest,
    ) -> Dict[str, object]:
        # An omitted pace keeps the one the run already had, so pausing and
        # resuming does not silently reset a carefully chosen pace.
        pace = (
            request.seconds_per_year
            if request.seconds_per_year is not None
            else runs.playback(run_id)["seconds_per_year"]
        )
        state = runs.set_playback(
            run_id,
            request.playing,
            seconds_per_year=pace,
        )
        return _playback_response(runs, run_id, state)

    @app.delete("/api/v1/runs/{run_id}", status_code=status.HTTP_200_OK)
    def delete_run(run_id: str) -> Dict[str, object]:
        runs.delete(run_id)
        return {"protocol_version": PROTOCOL_VERSION, "run_id": run_id}

    @app.get("/api/v1/runs/{run_id}/agents/{agent_id}")
    def agent_detail(
        run_id: str,
        agent_id: str,
    ) -> Dict[str, object]:
        return runs.agent_detail(run_id, agent_id)

    @app.get("/api/v1/runs/{run_id}/events")
    def events(
        run_id: str,
        since_tick: int = -1,
        limit: int = 200,
    ) -> Dict[str, object]:
        return runs.events(run_id, since_tick=since_tick, limit=limit)

    @app.get("/api/v1/runs/{run_id}/snapshot")
    def export_snapshot(run_id: str) -> Dict[str, object]:
        return runs.export_snapshot(run_id)

    @app.get("/api/v1/runs/{run_id}/checkpoint")
    def export_checkpoint(run_id: str) -> Dict[str, object]:
        return runs.export_checkpoint(run_id)

    return app


def _manager_from_environment() -> RunManager:
    directory = os.environ.get("HUMAN_SIM_CHECKPOINT_DIR")
    raw_ticks = os.environ.get("HUMAN_SIM_AUTOSAVE_TICKS", "0")
    try:
        autosave_ticks = int(raw_ticks)
    except ValueError:
        raise ValueError(
            "HUMAN_SIM_AUTOSAVE_TICKS must be a nonnegative integer"
        ) from None
    return RunManager(
        checkpoint_directory=None if not directory else Path(directory),
        autosave_ticks=autosave_ticks,
    )


def _playback_response(
    runs: RunManager,
    run_id: str,
    state: Dict[str, object],
) -> Dict[str, object]:
    """Playback state beside enough of the run to act on it."""

    manifest = runs.manifest(run_id)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run_id,
        "status": manifest["status"],
        "tick": manifest["tick"],
        "year": manifest["year"],
        "population": manifest["population"],
        "playback": state,
    }


def _error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "protocol_version": PROTOCOL_VERSION,
            "error": {
                "message": message,
            },
        },
    )


app = create_app()


def main() -> None:
    """Run the optional local development service."""

    import uvicorn

    uvicorn.run(
        "src.human_sim_service.api:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
