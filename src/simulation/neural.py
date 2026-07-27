"""Brains that are inherited rather than written.

Every person carries a small network. It reads their circumstances and adds a
bias to each action they might take; the rest of the decision — what the
options are, what they cost, whether they succeed — is unchanged. Nothing
trains these networks. There is no loss function, no gradient, and no target
behaviour anywhere in this file. Children get a recombined, slightly mutated
copy of their parents' weights, and whatever those weights do is judged only
by whether the person carrying them lives long enough to have children.

That is the whole point of doing it this way. A trained network would encode
an outcome somebody chose in advance, which is the one thing this project
refuses to do. An inherited one encodes nothing at the start — founders begin
with near-zero weights, so the first generation behaves exactly as it did
before networks existed — and any structure that appears later got there by
being survived with.

Three properties are load-bearing and worth stating plainly:

- **Deterministic.** Plain Python floats, fixed evaluation order, weights
  drawn from the run's own seeded generator. The digest still reproduces.
- **No dependency.** The simulation core promises no third-party runtime
  imports and this keeps that promise; a matrix library would be faster and
  is not worth the debt at this size.
- **Bounded.** Fixed shape, fixed cost per decision, weights bounded. A brain
  cannot grow without a configuration change, so the tick cost is knowable
  rather than emergent.
"""

import math
import random
from typing import List, Sequence

#: What a brain can perceive.
#:
#: Every entry is something the agent already has bounded local access to.
#: Nothing here is global knowledge, and nothing is a summary the engine
#: computes for the agent's benefit — a network that could see the population
#: total would be reading the observer's notes rather than its own senses.
SENSE_NAMES = (
    "bias",
    "energy",
    "health",
    "inventory",
    "materials",
    "age",
    "body_condition",
    "frailty",
    "neighbours",
    "infected",
    "has_partner",
    "knows_seafaring",
    "has_vessel",
    "research",
)

SENSES = len(SENSE_NAMES)


def squash(value: float) -> float:
    """A bounded activation that keeps runaway weights from taking over."""

    if value > 20.0:
        return 1.0
    if value < -20.0:
        return -1.0
    return math.tanh(value)


class Network:
    """One person's inherited decision bias: senses in, action scores out.

    Deliberately tiny. A single hidden layer with a handful of units cannot
    represent much, which is appropriate — this is a disposition, not a
    planner. Making it larger is a configuration change and a new
    experimental condition, not an improvement.
    """

    __slots__ = ("hidden", "output", "units", "outputs")

    def __init__(self, units: int, outputs: int) -> None:
        self.units = units
        self.outputs = outputs
        #: hidden[unit][sense]
        self.hidden: List[List[float]] = [
            [0.0] * SENSES for _ in range(units)
        ]
        #: output[action][unit]
        self.output: List[List[float]] = [
            [0.0] * units for _ in range(outputs)
        ]

    def evaluate(self, senses: Sequence[float]) -> List[float]:
        scores = [0.0] * self.outputs
        activations = [0.0] * self.units
        for unit in range(self.units):
            weights = self.hidden[unit]
            total = 0.0
            for index in range(SENSES):
                total += weights[index] * senses[index]
            activations[unit] = squash(total)
        for action in range(self.outputs):
            weights = self.output[action]
            total = 0.0
            for unit in range(self.units):
                total += weights[unit] * activations[unit]
            scores[action] = squash(total)
        return scores

    @property
    def magnitude(self) -> float:
        """Mean absolute weight: how strongly a brain pushes at all.

        Reported rather than used. A population whose magnitude climbs is one
        where having an opinion started paying; a population where it decays
        toward zero is telling you the environment does not reward one.
        """

        total = 0.0
        count = 0
        for row in self.hidden:
            for weight in row:
                total += abs(weight)
                count += 1
        for row in self.output:
            for weight in row:
                total += abs(weight)
                count += 1
        return total / count if count else 0.0


def founder_network(
    rng: random.Random,
    units: int,
    outputs: int,
    scale: float,
) -> Network:
    """A first-generation brain.

    At ``scale`` zero every founder is born with no opinions at all and the
    population behaves exactly as it did before brains were heritable. A small
    scale gives selection something to act on immediately without deciding in
    advance what it should favour.
    """

    network = Network(units, outputs)
    if scale <= 0.0:
        return network
    for unit in range(units):
        for index in range(SENSES):
            network.hidden[unit][index] = rng.gauss(0.0, scale)
    for action in range(outputs):
        for unit in range(units):
            network.output[action][unit] = rng.gauss(0.0, scale)
    return network


def inherit(
    first: Network,
    second: Network,
    rng: random.Random,
    mutation_rate: float,
    mutation_scale: float,
    limit: float,
) -> Network:
    """Recombine two brains and let the copy be imperfect.

    Per-weight choice rather than whole-layer, which mixes parental structure
    more finely than the packed genome does for traits. The two inheritance
    channels are deliberately separate: traits are discrete loci with
    crossover, dispositions are continuous weights, and conflating them would
    make either one harder to reason about.
    """

    child = Network(first.units, first.outputs)
    for unit in range(first.units):
        source_hidden = first.hidden[unit]
        other_hidden = second.hidden[unit]
        target = child.hidden[unit]
        for index in range(SENSES):
            weight = (
                source_hidden[index]
                if rng.random() < 0.5
                else other_hidden[index]
            )
            if rng.random() < mutation_rate:
                weight += rng.gauss(0.0, mutation_scale)
            target[index] = min(limit, max(-limit, weight))
    for action in range(first.outputs):
        source_output = first.output[action]
        other_output = second.output[action]
        target_output = child.output[action]
        for unit in range(first.units):
            weight = (
                source_output[unit]
                if rng.random() < 0.5
                else other_output[unit]
            )
            if rng.random() < mutation_rate:
                weight += rng.gauss(0.0, mutation_scale)
            target_output[unit] = min(limit, max(-limit, weight))
    return child
