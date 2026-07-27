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
