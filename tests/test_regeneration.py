"""Regrowth is a share of the deficit, swept a row at a time.

The sweep runs every tick over every cell, so its cost is set by the size of
the map rather than by how many people are alive. That made it the first thing
to fix before worlds are allowed to get large, and these tests pin the two
properties the faster sweep has to keep: it must be the same physics as the
formula it replaced, and it must stay linear with a small constant.
"""

import random
import unittest

from src.simulation.config import SimulationConfig
from src.simulation.scenario import CountrySpec, Rectangle, Scenario
from src.simulation.world import World


def reference_growth(world: World, elapsed_years: float, row_factors):
    """The formula the row sweep replaced, kept here as the authority.

    It lives in the test rather than the engine so there is exactly one
    implementation in the shipped model, and a second opinion to check it
    against.
    """

    total = 0.0
    factor_sum = 0.0
    productive = 0
    width = world.config.width
    for index, current in enumerate(world.resources):
        capacity = world.capacity[index]
        if capacity <= 0.0:
            continue
        factor = row_factors[index // width]
        factor_sum += factor
        productive += 1
        if current >= capacity:
            continue
        growth = (
            world.productivity[index]
            * elapsed_years
            * factor
            * (1.0 - current / capacity)
        )
        updated = min(capacity, current + max(growth, 0.0))
        total += updated - current
        world.resources[index] = updated
    return total, (factor_sum / productive if productive else 1.0)


def paired_worlds(**overrides):
    config = SimulationConfig(**{
        "width": 32,
        "height": 24,
        "initial_population": 0,
        **overrides,
    })
    scenario = Scenario.default(config)
    return (
        World(config, random.Random(9), scenario),
        World(config, random.Random(9), scenario),
    )


def sea_world() -> World:
    """A map with genuinely unproductive cells in it."""

    config = SimulationConfig(width=16, height=12, initial_population=0)
    scenario = Scenario(
        countries=(
            CountrySpec(
                id=0,
                name="Shore",
                region=Rectangle(0, 0, 8, 12),
                population=0,
            ),
        ),
        seas=(Rectangle(10, 0, 6, 12),),
    )
    return World(config, random.Random(4), scenario)


class EquivalenceTests(unittest.TestCase):
    """Same model, different arithmetic order — so compare, don't assume."""

    def test_a_long_run_tracks_the_reference_formula(self) -> None:
        swept, reference = paired_worlds()
        elapsed = 1.0 / swept.config.ticks_per_year

        for tick in range(400):
            if tick % 7 == 0:
                # Keep cells off capacity; a full world hides disagreement.
                for index in range(0, len(swept.resources), 11):
                    x, y = swept.coordinates(index)
                    taken = swept.resources[index] * 0.4
                    swept.harvest(x, y, taken)
                    reference.harvest(x, y, taken)
            swept.regenerate(tick)
            flow, season = reference_growth(
                reference,
                elapsed,
                reference._seasonal_row_factors(tick),
            )
            self.assertAlmostEqual(
                swept.last_food_regenerated, flow, delta=abs(flow) * 1e-9,
            )
            self.assertAlmostEqual(
                swept.last_seasonal_productivity, season, places=9,
            )

        for index in range(len(swept.resources)):
            self.assertAlmostEqual(
                swept.resources[index],
                reference.resources[index],
                places=9,
            )

    def test_the_seasonal_average_covers_productive_cells_only(self) -> None:
        """Sea is not a place where nothing grows; it is not a place."""

        world, _ = paired_worlds()
        world.regenerate(3)
        _, season = reference_growth(
            world, 1.0 / world.config.ticks_per_year,
            world._seasonal_row_factors(3),
        )

        self.assertAlmostEqual(
            world.last_seasonal_productivity, season, places=9,
        )


class PhysicalTests(unittest.TestCase):
    def test_nothing_grows_where_there_is_no_capacity(self) -> None:
        world = sea_world()
        sea = [
            index for index in range(len(world.capacity))
            if world.capacity[index] <= 0.0
        ]
        self.assertTrue(sea, "scenario should contain sea to test with")

        for tick in range(60):
            world.regenerate(tick)

        for index in sea:
            self.assertEqual(world.resources[index], 0.0)

    def test_growth_never_passes_capacity(self) -> None:
        world, _ = paired_worlds()
        for tick in range(400):
            world.regenerate(tick)
        for index in range(len(world.resources)):
            self.assertLessEqual(
                world.resources[index], world.capacity[index],
            )

    def test_an_overshooting_configuration_is_still_clamped(self) -> None:
        """The clamp is skipped only when arithmetic makes it unnecessary."""

        world, _ = paired_worlds(
            resource_regeneration=50.0,
            ticks_per_year=1,
        )
        for index in range(len(world.resources)):
            world.resources[index] = 0.0

        world.regenerate(0)

        for index in range(len(world.resources)):
            self.assertLessEqual(
                world.resources[index], world.capacity[index],
            )

    def test_an_empty_cell_refills_toward_capacity(self) -> None:
        world, _ = paired_worlds(seasonality_strength=0.0)
        index = next(
            i for i in range(len(world.capacity)) if world.capacity[i] > 0.0
        )
        x, y = world.coordinates(index)
        world.harvest(x, y, world.resources[index])
        self.assertEqual(world.resources[index], 0.0)

        for tick in range(600):
            world.regenerate(tick)

        self.assertGreater(world.resources[index], world.capacity[index] * 0.9)

    def test_regrowth_reports_what_it_added(self) -> None:
        world, _ = paired_worlds()
        before = sum(world.resources)

        world.regenerate(0)

        self.assertAlmostEqual(
            sum(world.resources) - before,
            world.last_food_regenerated,
            places=6,
        )


class MaterialTests(unittest.TestCase):
    def test_materials_do_not_renew_by_default(self) -> None:
        world, _ = paired_worlds()
        before = list(world.materials)

        for tick in range(24):
            world.regenerate(tick)

        self.assertEqual(list(world.materials), before)
        self.assertEqual(world.last_material_regenerated, 0.0)

    def test_renewable_materials_regrow_without_a_season(self) -> None:
        world, _ = paired_worlds(materials_renewable=True)
        index = next(
            i for i in range(len(world.material_capacity))
            if world.material_capacity[i] > 0.0
        )
        x, y = world.coordinates(index)
        world.harvest_material(x, y, world.materials[index])

        world.regenerate(0)

        self.assertGreater(world.materials[index], 0.0)
        self.assertGreater(world.last_material_regenerated, 0.0)


if __name__ == "__main__":
    unittest.main()
