"""Guard the optimized hot paths against silent behavioral drift.

These tests exist because the decision phase was optimized for speed. Each
one pins a property that an allocation- or lookup-level rewrite could break
without any existing test noticing.
"""

import time
import unittest

from src.simulation import Simulation, SimulationConfig
from src.simulation.models import InfectionStage


def reference_cell_indices(config, x, y, radius):
    """Straightforward neighborhood used to check the cached offset path."""
    if config.wrap_world:
        cells = []
        seen = set()
        for offset_y in range(-radius, radius + 1):
            for offset_x in range(-radius, radius + 1):
                column = (x + offset_x) % config.width
                row = (y + offset_y) % config.height
                index = row * config.width + column
                if index not in seen:
                    seen.add(index)
                    cells.append(index)
        return cells
    minimum_x = max(0, x - radius)
    maximum_x = min(config.width - 1, x + radius)
    minimum_y = max(0, y - radius)
    maximum_y = min(config.height - 1, y + radius)
    return [
        row * config.width + column
        for row in range(minimum_y, maximum_y + 1)
        for column in range(minimum_x, maximum_x + 1)
    ]


class NeighborhoodOffsetTests(unittest.TestCase):
    """The cached interior offsets must match the general clipped path."""

    def test_every_cell_and_radius_matches_the_reference(self) -> None:
        config = SimulationConfig(width=9, height=7, initial_population=0)
        simulation = Simulation(config=config, seed=0)
        world = simulation.world

        for radius in range(0, 4):
            for y in range(config.height):
                for x in range(config.width):
                    self.assertEqual(
                        list(world.nearby_cell_indices(x, y, radius)),
                        reference_cell_indices(config, x, y, radius),
                        msg=f"x={x} y={y} radius={radius}",
                    )

    def test_wrapping_world_matches_the_reference(self) -> None:
        config = SimulationConfig(
            width=6,
            height=5,
            initial_population=0,
            wrap_world=True,
        )
        simulation = Simulation(config=config, seed=0)
        world = simulation.world

        for radius in range(0, 3):
            for y in range(config.height):
                for x in range(config.width):
                    self.assertEqual(
                        list(world.nearby_cell_indices(x, y, radius)),
                        reference_cell_indices(config, x, y, radius),
                        msg=f"x={x} y={y} radius={radius}",
                    )

    def test_cached_offsets_do_not_leak_between_radii(self) -> None:
        config = SimulationConfig(width=11, height=11, initial_population=0)
        world = Simulation(config=config, seed=0).world

        first = list(world.nearby_cell_indices(5, 5, 1))
        second = list(world.nearby_cell_indices(5, 5, 3))
        repeated = list(world.nearby_cell_indices(5, 5, 1))

        self.assertEqual(len(first), 9)
        self.assertEqual(len(second), 49)
        self.assertEqual(first, repeated)


class SharedOrderingTests(unittest.TestCase):
    """Phases share one ordering, which must not depend on dict order."""

    def test_ordering_is_by_id_regardless_of_insertion_order(self) -> None:
        config = SimulationConfig(
            width=8,
            height=8,
            initial_population=24,
            initial_exposed_fraction=0.0,
        )
        simulation = Simulation(config=config, seed=3)

        expected = sorted(simulation.agents)
        self.assertEqual(
            [agent.id for agent in simulation._ordered_agents()],
            expected,
        )

        simulation.agents = dict(reversed(tuple(simulation.agents.items())))
        self.assertEqual(
            [agent.id for agent in simulation._ordered_agents()],
            expected,
        )

    def test_shared_ordering_matches_independent_sweeps(self) -> None:
        """Passing an ordering must equal letting each phase sort itself."""
        def build() -> Simulation:
            config = SimulationConfig(
                width=10,
                height=10,
                initial_population=30,
                baseline_mortality_rate_per_year=0.0,
            )
            return Simulation(config=config, seed=11)

        shared = build()
        ordered = shared._ordered_agents()
        shared_damage = shared._advance_disease(ordered)
        shared_deaths = shared._apply_time_and_metabolism(
            shared_damage,
            ordered,
        )

        separate = build()
        separate_damage = separate._advance_disease()
        separate_deaths = separate._apply_time_and_metabolism(
            separate_damage,
        )

        self.assertEqual(shared_damage, separate_damage)
        self.assertEqual(shared_deaths, separate_deaths)
        self.assertEqual(shared.state_digest(), separate.state_digest())


class DiseaseShortCircuitTests(unittest.TestCase):
    """Skipping the pressure grid must not change disease outcomes."""

    def test_no_infectious_agents_exposes_nobody(self) -> None:
        config = SimulationConfig(
            width=6,
            height=6,
            initial_population=20,
            initial_exposed_fraction=0.0,
            disease_transmission_rate_per_year=50.0,
            # This is a claim about local transmission alone, so the outside
            # reservoir is closed rather than left to introduce a case.
            environmental_exposure_rate_per_year=0.0,
        )
        simulation = Simulation(config=config, seed=7)
        for agent in simulation.agents.values():
            agent.infection_stage = InfectionStage.SUSCEPTIBLE
            agent.infection_ticks_remaining = 0
        infections_before = simulation.total_infections

        simulation._advance_disease()

        self.assertEqual(simulation.total_infections, infections_before)
        self.assertTrue(
            all(
                agent.infection_stage is InfectionStage.SUSCEPTIBLE
                for agent in simulation.agents.values()
            )
        )

    def test_an_infectious_agent_still_drives_transmission(self) -> None:
        config = SimulationConfig(
            width=1,
            height=1,
            initial_population=6,
            initial_exposed_fraction=0.0,
            disease_transmission_rate_per_year=500.0,
        )
        simulation = Simulation(config=config, seed=2)
        agents = simulation._ordered_agents()
        for agent in agents:
            agent.infection_stage = InfectionStage.SUSCEPTIBLE
        agents[0].infection_stage = InfectionStage.INFECTIOUS
        agents[0].infection_ticks_remaining = 10

        simulation._advance_disease()

        exposed = [
            agent
            for agent in simulation.agents.values()
            if agent.infection_stage is InfectionStage.EXPOSED
        ]
        self.assertTrue(exposed, "dense contact should expose someone")


class TickCostSmokeTests(unittest.TestCase):
    """A deliberately loose ceiling that only catches collapse in throughput.

    Wall-clock assertions are unreliable on shared machines, so this bound is
    roughly two orders of magnitude above the observed cost. Use
    ``sims/profile_engine.py`` for real measurement.
    """

    def test_small_run_completes_well_inside_a_generous_budget(self) -> None:
        config = SimulationConfig(
            width=24,
            height=24,
            initial_population=150,
        )
        simulation = Simulation(config=config, seed=1)
        simulation.step()

        started = time.perf_counter()
        for _ in range(5):
            simulation.step()
        seconds_per_tick = (time.perf_counter() - started) / 5

        self.assertLess(
            seconds_per_tick,
            2.0,
            "engine throughput collapsed; run sims/profile_engine.py",
        )


if __name__ == "__main__":
    unittest.main()
