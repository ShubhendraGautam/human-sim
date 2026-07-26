import unittest

from sims.scaling_experiment import (
    config_for_population,
    parse_integer_list,
)
from src.simulation import SimulationConfig


class ScalingExperimentTests(unittest.TestCase):
    def test_parse_integer_list(self) -> None:
        self.assertEqual(parse_integer_list("10, 20,30"), [10, 20, 30])

    def test_constant_density_scales_world_area(self) -> None:
        base = SimulationConfig(initial_population=1)

        small = config_for_population(base, 100, constant_density=0.25)
        large = config_for_population(base, 400, constant_density=0.25)

        self.assertEqual((small.width, small.height), (20, 20))
        self.assertEqual((large.width, large.height), (40, 40))
        self.assertAlmostEqual(
            small.initial_population / (small.width * small.height),
            large.initial_population / (large.width * large.height),
        )

    def test_fixed_world_only_changes_population(self) -> None:
        base = SimulationConfig(
            width=11,
            height=13,
            initial_population=1,
        )

        result = config_for_population(base, 50, constant_density=None)

        self.assertEqual(result.initial_population, 50)
        self.assertEqual((result.width, result.height), (11, 13))


if __name__ == "__main__":
    unittest.main()
