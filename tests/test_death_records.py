"""Death as a state rather than an absence of updates.

Someone who dies leaves the world, but an observer still has to be able to
ask what became of them. Without a record the service can only answer "no
such person", which a reader cannot tell apart from a person whose readings
merely stopped arriving.
"""

import unittest

from src.human_sim_service.backend import PythonSimulationBackend
from src.simulation import (
    Scenario,
    Simulation,
    SimulationConfig,
    observation,
)


def dying_simulation(**overrides) -> Simulation:
    config = SimulationConfig(**{
        "width": 12,
        "height": 12,
        "initial_population": 40,
        **overrides,
    })
    return Simulation(config=config, seed=13)


class DeathRecordTests(unittest.TestCase):
    def test_the_dead_are_remembered_with_a_cause(self) -> None:
        simulation = dying_simulation()
        victim = simulation._ordered_agents()[0]
        victim_id = victim.id
        age_at_death = victim.age

        simulation._remove_agent(victim_id, cause="starvation")

        record = simulation.deaths[victim_id]
        self.assertEqual(record.cause, "starvation")
        self.assertEqual(record.tick, simulation.tick)
        self.assertEqual(record.agent.id, victim_id)
        self.assertEqual(record.agent.age, age_at_death)

    def test_a_record_is_the_state_the_person_died_in(self) -> None:
        """Consequences of the death are applied before it is written."""

        simulation = dying_simulation()
        first, second = simulation._ordered_agents()[:2]
        simulation._bind_pair(first, second)

        simulation._remove_agent(first.id, cause="tested")

        self.assertIsNone(simulation.deaths[first.id].agent.partner_id)
        self.assertIsNone(second.partner_id, "the survivor was released")

    def test_the_dead_are_not_in_the_world(self) -> None:
        simulation = dying_simulation()
        victim_id = simulation._ordered_agents()[0].id

        simulation._remove_agent(victim_id, cause="tested")

        self.assertNotIn(victim_id, simulation.agents)
        self.assertNotIn(victim_id, simulation.entities)
        observation.validate_state(simulation)

    def test_the_store_is_bounded(self) -> None:
        simulation = dying_simulation(death_record_capacity=3)
        victims = [agent.id for agent in simulation._ordered_agents()[:6]]

        for victim_id in victims:
            simulation._remove_agent(victim_id, cause="tested")

        self.assertEqual(len(simulation.deaths), 3)
        self.assertEqual(list(simulation.deaths), victims[-3:])
        self.assertEqual(simulation.total_deaths, 6)

    def test_records_can_be_switched_off_entirely(self) -> None:
        simulation = dying_simulation(death_record_capacity=0)
        victim_id = simulation._ordered_agents()[0].id

        simulation._remove_agent(victim_id, cause="tested")

        self.assertEqual(simulation.deaths, {})
        self.assertEqual(simulation.total_deaths, 1)

    def test_a_long_run_remembers_its_recent_dead(self) -> None:
        simulation = dying_simulation(initial_population=80)
        simulation.run(240)

        self.assertGreater(simulation.total_deaths, 0)
        self.assertLessEqual(
            len(simulation.deaths),
            simulation.config.death_record_capacity,
        )
        for agent_id in simulation.deaths:
            self.assertNotIn(agent_id, simulation.agents)


class DeathThroughTheServiceTests(unittest.TestCase):
    def _backend(self) -> PythonSimulationBackend:
        config = SimulationConfig(
            width=12,
            height=12,
            initial_population=40,
        )
        return PythonSimulationBackend(
            config=config,
            seed=13,
            scenario=Scenario.default(config),
        )

    def test_a_dead_person_is_reported_as_deceased(self) -> None:
        backend = self._backend()
        simulation = backend._simulation
        victim_id = simulation._ordered_agents()[0].id
        simulation._remove_agent(victim_id, cause="starvation")

        detail = backend.agent(victim_id).agent

        self.assertEqual(detail["status"], "deceased")
        self.assertEqual(detail["death"]["cause"], "starvation")
        self.assertEqual(detail["death"]["tick"], simulation.tick)

    def test_the_living_are_reported_as_living(self) -> None:
        backend = self._backend()
        living_id = next(iter(backend._simulation.agents))

        detail = backend.agent(living_id).agent

        self.assertEqual(detail["status"], "living")
        self.assertIsNone(detail["death"])

    def test_a_dead_person_keeps_their_biology(self) -> None:
        """The panel keeps working; only its meaning changes."""

        backend = self._backend()
        simulation = backend._simulation
        victim_id = simulation._ordered_agents()[0].id
        before = backend.agent(victim_id).agent

        simulation._remove_agent(victim_id, cause="tested")
        after = backend.agent(victim_id).agent

        self.assertEqual(after["biology"], before["biology"])
        self.assertEqual(after["identity"]["generation"],
                         before["identity"]["generation"])

    def test_a_dead_person_reports_no_social_memory(self) -> None:
        """Their relationship row is back in the store and may be reused."""

        backend = self._backend()
        simulation = backend._simulation
        victim_id = simulation._ordered_agents()[0].id
        simulation._remove_agent(victim_id, cause="tested")

        detail = backend.agent(victim_id).agent

        self.assertEqual(detail["relationships"], [])

    def test_someone_who_never_existed_is_still_not_found(self) -> None:
        backend = self._backend()

        with self.assertRaises(KeyError):
            backend.agent(10_000_000)

    def test_a_forgotten_person_is_not_found(self) -> None:
        config = SimulationConfig(
            width=12,
            height=12,
            initial_population=40,
            death_record_capacity=1,
        )
        backend = PythonSimulationBackend(
            config=config,
            seed=13,
            scenario=Scenario.default(config),
        )
        simulation = backend._simulation
        first, second = [
            agent.id for agent in simulation._ordered_agents()[:2]
        ]
        simulation._remove_agent(first, cause="tested")
        simulation._remove_agent(second, cause="tested")

        with self.assertRaises(KeyError):
            backend.agent(first)
        self.assertEqual(backend.agent(second).agent["status"], "deceased")


if __name__ == "__main__":
    unittest.main()
