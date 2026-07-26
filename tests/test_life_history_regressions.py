import unittest
from dataclasses import replace

from src.simulation import (
    InfectionStage,
    ReproductiveRole,
    Simulation,
    SimulationConfig,
    age_capability,
    age_fecundity,
    effective_health_capacity,
    update_body_condition,
    update_development_exposure,
    update_frailty,
)


class DiseaseMortalityRegressionTests(unittest.TestCase):
    @staticmethod
    def _lethal_infection_simulation(
        infectious_ticks_remaining: int,
    ) -> tuple[Simulation, object]:
        simulation = Simulation(
            SimulationConfig(
                width=1,
                height=1,
                initial_population=1,
                initial_exposed_fraction=0.0,
                disease_health_damage_per_year=10_000.0,
                disease_energy_cost_per_year=0.0,
                health_recovery=10_000.0,
                starvation_damage=0.0,
                aging_damage_per_year=0.0,
                baseline_mortality_rate_per_year=0.0,
                frailty_mortality_rate_per_year=0.0,
            ),
            seed=81,
        )
        agent = next(iter(simulation.agents.values()))
        agent.health = 0.01
        agent.infection_stage = InfectionStage.INFECTIOUS
        agent.infection_ticks_remaining = infectious_ticks_remaining
        return simulation, agent

    def test_lethal_disease_cannot_recover_or_resurrect(self) -> None:
        simulation, agent = self._lethal_infection_simulation(20)

        simulation.step()

        self.assertNotIn(agent.id, simulation.agents)
        self.assertEqual(simulation.deaths_by_cause["infection"], 1)
        self.assertEqual(simulation.total_deaths, 1)
        self.assertEqual(simulation.total_recoveries, 0)

    def test_lethal_final_infectious_tick_is_not_a_recovery(self) -> None:
        simulation, agent = self._lethal_infection_simulation(1)

        simulation.step()

        self.assertNotIn(agent.id, simulation.agents)
        self.assertEqual(simulation.deaths_by_cause["infection"], 1)
        self.assertEqual(simulation.total_recoveries, 0)
        self.assertFalse(
            any(event.kind == "infection_recovery" for event in simulation.events)
        )


class PregnancyRegressionTests(unittest.TestCase):
    @staticmethod
    def _reproductive_simulation(
        *,
        ticks_per_year: int = 12,
        gestation_years: float = 1.0,
        reproduction_cooldown_years: float = 1.5,
        postpartum_cooldown_years: float = 1.0,
        vertical_transmission_probability: float = 0.02,
    ) -> tuple[Simulation, object, object]:
        simulation = Simulation(
            SimulationConfig(
                width=2,
                height=2,
                initial_population=2,
                ticks_per_year=ticks_per_year,
                initial_energy_minimum=100.0,
                initial_energy_maximum=100.0,
                base_metabolism_minimum=0.01,
                base_metabolism_maximum=0.01,
                reproduction_energy=10.0,
                reproduction_cost=2.0,
                reproduction_cooldown_years=reproduction_cooldown_years,
                maximum_conception_probability=1.0,
                gestation_years=gestation_years,
                gestation_energy_cost_per_tick=0.0,
                birth_energy_cost=0.0,
                birth_health_cost=0.0,
                postpartum_cooldown_years=postpartum_cooldown_years,
                vertical_transmission_probability=(
                    vertical_transmission_probability
                ),
                pregnancy_loss_base_rate_per_year=0.0,
                pregnancy_loss_condition_rate_per_year=0.0,
                initial_exposed_fraction=0.0,
                baseline_mortality_rate_per_year=0.0,
                frailty_mortality_rate_per_year=0.0,
            ),
            seed=82,
        )
        gestational_parent, other_parent = simulation.agents.values()
        gestational_parent.x = other_parent.x = 0
        gestational_parent.y = other_parent.y = 0
        gestational_parent.age = other_parent.age = 30.0
        gestational_parent.body_condition = 1.0
        other_parent.body_condition = 1.0
        gestational_parent.development_index = 1.0
        other_parent.development_index = 1.0
        gestational_parent.traits = replace(
            gestational_parent.traits,
            fertility=1.0,
            maturity_age=16.0,
        )
        other_parent.traits = replace(
            other_parent.traits,
            fertility=1.0,
            maturity_age=16.0,
        )
        gestational_parent.health = simulation._health_capacity(
            gestational_parent
        )
        other_parent.health = simulation._health_capacity(other_parent)
        gestational_parent.reproductive_role = ReproductiveRole.OVA
        other_parent.reproductive_role = ReproductiveRole.SPERM
        simulation.world.rebuild_spatial_index(simulation.agents.values())
        return simulation, gestational_parent, other_parent

    @classmethod
    def _child_after_condition_history(
        cls,
        ticks_per_year: int,
        gestation_years: float,
        conditions: list[float],
    ) -> object:
        simulation, gestational_parent, other_parent = (
            cls._reproductive_simulation(
                ticks_per_year=ticks_per_year,
                gestation_years=gestation_years,
            )
        )
        if not simulation._reproduce(
            gestational_parent,
            other_parent.id,
            set(),
        ):
            raise AssertionError("test setup failed to conceive")
        pregnancy = simulation.pregnancies[gestational_parent.id]
        gestation_ticks = pregnancy.due_tick - pregnancy.conception_tick
        if len(conditions) != gestation_ticks:
            raise AssertionError("condition history must cover gestation")

        for elapsed_ticks, condition in enumerate(conditions, start=1):
            simulation.tick = pregnancy.conception_tick + elapsed_ticks
            gestational_parent.body_condition = condition
            simulation._advance_pregnancies()

        return max(simulation.agents.values(), key=lambda agent: agent.id)

    def test_postpartum_cooldown_never_shortens_existing_cooldown(self) -> None:
        simulation, gestational_parent, other_parent = (
            self._reproductive_simulation(
                gestation_years=1.0 / 12.0,
                reproduction_cooldown_years=5.0,
                postpartum_cooldown_years=1.0,
            )
        )
        self.assertTrue(
            simulation._reproduce(
                gestational_parent,
                other_parent.id,
                set(),
            )
        )
        pregnancy = simulation.pregnancies[gestational_parent.id]
        existing_cooldown = gestational_parent.next_reproduction_tick

        simulation.tick = pregnancy.due_tick
        simulation._advance_pregnancies()

        self.assertEqual(
            gestational_parent.next_reproduction_tick,
            existing_cooldown,
        )
        self.assertGreater(
            gestational_parent.next_reproduction_tick,
            simulation.tick
            + round(
                simulation.config.postpartum_cooldown_years
                * simulation.config.ticks_per_year
            ),
        )

    def test_prenatal_condition_is_time_weighted_across_tick_rates(self) -> None:
        children = []
        for ticks_per_year in (12, 48):
            half = ticks_per_year // 2
            child = self._child_after_condition_history(
                ticks_per_year,
                1.0,
                [0.2] * half + [0.8] * half,
            )
            children.append(child)
            with self.subTest(ticks_per_year=ticks_per_year):
                self.assertAlmostEqual(child.development_index, 0.5)
                self.assertAlmostEqual(
                    child.development_exposure_years,
                    1.0,
                )

        self.assertAlmostEqual(
            children[0].development_index,
            children[1].development_index,
        )

    def test_birth_uses_actual_rounded_gestation_exposure(self) -> None:
        exposures = []
        for ticks_per_year in (12, 48):
            gestation_ticks = max(1, round(0.2 * ticks_per_year))
            child = self._child_after_condition_history(
                ticks_per_year,
                0.2,
                [0.4] * gestation_ticks,
            )
            expected_exposure = gestation_ticks / ticks_per_year
            exposures.append(child.development_exposure_years)
            with self.subTest(ticks_per_year=ticks_per_year):
                self.assertAlmostEqual(child.development_index, 0.4)
                self.assertAlmostEqual(
                    child.development_exposure_years,
                    expected_exposure,
                )
                self.assertNotAlmostEqual(
                    child.development_exposure_years,
                    0.2,
                )

        self.assertNotAlmostEqual(exposures[0], exposures[1])

    def test_vertical_infection_is_emitted_after_consistent_birth(
        self,
    ) -> None:
        simulation, gestational_parent, other_parent = (
            self._reproductive_simulation(
                gestation_years=1.0 / 12.0,
                vertical_transmission_probability=1.0,
            )
        )
        gestational_parent.infection_stage = InfectionStage.INFECTIOUS
        gestational_parent.infection_ticks_remaining = 20
        infections_before = simulation.total_infections
        self.assertTrue(
            simulation._reproduce(
                gestational_parent,
                other_parent.id,
                set(),
            )
        )
        pregnancy = simulation.pregnancies[gestational_parent.id]
        sink_observations = []

        def observe(event) -> None:
            if event.kind == "vertical_infection":
                sink_observations.append((
                    event.actors[1] in simulation.agents,
                    simulation.total_births,
                ))

        simulation._event_sink = observe

        simulation.tick = pregnancy.due_tick
        simulation._advance_pregnancies()

        child = max(simulation.agents.values(), key=lambda agent: agent.id)
        self.assertEqual(child.infection_stage, InfectionStage.EXPOSED)
        self.assertEqual(simulation.total_infections, infections_before + 1)
        event_kinds = [event.kind for event in simulation.events]
        self.assertLess(
            event_kinds.index("birth"),
            event_kinds.index("vertical_infection"),
        )
        infection_event = next(
            event
            for event in simulation.events
            if event.kind == "vertical_infection"
        )
        self.assertEqual(
            infection_event.actors,
            (gestational_parent.id, child.id),
        )
        self.assertEqual(sink_observations, [(True, 1)])


class EngineFormulaParityTests(unittest.TestCase):
    @staticmethod
    def _simulation() -> tuple[Simulation, object]:
        simulation = Simulation(
            SimulationConfig(
                width=1,
                height=1,
                initial_population=1,
                ticks_per_year=12,
                initial_exposed_fraction=0.0,
                starvation_damage=0.0,
                health_recovery=0.0,
                aging_damage_per_year=0.0,
                baseline_mortality_rate_per_year=0.0,
                frailty_mortality_rate_per_year=0.0,
            ),
            seed=83,
        )
        return simulation, next(iter(simulation.agents.values()))

    def test_engine_hot_scalar_formulas_match_pure_helpers(self) -> None:
        simulation, agent = self._simulation()
        config = simulation.config
        agent.development_index = 0.37
        agent.frailty = 0.29

        self.assertAlmostEqual(
            simulation._health_capacity(agent),
            effective_health_capacity(
                agent.traits.maximum_health,
                agent.development_index,
                agent.frailty,
                config.minimum_development_health_fraction,
                config.frailty_health_capacity_loss,
            ),
        )

        agent.age = (
            config.dependent_age + agent.traits.maturity_age
        ) / 2.0
        self.assertAlmostEqual(
            simulation._capability(agent),
            age_capability(
                agent.age,
                agent.traits.maturity_age,
                config.dependent_age,
                config.juvenile_capability_floor,
            ),
        )

        peak_age = (
            agent.traits.maturity_age
            + config.fecundity_maturation_ramp_years
        )
        for role, age in (
            (ReproductiveRole.OVA, 40.0),
            (ReproductiveRole.SPERM, 60.0),
        ):
            agent.reproductive_role = role
            agent.age = age
            with self.subTest(role=role):
                self.assertAlmostEqual(
                    simulation._age_fecundity(agent),
                    age_fecundity(
                        role.value,
                        age,
                        agent.traits.maturity_age,
                        peak_age,
                        config.ova_fecundity_decline_age,
                        config.ova_reproductive_end_age,
                        peak_age,
                        config.sperm_fecundity_decline_age,
                        config.sperm_reproductive_end_age,
                    ),
                )

    def test_engine_condition_and_development_match_pure_helpers(self) -> None:
        simulation, agent = self._simulation()
        config = simulation.config
        elapsed_years = 1.0 / config.ticks_per_year
        agent.age = 10.0
        agent.traits = replace(
            agent.traits,
            metabolism=1.0,
            maturity_age=16.0,
        )
        agent.energy = 80.0
        agent.body_condition = 0.25
        agent.development_index = 0.4
        agent.development_exposure_years = 2.0
        agent.inventory = 0.0
        agent.health = simulation._health_capacity(agent)

        expected_energy = 79.0
        expected_condition = update_body_condition(
            agent.body_condition,
            expected_energy / config.maximum_energy,
            elapsed_years,
            config.nutrition_memory_years,
        )
        expected_development, expected_exposure = (
            update_development_exposure(
                agent.development_index,
                agent.development_exposure_years,
                expected_condition,
                elapsed_years,
            )
        )

        deaths = simulation._apply_time_and_metabolism()

        self.assertEqual(deaths, [])
        self.assertAlmostEqual(agent.energy, expected_energy)
        self.assertAlmostEqual(agent.body_condition, expected_condition)
        self.assertAlmostEqual(
            agent.development_index,
            expected_development,
        )
        self.assertAlmostEqual(
            agent.development_exposure_years,
            expected_exposure,
        )

    def test_engine_frailty_update_matches_pure_helper(self) -> None:
        simulation, agent = self._simulation()
        config = simulation.config
        elapsed_years = 1.0 / config.ticks_per_year
        agent.age = 60.0
        agent.traits = replace(
            agent.traits,
            metabolism=1.0,
            lifespan=80.0,
            constitution=0.6,
        )
        agent.energy = 80.0
        agent.body_condition = 0.4
        agent.frailty = 0.1
        agent.inventory = 0.0
        agent.health = simulation._health_capacity(agent)

        expected_condition = update_body_condition(
            agent.body_condition,
            79.0 / config.maximum_energy,
            elapsed_years,
            config.nutrition_memory_years,
        )
        expected_frailty = update_frailty(
            agent.frailty,
            agent.age,
            elapsed_years,
            agent.traits.lifespan,
            agent.traits.constitution,
            expected_condition,
            config.aging_starts_fraction,
            config.frailty_accumulation_per_year,
            config.frailty_age_acceleration,
            config.frailty_constitution_protection,
            config.frailty_condition_penalty,
        )

        deaths = simulation._apply_time_and_metabolism()

        self.assertEqual(deaths, [])
        self.assertAlmostEqual(agent.body_condition, expected_condition)
        self.assertAlmostEqual(agent.frailty, expected_frailty)


if __name__ == "__main__":
    unittest.main()
