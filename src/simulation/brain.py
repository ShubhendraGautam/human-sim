import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, List, Tuple

from .config import SimulationConfig
from .models import Action, ActionKind, Agent, BrainKind

ACTION_KINDS = tuple(ActionKind)
ACTION_INDEX = {kind: index for index, kind in enumerate(ACTION_KINDS)}


@dataclass(slots=True)
class BrainState:
    """Bounded lifetime learning state; never inherited by children."""

    preferences: List[float] = field(
        default_factory=lambda: [0.0] * len(ACTION_KINDS)
    )
    last_action: str = ""

    def preference(self, action: Action) -> float:
        return self.preferences[ACTION_INDEX[action.kind]]

    def learn(
        self,
        action: Action,
        reward: float,
        learning_rate: float,
        multiplier: float,
        limit: float,
    ) -> None:
        index = ACTION_INDEX[action.kind]
        previous = self.preferences[index]
        updated = previous + learning_rate * multiplier * (reward - previous)
        self.preferences[index] = min(limit, max(-limit, updated))
        self.last_action = action.kind.value


def choose_action(
    options: List[Tuple[float, Action]],
    agent: Agent,
    neighbors: Iterable[Agent],
    rng: random.Random,
    config: SimulationConfig,
) -> Action:
    kind = agent.traits.brain_kind
    scored = list(options)

    if kind is BrainKind.HABITUAL:
        scored = [
            (
                utility
                + config.habit_preference_weight
                * agent.brain.preference(action),
                action,
            )
            for utility, action in scored
        ]
    elif kind is BrainKind.SOCIAL:
        observed = Counter(
            neighbor.brain.last_action
            for neighbor in neighbors
            if neighbor.brain.last_action
        )
        if observed:
            largest = max(observed.values())
            scored = [
                (
                    utility
                    + config.social_imitation_weight
                    * observed.get(action.kind.value, 0)
                    / largest,
                    action,
                )
                for utility, action in scored
            ]

    if kind is BrainKind.EXPLORATORY:
        temperature = config.exploratory_temperature * (
            0.5 + agent.traits.risk_tolerance
        )
        maximum = max(utility for utility, _ in scored)
        weights = [
            math.exp((utility - maximum) / temperature)
            for utility, _ in scored
        ]
        threshold = rng.random() * sum(weights)
        cumulative = 0.0
        for weight, (_, action) in zip(weights, scored):
            cumulative += weight
            if cumulative >= threshold:
                return action

    return max(scored, key=lambda option: option[0])[1]
