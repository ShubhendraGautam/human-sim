import random
import unittest
from dataclasses import replace

from src.simulation import (
    BrainKind,
    ReproductiveRole,
    Simulation,
    SimulationConfig,
)
from src.simulation.brain import ACTION_INDEX, choose_action
from src.simulation.models import Action, ActionKind


class EmergenceRegressionTests(unittest.TestCase):
    def test_reproductive_intent_matching_scales_in_dense_ring(self) -> None:
        for population in (12, 60):
            with self.subTest(population=population):
                conceptions = self._resolve_dense_reproductive_ring(population)

                # A greedy maximal matching on a ring contains at least n / 3
                # disjoint pairs. Requiring that bound catches both quadratic
                # all-pairs resolution and exact reciprocal-target matching.
                self.assertGreaterEqual(conceptions, population // 3)

    def test_tiny_social_weight_is_not_trusted_neighbor_influence(
        self,
    ) -> None:
        config = SimulationConfig(
            initial_population=2,
            decision_noise=0.0,
        )
        simulation = Simulation(config, seed=701)
        observer, exemplar = simulation.agents.values()
        observer.traits = replace(
            observer.traits,
            brain_kind=BrainKind.SOCIAL,
            affiliation=1.0,
            conformity=1.0,
        )
        observer.culture = replace(observer.culture, conformity=1.0)
        exemplar.brain.last_action = ActionKind.MOVE.value
        exemplar.brain.last_success = 1.0
        exemplar.brain.last_action_tick = simulation.tick
        options = [
            (0.0, Action(ActionKind.REST, observer.id)),
            (-0.5, Action(ActionKind.MOVE, observer.id, destination=(0, 0))),
        ]

        trusted_choice = choose_action(
            options,
            observer,
            (exemplar,),
            random.Random(1),
            config,
            social_weights={exemplar.id: 1.0},
            current_tick=simulation.tick,
        )
        tiny_weight_choice = choose_action(
            options,
            observer,
            (exemplar,),
            random.Random(1),
            config,
            social_weights={exemplar.id: 1e-9},
            current_tick=simulation.tick,
        )

        self.assertEqual(trusted_choice.kind, ActionKind.MOVE)
        self.assertEqual(tiny_weight_choice.kind, ActionKind.REST)

    def test_habitual_move_survives_raw_utility_shortcut(self) -> None:
        config = SimulationConfig(
            width=2,
            height=1,
            initial_population=1,
            initial_resource_fraction=0.0,
            initial_resource_variation=0.0,
            initial_inventory=0.0,
            decision_noise=0.0,
            rest_utility=1.0,
            movement_weight=0.1,
            habit_preference_weight=1.0,
            learned_preference_limit=2.0,
        )
        simulation = Simulation(config, seed=702)
        agent = next(iter(simulation.agents.values()))
        agent.x = 0
        agent.y = 0
        agent.age = max(agent.age, config.dependent_age)
        agent.energy = config.maximum_energy
        agent.inventory = 0.0
        agent.material_inventory = 0.0
        agent.traits = replace(
            agent.traits,
            brain_kind=BrainKind.HABITUAL,
            exploration=0.0,
        )
        agent.culture = replace(agent.culture, exploration=0.0)
        agent.brain.preferences[ACTION_INDEX[ActionKind.MOVE]] = (
            config.learned_preference_limit
        )
        simulation.world.resources[0] = 0.0
        simulation.world.resources[1] = simulation.world.capacity[1]
        simulation.world.materials[0] = 0.0
        simulation.world.materials[1] = 0.0
        simulation.world.rebuild_spatial_index(simulation.agents.values())

        action = simulation._decide(
            agent,
            simulation._decision_rng(agent.id),
        )

        self.assertEqual(action.kind, ActionKind.MOVE)
        self.assertEqual(action.destination, (1, 0))

    def test_stale_ties_are_remembered_but_not_active(self) -> None:
        config = SimulationConfig(
            initial_population=2,
            ticks_per_year=12,
            relationship_half_life_years=1.0,
        )
        simulation = Simulation(config, seed=703)
        first, second = simulation.agents.values()
        simulation.relationships.observe(
            first.relationship_slot,
            second.id,
            simulation.tick,
        )
        simulation.relationships.observe(
            second.relationship_slot,
            first.id,
            simulation.tick,
        )

        current = simulation.measure()
        self.assertEqual(current.mean_remembered_connections, 1.0)
        self.assertEqual(current.mean_social_connections, 1.0)
        self.assertEqual(current.isolated_population, 0)

        simulation.tick = config.ticks_per_year + 1
        stale = simulation.measure()

        self.assertEqual(stale.mean_remembered_connections, 1.0)
        self.assertEqual(stale.mean_social_connections, 0.0)
        self.assertEqual(stale.isolated_population, 2)

    def test_snapshot_can_omit_relationship_payload(self) -> None:
        simulation = Simulation(
            SimulationConfig(initial_population=2),
            seed=704,
        )
        first, second = simulation.agents.values()
        simulation.relationships.observe(
            first.relationship_slot,
            second.id,
            simulation.tick,
        )

        full = simulation.snapshot(include_world=False)
        compact = simulation.snapshot(
            include_world=False,
            include_relationships=False,
        )

        self.assertIn("relationships", full)
        self.assertEqual(full["relationships"]["source"], [first.id])
        self.assertIn("agents", compact)
        self.assertNotIn("relationships", compact)

    @staticmethod
    def _resolve_dense_reproductive_ring(population: int) -> int:
        config = SimulationConfig(
            width=1,
            height=1,
            initial_population=population,
            initial_energy_minimum=100.0,
            initial_energy_maximum=100.0,
            reproduction_energy=10.0,
            reproduction_cost=1.0,
            maximum_conception_probability=1.0,
            initial_exposed_fraction=0.0,
            baseline_mortality_rate_per_year=0.0,
        )
        simulation = Simulation(config, seed=700 + population)
        agents = tuple(
            sorted(simulation.agents.values(), key=lambda item: item.id)
        )
        for index, agent in enumerate(agents):
            agent.x = 0
            agent.y = 0
            agent.age = 30.0
            agent.energy = config.maximum_energy
            agent.body_condition = 1.0
            agent.development_index = 1.0
            agent.frailty = 0.0
            agent.reproductive_role = (
                ReproductiveRole.OVA
                if index % 2 == 0
                else ReproductiveRole.SPERM
            )
            agent.traits = replace(
                agent.traits,
                fertility=1.0,
                maturity_age=16.0,
            )
            agent.health = simulation._health_capacity(agent)
        simulation.world.rebuild_spatial_index(agents)

        actions = [
            Action(
                ActionKind.REPRODUCE,
                agent.id,
                target_id=agents[(index + 1) % population].id,
            )
            for index, agent in enumerate(agents)
        ]
        simulation._resolve(actions)

        return simulation.total_conceptions


if __name__ == "__main__":
    unittest.main()
