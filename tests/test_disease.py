"""How infection gets into a population, and what happens when it cannot.

The engine models one generic local SEIR process. Left to itself it has a
single door: whoever is seeded at founding. An outbreak that ends therefore
ends permanently, because nothing outside the population can reintroduce it,
and a founding seed that fizzles in a sparse world leaves a world that can
never be sick again. These tests pin both the door and its absence.
"""

import unittest

from src.simulation import (
    InfectionStage,
    Simulation,
    SimulationConfig,
)


def clean_population(**overrides) -> Simulation:
    """Nobody infected, nobody immune, nothing in flight."""

    config = SimulationConfig(**{
        "width": 10,
        "height": 10,
        "initial_population": 40,
        "initial_exposed_fraction": 0.0,
        "baseline_mortality_rate_per_year": 0.0,
        **overrides,
    })
    simulation = Simulation(config=config, seed=7)
    for agent in simulation.agents.values():
        agent.infection_stage = InfectionStage.SUSCEPTIBLE
        agent.infection_ticks_remaining = 0
    return simulation


def exposures_over(simulation: Simulation, ticks: int) -> int:
    before = simulation.total_infections
    for _ in range(ticks):
        simulation._advance_disease()
    return simulation.total_infections - before


class ClosedReservoirTests(unittest.TestCase):
    """The old behavior, kept reachable so runs stay comparable across it."""

    def test_nothing_reaches_a_clean_population(self) -> None:
        simulation = clean_population(
            environmental_exposure_rate_per_year=0.0,
        )

        self.assertEqual(exposures_over(simulation, 240), 0)

    def test_an_outbreak_that_ends_can_never_return(self) -> None:
        simulation = clean_population(
            environmental_exposure_rate_per_year=0.0,
            disease_transmission_rate_per_year=0.0,
        )
        patient = simulation._ordered_agents()[0]
        patient.infection_stage = InfectionStage.INFECTIOUS
        patient.infection_ticks_remaining = 2

        exposures_over(simulation, 240)

        self.assertEqual(simulation.total_infections, 0)
        self.assertEqual(
            {agent.infection_stage for agent in simulation.agents.values()},
            {InfectionStage.SUSCEPTIBLE},
            "immunity should have waned back to a fully susceptible world",
        )


class ReservoirTests(unittest.TestCase):
    def test_infection_can_enter_a_population_that_has_none(self) -> None:
        simulation = clean_population(
            environmental_exposure_rate_per_year=2.0,
            disease_transmission_rate_per_year=0.0,
        )

        self.assertGreater(exposures_over(simulation, 24), 0)

    def test_contact_with_the_reservoir_grows_with_the_population(
        self,
    ) -> None:
        """A hazard per person, not a fixed quota handed to the world."""

        small = clean_population(
            initial_population=20,
            environmental_exposure_rate_per_year=1.0,
            disease_transmission_rate_per_year=0.0,
        )
        large = clean_population(
            initial_population=200,
            environmental_exposure_rate_per_year=1.0,
            disease_transmission_rate_per_year=0.0,
        )

        self.assertGreater(
            exposures_over(large, 12),
            exposures_over(small, 12),
        )

    def test_the_immune_are_not_reinfected_from_outside(self) -> None:
        simulation = clean_population(
            environmental_exposure_rate_per_year=5.0,
            disease_transmission_rate_per_year=0.0,
        )
        for agent in simulation.agents.values():
            agent.infection_stage = InfectionStage.RECOVERED
            agent.infection_ticks_remaining = 10_000

        self.assertEqual(exposures_over(simulation, 24), 0)

    def test_a_healthier_host_is_harder_to_expose(self) -> None:
        """The reservoir is filtered by the same susceptibility as contact."""

        frail = clean_population(
            environmental_exposure_rate_per_year=0.6,
            disease_transmission_rate_per_year=0.0,
        )
        for agent in frail.agents.values():
            agent.body_condition = 0.2
            agent.frailty = 0.9

        hardy = clean_population(
            environmental_exposure_rate_per_year=0.6,
            disease_transmission_rate_per_year=0.0,
        )
        for agent in hardy.agents.values():
            agent.body_condition = 1.0
            agent.frailty = 0.0

        self.assertGreater(
            exposures_over(frail, 24),
            exposures_over(hardy, 24),
        )

    def test_both_doors_are_independent(self) -> None:
        """Being near an infectious neighbour does not close the other one."""

        both = clean_population(
            environmental_exposure_rate_per_year=0.5,
            disease_transmission_rate_per_year=0.5,
        )
        reservoir_only = clean_population(
            environmental_exposure_rate_per_year=0.5,
            disease_transmission_rate_per_year=0.0,
        )
        for simulation in (both, reservoir_only):
            for agent in list(simulation.agents.values())[:4]:
                agent.infection_stage = InfectionStage.INFECTIOUS
                agent.infection_ticks_remaining = 60

        self.assertGreaterEqual(
            exposures_over(both, 24),
            exposures_over(reservoir_only, 24),
        )


if __name__ == "__main__":
    unittest.main()
