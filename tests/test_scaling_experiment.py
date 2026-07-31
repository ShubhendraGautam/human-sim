import unittest

from sims.scaling_experiment import (
    config_for_population,
    parse_integer_list,
    parse_world_sizes,
)
from src.simulation import SimulationConfig


class ScalingExperimentTests(unittest.TestCase):
    def test_parse_integer_list(self) -> None:
        self.assertEqual(parse_integer_list("10, 20,30"), [10, 20, 30])

    def test_parse_world_sizes(self) -> None:
        self.assertEqual(
            parse_world_sizes("64x48, 128X96"),
            [(64, 48), (128, 96)],
        )

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

    def test_explicit_world_size_exposes_sparse_and_dense_cases(self) -> None:
        base = SimulationConfig(width=11, height=13, initial_population=1)

        sparse = config_for_population(
            base,
            50,
            constant_density=None,
            world_size=(40, 30),
        )
        dense = config_for_population(
            base,
            200,
            constant_density=None,
            world_size=(40, 30),
        )

        self.assertEqual((sparse.width, sparse.height), (40, 30))
        self.assertEqual((dense.width, dense.height), (40, 30))
        self.assertEqual(
            (sparse.initial_population, dense.initial_population),
            (50, 200),
        )


if __name__ == "__main__":
    unittest.main()
