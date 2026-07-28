"""Words: coined from nothing, copied imperfectly, agreed on or not.

The engine seeds no vocabulary. These tests pin the mechanism rather than the
outcome — that a word can be invented, spread, entrench, drift, and that a
population which never speaks stays mute. Whether a language actually forms is
a measurement, not a promise, and the probe in the design notes is where that
gets checked.
"""

import unittest

from src.simulation import Scenario, Simulation, SimulationConfig, language
from src.simulation.scenario import CountrySpec, Rectangle


class WordTests(unittest.TestCase):
    def test_a_coined_word_is_pronounceable(self) -> None:
        for draw in (0.0, 0.13, 0.5, 0.87, 0.999):
            word = language.coin(draw, draw)
            text = language.spell(word)

            self.assertGreaterEqual(len(text), 4)
            self.assertTrue(text.isalpha())

    def test_coining_is_reproducible(self) -> None:
        self.assertEqual(language.coin(0.4, 0.2), language.coin(0.4, 0.2))

    def test_a_word_round_trips_through_packing(self) -> None:
        for syllables in ([3, 17], [0, 0, 0], [79, 12, 44]):
            word = language.pack(syllables)
            self.assertEqual(
                len(language.unpack(word)),
                len(syllables),
            )
            self.assertNotEqual(word, language.NO_WORD)

    def test_no_word_spells_as_nothing(self) -> None:
        self.assertEqual(language.spell(language.NO_WORD), "")

    def test_mishearing_changes_the_word_but_not_its_length(self) -> None:
        word = language.coin(0.31, 0.9)
        heard = language.mutate(word, 0.5, 0.77)

        self.assertNotEqual(heard, word)
        self.assertEqual(
            len(language.unpack(heard)),
            len(language.unpack(word)),
        )


class LexiconTests(unittest.TestCase):
    def test_a_new_person_knows_nothing(self) -> None:
        lexicon = language.Lexicon()

        self.assertEqual(lexicon.size, 0)
        self.assertFalse(lexicon.knows(0))
        self.assertIsNone(lexicon.agreement(language.Lexicon()))

    def test_a_gap_is_filled_by_the_first_word_heard(self) -> None:
        lexicon = language.Lexicon()

        self.assertTrue(lexicon.hear(2, 5150))
        self.assertEqual(lexicon.word_for(2), 5150)

    def test_a_held_word_survives_a_single_disagreement(self) -> None:
        """Otherwise every exchange overwrites and nothing ever settles."""

        lexicon = language.Lexicon()
        lexicon.hear(2, 5150)
        lexicon.hear(2, 5150)

        self.assertFalse(lexicon.hear(2, 9999))
        self.assertEqual(lexicon.word_for(2), 5150)

    def test_sustained_disagreement_eventually_wins(self) -> None:
        lexicon = language.Lexicon()
        lexicon.hear(2, 5150)

        changed = any(lexicon.hear(2, 9999) for _ in range(12))

        self.assertTrue(changed)
        self.assertEqual(lexicon.word_for(2), 9999)

    def test_hearing_your_own_word_entrenches_it(self) -> None:
        entrenched = language.Lexicon()
        entrenched.hear(2, 5150)
        for _ in range(6):
            entrenched.hear(2, 5150)
        fresh = language.Lexicon()
        fresh.hear(2, 5150)

        pushes_to_switch = 0
        while entrenched.word_for(2) == 5150 and pushes_to_switch < 30:
            entrenched.hear(2, 9999)
            pushes_to_switch += 1
        fresh_pushes = 0
        while fresh.word_for(2) == 5150 and fresh_pushes < 30:
            fresh.hear(2, 9999)
            fresh_pushes += 1

        self.assertGreater(pushes_to_switch, fresh_pushes)

    def test_agreement_counts_only_shared_meanings(self) -> None:
        first = language.Lexicon()
        second = language.Lexicon()
        first.learn(0, 111)
        second.learn(0, 111)
        first.learn(1, 222)
        second.learn(1, 333)
        # Only the second knows this one, so it is not evidence either way.
        second.learn(2, 444)

        self.assertAlmostEqual(first.agreement(second), 0.5)


def population(**overrides) -> Simulation:
    config = SimulationConfig(**{
        "width": 14,
        "height": 14,
        "initial_population": 40,
        **overrides,
    })
    return Simulation(
        config=config,
        seed=5,
        scenario=Scenario.default(config),
    )


class SpeechTests(unittest.TestCase):
    def test_a_population_starts_mute(self) -> None:
        simulation = population()

        self.assertEqual(
            sum(agent.lexicon.size for agent in simulation.agents.values()),
            0,
        )

    def test_words_appear_once_people_talk(self) -> None:
        simulation = population()
        simulation.run(180)

        vocabulary = sum(
            agent.lexicon.size for agent in simulation.agents.values()
        )
        self.assertGreater(vocabulary, 0)
        self.assertGreater(simulation.total_coinages, 0)

    def test_a_silent_world_never_invents_a_word(self) -> None:
        """The off switch that reproduces the model before language."""

        simulation = population(language_enabled=False)
        simulation.run(180)

        self.assertEqual(
            sum(agent.lexicon.size for agent in simulation.agents.values()),
            0,
        )
        self.assertEqual(simulation.total_coinages, 0)

    def test_nobody_can_name_what_the_model_has_no_notion_of(self) -> None:
        simulation = population()
        simulation.run(120)

        for agent in simulation.agents.values():
            self.assertEqual(
                len(agent.lexicon.words),
                len(language.MEANINGS),
            )

    def test_speech_is_reproducible_from_a_seed(self) -> None:
        first = population()
        second = population()
        first.run(120)
        second.run(120)

        self.assertEqual(
            sorted(
                tuple(agent.lexicon.words)
                for agent in first.agents.values()
            ),
            sorted(
                tuple(agent.lexicon.words)
                for agent in second.agents.values()
            ),
        )

    def test_separated_populations_do_not_share_words(self) -> None:
        """Divergence is not implemented; it is what isolation produces."""

        config = SimulationConfig(
            width=26,
            height=14,
            initial_population=0,
            # A hull costs more material than anyone can carry, so nobody
            # can put to sea and the two halves genuinely never meet. This
            # was not needed while brains were too quiet to act on being at
            # a coast; once they could, this scenario started producing
            # crossings and quietly stopped testing isolation at all. The
            # guard below is what caught it.
            vessel_material_cost=100.0,
        )
        scenario = Scenario(
            countries=(
                CountrySpec(
                    id=0,
                    name="West",
                    region=Rectangle(0, 0, 10, 14),
                    population=40,
                ),
                CountrySpec(
                    id=1,
                    name="East",
                    region=Rectangle(16, 0, 10, 14),
                    population=40,
                ),
            ),
            seas=(Rectangle(10, 0, 6, 14),),
        )
        simulation = Simulation(config=config, seed=3, scenario=scenario)
        simulation.run(360)

        # Meaning and form together, not the form alone. The sound
        # inventory is small enough that two isolated populations coining
        # ~50 words each will land on the same syllables now and again —
        # seed 3 produces "zesu" on both sides, meaning "food" in the east
        # and "person" in the west. That is a homophone between two
        # unrelated languages, which is a thing real languages do, not
        # evidence that anyone crossed the water.
        def vocabulary(country: int) -> set:
            return {
                (meaning, word)
                for agent in simulation.agents.values()
                if agent.birth_country_id == country
                for meaning, word in enumerate(agent.lexicon.words)
                if word != language.NO_WORD
            }

        west = vocabulary(0)
        east = vocabulary(1)

        self.assertTrue(west, "the west should have coined something")
        self.assertTrue(east, "the east should have coined something")
        self.assertEqual(
            simulation.total_sea_crossings,
            0,
            "this scenario is only a test of isolation while nobody crosses",
        )
        self.assertEqual(
            west & east,
            set(),
            "two populations that never meet cannot share a word for a thing",
        )


if __name__ == "__main__":
    unittest.main()


class AcquisitionTests(unittest.TestCase):
    """The channel that carries a language across a generation.

    Without it every child starts mute and coins its own forms, so a
    vocabulary cannot outlive the people who invented it however well those
    people agreed among themselves.
    """

    def test_a_caregiver_speaking_teaches_the_child_being_fed(self) -> None:
        simulation = population()
        guardian = simulation.agents[min(simulation.agents)]
        child = None
        for agent in simulation.agents.values():
            if agent.id != guardian.id:
                child = agent
                break
        assert child is not None
        child.age = 1.0
        child.x, child.y = guardian.x, guardian.y
        child.guardian_id = guardian.id
        child.inventory = 0.0
        guardian.inventory = simulation.config.inventory_capacity
        meaning = language.MEANING_INDEX["food"]
        guardian.lexicon.learn(meaning, 4242)
        simulation.dependents_by_guardian.setdefault(
            guardian.id, set()
        ).add(child.id)

        heard = False
        for _ in range(60):
            simulation._care(guardian, child.id)
            if child.lexicon.size:
                heard = True
                break
            child.inventory = 0.0
            guardian.inventory = simulation.config.inventory_capacity
            simulation.tick += 1

        self.assertTrue(heard)

    def test_caregiver_transmission_can_be_switched_off(self) -> None:
        simulation = population(language_caregiver_transmission=False)
        guardian = simulation.agents[min(simulation.agents)]
        child = None
        for agent in simulation.agents.values():
            if agent.id != guardian.id:
                child = agent
                break
        assert child is not None
        child.age = 1.0
        child.x, child.y = guardian.x, guardian.y
        child.guardian_id = guardian.id
        guardian.lexicon.learn(language.MEANING_INDEX["food"], 4242)
        simulation.dependents_by_guardian.setdefault(
            guardian.id, set()
        ).add(child.id)

        for _ in range(60):
            child.inventory = 0.0
            guardian.inventory = simulation.config.inventory_capacity
            simulation._care(guardian, child.id)
            simulation.tick += 1

        self.assertEqual(child.lexicon.size, 0)


class InventionRestraintTests(unittest.TestCase):
    def test_nobody_coins_a_rival_for_something_they_have_heard(self) -> None:
        """Invention is a last resort, not a reflex.

        A newcomer who has heard people name a thing waits and copies rather
        than minting a competing sound. Without this, invention permanently
        outruns copying and the population accumulates variants instead of
        settling on any of them.
        """

        lexicon = language.Lexicon()
        meaning = language.MEANING_INDEX["food"]

        self.assertFalse(lexicon.exposed[meaning])
        lexicon.note_exposure(meaning)
        self.assertTrue(lexicon.exposed[meaning])
        # Exposure is not comprehension: still no word of their own.
        self.assertFalse(lexicon.knows(meaning))


class MajorityAdoptionTests(unittest.TestCase):
    def test_the_form_heard_most_wins_not_the_form_heard_last(self) -> None:
        """A voter process never settles; a running majority does."""

        lexicon = language.Lexicon()
        lexicon.learn(0, 111, confidence=1)

        # One rival said repeatedly displaces the held form.
        for _ in range(6):
            lexicon.hear(0, 222, initial_confidence=1)

        self.assertEqual(lexicon.word_for(0), 222)

    def test_two_different_rivals_cancel_instead_of_compounding(
        self,
    ) -> None:
        lexicon = language.Lexicon()
        lexicon.learn(0, 111, confidence=2)

        # Alternating oddities are noise, not evidence for either of them.
        for _ in range(10):
            lexicon.hear(0, 222, initial_confidence=2)
            lexicon.hear(0, 333, initial_confidence=2)

        self.assertEqual(lexicon.word_for(0), 111)
