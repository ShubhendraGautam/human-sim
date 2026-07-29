"""Brains that are inherited, and the guarantees that keeps them honest.

Nothing here asserts that evolved brains are better. Whether having opinions
pays is a property of the environment, and if it does not, the right result is
that weights decay toward zero — which is a measurement, not a failure. What
these tests pin is that the mechanism cannot cheat: it sees only local state,
it cannot override the world, it is reproducible, and it can be switched off
to recover exactly the model that came before it.
"""

import random
import unittest

from src.simulation import (
    ActionKind,
    Scenario,
    Simulation,
    SimulationConfig,
    neural,
)


class NetworkTests(unittest.TestCase):
    def test_a_blank_brain_has_no_opinion(self) -> None:
        network = neural.Network(4, len(ActionKind))

        scores = network.evaluate([0.5] * neural.SENSES)

        self.assertEqual(scores, [0.0] * len(ActionKind))
        self.assertEqual(network.magnitude, 0.0)

    def test_output_is_bounded_however_wild_the_weights(self) -> None:
        """A runaway weight must not be able to dominate every decision."""

        network = neural.Network(4, len(ActionKind))
        for unit in range(4):
            for index in range(neural.SENSES):
                network.hidden[unit][index] = 1e6
        for action in range(len(ActionKind)):
            for unit in range(4):
                network.output[action][unit] = 1e6

        for score in network.evaluate([1e6] * neural.SENSES):
            self.assertGreaterEqual(score, -1.0)
            self.assertLessEqual(score, 1.0)

    def test_evaluation_is_reproducible(self) -> None:
        first = neural.founder_network(
            random.Random(4), 5, len(ActionKind), 0.2,
        )
        second = neural.founder_network(
            random.Random(4), 5, len(ActionKind), 0.2,
        )
        senses = [0.3] * neural.SENSES

        self.assertEqual(first.evaluate(senses), second.evaluate(senses))

    def test_a_founder_scale_of_zero_produces_blank_brains(self) -> None:
        network = neural.founder_network(
            random.Random(1), 5, len(ActionKind), 0.0,
        )

        self.assertEqual(network.magnitude, 0.0)

    def test_a_child_is_built_from_both_parents(self) -> None:
        first = neural.Network(3, 4)
        second = neural.Network(3, 4)
        for unit in range(3):
            for index in range(neural.SENSES):
                first.hidden[unit][index] = 1.0
                second.hidden[unit][index] = -1.0

        child = neural.inherit(
            first, second, random.Random(7), 0.0, 0.0, 3.0,
        )

        values = {
            child.hidden[unit][index]
            for unit in range(3)
            for index in range(neural.SENSES)
        }
        self.assertTrue(values <= {1.0, -1.0})
        self.assertEqual(values, {1.0, -1.0}, "both parents should show")

    def test_inheritance_without_mutation_copies_a_uniform_parent(
        self,
    ) -> None:
        parent = neural.founder_network(
            random.Random(2), 3, 4, 0.4,
        )

        child = neural.inherit(
            parent, parent, random.Random(9), 0.0, 0.0, 3.0,
        )

        self.assertEqual(child.hidden, parent.hidden)
        self.assertEqual(child.output, parent.output)

    def test_magnitude_matches_the_weights_it_stands_for(self) -> None:
        """It is held rather than derived, so it has to be kept true.

        Anything that charges for a brain reads this every tick for every
        person, which is why it is not recomputed on demand — and why a
        factory that forgets to refresh it would quietly bill everyone the
        wrong amount for the rest of the run.
        """

        rng = random.Random(4)
        network = neural.founder_network(rng, 4, len(ActionKind), 0.3)

        expected = sum(
            abs(weight)
            for row in list(network.hidden) + list(network.output)
            for weight in row
        ) / (4 * neural.SENSES + len(ActionKind) * 4)

        self.assertAlmostEqual(network.magnitude, expected, places=12)
        self.assertGreater(network.magnitude, 0.0)

    def test_a_child_reports_its_own_magnitude(self) -> None:
        rng = random.Random(5)
        first = neural.founder_network(rng, 3, len(ActionKind), 0.4)
        second = neural.founder_network(rng, 3, len(ActionKind), 0.4)

        child = neural.inherit(first, second, rng, 0.2, 0.1, 3.0)

        held = child.magnitude
        child.refresh_magnitude()
        self.assertEqual(held, child.magnitude)

    def test_a_blank_brain_has_no_magnitude(self) -> None:
        self.assertEqual(neural.Network(4, len(ActionKind)).magnitude, 0.0)

    def test_only_grown_units_think(self) -> None:
        """An ungrown unit is allocated storage, not a part of the brain.

        Reading it would let a child decide with a brain it has not built,
        which is the whole difference between a ceiling and a size.
        """

        rng = random.Random(11)
        grown = neural.founder_network(rng, 5, len(ActionKind), 0.4)
        partial = neural.Network(5, len(ActionKind), active=2)
        for unit in range(5):
            partial.hidden[unit][:] = list(grown.hidden[unit])
        for action in range(len(ActionKind)):
            partial.output[action][:] = list(grown.output[action])
        partial.refresh_magnitude()

        small = neural.Network(2, len(ActionKind))
        for unit in range(2):
            small.hidden[unit][:] = list(grown.hidden[unit])
        for action in range(len(ActionKind)):
            small.output[action][:] = list(grown.output[action][:2])
        small.refresh_magnitude()

        senses = [0.3] * neural.SENSES
        self.assertEqual(partial.respond(senses), small.respond(senses))
        self.assertAlmostEqual(partial.magnitude, small.magnitude, places=12)

    def test_growth_stops_at_the_ceiling(self) -> None:
        network = neural.Network(4, len(ActionKind), active=1)

        self.assertTrue(network.grow_to(3))
        self.assertEqual(network.active, 3)
        self.assertTrue(network.grow_to(99))
        self.assertEqual(network.active, 4)
        self.assertFalse(network.grow_to(99))

    def test_growth_never_goes_backwards(self) -> None:
        network = neural.Network(6, len(ActionKind), active=4)

        self.assertFalse(network.grow_to(2))
        self.assertEqual(network.active, 4)

    def test_parents_of_different_ceilings_can_have_a_child(self) -> None:
        """Positional recombination over what they share, and no crash."""

        rules = neural.GrowthRules(
            birth_units=2,
            minimum_ceiling=3,
            maximum_ceiling=10,
            minimum_rate=0.1,
            maximum_rate=0.5,
            ceiling_mutation_rate=0.5,
            rate_mutation_scale=0.05,
        )
        rng = random.Random(12)
        small = neural.founder_network(rng, 3, len(ActionKind), 0.3, rules)
        large = neural.founder_network(rng, 9, len(ActionKind), 0.3, rules)

        for _ in range(40):
            child = neural.inherit(
                small, large, rng, 0.1, 0.05, 3.0, rules,
            )
            self.assertGreaterEqual(child.units, rules.minimum_ceiling)
            self.assertLessEqual(child.units, rules.maximum_ceiling)
            self.assertEqual(child.active, rules.birth_units)
            self.assertEqual(len(child.hidden), child.units)
            for row in child.output:
                self.assertEqual(len(row), child.units)

    def test_weights_stay_inside_their_limit(self) -> None:
        parent = neural.founder_network(random.Random(3), 3, 4, 2.0)

        child = neural.inherit(
            parent, parent, random.Random(5), 1.0, 40.0, 1.5,
        )

        for row in child.hidden + child.output:
            for weight in row:
                self.assertLessEqual(abs(weight), 1.5)


def build(**overrides) -> Simulation:
    config = SimulationConfig(**{
        "width": 18,
        "height": 14,
        "initial_population": 60,
        **overrides,
    })
    return Simulation(
        config=config,
        seed=17,
        scenario=Scenario.default(config),
    )


class IntegrationTests(unittest.TestCase):
    def test_switching_brains_off_removes_them_from_the_run(self) -> None:
        """The arm every experiment with these brains compares against.

        Brains are built and recombined from the run's own generators, so a
        feature that is "off" but still draws a number would shift every
        later decision and quietly invalidate the comparison. If any
        randomness were still being spent on networks, changing their shape
        would change the run; it must not.
        """

        small = build(neural_brains_enabled=False, neural_hidden_units=2)
        large = build(neural_brains_enabled=False, neural_hidden_units=12)
        small.run(180)
        large.run(180)

        self.assertEqual(small.state_digest(), large.state_digest())

    def test_upkeep_takes_energy_from_people_who_have_opinions(self) -> None:
        """A brain that costs nothing has no reason to be small.

        Measured behaviour without this: mean network magnitude climbs
        identically whether or not the network is allowed to influence a
        decision, because mutation inflates it and nothing pushes back.
        Charging for it is what makes brain size a trade-off rather than a
        ratchet. Whether that helps a population is a separate question, and
        the default is zero until it is measured.
        """

        free = build(neural_maintenance_cost=0.0)
        charged = build(neural_maintenance_cost=4.0)
        free.step()
        charged.step()

        # One tick, so the two runs still hold the same people and the
        # comparison is of the charge itself. Over many ticks the populations
        # diverge and total energy stops being about upkeep at all — a
        # smaller population can carry more energy per head.
        free_energy = {a.id: a.energy for a in free.agents.values()}
        charged_energy = {a.id: a.energy for a in charged.agents.values()}
        self.assertEqual(set(free_energy), set(charged_energy))

        opinionated = [
            agent.id
            for agent in free.agents.values()
            if agent.network.magnitude > 0.0
        ]
        self.assertTrue(opinionated, "founders were born blank")
        for agent_id in opinionated:
            self.assertLess(
                charged_energy[agent_id],
                free_energy[agent_id],
                f"agent {agent_id} was not charged for its brain",
            )

    def test_a_brain_is_built_over_a_life(self) -> None:
        growing = build(neural_growth_enabled=True)
        born_with = [a.network.active for a in growing.agents.values()]
        growing.run(30 * 12)
        grown = [
            agent.network.active
            for agent in growing.agents.values()
            if agent.age > 25.0
        ]

        self.assertEqual(set(born_with), {growing.config.neural_birth_units})
        self.assertTrue(grown, "nobody lived long enough to grow")
        self.assertGreater(max(grown), growing.config.neural_birth_units)

    def test_a_child_is_born_small_however_grown_its_parents(self) -> None:
        """The Weismann barrier for development.

        A brain grown over a life is not passed on any more than a learned
        weight is. What a child inherits is the capacity and the schedule;
        what it has to build is the brain. Without this, one long-lived
        ancestor would hand every descendant a head start it never earned.
        """

        growing = build(neural_growth_enabled=True)
        growing.run(60 * 12)

        newborns = [
            agent
            for agent in growing.agents.values()
            if agent.age < 1.0
        ]
        self.assertTrue(newborns, "no children were born")
        for child in newborns:
            self.assertEqual(
                child.network.active,
                growing.config.neural_birth_units,
            )

    def test_ceilings_and_rates_are_inherited_and_vary(self) -> None:
        growing = build(neural_growth_enabled=True)
        growing.run(60 * 12)

        ceilings = {a.network.units for a in growing.agents.values()}
        rates = {round(a.network.growth_rate, 4)
                 for a in growing.agents.values()}

        self.assertGreater(len(ceilings), 1, "every brain has one ceiling")
        self.assertGreater(len(rates), 1, "every brain grows at one rate")
        for ceiling in ceilings:
            self.assertGreaterEqual(
                ceiling, growing.config.neural_minimum_ceiling
            )
            self.assertLessEqual(
                ceiling, growing.config.neural_maximum_ceiling
            )

    def test_brain_shape_matters_when_they_are_on(self) -> None:
        """The counterpart: proof the previous test could have failed."""

        small = build(neural_hidden_units=2)
        large = build(neural_hidden_units=12)
        small.run(180)
        large.run(180)

        self.assertNotEqual(small.state_digest(), large.state_digest())

    def test_brains_change_what_people_do(self) -> None:
        without = build(neural_output_weight=0.0)
        with_brains = build()
        without.run(180)
        with_brains.run(180)

        self.assertNotEqual(
            without.state_digest(),
            with_brains.state_digest(),
        )

    def test_a_run_is_reproducible_with_brains(self) -> None:
        first = build()
        second = build()
        first.run(180)
        second.run(180)

        self.assertEqual(first.state_digest(), second.state_digest())

    def test_everyone_carries_a_brain_of_the_configured_shape(self) -> None:
        simulation = build(neural_hidden_units=4)
        simulation.run(240)

        self.assertGreater(len(simulation.agents), 0)
        for agent in simulation.agents.values():
            self.assertEqual(agent.network.units, 4)
            self.assertEqual(agent.network.outputs, len(ActionKind))
            self.assertEqual(len(agent.network.hidden), 4)

    def test_children_born_after_a_parent_dies_still_inherit(self) -> None:
        """Inheritance is fixed at conception, not read at birth."""

        simulation = build(initial_population=80)
        simulation.run(360)
        born = [
            agent for agent in simulation.agents.values()
            if agent.generation > 0
        ]

        self.assertTrue(born, "a run this long should produce children")
        for agent in born:
            self.assertEqual(len(agent.network.hidden[0]), neural.SENSES)

    def test_a_brain_cannot_reach_past_its_own_senses(self) -> None:
        """The sense vector is the whole of what a network is allowed."""

        from src.simulation.brain import sense

        simulation = build()
        agent = simulation._ordered_agents()[0]

        senses = sense(agent, simulation.config, 3)

        self.assertEqual(len(senses), neural.SENSES)
        for value in senses:
            self.assertGreaterEqual(value, -5.0)
            self.assertLessEqual(value, 5.0)


if __name__ == "__main__":
    unittest.main()
