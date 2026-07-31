"""What can be worked out is a table, not a hard-coded skill.

The engine used to know how to do exactly one thing. These pin that the loop
— notice an opportunity, work at it, succeed, show someone else — is written
against no technique in particular, and that seafaring still behaves as it
did when it was the only one.
"""

import unittest

from src.simulation import Simulation, SimulationConfig
from src.simulation import knowledge


def learner_world(**overrides) -> Simulation:
    values = {
        "width": 20,
        "height": 20,
        "initial_population": 30,
        "initial_fauna_density": 0.0,
    }
    values.update(overrides)
    return Simulation(config=SimulationConfig(**values), seed=4)


class TableTest(unittest.TestCase):
    def test_more_than_one_thing_can_be_learned(self) -> None:
        self.assertGreater(knowledge.TECHNIQUE_COUNT, 1)

    def test_every_technique_has_a_distinct_bit(self) -> None:
        indices = [technique.index for technique in knowledge.TECHNIQUES]

        self.assertEqual(len(set(indices)), len(indices))
        self.assertEqual(sorted(indices), list(range(len(indices))))

    def test_knowing_nothing_changes_nothing(self) -> None:
        self.assertEqual(knowledge.harvest_multiplier(0), 1.0)
        self.assertEqual(knowledge.hunt_multiplier(0), 1.0)
        self.assertFalse(knowledge.opens_water(0))
        self.assertEqual(knowledge.names(0), ())

    def test_a_technique_is_only_thinkable_where_it_applies(self) -> None:
        coast_only = 1 << knowledge.Affordance.COAST

        found = knowledge.discoverable(0, coast_only)
        nowhere = knowledge.discoverable(0, 0)

        self.assertIsNotNone(found)
        self.assertIs(found.affordance, knowledge.Affordance.COAST)
        self.assertIsNone(nowhere)

    def test_something_already_known_is_not_rediscovered(self) -> None:
        mask = knowledge.with_technique(0, knowledge.SEAFARING)
        coast_only = 1 << knowledge.Affordance.COAST

        self.assertIsNone(knowledge.discoverable(mask, coast_only))

    def test_teaching_finds_what_the_learner_is_missing(self) -> None:
        teacher = knowledge.with_technique(0, knowledge.TECHNIQUES[1])
        teacher = knowledge.with_technique(teacher, knowledge.TECHNIQUES[0])
        learner = knowledge.with_technique(0, knowledge.TECHNIQUES[0])

        technique = knowledge.teachable(teacher, learner)

        self.assertIsNotNone(technique)
        self.assertEqual(technique.index, knowledge.TECHNIQUES[1].index)

    def test_nothing_to_teach_when_the_learner_already_has_it_all(
        self,
    ) -> None:
        both = knowledge.with_technique(0, knowledge.TECHNIQUES[0])

        self.assertIsNone(knowledge.teachable(both, both))


class EngineTest(unittest.TestCase):
    def test_seafaring_still_names_the_same_bit(self) -> None:
        simulation = learner_world()
        agent = simulation.agents[min(simulation.agents)]

        self.assertFalse(agent.knows_seafaring)
        agent.known_techniques = knowledge.with_technique(
            agent.known_techniques,
            knowledge.SEAFARING,
        )
        self.assertTrue(agent.knows_seafaring)

    def test_a_technique_can_be_discovered_where_its_affordance_is(
        self,
    ) -> None:
        simulation = learner_world(discovery_threshold=0.01)
        agent = simulation.agents[min(simulation.agents)]
        agent.material_inventory = (
            simulation.config.material_inventory_capacity
        )
        agent.energy = simulation.config.maximum_energy

        worked = simulation._research(agent)

        self.assertTrue(worked)
        self.assertGreater(knowledge.count(agent.known_techniques), 0)

    def test_nothing_is_discovered_where_nothing_is_afforded(self) -> None:
        simulation = learner_world(initial_fauna_density=0.0)
        agent = simulation.agents[min(simulation.agents)]
        agent.material_inventory = 0.0
        agent.energy = simulation.config.maximum_energy
        # Inland, nothing to hand, no animals: nothing poses a problem.
        for index in range(len(simulation.world.materials)):
            simulation.world.materials[index] = 0.0

        placed = False
        for agent_id in sorted(simulation.agents):
            candidate = simulation.agents[agent_id]
            if not simulation.world.is_coast(candidate.x, candidate.y):
                candidate.material_inventory = 0.0
                candidate.energy = simulation.config.maximum_energy
                self.assertEqual(simulation._affordances(candidate), 0)
                self.assertFalse(simulation._research(candidate))
                placed = True
                break

        self.assertTrue(placed, "no inland person to test with")

    def test_teaching_transmits_whatever_the_teacher_has(self) -> None:
        simulation = learner_world()
        ids = sorted(simulation.agents)
        teacher = simulation.agents[ids[0]]
        learner = simulation.agents[ids[1]]
        learner.x, learner.y = teacher.x, teacher.y
        teacher.known_techniques = knowledge.with_technique(
            0,
            knowledge.TECHNIQUES[1],
        )
        learner.known_techniques = 0

        taught = simulation._teach(teacher, learner.id)

        self.assertTrue(taught)
        self.assertTrue(
            knowledge.knows(
                learner.known_techniques,
                knowledge.TECHNIQUES[1],
            )
        )

    def test_a_teacher_with_nothing_to_offer_teaches_nothing(self) -> None:
        simulation = learner_world()
        ids = sorted(simulation.agents)
        teacher = simulation.agents[ids[0]]
        learner = simulation.agents[ids[1]]
        learner.x, learner.y = teacher.x, teacher.y
        teacher.known_techniques = 0

        self.assertFalse(simulation._teach(teacher, learner.id))

    def test_teaching_can_transmit_a_policy_and_its_lineage(self) -> None:
        simulation = learner_world(policy_teaching_rate=1.0)
        first, second, third = (
            simulation.agents[agent_id]
            for agent_id in sorted(simulation.agents)[:3]
        )
        second.x, second.y = first.x, first.y
        third.x, third.y = first.x, first.y
        for agent in (first, second, third):
            agent.known_techniques = 0
        first.network.output[0][0] = 0.9
        second.network.output[0][0] = -0.4
        third.network.output[0][0] = -0.8

        self.assertTrue(simulation._teach(first, second.id))
        self.assertTrue(simulation._teach(second, third.id))

        self.assertEqual(second.brain.policy_teacher_id, first.id)
        self.assertEqual(second.brain.policy_origin_id, first.id)
        self.assertEqual(second.brain.policy_generation, 1)
        self.assertEqual(third.brain.policy_teacher_id, second.id)
        self.assertEqual(third.brain.policy_origin_id, first.id)
        self.assertEqual(third.brain.policy_generation, 2)
        self.assertEqual(simulation.total_policy_transmissions, 2)
        self.assertEqual(simulation.events[-1].kind, "teach_policy")
        self.assertEqual(simulation.events[-1].actors, (second.id, third.id))
        self.assertEqual(
            dict(simulation.events[-1].details),
            {"origin": float(first.id), "generation": 2.0},
        )
        metrics = simulation.measure()
        self.assertEqual(metrics.taught_policy_population, 2)
        self.assertEqual(metrics.taught_policy_lineages, 1)
        self.assertEqual(metrics.policy_transmissions, 2)

    def test_policy_teaching_requires_local_contact(self) -> None:
        simulation = learner_world(policy_teaching_rate=1.0)
        teacher, learner = (
            simulation.agents[agent_id]
            for agent_id in sorted(simulation.agents)[:2]
        )
        teacher.known_techniques = learner.known_techniques = 0
        teacher.network.output[0][0] = 0.9
        learner.network.output[0][0] = -0.4
        learner.x = (teacher.x + 5) % simulation.config.width
        learner.y = (teacher.y + 5) % simulation.config.height

        self.assertFalse(simulation._teach(teacher, learner.id))
        self.assertEqual(simulation.total_policy_transmissions, 0)

    def test_policy_teaching_does_not_assume_the_policy_is_a_benefit(
        self,
    ) -> None:
        simulation = learner_world(
            policy_teaching_rate=1.0,
            cultural_transmission_rate=1.0,
        )
        teacher, learner = (
            simulation.agents[agent_id]
            for agent_id in sorted(simulation.agents)[:2]
        )
        learner.x, learner.y = teacher.x, teacher.y
        teacher.known_techniques = learner.known_techniques = 0
        teacher.network.output[0][0] = 0.9
        learner.network.output[0][0] = -0.4
        culture_before = learner.culture

        self.assertTrue(simulation._teach(teacher, learner.id))

        self.assertEqual(learner.culture, culture_before)
        relationship = simulation.relationships.view(
            learner.relationship_slot,
            teacher.id,
            simulation.tick,
        )
        self.assertIsNotNone(relationship)
        self.assertEqual(relationship.encounters, 1)
        self.assertEqual(relationship.trust, 0.0)
        self.assertEqual(relationship.balance, 0.0)

    def test_a_learned_technique_changes_what_someone_can_do(self) -> None:
        toolmaking = knowledge.BY_NAME["toolmaking"]
        mask = knowledge.with_technique(0, toolmaking)

        self.assertGreater(
            knowledge.harvest_multiplier(mask),
            knowledge.harvest_multiplier(0),
        )

    def test_the_snapshot_publishes_the_table(self) -> None:
        simulation = learner_world()

        published = simulation.snapshot()["techniques"]

        self.assertEqual(len(published), knowledge.TECHNIQUE_COUNT)
        self.assertEqual(
            [entry["name"] for entry in published],
            [technique.name for technique in knowledge.TECHNIQUES],
        )


if __name__ == "__main__":
    unittest.main()
