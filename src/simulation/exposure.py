"""Pure formulas for the physical cost of standing in the environment.

The world does not have a climate layer yet.  What it already has is a local,
latitude-dependent season which agents can sense.  Its distance from the
annual midpoint is therefore the smallest honest exposure signal available:
both a hot and a cold extreme make thermoregulation costlier, while an
equable row does not.

Insulation is an input rather than an artifact lookup.  Today every caller
passes the default of zero; Track B2 can later supply a measurable physical
effect without teaching this module what a house is.
"""


def seasonal_exposure(season: float, insulation: float = 0.0) -> float:
    """Return effective local exposure after bounded insulation.

    ``season`` is the value returned by :meth:`World.season_at`, centred on
    zero.  Insulation is a fraction of that pressure removed.  Clamping here
    keeps a future artifact from creating energy when its effects overlap.
    """

    protection = min(1.0, max(0.0, insulation))
    return abs(season) * (1.0 - protection)


def exposure_energy_cost(
    season: float,
    annual_cost: float,
    elapsed_years: float,
    insulation: float = 0.0,
) -> float:
    """Energy required over an interval by the local seasonal extreme."""

    return (
        annual_cost
        * elapsed_years
        * seasonal_exposure(season, insulation)
    )
