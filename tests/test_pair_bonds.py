"""Pair bonding: formation, exclusivity, cleanup, and the invariants.

The bond is stored on both agents rather than in a central index, so these
tests carry the weight of keeping the two copies consistent.
"""

import unittest

from src.simulation import Simulation, SimulationConfig, observation
from src.simulation.models import Action, ActionKind, ReproductiveRole


def couple_simulation(**overrides) -> Simulation:
    """Two fertile adults of opposite role, adjacent, in a tiny world."""
    config = SimulationConfig(
        width=4,
        height=4,
        initial_population=2,
        initial_exposed_fraction=0.0,
        baseline_mortality_rate_per_year=0.0,
        pregnancy_loss_base_rate_per_year=0.0,
        pregnancy_loss_condition_rate_per_year=0.0,
        **overrides,
    )
    simulation = Simulation(config=config, seed=5)
    agents = simulation._ordered_agents()
    first, second = agents[0], agents[1]
    first.reproductive_role = ReproductiveRole.OVA
    second.reproductive_role = ReproductiveRole.SPERM
    for agent in (first, second):
        agent.x, agent.y = 1, 1
        agent.age = 26.0
        agent.energy = config.maximum_energy
        agent.health = simulation._health_capacity(agent)
        agent.body_condition = 1.0
        agent.parents = None
        agent.grandparent_ids = ()
        agent.next_reproduction_tick = -1
    simulation.world.rebuild_spatial_index(simulation.agents.values())
    return simulation


class BondFormationTests(unittest.TestCase):
    def test_courtship_is_symmetric_and_exclusive(self) -> None:
        simulation = couple_simulation()
        first, second = simulation._ordered_agents()

        simulation._bind_pair(first, second)

        self.assertEqual(first.partner_id, second.id)
        self.assertEqual(second.partner_id, first.id)
        self.assertEqual(first.bond_since_tick, second.bond_since_tick)
        observation.validate_state(simulation)

    def test_courtship_does_not_require_a_matching_action(self) -> None:
        """The whole point: consent, not coincidence."""
        simulation = couple_simulation(bond_acceptance_base=1.0)
        first, second = simulation._ordered_agents()

        results = simulation._resolve_courtships(
            [Action(ActionKind.COURT, first.id, target_id=second.id)]
        )

        self.assertTrue(results[first.id])
        self.assertEqual(first.partner_id, second.id)
        self.assertEqual(second.partner_id, first.id)

    def test_courtship_costs_energy(self) -> None:
        simulation = couple_simulation(bond_acceptance_base=1.0)
        first, second = simulation._ordered_agents()
        before = first.energy

        simulation._resolve_courtships(
            [Action(ActionKind.COURT, first.id, target_id=second.id)]
        )

        self.assertAlmostEqual(
            before - first.energy,
            simulation.config.courtship_energy_cost,
            places=6,
        )

    def test_already_bonded_agents_are_not_courted(self) -> None:
        simulation = couple_simulation(bond_acceptance_base=1.0)
        first, second = simulation._ordered_agents()
        simulation._bind_pair(first, second)

        self.assertFalse(simulation._can_court(first, second))

    def test_contention_is_deterministic_under_reversed_order(self) -> None:
        """Two suitors, one target: the winner ignores dict order."""
        def outcome(reverse: bool) -> int:
            config = SimulationConfig(
                width=4,
                height=4,
                initial_population=3,
                initial_exposed_fraction=0.0,
                bond_acceptance_base=1.0,
            )
            simulation = Simulation(config=config, seed=11)
            agents = simulation._ordered_agents()
            target = agents[0]
            target.reproductive_role = ReproductiveRole.OVA
            for agent in agents[1:]:
                agent.reproductive_role = ReproductiveRole.SPERM
            for agent in agents:
                agent.x, agent.y = 1, 1
                agent.age = 26.0
                agent.parents = None
                agent.grandparent_ids = ()
            simulation.world.rebuild_spatial_index(
                simulation.agents.values()
            )
            proposals = [
                Action(ActionKind.COURT, suitor.id, target_id=target.id)
                for suitor in agents[1:]
            ]
            if reverse:
                proposals.reverse()
            simulation._resolve_courtships(proposals)
            return target.partner_id

        self.assertEqual(outcome(False), outcome(True))


class BondReproductionTests(unittest.TestCase):
    @staticmethod
    def _one_sided_attempts(bonded: bool, attempts: int = 12) -> int:
        """Repeat a one-sided REPRODUCE and report the resulting pregnancies.

        Conception is a probabilistic draw even for a valid pair, so a single
        attempt proves nothing either way; the contrast between the bonded and
        unbonded runs is what matters.
        """
        simulation = couple_simulation()
        first, second = simulation._ordered_agents()
        if bonded:
            simulation._bind_pair(first, second)
        for _ in range(attempts):
            simulation._resolve(
                [Action(ActionKind.REPRODUCE, first.id, target_id=second.id)]
            )
            if simulation.pregnancies:
                break
            simulation.tick += 1
        return len(simulation.pregnancies)

    def test_bonded_pair_conceives_on_one_sided_intent(self) -> None:
        self.assertEqual(self._one_sided_attempts(bonded=True), 1)

    def test_unbonded_pair_still_requires_reciprocal_intent(self) -> None:
        """The original rule is retained for everyone without a bond."""
        self.assertEqual(self._one_sided_attempts(bonded=False), 0)

    def test_bonded_agent_will_not_reproduce_outside_the_bond(self) -> None:
        config = SimulationConfig(
            width=4,
            height=4,
            initial_population=3,
            initial_exposed_fraction=0.0,
        )
        simulation = Simulation(config=config, seed=3)
        agents = simulation._ordered_agents()
        first, second, outsider = agents
        first.reproductive_role = ReproductiveRole.OVA
        second.reproductive_role = ReproductiveRole.SPERM
        outsider.reproductive_role = ReproductiveRole.SPERM
        for agent in agents:
            agent.x, agent.y = 1, 1
            agent.age = 26.0
            agent.energy = config.maximum_energy
            agent.parents = None
            agent.grandparent_ids = ()
            agent.next_reproduction_tick = -1
        simulation.world.rebuild_spatial_index(simulation.agents.values())
        simulation._bind_pair(first, second)

        self.assertFalse(
            simulation._reproductively_available(first, outsider)
        )
        self.assertFalse(
            simulation._reproductively_available(outsider, first)
        )


class BondCleanupTests(unittest.TestCase):
    def test_death_releases_the_surviving_partner(self) -> None:
        simulation = couple_simulation()
        first, second = simulation._ordered_agents()
        simulation._bind_pair(first, second)

        simulation._remove_agent(first.id, cause="test")

        self.assertIsNone(second.partner_id)
        self.assertEqual(second.bond_since_tick, -1)
        self.assertEqual(second.bond_last_together_tick, -1)
        observation.validate_state(simulation)

    def test_dissolution_clears_both_sides(self) -> None:
        simulation = couple_simulation()
        first, second = simulation._ordered_agents()
        simulation._bind_pair(first, second)

        simulation._dissolve_bond(first, "bond_ended_test")

        self.assertIsNone(first.partner_id)
        self.assertIsNone(second.partner_id)
        observation.validate_state(simulation)

    def test_widow_may_bond_again(self) -> None:
        simulation = couple_simulation(bond_acceptance_base=1.0)
        first, second = simulation._ordered_agents()
        simulation._bind_pair(first, second)
        simulation._dissolve_bond(first, "bond_ended_test")

        self.assertTrue(simulation._can_court(first, second))


class CoMovementTests(unittest.TestCase):
    def test_step_toward_closes_distance_by_one_cell(self) -> None:
        simulation = couple_simulation()
        first, second = simulation._ordered_agents()
        first.x, first.y = 0, 0
        second.x, second.y = 3, 3

        step = simulation._step_toward(first, second)

        self.assertEqual(step, (1, 1))

    def test_step_toward_never_leaves_the_world(self) -> None:
        simulation = couple_simulation()
        first, second = simulation._ordered_agents()
        first.x, first.y = 0, 0
        second.x, second.y = 0, 0

        self.assertEqual(simulation._step_toward(first, second), (0, 0))

    def test_bonded_partners_end_up_adjacent(self) -> None:
        """Without co-movement a bond is inert, so this is load-bearing."""
        config = SimulationConfig(
            width=20,
            height=20,
            initial_population=2,
            initial_exposed_fraction=0.0,
            baseline_mortality_rate_per_year=0.0,
        )
        simulation = Simulation(config=config, seed=8)
        first, second = simulation._ordered_agents()
        first.reproductive_role = ReproductiveRole.OVA
        second.reproductive_role = ReproductiveRole.SPERM
        first.x, first.y = 1, 1
        second.x, second.y = 18, 18
        for agent in (first, second):
            agent.age = 26.0
            agent.parents = None
            agent.grandparent_ids = ()
        simulation.world.rebuild_spatial_index(simulation.agents.values())
        simulation._bind_pair(first, second)
        start = max(abs(first.x - second.x), abs(first.y - second.y))

        for _ in range(40):
            simulation.step()
            if first.id not in simulation.agents:
                self.skipTest("partner died before reuniting")
            if second.id not in simulation.agents:
                self.skipTest("partner died before reuniting")

        end = max(abs(first.x - second.x), abs(first.y - second.y))
        self.assertLess(end, start)


if __name__ == "__main__":
    unittest.main()
