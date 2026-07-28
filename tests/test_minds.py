"""Minds that see the world, learn within a life, and remember places.

Three things were missing and are tested here. A brain that could only feel
its own hunger had nothing to have a policy about. A brain whose weights were
fixed at conception could not change no matter what happened to it. And a
forager with no memory of where it had been was rolling downhill rather than
foraging.

None of these tests assert that a population behaves *better*. Whether the
machinery earns its cost is a measurement across seeds, not a unit test.
"""

import random
import unittest

from src.simulation import Simulation, SimulationConfig
from src.simulation.brain import BrainState, Surroundings, sense
from src.simulation.memory import PlaceMemory
from src.simulation.brain import ACTION_INDEX
from src.simulation.models import Action, ActionKind
from src.simulation import neural
from src.simulation.neural import SENSE_NAMES, SENSES, Network


def world(**overrides) -> Simulation:
    values = {
        "width": 24,
        "height": 24,
        "initial_population": 40,
    }
    values.update(overrides)
    return Simulation(config=SimulationConfig(**values), seed=6)


class PerceptionTests(unittest.TestCase):
    def test_a_brain_can_perceive_the_world_and_not_only_itself(self) -> None:
        outward = {
            "neighbours",
            "food_here",
            "food_nearby",
            "material_here",
            "season",
            "animal_near",
            "on_coast",
            "remembered_place",
        }

        self.assertTrue(outward.issubset(set(SENSE_NAMES)))

    def test_every_sense_has_a_value(self) -> None:
        simulation = world()
        agent = simulation.agents[min(simulation.agents)]

        values = sense(agent, simulation.config, 3, Surroundings())

        self.assertEqual(len(values), SENSES)
        self.assertEqual(len(SENSE_NAMES), SENSES)

    def test_the_world_changes_what_a_brain_sees(self) -> None:
        simulation = world()
        agent = simulation.agents[min(simulation.agents)]
        config = simulation.config

        bare = sense(agent, config, 0, Surroundings(food_here=0.0))
        rich = sense(agent, config, 0, Surroundings(food_here=1.0))

        self.assertNotEqual(bare, rich)

    def test_a_blind_reading_is_the_default(self) -> None:
        """Callers that score outside a decision get zeros, not garbage."""

        simulation = world()
        agent = simulation.agents[min(simulation.agents)]

        values = sense(agent, simulation.config, 0)

        self.assertEqual(len(values), SENSES)


class PlasticityTests(unittest.TestCase):
    def test_an_outcome_moves_the_output_layer(self) -> None:
        brain = BrainState()
        brain.last_activations = [1.0] * 4

        changed = brain.adapt(
            Action(ActionKind.GATHER, 1), 0.5, 0.1, 1.5, 4
        )

        self.assertTrue(changed)
        self.assertGreater(brain.plasticity_magnitude, 0.0)

    def test_nothing_is_learned_without_a_decision_behind_it(self) -> None:
        brain = BrainState()

        self.assertFalse(
            brain.adapt(Action(ActionKind.GATHER, 1), 0.5, 0.1, 1.5, 4)
        )
        self.assertIsNone(brain.plastic)

    def test_learning_is_bounded(self) -> None:
        brain = BrainState()
        brain.last_activations = [1.0] * 4
        for _ in range(500):
            brain.adapt(Action(ActionKind.GATHER, 1), 1.0, 0.5, 1.5, 4)

        self.assertLessEqual(brain.plasticity_magnitude, 1.5)

    def test_credit_goes_to_the_units_that_were_active(self) -> None:
        """Otherwise the same thing is learned in every circumstance."""

        brain = BrainState()
        brain.last_activations = [1.0, 0.0, 0.0, 0.0]
        brain.adapt(Action(ActionKind.GATHER, 1), 1.0, 0.2, 1.5, 4)
        row = brain.plastic[ACTION_INDEX[ActionKind.GATHER]]

        self.assertGreater(abs(row[0]), 0.0)
        self.assertEqual(row[1], 0.0)

    def test_experience_accumulates_over_a_life(self) -> None:
        # Plasticity ships off, so it is switched on explicitly here: the
        # mechanism has to keep working for the experiments that use it.
        simulation = world(plasticity_rate=0.5)
        simulation.run(200)
        adults = [
            agent for agent in simulation.agents.values() if agent.age > 25
        ]
        self.assertTrue(adults)

        self.assertGreater(
            max(agent.brain.plasticity_magnitude for agent in adults),
            0.0,
        )

    def test_what_is_learned_cannot_reach_the_inherited_channel(
        self,
    ) -> None:
        """The Weismann barrier for minds.

        A child recombines what its parents were *born* with. If lifetime
        learning leaked into that channel it would be Lamarck by accident,
        so this maxes out a parent's learning and checks that the very same
        recombination comes out the other side unchanged.
        """

        simulation = world()
        simulation.run(60)
        ids = sorted(simulation.agents)
        first = simulation.agents[ids[0]]
        second = simulation.agents[ids[1]]
        config = simulation.config

        def recombine() -> list:
            return [
                list(row)
                for row in neural.inherit(
                    first.network,
                    second.network,
                    random.Random(1234),
                    config.neural_mutation_rate,
                    config.neural_mutation_scale,
                    config.neural_weight_limit,
                ).output
            ]

        before = recombine()
        first.brain.plastic = [
            [config.plasticity_limit] * config.neural_hidden_units
            for _ in range(len(ACTION_INDEX))
        ]
        second.brain.plastic = [
            [-config.plasticity_limit] * config.neural_hidden_units
            for _ in range(len(ACTION_INDEX))
        ]

        self.assertEqual(before, recombine())

    def test_a_newborn_has_learned_less_than_an_old_hand(self) -> None:
        simulation = world(
            width=32,
            height=32,
            initial_population=150,
            plasticity_rate=0.5,
        )
        simulation.run(300)
        newest = [
            agent
            for agent in simulation.agents.values()
            if agent.birth_tick >= simulation.tick - 24 and agent.parents
        ]
        veterans = [
            agent
            for agent in simulation.agents.values()
            if agent.age > 30
        ]
        self.assertTrue(newest and veterans)

        self.assertLess(
            max(agent.brain.plasticity_magnitude for agent in newest),
            max(agent.brain.plasticity_magnitude for agent in veterans),
        )

    def test_plasticity_is_off_by_default(self) -> None:
        """It measured worse than not learning, so it does not ship on.

        The design notes' kill criterion is that a mechanism which cannot be
        told apart from its absence is decoration. This one could be told
        apart, in the wrong direction.
        """

        self.assertEqual(SimulationConfig().plasticity_rate, 0.0)

        simulation = world()
        simulation.run(160)

        for agent in simulation.agents.values():
            self.assertIsNone(agent.brain.plastic)

    def test_plasticity_still_works_when_switched_on(self) -> None:
        simulation = world(plasticity_rate=0.5)
        simulation.run(160)

        self.assertTrue(
            any(
                agent.brain.plastic is not None
                for agent in simulation.agents.values()
            )
        )

    def test_changing_your_mind_is_not_free(self) -> None:
        """A free lunch would be taken by everybody for no reason."""

        self.assertGreater(SimulationConfig().plasticity_energy_cost, 0.0)


class PlaceMemoryTests(unittest.TestCase):
    def test_a_new_person_remembers_nowhere(self) -> None:
        memory = PlaceMemory()

        self.assertEqual(len(memory), 0)
        self.assertIsNone(memory.best(0, 24.0))

    def test_a_place_is_remembered_and_recalled(self) -> None:
        memory = PlaceMemory()
        memory.remember(42, 0.8, tick=0, capacity=4)

        recalled = memory.best(0, 24.0)

        self.assertEqual(recalled, (42, 0.8))

    def test_memory_is_bounded(self) -> None:
        memory = PlaceMemory()
        for cell in range(50):
            memory.remember(cell, 0.5, tick=0, capacity=4)

        self.assertLessEqual(len(memory), 4)

    def test_standing_somewhere_twice_is_one_memory(self) -> None:
        memory = PlaceMemory()
        memory.remember(7, 0.4, tick=0, capacity=4)
        memory.remember(7, 0.9, tick=5, capacity=4)

        self.assertEqual(len(memory), 1)
        self.assertEqual(memory.best(5, 24.0), (7, 0.9))

    def test_an_old_memory_is_worth_less_than_a_fresh_one(self) -> None:
        memory = PlaceMemory()
        memory.remember(1, 1.0, tick=0, capacity=4)

        fresh = memory.best(0, 24.0)
        stale = memory.best(48, 24.0)

        self.assertIsNotNone(fresh)
        self.assertIsNotNone(stale)
        self.assertLess(stale[1], fresh[1])

    def test_a_place_that_turned_out_to_be_bare_is_forgotten(self) -> None:
        memory = PlaceMemory()
        memory.remember(3, 0.7, tick=0, capacity=4)
        memory.forget(3)

        self.assertEqual(len(memory), 0)

    def test_where_you_already_are_is_not_somewhere_to_go(self) -> None:
        memory = PlaceMemory()
        memory.remember(9, 0.9, tick=0, capacity=4)

        self.assertIsNone(memory.best(0, 24.0, exclude_cell=9))

    def test_foraging_builds_a_memory_of_places(self) -> None:
        simulation = world()
        simulation.run(60)

        held = [
            agent for agent in simulation.agents.values() if agent.places
        ]

        self.assertTrue(held, "somebody should have found somewhere")

    def test_place_memory_can_be_switched_off(self) -> None:
        simulation = world(place_memory_capacity=0)
        simulation.run(60)

        for agent in simulation.agents.values():
            self.assertFalse(agent.places and len(agent.places))


class DeterminismTests(unittest.TestCase):
    def test_minds_do_not_break_reproducibility(self) -> None:
        first = world()
        second = world()
        first.run(120)
        second.run(120)

        self.assertEqual(first.state_digest(), second.state_digest())

    def test_a_network_reports_the_state_that_produced_its_scores(
        self,
    ) -> None:
        network = Network(4, 6)
        scores, activations = network.respond([0.5] * SENSES)

        self.assertEqual(len(scores), 6)
        self.assertEqual(len(activations), 4)


if __name__ == "__main__":
    unittest.main()
