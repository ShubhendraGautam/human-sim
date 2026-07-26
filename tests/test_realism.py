import math
import random
import unittest
from dataclasses import replace

from src.simulation import (
    ReproductiveRole,
    InfectionStage,
    Simulation,
    SimulationConfig,
    age_fecundity,
    annual_hazard_to_tick,
    effective_health_capacity,
    update_body_condition,
    update_development_exposure,
    update_frailty,
    transmission_probability,
)
from src.simulation.models import Action, ActionKind


class LifeHistoryTests(unittest.TestCase):
    def test_body_condition_is_stable_across_tick_resolutions(self) -> None:
        def after_one_year(ticks: int) -> float:
            condition = 1.0
            for _ in range(ticks):
                condition = update_body_condition(
                    condition,
                    0.0,
                    1.0 / ticks,
                    0.5,
                )
            return condition

        self.assertAlmostEqual(
            after_one_year(4),
            after_one_year(12),
            places=12,
        )
        self.assertAlmostEqual(after_one_year(4), math.exp(-2.0), places=12)

    def test_prenatal_and_childhood_condition_form_a_weighted_history(
        self,
    ) -> None:
        well_developed, exposure = update_development_exposure(
            0.8,
            0.75,
            1.0,
            0.25,
        )
        poorly_developed, poor_exposure = update_development_exposure(
            0.8,
            0.75,
            0.2,
            0.25,
        )

        self.assertAlmostEqual(exposure, 1.0)
        self.assertEqual(exposure, poor_exposure)
        self.assertGreater(well_developed, poorly_developed)
        self.assertGreater(poorly_developed, 0.2)

    def test_age_fecundity_rises_and_declines(self) -> None:
        values = [
            age_fecundity(
                "ova",
                age,
                16.0,
                18.0,
                32.0,
                50.0,
                18.0,
                45.0,
                80.0,
            )
            for age in (15.0, 18.0, 32.0, 45.0, 50.0)
        ]

        self.assertEqual(values[0], 0.0)
        self.assertEqual(values[1], 1.0)
        self.assertEqual(values[2], 1.0)
        self.assertGreater(values[3], values[4])
        self.assertEqual(values[4], 0.0)

    def test_frailty_lowers_realized_health_capacity(self) -> None:
        frailty = update_frailty(
            0.0,
            age_years=80.0,
            elapsed_years=1.0,
            longevity_years=80.0,
            constitution=0.5,
            body_condition=0.5,
            onset_fraction=0.6,
            base_annual_rate=0.05,
            age_acceleration=3.0,
            constitution_protection=0.5,
            nutrition_penalty=0.5,
        )
        healthy_capacity = effective_health_capacity(
            100.0,
            development=1.0,
            frailty=0.0,
            developmental_floor=0.65,
            maximum_frailty_loss=0.55,
        )
        frail_capacity = effective_health_capacity(
            100.0,
            development=1.0,
            frailty=frailty,
            developmental_floor=0.65,
            maximum_frailty_loss=0.55,
        )

        self.assertGreater(frailty, 0.0)
        self.assertLess(frail_capacity, healthy_capacity)
        probability = annual_hazard_to_tick(0.36, 0.25)
        self.assertAlmostEqual((1.0 - probability) ** 4, math.exp(-0.36))


class EcologyTests(unittest.TestCase):
    def test_regeneration_scales_with_capacity_and_reports_flow(self) -> None:
        simulation = Simulation(
            SimulationConfig(
                width=2,
                height=1,
                initial_population=0,
                ticks_per_year=4,
                cell_capacity=100.0,
                minimum_cell_fertility=1.0,
                maximum_cell_fertility=1.0,
                initial_resource_fraction=0.0,
                resource_regeneration=0.4,
                seasonality_strength=0.0,
                material_regeneration=0.0,
            ),
            seed=21,
        )
        world = simulation.world
        world.capacity[0] = 100.0
        world.capacity[1] = 200.0
        world.productivity[0] = 40.0
        world.productivity[1] = 80.0

        world.begin_tick()
        world.regenerate(0)

        self.assertAlmostEqual(world.resources[0], 10.0)
        self.assertAlmostEqual(world.resources[1], 20.0)
        self.assertAlmostEqual(world.last_food_regenerated, 30.0)

    def test_hemispheres_have_opposite_seasons(self) -> None:
        simulation = Simulation(
            SimulationConfig(
                width=1,
                height=2,
                initial_population=0,
                ticks_per_year=4,
                minimum_cell_fertility=1.0,
                maximum_cell_fertility=1.0,
                seasonality_strength=0.5,
                seasonal_equator_fraction=0.0,
            ),
            seed=22,
        )

        factors = simulation.world._seasonal_factors(1)

        self.assertAlmostEqual(factors[0], 1.5)
        self.assertAlmostEqual(factors[1], 0.5)
        self.assertGreaterEqual(min(factors), 0.0)

    def test_sea_in_first_column_does_not_disable_row_seasonality(
        self,
    ) -> None:
        from src.simulation import CountrySpec, Rectangle, Scenario

        config = SimulationConfig(
            width=2,
            height=2,
            initial_population=0,
            ticks_per_year=4,
            minimum_cell_fertility=1.0,
            maximum_cell_fertility=1.0,
            seasonality_strength=0.5,
            seasonal_equator_fraction=0.0,
        )
        scenario = Scenario(
            countries=(
                CountrySpec(0, "East", Rectangle(1, 0, 1, 2), 0),
            ),
            seas=(Rectangle(0, 0, 1, 2),),
        )
        simulation = Simulation(config, seed=220, scenario=scenario)

        factors = simulation.world._seasonal_row_factors(1)

        self.assertAlmostEqual(factors[0], 1.5)
        self.assertAlmostEqual(factors[1], 0.5)

    def test_materials_do_not_reappear_when_nonrenewable(self) -> None:
        simulation = Simulation(
            SimulationConfig(
                width=1,
                height=1,
                initial_population=0,
                materials_renewable=False,
                material_regeneration=10.0,
            ),
            seed=23,
        )
        simulation.world.materials[0] = 0.0

        simulation.world.regenerate(1)

        self.assertEqual(simulation.world.materials[0], 0.0)
        self.assertEqual(simulation.world.last_material_regenerated, 0.0)


class DiseaseTests(unittest.TestCase):
    def test_zero_transmission_rate_prevents_local_spread(self) -> None:
        simulation = Simulation(
            SimulationConfig(
                width=1,
                height=1,
                initial_population=2,
                initial_exposed_fraction=0.0,
                disease_transmission_rate_per_year=0.0,
                baseline_mortality_rate_per_year=0.0,
            ),
            seed=26,
        )
        source, target = simulation.agents.values()
        source.infection_stage = InfectionStage.INFECTIOUS
        source.infection_ticks_remaining = 20

        simulation._advance_disease()

        self.assertEqual(target.infection_stage, InfectionStage.SUSCEPTIBLE)
        self.assertEqual(
            transmission_probability(0.0, 100.0, 1.0, 1.0),
            0.0,
        )

    def test_dense_local_exposure_uses_host_state_and_is_deterministic(
        self,
    ) -> None:
        config = SimulationConfig(
            width=1,
            height=1,
            initial_population=2,
            initial_exposed_fraction=0.0,
            disease_transmission_rate_per_year=1_000_000.0,
            baseline_mortality_rate_per_year=0.0,
        )
        first = Simulation(config, seed=27)
        second = Simulation(config, seed=27)
        for simulation in (first, second):
            source, _ = simulation.agents.values()
            source.infection_stage = InfectionStage.INFECTIOUS
            source.infection_ticks_remaining = 20
            simulation._advance_disease()

        target_first = first.agents[1]
        target_second = second.agents[1]
        self.assertEqual(target_first.infection_stage, InfectionStage.EXPOSED)
        self.assertEqual(
            target_first.infection_ticks_remaining,
            target_second.infection_ticks_remaining,
        )
        self.assertEqual(first.total_infections, second.total_infections)

    def test_infectious_health_damage_has_an_observed_death_cause(
        self,
    ) -> None:
        simulation = Simulation(
            SimulationConfig(
                width=1,
                height=1,
                initial_population=1,
                initial_exposed_fraction=0.0,
                disease_health_damage_per_year=10_000.0,
                baseline_mortality_rate_per_year=0.0,
                frailty_mortality_rate_per_year=0.0,
            ),
            seed=28,
        )
        agent = next(iter(simulation.agents.values()))
        agent.infection_stage = InfectionStage.INFECTIOUS
        agent.infection_ticks_remaining = 20

        simulation.step()

        self.assertNotIn(agent.id, simulation.agents)
        self.assertEqual(simulation.deaths_by_cause["infection"], 1)


class DemographyIntegrationTests(unittest.TestCase):
    @staticmethod
    def _reproductive_simulation() -> tuple[Simulation, object, object]:
        config = SimulationConfig(
            width=2,
            height=2,
            initial_population=2,
            initial_energy_minimum=100.0,
            initial_energy_maximum=100.0,
            base_metabolism_minimum=0.01,
            base_metabolism_maximum=0.01,
            reproduction_energy=10.0,
            reproduction_cost=2.0,
            maximum_conception_probability=1.0,
            gestation_years=1.0,
            gestation_energy_cost_per_tick=3.0,
            birth_energy_cost=4.0,
            pregnancy_loss_base_rate_per_year=0.0,
            pregnancy_loss_condition_rate_per_year=0.0,
            baseline_mortality_rate_per_year=0.0,
            frailty_mortality_rate_per_year=0.0,
        )
        simulation = Simulation(config, seed=24)
        first, second = simulation.agents.values()
        first.x = second.x = 0
        first.y = second.y = 0
        first.age = second.age = 30.0
        first.body_condition = second.body_condition = 1.0
        first.development_index = second.development_index = 1.0
        first.health = simulation._health_capacity(first)
        second.health = simulation._health_capacity(second)
        first.traits = replace(
            first.traits,
            fertility=1.0,
            maturity_age=16.0,
        )
        second.traits = replace(
            second.traits,
            fertility=1.0,
            maturity_age=16.0,
        )
        first.reproductive_role = ReproductiveRole.OVA
        second.reproductive_role = ReproductiveRole.SPERM
        simulation.world.rebuild_spatial_index(simulation.agents.values())
        return simulation, first, second

    def test_reproduction_requires_reciprocal_intent(self) -> None:
        simulation, first, second = self._reproductive_simulation()

        simulation._resolve([
            Action(ActionKind.REPRODUCE, first.id, target_id=second.id),
            Action(ActionKind.REST, second.id),
        ])
        self.assertEqual(len(simulation.pregnancies), 0)
        self.assertEqual(first.energy, 100.0)
        self.assertEqual(second.energy, 100.0)

        simulation._resolve([
            Action(ActionKind.REPRODUCE, second.id, target_id=first.id),
            Action(ActionKind.REPRODUCE, first.id, target_id=second.id),
        ])
        self.assertEqual(len(simulation.pregnancies), 1)
        self.assertEqual(simulation.total_conceptions, 1)

    def test_newborn_reserves_use_only_actual_gestational_investment(
        self,
    ) -> None:
        simulation, first, second = self._reproductive_simulation()
        self.assertTrue(simulation._reproduce(first, second.id, set()))
        pregnancy = simulation.pregnancies[first.id]
        self.assertEqual(pregnancy.invested_energy, 4.0)

        first.traits = replace(first.traits, metabolism=0.01)
        first.energy = 1.0
        simulation._apply_time_and_metabolism()
        self.assertLessEqual(pregnancy.invested_energy, 5.0)
        paid = pregnancy.invested_energy
        first.energy = 0.0
        simulation._apply_time_and_metabolism()
        self.assertEqual(pregnancy.invested_energy, paid)

        simulation.tick = pregnancy.due_tick
        simulation._advance_pregnancies()
        child = max(simulation.agents.values(), key=lambda agent: agent.id)
        self.assertLessEqual(child.energy, paid)

    def test_guardian_index_transfers_without_population_scan(self) -> None:
        simulation, first, second = self._reproductive_simulation()
        self.assertTrue(simulation._reproduce(first, second.id, set()))
        pregnancy = simulation.pregnancies[first.id]
        simulation.tick = pregnancy.due_tick
        simulation._advance_pregnancies()
        child = max(simulation.agents.values(), key=lambda agent: agent.id)

        self.assertIn(child.id, simulation.dependents_by_guardian[first.id])
        simulation._remove_agent(first.id, cause="test")

        self.assertEqual(child.guardian_id, second.id)
        self.assertIn(child.id, simulation.dependents_by_guardian[second.id])
        simulation.validate_state()


class AttentionTests(unittest.TestCase):
    def test_dense_neighbor_attention_is_bounded_unique_and_local(
        self,
    ) -> None:
        simulation = Simulation(
            SimulationConfig(
                width=1,
                height=1,
                initial_population=100,
                maximum_social_neighbors=8,
            ),
            seed=25,
        )
        actor = simulation.agents[0]
        sample = simulation.world.sample_nearby_agent_ids(
            actor.x,
            actor.y,
            radius=1,
            exclude=actor.id,
            limit=8,
            rng=random.Random(1),
        )

        self.assertEqual(len(sample), 8)
        self.assertEqual(len(set(sample)), 8)
        self.assertNotIn(actor.id, sample)
        self.assertTrue(all(item in simulation.agents for item in sample))


if __name__ == "__main__":
    unittest.main()
