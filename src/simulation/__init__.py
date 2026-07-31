"""Deterministic, headless society simulation primitives."""

from .brain import BrainState
from .config import CONFIG_SCHEMA_VERSION, SimulationConfig
from .engine import Simulation
from .entities import (
    INERT_KINDS,
    LIVING_KINDS,
    EntityKind,
    EntityRegistry,
    Placeable,
)
from .genetics import GENOME_SCHEMA_VERSION, Gene, Genome, genetic_distance
from .health import (
    InfectionStage,
    disease_severity,
    duration_ticks,
    host_susceptibility,
    transmission_probability,
)
from .life_history import (
    age_capability,
    age_fecundity,
    annual_hazard_to_tick,
    effective_health_capacity,
    update_body_condition,
    update_development,
    update_development_exposure,
    update_frailty,
)
from .models import (
    ActionKind,
    Agent,
    BrainKind,
    CultureState,
    Event,
    Metrics,
    Pregnancy,
    ReproductiveRole,
    Terrain,
    Traits,
)
from . import neural
from .scenario import CountrySpec, Rectangle, Scenario
from .relationships import RelationshipStore, RelationshipView
from .versions import CHECKPOINT_SCHEMA_VERSION
from .world import LocalConditions

__all__ = [
    "ActionKind",
    "Agent",
    "BrainKind",
    "BrainState",
    "CHECKPOINT_SCHEMA_VERSION",
    "CountrySpec",
    "CONFIG_SCHEMA_VERSION",
    "CultureState",
    "EntityKind",
    "EntityRegistry",
    "Event",
    "INERT_KINDS",
    "LIVING_KINDS",
    "LocalConditions",
    "Gene",
    "Genome",
    "GENOME_SCHEMA_VERSION",
    "InfectionStage",
    "Metrics",
    "Placeable",
    "Pregnancy",
    "Rectangle",
    "ReproductiveRole",
    "RelationshipStore",
    "RelationshipView",
    "Scenario",
    "neural",
    "Simulation",
    "SimulationConfig",
    "Terrain",
    "Traits",
    "age_capability",
    "age_fecundity",
    "annual_hazard_to_tick",
    "effective_health_capacity",
    "disease_severity",
    "duration_ticks",
    "genetic_distance",
    "host_susceptibility",
    "transmission_probability",
    "update_body_condition",
    "update_development",
    "update_development_exposure",
    "update_frailty",
]
