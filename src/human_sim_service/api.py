"""Optional FastAPI transport for the framework-neutral run service.

Install ``requirements-api.txt`` to use this module.  The simulation package
itself remains dependency-free.
"""

from typing import Annotated, Any, Dict, Optional

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


class ResetRunRequest(BaseModel):
    """Recreate a run from its original immutable definition."""

    model_config = ConfigDict(extra="forbid")

    include_resources: bool = False


class ValidateScenarioRequest(BaseModel):
    """Validate and normalize scenario-editor input through the engine rules."""

    model_config = ConfigDict(extra="forbid")

    config: Optional[Dict[str, Any]] = None
    scenario: Optional[Dict[str, Any]] = None


def create_app(manager: Optional[RunManager] = None) -> FastAPI:
    """Build an application with an injectable run registry for tests/hosting."""

    runs = manager or RunManager()
    app = FastAPI(
        title="Human-Sim service",
        summary="Versioned control and observation API for Human-Sim runs.",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
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

    @app.get("/api/v1/runs/{run_id}/agents/{agent_id}")
    def agent_detail(
        run_id: str,
        agent_id: str,
    ) -> Dict[str, object]:
        return runs.agent_detail(run_id, agent_id)

    @app.get("/api/v1/runs/{run_id}/snapshot")
    def export_snapshot(run_id: str) -> Dict[str, object]:
        return runs.export_snapshot(run_id)

    return app


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
