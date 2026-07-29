import math
import random
from array import array
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, List, Mapping, Optional, Tuple

from .config import SimulationConfig
from .models import (
    Action,
    ActionKind,
    Agent,
    BrainKind,
    InfectionStage,
)

ACTION_KINDS = tuple(ActionKind)
ACTION_INDEX = {kind: index for index, kind in enumerate(ACTION_KINDS)}


@dataclass(slots=True)
class BrainState:
    """Bounded lifetime learning state; never inherited by children.

    This is where the Weismann barrier for minds lives. What a person is born
    with sits in ``Agent.network`` and is what their children recombine; what
    they work out for themselves sits here and dies with them. Keeping the
    learned overlay in this object rather than on the network is what stops
    lifetime experience quietly becoming heritable — a child would otherwise
    inherit its parent's habits along with its parent's disposition, which is
    Lamarck by accident rather than by decision.
    """

    preferences: array = field(
        default_factory=lambda: array("f", [0.0]) * len(ACTION_KINDS)
    )
    #: Learned adjustment to the network's output layer, action by unit.
    #: Allocated on first use, because most brains never learn anything and
    #: an always-present matrix would cost every agent for the few that do.
    plastic: Optional[List[List[float]]] = None
    #: The hidden state that produced the last decision. Lifetime plasticity
    #: uses it for credit assignment; recurrent networks also use it as their
    #: one-step memory. It lives here rather than on the inherited network so
    #: a child's state starts empty however active its parents' minds were.
    last_activations: Optional[List[float]] = None
    last_action: str = ""
    last_success: float = 0.0
    last_target_id: int = -1
    last_action_tick: int = -1

    def preference(self, action: Action) -> float:
        return self.preferences[ACTION_INDEX[action.kind]]

    def adapt(
        self,
        action: Action,
        signal: float,
        rate: float,
        limit: float,
        units: int,
    ) -> bool:
        """Move the output layer toward what just worked.

        Three factors: how surprising the outcome was, how active each hidden
        unit was when the choice was made, and a rate. Nothing here knows
        which action *ought* to be preferred — the same rule runs for eating,
        hunting and resting, and the only thing that separates them is what
        the world paid out. That is what keeps this learning rather than
        instruction.

        Returns whether anything actually changed, so the caller can charge
        for it only when it did.
        """

        activations = self.last_activations
        if activations is None or rate <= 0.0 or signal == 0.0:
            return False
        if self.plastic is None:
            self.plastic = [
                [0.0] * units for _ in range(len(ACTION_KINDS))
            ]
        row = self.plastic[ACTION_INDEX[action.kind]]
        changed = False
        for unit in range(min(units, len(activations))):
            delta = rate * signal * activations[unit]
            if delta == 0.0:
                continue
            updated = row[unit] + delta
            row[unit] = min(limit, max(-limit, updated))
            changed = True
        return changed

    @property
    def plasticity_magnitude(self) -> float:
        """How much this person has learned, as a mean absolute weight."""

        if self.plastic is None:
            return 0.0
        total = 0.0
        count = 0
        for row in self.plastic:
            for weight in row:
                total += abs(weight)
                count += 1
        return total / count if count else 0.0

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


@dataclass(frozen=True, slots=True)
class Surroundings:
    """What the world looks like from where one person is standing.

    Every field is something the deciding code already computes for its own
    purposes, so passing them through costs nothing extra and the brain sees
    exactly what the utility rules see. Keeping it a value rather than
    letting `sense` reach into the world is what stops a brain quietly
    acquiring a query nobody budgeted for.
    """

    food_here: float = 0.0
    food_nearby: float = 0.0
    material_here: float = 0.0
    season: float = 0.0
    animal_near: bool = False
    on_coast: bool = False
    remembered_place: float = 0.0


#: What a brain perceives when nobody has told it anything about the world.
#: Used for the handful of callers that score an action outside a full
#: decision; a blind reading is better than a wrong one.
NOWHERE = Surroundings()


def sense(
    agent: Agent,
    config: SimulationConfig,
    neighbour_count: int,
    surroundings: Surroundings = NOWHERE,
) -> List[float]:
    """What the inherited network gets to see.

    Scaled into roughly [-1, 1] so no single sense dominates purely by having
    larger units than the others. These are the same quantities the agent's
    own body and immediate surroundings already provide; nothing here is
    knowledge it could not have.
    """

    return [
        1.0,
        min(2.0, agent.energy / max(1e-9, config.maximum_energy)) - 0.5,
        min(2.0, agent.health / max(1e-9, config.maximum_health)) - 0.5,
        min(2.0, agent.inventory / max(1e-9, config.harvest_amount * 4)),
        min(2.0, agent.material_inventory
            / max(1e-9, config.material_harvest_amount * 4)),
        min(2.0, agent.age / max(1e-9, config.maximum_age)) - 0.5,
        agent.body_condition - 0.5,
        agent.frailty,
        min(1.0, neighbour_count / 6.0),
        1.0 if agent.infection_stage is not InfectionStage.SUSCEPTIBLE
        else 0.0,
        1.0 if agent.partner_id is not None else 0.0,
        1.0 if agent.knows_seafaring else 0.0,
        1.0 if agent.vessel_durability > 0.0 else 0.0,
        min(1.0, agent.research_progress
            / max(1e-9, config.discovery_threshold)),
        surroundings.food_here,
        surroundings.food_nearby,
        surroundings.material_here,
        surroundings.season,
        1.0 if surroundings.animal_near else 0.0,
        1.0 if surroundings.on_coast else 0.0,
        surroundings.remembered_place,
    ]


def choose_action(
    options: List[Tuple[float, Action]],
    agent: Agent,
    neighbors: Iterable[Agent],
    rng: random.Random,
    config: SimulationConfig,
    social_weights: Optional[Mapping[int, float]] = None,
    current_tick: int = 0,
    surroundings: Surroundings = NOWHERE,
) -> Action:
    kind = agent.traits.brain_kind
    scored = list(options)
    # Materialised once: the social branch reads it too, and a generator
    # consumed here would silently arrive empty there.
    attended = list(neighbors)

    if config.neural_brains_enabled and config.neural_output_weight != 0.0:
        # The network shifts preferences; it never invents an option, hides
        # one, or overrides the locality and resource checks that resolve it.
        # A brain can want anything and still be refused by the world.
        bias, activations = agent.network.respond(
            sense(agent, config, len(attended), surroundings),
            agent.brain.plastic,
            agent.brain.last_activations,
            config.neural_recurrence_weight,
        )
        # Kept so the outcome can be credited to the state that caused it.
        agent.brain.last_activations = activations
        weight = config.neural_output_weight
        scored = [
            (
                utility + weight * bias[ACTION_INDEX[action.kind]],
                action,
            )
            for utility, action in scored
        ]

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
        for neighbor in attended:
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
