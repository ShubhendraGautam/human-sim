"""The world's identity space, and the rules about how things come to be."""

import unittest
from dataclasses import dataclass

from src.simulation import (
    EntityKind,
    EntityRegistry,
    Simulation,
    SimulationConfig,
)


@dataclass(slots=True)
class _Structure:
    """A stand-in for anything inert until artifacts exist in the engine."""

    kind = EntityKind.ARTIFACT

    id: int
    x: int
    y: int


@dataclass(slots=True)
class _Creature:
    kind = EntityKind.FAUNA

    id: int
    x: int
    y: int


class EntityRegistryTest(unittest.TestCase):
    def test_one_identity_space_is_shared_by_every_kind(self) -> None:
        registry = EntityRegistry()
        person_id = registry.claim_id()
        creature_id = registry.claim_id()
        structure_id = registry.claim_id()

        self.assertEqual([person_id, creature_id, structure_id], [0, 1, 2])
        self.assertEqual(registry.claimed_ids, 3)

    def test_living_things_register_themselves(self) -> None:
        registry = EntityRegistry()
        creature = _Creature(id=registry.claim_id(), x=1, y=2)

        registry.register(creature)

        self.assertIs(registry.get(creature.id), creature)
        self.assertIs(registry.kind_of(creature.id), EntityKind.FAUNA)
        self.assertIsNone(registry.creator_of(creature.id))

    def test_a_living_thing_cannot_be_attributed_to_a_creator(self) -> None:
        registry = EntityRegistry()
        builder_id = registry.claim_id()
        creature = _Creature(id=registry.claim_id(), x=0, y=0)

        with self.assertRaises(ValueError):
            registry.register(creature, created_by=builder_id)

    def test_inert_things_require_whatever_made_them(self) -> None:
        registry = EntityRegistry()
        builder_id = registry.claim_id()
        structure = _Structure(id=registry.claim_id(), x=3, y=4)

        with self.assertRaises(ValueError):
            registry.register(structure)

        registry.register(structure, created_by=builder_id)
        self.assertEqual(registry.creator_of(structure.id), builder_id)

    def test_provenance_outlives_the_creator(self) -> None:
        registry = EntityRegistry()
        builder = _Creature(id=registry.claim_id(), x=0, y=0)
        registry.register(builder)
        structure = _Structure(id=registry.claim_id(), x=1, y=1)
        registry.register(structure, created_by=builder.id)

        registry.deregister(builder.id)

        self.assertIsNone(registry.get(builder.id))
        self.assertEqual(registry.creator_of(structure.id), builder.id)

    def test_unclaimed_identities_are_refused(self) -> None:
        registry = EntityRegistry()
        stranger = _Creature(id=97, x=0, y=0)

        with self.assertRaises(ValueError):
            registry.register(stranger)

    def test_registering_twice_is_refused(self) -> None:
        registry = EntityRegistry()
        creature = _Creature(id=registry.claim_id(), x=0, y=0)
        registry.register(creature)

        with self.assertRaises(ValueError):
            registry.register(creature)

    def test_kinds_are_stored_apart(self) -> None:
        registry = EntityRegistry()
        creature = _Creature(id=registry.claim_id(), x=0, y=0)
        builder_id = registry.claim_id()
        structure = _Structure(id=registry.claim_id(), x=0, y=0)
        registry.register(creature)
        registry.register(structure, created_by=builder_id)

        self.assertEqual(
            set(registry.of_kind(EntityKind.FAUNA)),
            {creature.id},
        )
        self.assertEqual(
            set(registry.of_kind(EntityKind.ARTIFACT)),
            {structure.id},
        )
        self.assertEqual(len(registry), 2)
        self.assertEqual(
            registry.counts(),
            {"fauna": 1, "artifact": 1},
        )

    def test_deregistering_something_absent_is_harmless(self) -> None:
        registry = EntityRegistry()

        self.assertIsNone(registry.deregister(5))


class PopulationIsRegisteredTest(unittest.TestCase):
    """People are simply the first kind to live on the shared substrate."""

    def _simulation(self) -> Simulation:
        return Simulation(
            config=SimulationConfig(
                width=24,
                height=24,
                initial_population=60,
            ),
            seed=11,
        )

    def test_the_population_is_the_registry_not_a_copy_of_it(self) -> None:
        simulation = self._simulation()

        self.assertIs(
            simulation.agents,
            simulation.entities.of_kind(EntityKind.PERSON),
        )
        # The registry holds animals too, so it is larger than the
        # population. What must hold is that people are exactly its person
        # bucket and nothing has landed in the wrong one.
        self.assertEqual(
            len(simulation.entities),
            (
                len(simulation.agents)
                + len(simulation.fauna)
                + len(simulation.artifacts)
            ),
        )

    def test_people_are_registered_as_people(self) -> None:
        simulation = self._simulation()

        for agent_id, agent in simulation.agents.items():
            self.assertIs(agent.kind, EntityKind.PERSON)
            self.assertIs(
                simulation.entities.kind_of(agent_id),
                EntityKind.PERSON,
            )
            self.assertIsNone(simulation.entities.creator_of(agent_id))

    def test_births_and_deaths_move_through_the_registry(self) -> None:
        simulation = self._simulation()
        simulation.run(120)

        self.assertGreater(simulation.total_births, 0)
        self.assertGreater(simulation.total_deaths, 0)
        self.assertEqual(
            len(simulation.entities),
            (
                len(simulation.agents)
                + len(simulation.fauna)
                + len(simulation.artifacts)
            ),
        )
        # Every identity ever issued was issued once, to one thing.
        self.assertGreaterEqual(
            simulation.entities.claimed_ids,
            len(simulation.agents),
        )
        for agent_id in simulation.agents:
            self.assertLess(agent_id, simulation.entities.claimed_ids)
        simulation.validate_state()

    def test_the_dead_leave_the_registry(self) -> None:
        simulation = self._simulation()
        victim_id = min(simulation.agents)

        simulation._remove_agent(victim_id, cause="tested")

        self.assertNotIn(victim_id, simulation.entities)
        self.assertIsNone(simulation.entities.get(victim_id))
        self.assertNotIn(victim_id, simulation.agents)

    def test_identities_are_never_reissued(self) -> None:
        simulation = self._simulation()
        simulation.run(60)
        seen = set(simulation.agents)

        simulation.run(60)

        for agent in simulation.agents.values():
            if agent.birth_tick > 60:
                self.assertNotIn(
                    agent.id,
                    seen,
                    "a newborn reused a dead person's identity",
                )


class SpatialIndexKindTest(unittest.TestCase):
    def test_the_index_keeps_kinds_in_separate_buckets(self) -> None:
        simulation = Simulation(
            config=SimulationConfig(
                width=16,
                height=16,
                initial_population=40,
            ),
            seed=3,
        )
        world = simulation.world

        people = world.occupants_of_kind(EntityKind.PERSON)
        indexed = {
            entity_id
            for entity_ids in people.values()
            for entity_id in entity_ids
        }

        self.assertEqual(indexed, set(simulation.agents))
        animals = world.occupants_of_kind(EntityKind.FAUNA)
        indexed_animals = {
            entity_id
            for entity_ids in animals.values()
            for entity_id in entity_ids
        }
        self.assertEqual(indexed_animals, set(simulation.fauna))
        # No animal was filed as a person, and vice versa.
        self.assertFalse(indexed & indexed_animals)
        for kind in (EntityKind.FLORA, EntityKind.ARTIFACT):
            self.assertEqual(world.occupants_of_kind(kind), {})

    def test_other_kinds_do_not_appear_to_local_perception(self) -> None:
        """A structure in a cell must not read as a person standing there."""

        simulation = Simulation(
            config=SimulationConfig(
                width=16,
                height=16,
                initial_population=20,
            ),
            seed=5,
        )
        person = simulation.agents[min(simulation.agents)]
        structure = _Structure(
            id=simulation.entities.claim_id(),
            x=person.x,
            y=person.y,
        )
        simulation.entities.register(structure, created_by=person.id)

        simulation.world.rebuild_spatial_index(simulation.entities.placed())

        neighbors = simulation.world.nearby_agent_ids(
            person.x,
            person.y,
            radius=1,
            exclude=person.id,
        )
        self.assertNotIn(structure.id, neighbors)
        self.assertEqual(
            simulation.world.occupants_of_kind(EntityKind.ARTIFACT),
            {simulation.world.cell_index(person.x, person.y): [structure.id]},
        )
        simulation.validate_state()


if __name__ == "__main__":
    unittest.main()
