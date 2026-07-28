"""Words, invented and passed on.

A population starts mute. Nothing here seeds a vocabulary, and no word means
anything until two people have used it for the same thing. What a word *is* —
which sounds carry which meaning — is never decided by the model; it is
whatever the first speaker happened to coin and enough listeners happened to
copy.

The mechanism is deliberately small:

- There is a fixed inventory of **meanings**: things a person can be in the
  presence of and point at. These are not vocabulary, they are situations the
  engine already tracks. A person cannot talk about something the model has
  no notion of.
- A **word** is a short string of syllables packed into an integer. Two words
  are the same word when their integers match; there is no notion of a word
  being "correct".
- Speaking about something you have no word for **coins** one, at random.
- Hearing a word used for a situation you can see teaches it, sometimes, and
  copying is imperfect, so forms **drift**.

From those four rules alone a vocabulary appears, spreads along the paths
people actually walk, and diverges wherever contact is thin. Divergence is not
implemented — it is what happens when the same rules run in two places that
rarely speak to each other. Whether that occurs is a measurement, which is why
`observation` reports agreement between and within groups rather than a count
of "languages".
"""

from typing import Dict, List, Optional, Sequence, Tuple

#: Situations a person can refer to.
#:
#: Every entry must be something an observer could point at in the world, and
#: something the engine independently knows about a person's circumstances.
#: Adding an abstract concept here would be inventing a thought the model
#: cannot have.
MEANINGS: Tuple[str, ...] = (
    "food",
    "hunger",
    "water",
    "stone",
    "person",
    "child",
    "partner",
    "give",
    "come",
    "sickness",
    "death",
    "far",
)

MEANING_INDEX: Dict[str, int] = {
    name: index for index, name in enumerate(MEANINGS)
}

#: A small phonology. The sounds themselves carry no meaning; they exist so
#: that coined words are pronounceable and distinguishable to a reader.
CONSONANTS: Tuple[str, ...] = (
    "b", "d", "g", "h", "k", "l", "m", "n",
    "p", "r", "s", "t", "v", "w", "y", "z",
)
VOWELS: Tuple[str, ...] = ("a", "e", "i", "o", "u")

SYLLABLES: int = len(CONSONANTS) * len(VOWELS)
#: Words are two or three syllables, packed little-endian into an integer.
MAXIMUM_SYLLABLES: int = 3
#: A word is never zero, so zero can mean "no word".
NO_WORD: int = 0


def syllable_text(value: int) -> str:
    consonant = CONSONANTS[(value // len(VOWELS)) % len(CONSONANTS)]
    vowel = VOWELS[value % len(VOWELS)]
    return consonant + vowel


def spell(word: int) -> str:
    """Render a packed word as something a reader can pronounce."""

    if word <= NO_WORD:
        return ""
    letters: List[str] = []
    remaining = word
    while remaining > 0:
        letters.append(syllable_text((remaining % (SYLLABLES + 1)) - 1))
        remaining //= SYLLABLES + 1
    return "".join(letters)


def pack(syllables: Sequence[int]) -> int:
    """Pack syllable indices into one integer, low syllable first."""

    word = 0
    for position, syllable in enumerate(reversed(list(syllables))):
        word = word * (SYLLABLES + 1) + (syllable % SYLLABLES) + 1
    return word


def unpack(word: int) -> List[int]:
    syllables: List[int] = []
    remaining = word
    while remaining > 0:
        syllables.append((remaining % (SYLLABLES + 1)) - 1)
        remaining //= SYLLABLES + 1
    return syllables


def coin(draw: float, length_draw: float) -> int:
    """Invent a word from nothing.

    Called when someone needs to refer to something they have never had a
    word for. This is the only place a word enters the world, and it is pure
    chance — which is the point: nothing about the situation makes any
    particular sounds apt for it.
    """

    length = 2 if length_draw < 0.62 else 3
    scaled = max(0.0, min(0.999999, draw))
    syllables = []
    for position in range(length):
        # Spread one draw across the syllables deterministically rather than
        # consuming several, so a coinage costs one number.
        rotated = (scaled * (SYLLABLES ** (position + 1))) % SYLLABLES
        syllables.append(int(rotated))
    return pack(syllables)


def mutate(word: int, position_draw: float, syllable_draw: float) -> int:
    """Copy a word imperfectly.

    Transmission is by ear, and a syllable heard slightly wrong is how forms
    drift apart in places that do not speak often. The word stays the same
    length: this is mishearing, not coining.
    """

    syllables = unpack(word)
    if not syllables:
        return word
    position = min(
        len(syllables) - 1,
        int(max(0.0, min(0.999999, position_draw)) * len(syllables)),
    )
    replacement = int(max(0.0, min(0.999999, syllable_draw)) * SYLLABLES)
    if replacement == syllables[position]:
        replacement = (replacement + 1) % SYLLABLES
    syllables[position] = replacement
    return pack(list(reversed(syllables)))


class Lexicon:
    """One person's words: at most one form per meaning.

    Holding a single form per meaning is a strong simplification — real
    speakers carry variants and can understand words they would not use. It
    keeps the store to a fixed dozen integers per person, which is what makes
    a language affordable at population scale, and it still produces the
    thing worth watching: agreement where people talk, difference where they
    do not.
    """

    __slots__ = ("words", "confidence", "exposed", "challenger",
                 "challenger_count")

    #: How much accumulated evidence it takes to give up a word you use.
    MAXIMUM_CONFIDENCE = 6

    def __init__(self) -> None:
        self.words: List[int] = [NO_WORD] * len(MEANINGS)
        # Whether anyone has ever said anything to this person about each
        # meaning, adopted or not. Someone who has heard others talk about
        # a thing does not make up their own sound for it; they wait and
        # copy. Without that, every newcomer mints a fresh form and
        # invention permanently outruns copying, so the population
        # accumulates variants instead of converging on any of them.
        self.exposed: List[bool] = [False] * len(MEANINGS)
        # The one rival form currently being weighed against the held one,
        # and how far ahead of it that rival is. Keeping a single challenger
        # is a running majority vote: a form that really is the common one
        # locally keeps being reinforced and eventually displaces the held
        # form, while passing oddities cancel each other out and never do.
        #
        # This is the part that makes a language possible. Copying whatever
        # you heard last is a voter process, and a voter process does not
        # converge on any timescale a run covers — it just relabels everyone
        # forever. Adopting what you hear *most* does converge, and it is
        # also what a learner surrounded by speakers actually does.
        self.challenger: List[int] = [NO_WORD] * len(MEANINGS)
        self.challenger_count: List[int] = [0] * len(MEANINGS)
        # Evidence for the form currently held. Copying whatever you last
        # heard is a voter process, and a voter process on a spread-out
        # population takes far longer than a run to settle — everyone keeps
        # overwriting everyone. Requiring repeated disagreement before
        # switching lets a locally common form reinforce itself, which is
        # both how consensus actually forms and the difference between a
        # language and permanent babel.
        self.confidence: List[int] = [0] * len(MEANINGS)

    def knows(self, meaning: int) -> bool:
        return self.words[meaning] != NO_WORD

    def note_exposure(self, meaning: int) -> None:
        """Record that someone used a word for this, whether or not it stuck.

        Exposure is not comprehension. It only says the meaning is one other
        people evidently have a sound for, which is reason enough not to
        invent a competing one.
        """

        self.exposed[meaning] = True

    def word_for(self, meaning: int) -> int:
        return self.words[meaning]

    def learn(self, meaning: int, word: int, confidence: int = 1) -> None:
        self.words[meaning] = word
        self.confidence[meaning] = max(1, min(self.MAXIMUM_CONFIDENCE,
                                              confidence))
        self.challenger[meaning] = NO_WORD
        self.challenger_count[meaning] = 0

    def hear(
        self,
        meaning: int,
        word: int,
        initial_confidence: int = 1,
    ) -> bool:
        """Take in someone else's word for something.

        Returns whether the listener's own usage changed. Hearing your own
        form again entrenches it; hearing a different one chips away at it,
        and only sustained disagreement makes you switch.

        ``initial_confidence`` is how much credit a freshly taken-up form
        gets. At one, a word adopted a moment ago is discarded by the very
        next speaker who says something else, which is a voter process: on a
        spread-out population it churns forever and no form ever wins. Giving
        a new word more than one unit of credit means a locally common form
        has to be contradicted repeatedly to be dislodged, which is what lets
        neighbourhoods settle and is the difference between a language and
        permanent babel.
        """

        if word == NO_WORD:
            return False
        mine = self.words[meaning]
        if mine == NO_WORD:
            self.learn(meaning, word, initial_confidence)
            return True
        if mine == word:
            self.confidence[meaning] = min(
                self.MAXIMUM_CONFIDENCE,
                self.confidence[meaning] + 1,
            )
            if self.challenger_count[meaning] > 0:
                self.challenger_count[meaning] -= 1
            return False
        if word == self.challenger[meaning]:
            self.challenger_count[meaning] += 1
        elif self.challenger_count[meaning] <= 0:
            self.challenger[meaning] = word
            self.challenger_count[meaning] = 1
        else:
            # Two different rivals cancel rather than compound. Only a form
            # that is consistently the one being said gets anywhere.
            self.challenger_count[meaning] -= 1
            return False
        if self.challenger_count[meaning] > self.confidence[meaning]:
            self.learn(
                meaning,
                self.challenger[meaning],
                initial_confidence,
            )
            return True
        return False

    @property
    def size(self) -> int:
        return sum(1 for word in self.words if word != NO_WORD)

    def agreement(self, other: "Lexicon") -> Optional[float]:
        """Share of meanings both can name where they use the same form.

        ``None`` when there is no meaning both have a word for, which is a
        different state from disagreeing about everything and should not be
        averaged in with it.
        """

        shared = 0
        matching = 0
        for mine, theirs in zip(self.words, other.words):
            if mine == NO_WORD or theirs == NO_WORD:
                continue
            shared += 1
            if mine == theirs:
                matching += 1
        if shared == 0:
            return None
        return matching / shared
