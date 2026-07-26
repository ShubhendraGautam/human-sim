import math
import random
from array import array
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, List, Mapping, Optional, Tuple

from .config import SimulationConfig
from .models import Action, ActionKind, Agent, BrainKind

ACTION_KINDS = tuple(ActionKind)
ACTION_INDEX = {kind: index for index, kind in enumerate(ACTION_KINDS)}


@dataclass(slots=True)
class BrainState:
    """Bounded lifetime learning state; never inherited by children."""

    preferences: array = field(
        default_factory=lambda: array("f", [0.0]) * len(ACTION_KINDS)
    )
    last_action: str = ""
    last_success: float = 0.0
    last_target_id: int = -1
    last_action_tick: int = -1

    def preference(self, action: Action) -> float:
        return self.preferences[ACTION_INDEX[action.kind]]

    def learn(
        self,
        action: Action,
        reward: float,
        learning_rate: float,
        multiplier: float,
        limit: float,
        tick: int = 0,
        success: Optional[float] = None,
    ) -> None:
        index = ACTION_INDEX[action.kind]
        previous = self.preferences[index]
        updated = previous + learning_rate * multiplier * (reward - previous)
        self.preferences[index] = min(limit, max(-limit, updated))
        self.last_action = action.kind.value
        self.last_success = (
            min(1.0, max(0.0, float(success)))
            if success is not None
            else float(reward > 0.0)
        )
        self.last_target_id = (
            action.target_id if action.target_id is not None else -1
        )
        self.last_action_tick = tick


def choose_action(
    options: List[Tuple[float, Action]],
    agent: Agent,
    neighbors: Iterable[Agent],
    rng: random.Random,
    config: SimulationConfig,
    social_weights: Optional[Mapping[int, float]] = None,
    current_tick: int = 0,
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
        observed: Counter[str] = Counter()
        attended_neighbors = 0
        memory_ticks = max(
            1.0,
            config.social_success_memory_years * config.ticks_per_year,
        )
        for neighbor in neighbors:
            attended_neighbors += 1
            if (
                not neighbor.brain.last_action
                or neighbor.brain.last_success <= 0.0
            ):
                continue
            age = max(0, current_tick - neighbor.brain.last_action_tick)
            recency = math.exp(-math.log(2.0) * age / memory_ticks)
            relationship_weight = (
                social_weights.get(neighbor.id, 0.15)
                if social_weights is not None
                else 1.0
            )
            observed[neighbor.brain.last_action] += (
                neighbor.brain.last_success
                * recency
                * min(1.0, max(relationship_weight, 0.0))
            )
        if observed:
            evidence_budget = max(1, attended_neighbors)
            conformity = (
                agent.traits.conformity
                * (1.0 - config.cultural_influence)
                + agent.culture.conformity
                * config.cultural_influence
            )
            scored = [
                (
                    utility
                    + config.social_imitation_weight
                    * (0.5 + agent.traits.affiliation)
                    * conformity
                    * observed.get(action.kind.value, 0)
                    / evidence_budget,
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
