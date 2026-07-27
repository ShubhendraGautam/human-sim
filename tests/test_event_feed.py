"""Events and biographies: what an observer can be told after the fact.

The engine has always written a causal event log; nothing outside the engine
could read it. These tests pin the reading, including the two places it is
obliged to admit ignorance — a log that no longer reaches back far enough, and
a life whose early years have scrolled out of it.
"""

import unittest

from src.human_sim_service.backend import PythonSimulationBackend
from src.human_sim_service.sessions import RunManager
from src.simulation import Scenario, Simulation, SimulationConfig


def backend(**overrides) -> PythonSimulationBackend:
    config = SimulationConfig(**{
        "width": 16,
        "height": 16,
        "initial_population": 60,
        **overrides,
    })
    return PythonSimulationBackend(
        config=config,
        seed=5,
        scenario=Scenario.default(config),
    )


class EventFeedTests(unittest.TestCase):
    def test_a_fresh_run_reports_what_has_happened(self) -> None:
        source = backend()
        source.advance(60)

        feed = source.events()

        self.assertGreater(len(feed.events), 0)
        self.assertEqual(feed.tick, 60)
        for event in feed.events:
            self.assertIn("kind", event)
            self.assertIn("actors", event)
            self.assertLessEqual(event["tick"], 60)

    def test_events_arrive_newest_first(self) -> None:
        source = backend()
        source.advance(120)

        ticks = [event["tick"] for event in source.events().events]

        self.assertEqual(ticks, sorted(ticks, reverse=True))

    def test_a_window_never_exceeds_its_limit(self) -> None:
        source = backend()
        source.advance(120)

        self.assertLessEqual(len(source.events(limit=7).events), 7)
        self.assertEqual(source.events(limit=0).events, ())

    def test_since_tick_excludes_what_the_reader_already_saw(self) -> None:
        source = backend()
        source.advance(60)
        seen = source.events(limit=500).events[0]["tick"]
        source.advance(12)

        feed = source.events(since_tick=seen, limit=500)

        self.assertTrue(feed.events, "twelve ticks should produce something")
        for event in feed.events:
            self.assertGreater(event["tick"], seen)

    def test_a_reader_that_fell_behind_is_told_so(self) -> None:
        """Silence and a gap must not look the same to a notification list."""

        source = backend(event_log_capacity=8)
        source.advance(120)

        self.assertTrue(source.events(since_tick=0).dropped)

    def test_a_reader_that_kept_up_is_not_warned(self) -> None:
        source = backend()
        source.advance(24)
        feed = source.events(limit=500)

        caught_up = source.events(since_tick=feed.tick)

        self.assertFalse(caught_up.dropped)
        self.assertEqual(caught_up.events, ())

    def test_the_feed_never_writes_to_the_simulation(self) -> None:
        source = backend()
        source.advance(48)
        before = source._simulation.state_digest()

        source.events(limit=500)
        source.events(since_tick=3)

        self.assertEqual(source._simulation.state_digest(), before)


class BiographyTests(unittest.TestCase):
    def _dead_agent(self, simulation: Simulation) -> int:
        victim = simulation._ordered_agents()[0]
        simulation._remove_agent(victim.id, cause="starvation")
        return victim.id

    def test_the_living_have_no_biography(self) -> None:
        source = backend()
        living = next(iter(source._simulation.agents))

        self.assertIsNone(source.agent(living).agent["biography"])

    def test_a_life_is_summarised_once_it_ends(self) -> None:
        source = backend()
        source.advance(120)
        victim = self._dead_agent(source._simulation)

        life = source.agent(victim).agent["biography"]

        self.assertEqual(life["cause"], "starvation")
        self.assertGreater(life["died_year"], life["born_year"])
        self.assertAlmostEqual(
            life["died_year"] - life["born_year"],
            life["age_at_death"],
            places=6,
        )

    def test_a_biography_counts_the_survivors(self) -> None:
        """The mark a life leaves that the model can still see."""

        source = backend()
        source.advance(240)
        simulation = source._simulation
        parent = next(
            (
                agent for agent in simulation.agents.values()
                if any(
                    other.parents is not None and agent.id in other.parents
                    for other in simulation.agents.values()
                )
            ),
            None,
        )
        self.assertIsNotNone(parent, "a run this long should have families")
        expected = sum(
            1 for other in simulation.agents.values()
            if other.parents is not None and parent.id in other.parents
        )
        simulation._remove_agent(parent.id, cause="tested")

        life = source.agent(parent.id).agent["biography"]

        self.assertEqual(life["living_children"], expected)

    def test_a_partial_record_says_that_it_is_partial(self) -> None:
        source = backend(event_log_capacity=4)
        source.advance(120)
        victim = self._dead_agent(source._simulation)

        life = source.agent(victim).agent["biography"]

        self.assertFalse(life["moments_complete"])

    def test_moments_only_include_that_person(self) -> None:
        source = backend()
        source.advance(120)
        victim = self._dead_agent(source._simulation)

        life = source.agent(victim).agent["biography"]

        for moment in life["moments"]:
            self.assertIn(str(victim), moment["actors"])


class EventRouteTests(unittest.TestCase):
    def test_a_run_serves_its_events_through_the_service(self) -> None:
        service = RunManager()
        config = SimulationConfig(
            width=16,
            height=16,
            initial_population=60,
        )
        created = service.create(seed=5, config=config)
        run_id = created["run_id"]
        service.step(run_id, ticks=60)

        payload = service.events(run_id, limit=10)

        self.assertEqual(payload["kind"], "event_feed")
        self.assertEqual(payload["run_id"], run_id)
        self.assertLessEqual(len(payload["events"]), 10)
        self.assertIn("dropped", payload)

    def test_a_nonsense_window_is_rejected(self) -> None:
        service = RunManager()
        config = SimulationConfig(
            width=16,
            height=16,
            initial_population=20,
        )
        run_id = service.create(seed=5, config=config)["run_id"]

        with self.assertRaises(ValueError):
            service.events(run_id, limit=0)
        with self.assertRaises(ValueError):
            service.events(run_id, since_tick="soon")


if __name__ == "__main__":
    unittest.main()
