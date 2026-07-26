"""Pure disease-state helpers for the reference and future native backends."""

import math
from enum import IntEnum


class InfectionStage(IntEnum):
    SUSCEPTIBLE = 0
    EXPOSED = 1
    INFECTIOUS = 2
    RECOVERED = 3


def transmission_probability(
    annual_rate: float,
    local_infectious_pressure: float,
    susceptibility: float,
    elapsed_years: float,
) -> float:
    """Convert local infectious pressure into a bounded interval probability."""

    for value, name in (
        (annual_rate, "annual_rate"),
        (local_infectious_pressure, "local_infectious_pressure"),
        (susceptibility, "susceptibility"),
        (elapsed_years, "elapsed_years"),
    ):
        if value < 0.0 or not math.isfinite(value):
            raise ValueError(f"{name} must be finite and nonnegative")
    hazard = annual_rate * local_infectious_pressure * susceptibility
    return min(1.0, max(0.0, -math.expm1(-hazard * elapsed_years)))


def host_susceptibility(
    age_years: float,
    maturity_age_years: float,
    immune_strength: float,
    body_condition: float,
    frailty: float,
) -> float:
    """Return abstract relative susceptibility from current host condition."""

    if age_years < 0.0 or maturity_age_years <= 0.0:
        raise ValueError("ages must be nonnegative with positive maturity")
    immune = _clamp(immune_strength)
    condition = _clamp(body_condition)
    frailty_value = _clamp(frailty)
    juvenile_vulnerability = (
        0.25 * (1.0 - min(age_years / maturity_age_years, 1.0))
    )
    return max(
        0.05,
        (1.15 - 0.65 * immune)
        * (0.75 + 0.50 * (1.0 - condition))
        * (1.0 + 0.75 * frailty_value)
        * (1.0 + juvenile_vulnerability),
    )


def disease_severity(
    immune_strength: float,
    body_condition: float,
    frailty: float,
) -> float:
    """Return relative energetic and health burden while infectious."""

    immune = _clamp(immune_strength)
    condition = _clamp(body_condition)
    frailty_value = _clamp(frailty)
    return max(
        0.05,
        (1.20 - 0.65 * immune)
        * (0.75 + 0.75 * (1.0 - condition))
        * (1.0 + frailty_value),
    )


def duration_ticks(
    years: float,
    ticks_per_year: int,
    multiplier: float = 1.0,
) -> int:
    """Convert a positive stage duration to at least one simulation tick."""

    if years <= 0.0 or not math.isfinite(years):
        raise ValueError("stage duration must be finite and positive")
    if ticks_per_year <= 0:
        raise ValueError("ticks_per_year must be positive")
    if multiplier <= 0.0 or not math.isfinite(multiplier):
        raise ValueError("duration multiplier must be finite and positive")
    return max(1, round(years * ticks_per_year * multiplier))


def _clamp(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("host state must be finite")
    return min(1.0, max(0.0, value))


__all__ = [
    "InfectionStage",
    "disease_severity",
    "duration_ticks",
    "host_susceptibility",
    "transmission_probability",
]
