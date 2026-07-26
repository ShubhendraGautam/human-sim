"""Pure life-history functions shared by simulation backends.

All ages, durations, and rates in this module use years.  The functions hold
no simulation state, consume no randomness, and depend only on scalar inputs,
which keeps their formulas straightforward to reproduce in a native backend.
"""

import math

OVA_ROLE = "ova"
SPERM_ROLE = "sperm"


def clamp(
    value: float,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    """Return *value* restricted to the inclusive [minimum, maximum] range."""

    if minimum > maximum:
        raise ValueError("minimum cannot exceed maximum")
    if not (
        math.isfinite(value)
        and math.isfinite(minimum)
        and math.isfinite(maximum)
    ):
        raise ValueError("clamp inputs must be finite")
    return min(maximum, max(minimum, value))


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    """Return a smooth cubic transition from zero to one between two edges."""

    if not (
        math.isfinite(edge0)
        and math.isfinite(edge1)
        and math.isfinite(value)
    ):
        raise ValueError("smoothstep inputs must be finite")
    if edge1 <= edge0:
        raise ValueError("edge1 must be greater than edge0")
    progress = clamp((value - edge0) / (edge1 - edge0))
    return progress * progress * (3.0 - 2.0 * progress)


def age_capability(
    age_years: float,
    maturity_age_years: float,
    onset_age_years: float = 0.0,
    minimum_capability: float = 0.0,
) -> float:
    """Return continuous capability during growth.

    Capability equals ``minimum_capability`` through ``onset_age_years``,
    follows a smooth transition during development, and equals one from
    ``maturity_age_years`` onward.
    """

    if age_years < 0.0:
        raise ValueError("age_years cannot be negative")
    if onset_age_years < 0.0:
        raise ValueError("onset_age_years cannot be negative")
    if maturity_age_years <= onset_age_years:
        raise ValueError("maturity age must be greater than onset age")
    floor = clamp(minimum_capability)
    progress = smoothstep(
        onset_age_years,
        maturity_age_years,
        age_years,
    )
    return floor + (1.0 - floor) * progress


def age_fecundity(
    role: str,
    age_years: float,
    maturity_age_years: float,
    ova_peak_age_years: float,
    ova_decline_age_years: float,
    ova_end_age_years: float,
    sperm_peak_age_years: float,
    sperm_decline_age_years: float,
    sperm_end_age_years: float,
) -> float:
    """Return the age component of fecundity for a reproductive role.

    The selected curve rises smoothly from zero at biological maturity to one
    at its peak, remains at one through the decline age, then falls smoothly to
    zero at the reproductive end age.
    """

    if age_years < 0.0:
        raise ValueError("age_years cannot be negative")
    if role == OVA_ROLE:
        peak_age = ova_peak_age_years
        decline_age = ova_decline_age_years
        end_age = ova_end_age_years
    elif role == SPERM_ROLE:
        peak_age = sperm_peak_age_years
        decline_age = sperm_decline_age_years
        end_age = sperm_end_age_years
    else:
        raise ValueError(f"unknown reproductive role: {role!r}")

    if not (
        0.0 <= maturity_age_years < peak_age <= decline_age < end_age
    ):
        raise ValueError(
            "fecundity ages must satisfy "
            "0 <= maturity < peak <= decline < end"
        )
    rise = smoothstep(maturity_age_years, peak_age, age_years)
    decline = 1.0 - smoothstep(decline_age, end_age, age_years)
    return clamp(rise * decline)


def annual_hazard_to_tick(
    annual_hazard: float,
    elapsed_years: float,
) -> float:
    """Convert a constant annual hazard rate to an interval probability."""

    if annual_hazard < 0.0 or not math.isfinite(annual_hazard):
        raise ValueError("annual_hazard must be finite and nonnegative")
    if elapsed_years < 0.0 or not math.isfinite(elapsed_years):
        raise ValueError("elapsed_years must be finite and nonnegative")
    return clamp(-math.expm1(-annual_hazard * elapsed_years))


def update_body_condition(
    current_condition: float,
    energy_fraction: float,
    elapsed_years: float,
    memory_years: float,
) -> float:
    """Apply an exact exponential moving average of current energy sufficiency.

    ``memory_years`` is the EMA time constant.  For a constant energy signal,
    this exact update gives the same result whether an interval is processed as
    one long step or many shorter steps.
    """

    if elapsed_years < 0.0 or not math.isfinite(elapsed_years):
        raise ValueError("elapsed_years must be finite and nonnegative")
    if memory_years <= 0.0 or not math.isfinite(memory_years):
        raise ValueError("memory_years must be finite and positive")
    current = clamp(current_condition)
    target = clamp(energy_fraction)
    retention = math.exp(-elapsed_years / memory_years)
    return clamp(target + (current - target) * retention)


def update_development(
    current_development: float,
    age_years: float,
    body_condition: float,
    elapsed_years: float,
    maturity_age_years: float,
) -> float:
    """Update the time-weighted mean condition observed during childhood.

    Only the portion of the interval before biological maturity contributes.
    Once maturity has been reached, the returned developmental value is frozen.
    ``age_years`` is the age at the beginning of the interval.
    """

    if age_years < 0.0 or not math.isfinite(age_years):
        raise ValueError("age_years must be finite and nonnegative")
    if elapsed_years < 0.0 or not math.isfinite(elapsed_years):
        raise ValueError("elapsed_years must be finite and nonnegative")
    if maturity_age_years <= 0.0 or not math.isfinite(maturity_age_years):
        raise ValueError("maturity_age_years must be finite and positive")

    current = clamp(current_development)
    condition = clamp(body_condition)
    observed_before = min(age_years, maturity_age_years)
    observed_after = min(
        age_years + elapsed_years,
        maturity_age_years,
    )
    new_exposure = observed_after - observed_before
    if new_exposure <= 0.0:
        return current
    if observed_after <= 0.0:
        return condition
    return clamp(
        (
            current * observed_before
            + condition * new_exposure
        )
        / observed_after
    )


def update_development_exposure(
    current_development: float,
    observed_years: float,
    body_condition: float,
    new_exposure_years: float,
) -> tuple[float, float]:
    """Extend a time-weighted developmental-condition history.

    Unlike :func:`update_development`, the amount of prior exposure is
    explicit. This lets prenatal condition contribute a gestation-sized prior
    without pretending that a newborn's chronological age is nonzero.
    """

    if observed_years < 0.0 or not math.isfinite(observed_years):
        raise ValueError("observed_years must be finite and nonnegative")
    if new_exposure_years < 0.0 or not math.isfinite(new_exposure_years):
        raise ValueError(
            "new_exposure_years must be finite and nonnegative"
        )
    current = clamp(current_development)
    condition = clamp(body_condition)
    total = observed_years + new_exposure_years
    if total <= 0.0:
        return current, 0.0
    return (
        clamp(
            (
                current * observed_years
                + condition * new_exposure_years
            )
            / total
        ),
        total,
    )


def update_frailty(
    current_frailty: float,
    age_years: float,
    elapsed_years: float,
    longevity_years: float,
    constitution: float,
    body_condition: float,
    onset_fraction: float,
    base_annual_rate: float,
    age_acceleration: float,
    constitution_protection: float,
    nutrition_penalty: float,
) -> float:
    """Accumulate bounded frailty from an age-accelerating annual rate.

    Frailty begins at ``longevity_years * onset_fraction``.  The age component
    grows exponentially with age measured as a fraction of the longevity
    scale.  Its integral is evaluated analytically, making accumulation stable
    across different tick sizes while constitution and body condition remain
    constant over the interval.
    """

    if age_years < 0.0 or not math.isfinite(age_years):
        raise ValueError("age_years must be finite and nonnegative")
    if elapsed_years < 0.0 or not math.isfinite(elapsed_years):
        raise ValueError("elapsed_years must be finite and nonnegative")
    if longevity_years <= 0.0 or not math.isfinite(longevity_years):
        raise ValueError("longevity_years must be finite and positive")
    if base_annual_rate < 0.0 or not math.isfinite(base_annual_rate):
        raise ValueError("base_annual_rate must be finite and nonnegative")
    if age_acceleration < 0.0 or not math.isfinite(age_acceleration):
        raise ValueError("age_acceleration must be finite and nonnegative")
    if nutrition_penalty < 0.0 or not math.isfinite(nutrition_penalty):
        raise ValueError("nutrition_penalty must be finite and nonnegative")

    frailty = clamp(current_frailty)
    constitution_value = clamp(constitution)
    condition = clamp(body_condition)
    onset = clamp(onset_fraction)
    protection = clamp(constitution_protection)
    onset_age = longevity_years * onset
    exposed_start = max(age_years, onset_age)
    exposed_end = max(age_years + elapsed_years, onset_age)
    exposed_years = exposed_end - exposed_start
    if exposed_years <= 0.0 or base_annual_rate == 0.0:
        return frailty

    start_fraction = (exposed_start - onset_age) / longevity_years
    if age_acceleration == 0.0:
        age_integral = exposed_years
    else:
        interval_fraction = exposed_years / longevity_years
        age_integral = (
            longevity_years
            * math.exp(age_acceleration * start_fraction)
            * math.expm1(age_acceleration * interval_fraction)
            / age_acceleration
        )

    vulnerability = (
        (1.0 - protection * constitution_value)
        * (1.0 + nutrition_penalty * (1.0 - condition))
    )
    return clamp(
        frailty + base_annual_rate * age_integral * vulnerability
    )


def effective_health_capacity(
    genetic_health_capacity: float,
    development: float,
    frailty: float,
    developmental_floor: float,
    maximum_frailty_loss: float,
) -> float:
    """Return current health capacity after development and accumulated frailty."""

    if (
        genetic_health_capacity < 0.0
        or not math.isfinite(genetic_health_capacity)
    ):
        raise ValueError(
            "genetic_health_capacity must be finite and nonnegative"
        )
    development_value = clamp(development)
    frailty_value = clamp(frailty)
    floor = clamp(developmental_floor)
    frailty_loss = clamp(maximum_frailty_loss)
    developmental_multiplier = (
        floor + (1.0 - floor) * development_value
    )
    frailty_multiplier = 1.0 - frailty_loss * frailty_value
    return (
        genetic_health_capacity
        * developmental_multiplier
        * frailty_multiplier
    )


__all__ = [
    "OVA_ROLE",
    "SPERM_ROLE",
    "age_capability",
    "age_fecundity",
    "annual_hazard_to_tick",
    "clamp",
    "effective_health_capacity",
    "smoothstep",
    "update_body_condition",
    "update_development",
    "update_development_exposure",
    "update_frailty",
]
