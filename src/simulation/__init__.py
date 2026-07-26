"""Deterministic, headless society simulation primitives."""

from .brain import BrainState
from .config import SimulationConfig
from .engine import Simulation
from .genetics import Gene, Genome, genetic_distance
from .models import (
    ActionKind,
    Agent,
    BrainKind,
    Event,
    Metrics,
    ReproductiveRole,
    Terrain,
    Traits,
)
from .scenario import CountrySpec, Rectangle, Scenario

__all__ = [
    "ActionKind",
    "Agent",
    "BrainKind",
    "BrainState",
    "CountrySpec",
    "Event",
    "Gene",
    "Genome",
    "Metrics",
    "Rectangle",
    "ReproductiveRole",
    "Scenario",
    "Simulation",
    "SimulationConfig",
    "Terrain",
    "Traits",
    "genetic_distance",
]
