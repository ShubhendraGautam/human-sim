import random
from collections import Counter, deque
from statistics import fmean
from typing import Callable, Deque, Dict, Iterable, List, Optional, Tuple

from .brain import BrainState, choose_action
from .config import SimulationConfig
from .genetics import Gene, Genome, express_traits
from .models import (
    Action,
    ActionKind,
    Agent,
    BrainKind,
    Event,
    Metrics,
    ReproductiveRole,
    Terrain,
)
from .scenario import CountrySpec, Scenario
from .world import World

EventSink = Callable[[Event], None]
MetricsSink = Callable[[Metrics], None]


class Simulation:
    """Owns all mutable state for one reproducible simulation run."""

    def __init__(
        self,
        config: Optional[SimulationConfig] = None,
        seed: int = 0,
        scenario: Optional[Scenario] = None,
        event_sink: Optional[EventSink] = None,
        metrics_sink: Optional[MetricsSink] = None,
    ):
        self.config = config or SimulationConfig()
        self.seed = seed
        self.rng = random.Random(seed)
        self.scenario = scenario or Scenario.default(self.config)
        self.scenario.validate(self.config)
        self.world = World(self.config, self.rng, self.scenario)
        self.agents: Dict[int, Agent] = {}
        self.tick = 0
        self.total_births = 0
        self.total_deaths = 0
        self.total_inventions = 0
        self.total_sea_crossings = 0
        self._next_agent_id = 0
        self._event_sink = event_sink
        self._metrics_sink = metrics_sink
        self.events: Deque[Event] = deque(
            maxlen=self.config.event_log_capacity
        )
        self.metrics_history: Deque[Metrics] = deque(
            maxlen=self.config.metrics_history_capacity
        )
        self._last_action_counts: Counter[str] = Counter()

        for country in self.scenario.countries:
            for _ in range(country.population):
                self._add_founder(country)
        self.world.rebuild_spatial_index(self.agents.values())
        self._sample_metrics(force=True)

    @property
    def year(self) -> float:
        return self.tick / self.config.ticks_per_year

    def run(self, ticks: int) -> Metrics:
        if ticks < 0:
            raise ValueError("ticks cannot be negative")
        for _ in range(ticks):
            self.step()
        return self.measure()

    def step(self) -> None:
        self.tick += 1
        deaths = self._apply_time_and_metabolism()
        for agent_id in deaths:
            self._remove_agent(agent_id)

        self.world.rebuild_spatial_index(self.agents.values())
        actions = [self._decide(agent) for agent in self.agents.values()]
        self.rng.shuffle(actions)
        self._resolve(actions)
        self.world.regenerate()
        self.world.rebuild_spatial_index(self.agents.values())
        self._sample_metrics()

    def measure(self) -> Metrics:
        population = len(self.agents)
        agents = self.agents.values()
        if population:
            energies = [agent.energy for agent in agents]
            # values() is a reusable view; subsequent comprehensions are safe.
            mean_energy = fmean(energies)
            mean_health = fmean(agent.health for agent in agents)
            mean_inventory = fmean(agent.inventory for agent in agents)
            mean_age = fmean(agent.age for agent in agents)
            maximum_generation = max(
                agent.generation for agent in agents
            )
            energy_gini = _gini(energies)
            seafaring_population = sum(
                agent.knows_seafaring for agent in agents
            )
            vessels = sum(agent.vessel_durability > 0.0 for agent in agents)
            country_population = Counter(
                self.world.country_at(agent.x, agent.y)
                for agent in agents
            )
            belief_population = Counter(
                agent.belief_id for agent in agents
            )
            brain_population = Counter(
                agent.traits.brain_kind.value for agent in agents
            )
            reproductive_roles = Counter(
                agent.reproductive_role.value for agent in agents
            )
            mean_heterozygosity = fmean(
                sum(
                    abs(
                        agent.genome.alleles[offset]
                        - agent.genome.alleles[offset + 1]
                    )
                    for offset in range(0, len(agent.genome.alleles), 2)
                )
                / (len(agent.genome.alleles) / 2)
                for agent in agents
            )
        else:
            mean_energy = 0.0
            mean_health = 0.0
            mean_inventory = 0.0
            mean_age = 0.0
            maximum_generation = 0
            energy_gini = 0.0
            seafaring_population = 0
            vessels = 0
            country_population = Counter()
            belief_population = Counter()
            brain_population = Counter()
            reproductive_roles = Counter()
            mean_heterozygosity = 0.0

        return Metrics(
            tick=self.tick,
            year=self.year,
            population=population,
            births=self.total_births,
            deaths=self.total_deaths,
            total_resources=self.world.total_resources(),
            total_materials=self.world.total_materials(),
            mean_energy=mean_energy,
            mean_health=mean_health,
            mean_inventory=mean_inventory,
            mean_age=mean_age,
            maximum_generation=maximum_generation,
            energy_gini=energy_gini,
            seafaring_population=seafaring_population,
            vessels=vessels,
            inventions=self.total_inventions,
            sea_crossings=self.total_sea_crossings,
            country_population=dict(country_population),
            belief_population=dict(belief_population),
            brain_population=dict(brain_population),
            reproductive_roles=dict(reproductive_roles),
            mean_heterozygosity=mean_heterozygosity,
            actions=dict(self._last_action_counts),
        )

    def state_digest(self) -> Tuple[object, ...]:
        """Stable compact state representation used for reproducibility checks."""

        agents = tuple(
            (
                agent.id,
                agent.x,
                agent.y,
                round(agent.age, 8),
                round(agent.energy, 8),
                round(agent.health, 8),
                round(agent.inventory, 8),
                round(agent.material_inventory, 8),
                agent.genome.alleles,
                agent.traits,
                agent.reproductive_role,
                tuple(sorted(agent.brain.preferences.items())),
                agent.brain.last_action,
                agent.country_id,
                agent.belief_id,
                round(agent.research_progress, 8),
                agent.knows_seafaring,
                round(agent.vessel_durability, 8),
                agent.voyage_dx,
                agent.voyage_dy,
                agent.generation,
                agent.parents,
                agent.birth_tick,
                agent.last_reproduction_tick,
            )
            for agent in sorted(self.agents.values(), key=lambda item: item.id)
        )
        resources = tuple(round(value, 8) for value in self.world.resources)
        materials = tuple(round(value, 8) for value in self.world.materials)
        return (
            self.tick,
            self.total_births,
            self.total_deaths,
            self.total_inventions,
            self.total_sea_crossings,
            agents,
            resources,
            materials,
        )

    def snapshot(
        self,
        include_world: bool = True,
        include_agents: bool = True,
    ) -> Dict[str, object]:
        """Return a versioned, JSON-serializable state for UIs and recorders."""

        result: Dict[str, object] = {
            "schema_version": 1,
            "tick": self.tick,
            "year": self.year,
            "metrics": self.measure().to_dict(),
            "scenario": self.scenario.to_dict(),
        }
        if include_world:
            result["world"] = {
                "width": self.config.width,
                "height": self.config.height,
                "terrain": list(self.world.terrain),
                "country": list(self.world.country),
                "food": list(self.world.resources),
                "materials": list(self.world.materials),
            }
        if include_agents:
            ordered = sorted(self.agents.values(), key=lambda agent: agent.id)
            result["agents"] = {
                "id": [agent.id for agent in ordered],
                "x": [agent.x for agent in ordered],
                "y": [agent.y for agent in ordered],
                "origin_country": [agent.country_id for agent in ordered],
                "belief": [agent.belief_id for agent in ordered],
                "energy": [agent.energy for agent in ordered],
                "health": [agent.health for agent in ordered],
                "age": [agent.age for agent in ordered],
                "generation": [agent.generation for agent in ordered],
                "reproductive_role": [
                    agent.reproductive_role.value for agent in ordered
                ],
                "brain_kind": [
                    agent.traits.brain_kind.value for agent in ordered
                ],
                "last_action": [
                    agent.brain.last_action for agent in ordered
                ],
                "fertility": [
                    agent.traits.fertility for agent in ordered
                ],
                "constitution": [
                    agent.traits.constitution for agent in ordered
                ],
                "lifespan": [
                    agent.traits.lifespan for agent in ordered
                ],
                "knows_seafaring": [
                    agent.knows_seafaring for agent in ordered
                ],
                "vessel_durability": [
                    agent.vessel_durability for agent in ordered
                ],
                "voyage_dx": [agent.voyage_dx for agent in ordered],
                "voyage_dy": [agent.voyage_dy for agent in ordered],
            }
        return result

    def _add_founder(self, country: CountrySpec) -> Agent:
        config = self.config
        traits = Traits(
            metabolism=self.rng.uniform(
                config.base_metabolism_minimum,
                config.base_metabolism_maximum,
            ),
            harvest_skill=self.rng.uniform(
                config.harvest_skill_minimum,
                config.harvest_skill_maximum,
            ),
            generosity=self._founder_cultural_trait(country.generosity_mean),
            fertility=self.rng.random(),
            exploration=self._founder_cultural_trait(
                country.exploration_mean
            ),
            curiosity=self._founder_cultural_trait(country.curiosity_mean),
            conformity=self._founder_cultural_trait(country.conformity_mean),
            vision=self.rng.randint(
                config.vision_minimum,
                config.vision_maximum,
            ),
        )
        cell = self.rng.choice(self.world.country_land_cells[country.id])
        x, y = self.world.coordinates(cell)
        agent = Agent(
            id=self._claim_agent_id(),
            x=x,
            y=y,
            age=self.rng.uniform(
                config.initial_age_minimum,
                config.initial_age_maximum,
            ),
            energy=min(
                config.maximum_energy,
                self.rng.uniform(
                    config.initial_energy_minimum,
                    config.initial_energy_maximum,
                )
                * country.starting_energy_multiplier,
            ),
            health=config.maximum_health,
            inventory=config.initial_inventory,
            material_inventory=0.0,
            traits=traits,
            country_id=country.id,
            belief_id=self.scenario.belief_id_for(country),
        )
        self.agents[agent.id] = agent
        return agent

    def _founder_cultural_trait(self, center: float) -> float:
        half_range = self.config.cultural_trait_variation
        return min(1.0, max(0.0, self.rng.uniform(
            center - half_range,
            center + half_range,
        )))

    def _claim_agent_id(self) -> int:
        agent_id = self._next_agent_id
        self._next_agent_id += 1
        return agent_id

    def _apply_time_and_metabolism(self) -> List[int]:
        config = self.config
        elapsed_years = 1.0 / config.ticks_per_year
        deaths = []
        for agent in self.agents.values():
            agent.age += elapsed_years
            agent.energy = max(
                0.0,
                agent.energy - agent.traits.metabolism,
            )
            if agent.energy <= 0.0:
                agent.health -= config.starvation_damage
            else:
                agent.health = min(
                    config.maximum_health,
                    agent.health + config.health_recovery,
                )
            if agent.age > config.aging_starts_at:
                age_pressure = (
                    (agent.age - config.aging_starts_at)
                    / max(
                        config.maximum_age - config.aging_starts_at,
                        elapsed_years,
                    )
                )
                agent.health -= (
                    config.aging_damage_per_year
                    * elapsed_years
                    * max(age_pressure, 0.0)
                )
            if agent.health <= 0.0 or agent.age >= config.maximum_age:
                deaths.append(agent.id)
        return deaths

    def _decide(self, agent: Agent) -> Action:
        config = self.config
        hunger = 1.0 - agent.energy / config.maximum_energy
        inventory_space = 1.0 - agent.inventory / config.inventory_capacity
        material_space = (
            1.0
            - agent.material_inventory / config.material_inventory_capacity
        )
        current_resource = self.world.resource_at(agent.x, agent.y)
        current_material = self.world.material_at(agent.x, agent.y)
        cell_capacity = self.world.capacity[
            self.world.cell_index(agent.x, agent.y)
        ]
        resource_fraction = (
            current_resource / cell_capacity if cell_capacity else 0.0
        )

        options: List[Tuple[float, Action]] = [
            (
                config.rest_utility + self._noise(),
                Action(ActionKind.REST, agent.id),
            )
        ]

        if agent.inventory > 0.0 and agent.energy < config.maximum_energy:
            options.append(
                (
                    config.hunger_weight * max(hunger, 0.0)
                    + self._noise(),
                    Action(ActionKind.EAT, agent.id),
                )
            )

        if current_resource > 0.0 and agent.inventory < config.inventory_capacity:
            gather_utility = config.gather_weight * (
                config.gather_inventory_emphasis
                * max(inventory_space, 0.0)
                + (1.0 - config.gather_inventory_emphasis)
                * resource_fraction
            )
            options.append(
                (
                    gather_utility + self._noise(),
                    Action(ActionKind.GATHER, agent.id),
                )
            )

        if (
            current_material > 0.0
            and agent.material_inventory < config.material_inventory_capacity
        ):
            options.append(
                (
                    config.material_gather_weight
                    * max(material_space, 0.0)
                    + self._noise(),
                    Action(ActionKind.GATHER_MATERIAL, agent.id),
                )
            )

        neighbor_ids = self.world.nearby_agent_ids(
            agent.x,
            agent.y,
            radius=config.interaction_radius,
            exclude=agent.id,
        )
        living_neighbors = [
            self.agents[neighbor_id]
            for neighbor_id in neighbor_ids
        ]

        if agent.inventory >= config.share_amount and living_neighbors:
            recipient = min(
                living_neighbors,
                key=lambda neighbor: (
                    neighbor.energy
                    + neighbor.inventory * config.food_energy,
                    neighbor.id,
                ),
            )
            recipient_need = 1.0 - (
                recipient.energy / config.maximum_energy
            )
            share_utility = (
                config.sharing_weight
                * agent.traits.generosity
                * max(recipient_need, 0.0)
            )
            options.append(
                (
                    share_utility + self._noise(),
                    Action(
                        ActionKind.SHARE,
                        agent.id,
                        target_id=recipient.id,
                    ),
                )
            )

        learners = [
            neighbor
            for neighbor in living_neighbors
            if agent.knows_seafaring and not neighbor.knows_seafaring
        ]
        if learners:
            learner = max(
                learners,
                key=lambda neighbor: (neighbor.traits.curiosity, -neighbor.id),
            )
            options.append(
                (
                    config.teaching_weight
                    * agent.traits.generosity
                    * learner.traits.curiosity
                    + self._noise(),
                    Action(ActionKind.TEACH, agent.id, target_id=learner.id),
                )
            )

        if (
            agent.knows_seafaring
            and agent.vessel_durability <= 0.0
            and agent.material_inventory >= config.vessel_material_cost
            and agent.energy >= config.vessel_energy_cost
            and not self.world.is_sea(agent.x, agent.y)
        ):
            options.append(
                (
                    config.vessel_build_weight + self._noise(),
                    Action(ActionKind.BUILD_VESSEL, agent.id),
                )
            )

        if (
            not agent.knows_seafaring
            and self.world.is_coast(agent.x, agent.y)
            and agent.material_inventory >= config.research_material_cost
            and agent.energy >= config.research_energy_minimum
        ):
            options.append(
                (
                    config.research_weight
                    * agent.traits.curiosity
                    * agent.traits.exploration
                    + self._noise(),
                    Action(ActionKind.RESEARCH, agent.id),
                )
            )

        if agent.vessel_durability > 0.0:
            if self.world.is_sea(agent.x, agent.y):
                voyage = self._voyage_destination(agent)
                if voyage != (agent.x, agent.y):
                    options.append(
                        (
                            config.voyage_weight + self._noise(),
                            Action(
                                ActionKind.MOVE,
                                agent.id,
                                destination=voyage,
                            ),
                        )
                    )
            else:
                sea_destinations = self.world.adjacent_sea_destinations(
                    agent.x,
                    agent.y,
                )
                if sea_destinations:
                    destination = self.rng.choice(sea_destinations)
                    options.append(
                        (
                            config.sea_exploration_weight
                            * agent.traits.curiosity
                            * agent.traits.exploration
                            + self._noise(),
                            Action(
                                ActionKind.MOVE,
                                agent.id,
                                destination=destination,
                            ),
                        )
                    )

        partners = [
            neighbor
            for neighbor in living_neighbors
            if self._can_reproduce(neighbor)
        ]
        if self._can_reproduce(agent) and partners:
            partner = max(
                partners,
                key=lambda candidate: (
                    candidate.traits.fertility,
                    candidate.energy,
                    -candidate.id,
                ),
            )
            combined_fertility = (
                agent.traits.fertility + partner.traits.fertility
            ) / 2.0
            surplus_energy = (
                agent.energy - config.reproduction_energy
            ) / max(
                config.maximum_energy - config.reproduction_energy,
                1.0,
            )
            reproduction_utility = (
                config.reproduction_weight
                * combined_fertility
                * max(surplus_energy, 0.0)
            )
            options.append(
                (
                    reproduction_utility + self._noise(),
                    Action(
                        ActionKind.REPRODUCE,
                        agent.id,
                        target_id=partner.id,
                    ),
                )
            )

        # Avoid the most expensive perception query when movement cannot beat
        # an action already available to the agent.
        movement_upper_bound = (
            config.movement_weight + config.decision_noise
        )
        best_known_utility = max(utility for utility, _ in options)
        if best_known_utility <= movement_upper_bound:
            destination = self.world.best_neighbor(
                agent,
                self.rng,
                can_cross_sea=agent.vessel_durability > 0.0,
            )
        else:
            destination = (agent.x, agent.y)
        if destination != (agent.x, agent.y):
            scarcity = 1.0 - resource_fraction
            movement_utility = config.movement_weight * (
                config.movement_scarcity_emphasis
                * max(scarcity, 0.0)
                + (1.0 - config.movement_scarcity_emphasis)
                * agent.traits.exploration
            )
            options.append(
                (
                    movement_utility + self._noise(),
                    Action(
                        ActionKind.MOVE,
                        agent.id,
                        destination=destination,
                    ),
                )
            )

        return max(options, key=lambda option: option[0])[1]

    def _noise(self) -> float:
        return self.rng.uniform(
            -self.config.decision_noise,
            self.config.decision_noise,
        )

    def _can_reproduce(self, agent: Agent) -> bool:
        config = self.config
        cooldown = int(
            config.reproduction_cooldown_years * config.ticks_per_year
        )
        return (
            agent.age >= config.maturity_age
            and agent.energy >= config.reproduction_energy
            and self.tick - agent.last_reproduction_tick >= cooldown
        )

    def _resolve(self, actions: Iterable[Action]) -> None:
        counts: Counter[str] = Counter()
        reproduced = set()

        for action in actions:
            agent = self.agents.get(action.actor_id)
            if agent is None:
                continue

            applied = False
            if action.kind is ActionKind.EAT:
                applied = self._eat(agent)
            elif action.kind is ActionKind.GATHER:
                applied = self._gather(agent)
            elif action.kind is ActionKind.GATHER_MATERIAL:
                applied = self._gather_material(agent)
            elif action.kind is ActionKind.SHARE:
                applied = self._share(agent, action.target_id)
            elif action.kind is ActionKind.RESEARCH:
                applied = self._research(agent)
            elif action.kind is ActionKind.TEACH:
                applied = self._teach(agent, action.target_id)
            elif action.kind is ActionKind.BUILD_VESSEL:
                applied = self._build_vessel(agent)
            elif action.kind is ActionKind.REPRODUCE:
                applied = self._reproduce(
                    agent,
                    action.target_id,
                    reproduced,
                )
            elif action.kind is ActionKind.MOVE:
                if action.destination is not None:
                    applied = self._move(agent, action.destination)
            else:
                applied = True

            if applied:
                counts[action.kind.value] += 1

        self._last_action_counts = counts

    def _eat(self, agent: Agent) -> bool:
        amount = min(agent.inventory, self.config.eat_amount)
        if amount <= 0.0:
            return False
        energy_room = (
            self.config.maximum_energy - agent.energy
        ) / self.config.food_energy
        amount = min(amount, max(energy_room, 0.0))
        if amount <= 0.0:
            return False
        agent.inventory -= amount
        agent.energy = min(
            self.config.maximum_energy,
            agent.energy + amount * self.config.food_energy,
        )
        return True

    def _gather(self, agent: Agent) -> bool:
        requested = min(
            self.config.harvest_amount * agent.traits.harvest_skill,
            self.config.inventory_capacity - agent.inventory,
        )
        amount = self.world.harvest(agent.x, agent.y, requested)
        agent.inventory += amount
        return amount > 0.0

    def _gather_material(self, agent: Agent) -> bool:
        requested = min(
            self.config.material_harvest_amount * agent.traits.harvest_skill,
            self.config.material_inventory_capacity
            - agent.material_inventory,
        )
        amount = self.world.harvest_material(
            agent.x,
            agent.y,
            requested,
        )
        agent.material_inventory += amount
        return amount > 0.0

    def _move(self, agent: Agent, destination: Tuple[int, int]) -> bool:
        destination_index = self.world.try_cell_index(*destination)
        if destination_index is None:
            return False
        distance_x = abs(destination[0] - agent.x)
        distance_y = abs(destination[1] - agent.y)
        if self.config.wrap_world:
            distance_x = min(distance_x, self.config.width - distance_x)
            distance_y = min(distance_y, self.config.height - distance_y)
        if max(distance_x, distance_y) != 1:
            return False
        current_is_sea = self.world.is_sea(agent.x, agent.y)
        destination_is_sea = (
            self.world.terrain[destination_index] == Terrain.SEA
        )
        cost = self.config.movement_energy_cost
        if current_is_sea or destination_is_sea:
            if agent.vessel_durability <= 0.0:
                return False
            cost += self.config.sea_movement_cost
        if agent.energy < cost:
            return False
        agent.energy -= cost
        if current_is_sea or destination_is_sea:
            agent.vessel_durability = max(
                0.0,
                agent.vessel_durability - 1.0,
            )
        if current_is_sea and not destination_is_sea:
            self.total_sea_crossings += 1
            self._record(Event(self.tick, "landfall", (agent.id,)))
            agent.voyage_dx = 0
            agent.voyage_dy = 0
        elif not current_is_sea and destination_is_sea:
            agent.voyage_dx = destination[0] - agent.x
            agent.voyage_dy = destination[1] - agent.y
        elif current_is_sea and destination_is_sea:
            agent.voyage_dx = destination[0] - agent.x
            agent.voyage_dy = destination[1] - agent.y
        agent.x, agent.y = destination
        return True

    def _voyage_destination(self, agent: Agent) -> Tuple[int, int]:
        if agent.voyage_dx or agent.voyage_dy:
            destination = self.world.normalize(
                agent.x + agent.voyage_dx,
                agent.y + agent.voyage_dy,
            )
            if destination is not None:
                return destination
        candidates = []
        for offset_x, offset_y in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            destination = self.world.normalize(
                agent.x + offset_x,
                agent.y + offset_y,
            )
            if destination is not None:
                candidates.append((destination, offset_x, offset_y))
        if not candidates:
            return agent.x, agent.y
        destination, _, _ = self.rng.choice(candidates)
        return destination

    def _research(self, agent: Agent) -> bool:
        config = self.config
        if (
            agent.knows_seafaring
            or not self.world.is_coast(agent.x, agent.y)
            or agent.material_inventory < config.research_material_cost
            or agent.energy < config.research_energy_cost
        ):
            return False
        agent.material_inventory -= config.research_material_cost
        agent.energy -= config.research_energy_cost
        agent.research_progress += (
            agent.traits.curiosity
            * agent.traits.exploration
            * self.rng.uniform(
                config.research_gain_minimum,
                config.research_gain_maximum,
            )
        )
        if agent.research_progress >= config.seafaring_discovery_threshold:
            agent.knows_seafaring = True
            self.total_inventions += 1
            self._record(Event(self.tick, "invent_seafaring", (agent.id,)))
        return True

    def _teach(self, agent: Agent, target_id: Optional[int]) -> bool:
        if target_id is None or not agent.knows_seafaring:
            return False
        target = self.agents.get(target_id)
        if target is None or target.knows_seafaring:
            return False
        target.knows_seafaring = True
        self._transmit_belief(agent, target)
        self._record(Event(self.tick, "teach_seafaring", (agent.id, target.id)))
        return True

    def _build_vessel(self, agent: Agent) -> bool:
        config = self.config
        if (
            not agent.knows_seafaring
            or agent.vessel_durability > 0.0
            or agent.material_inventory < config.vessel_material_cost
            or agent.energy < config.vessel_energy_cost
            or self.world.is_sea(agent.x, agent.y)
        ):
            return False
        agent.material_inventory -= config.vessel_material_cost
        agent.energy -= config.vessel_energy_cost
        agent.vessel_durability = config.vessel_durability
        self._record(Event(self.tick, "build_vessel", (agent.id,)))
        return True

    def _share(self, agent: Agent, target_id: Optional[int]) -> bool:
        if target_id is None:
            return False
        target = self.agents.get(target_id)
        if target is None:
            return False
        amount = min(
            self.config.share_amount,
            agent.inventory,
            self.config.inventory_capacity - target.inventory,
        )
        if amount <= 0.0:
            return False
        agent.inventory -= amount
        target.inventory += amount
        self._transmit_belief(agent, target)
        self._record(Event(self.tick, "share", (agent.id, target.id)))
        return True

    def _transmit_belief(self, source: Agent, target: Agent) -> None:
        probability = (
            self.config.cultural_transmission_rate
            * target.traits.conformity
        )
        if source.belief_id != target.belief_id and self.rng.random() < probability:
            target.belief_id = source.belief_id

    def _reproduce(
        self,
        agent: Agent,
        target_id: Optional[int],
        reproduced: set,
    ) -> bool:
        if target_id is None or agent.id in reproduced:
            return False
        partner = self.agents.get(target_id)
        if (
            partner is None
            or partner.id in reproduced
            or not self._can_reproduce(agent)
            or not self._can_reproduce(partner)
        ):
            return False

        agent.energy -= self.config.reproduction_cost
        partner.energy -= self.config.reproduction_cost
        agent.last_reproduction_tick = self.tick
        partner.last_reproduction_tick = self.tick
        reproduced.update((agent.id, partner.id))

        child = Agent(
            id=self._claim_agent_id(),
            x=agent.x,
            y=agent.y,
            age=0.0,
            energy=self.config.newborn_energy,
            health=self.config.maximum_health,
            inventory=0.0,
            material_inventory=0.0,
            traits=self._inherit_traits(agent.traits, partner.traits),
            country_id=(
                self.world.country_at(agent.x, agent.y)
                if self.world.country_at(agent.x, agent.y) >= 0
                else self.rng.choice((agent.country_id, partner.country_id))
            ),
            belief_id=self.rng.choice(
                (agent.belief_id, partner.belief_id)
            ),
            generation=max(agent.generation, partner.generation) + 1,
            parents=(agent.id, partner.id),
            birth_tick=self.tick,
        )
        self.agents[child.id] = child
        self.total_births += 1
        self._record(
            Event(
                self.tick,
                "birth",
                (agent.id, partner.id, child.id),
                (("generation", float(child.generation)),),
            )
        )
        return True

    def _inherit_traits(self, first: Traits, second: Traits) -> Traits:
        config = self.config

        def inherited(
            first_value: float,
            second_value: float,
            minimum: float,
            maximum: float,
        ) -> float:
            midpoint = (first_value + second_value) / 2.0
            mutated = midpoint + self.rng.gauss(
                0.0,
                config.mutation_rate * (maximum - minimum),
            )
            return min(maximum, max(minimum, mutated))

        vision = round(
            inherited(
                float(first.vision),
                float(second.vision),
                float(config.vision_minimum),
                float(config.vision_maximum),
            )
        )
        return Traits(
            metabolism=inherited(
                first.metabolism,
                second.metabolism,
                config.base_metabolism_minimum,
                config.base_metabolism_maximum,
            ),
            harvest_skill=inherited(
                first.harvest_skill,
                second.harvest_skill,
                config.harvest_skill_minimum,
                config.harvest_skill_maximum,
            ),
            generosity=inherited(
                first.generosity,
                second.generosity,
                0.0,
                1.0,
            ),
            fertility=inherited(
                first.fertility,
                second.fertility,
                0.0,
                1.0,
            ),
            exploration=inherited(
                first.exploration,
                second.exploration,
                0.0,
                1.0,
            ),
            curiosity=inherited(
                first.curiosity,
                second.curiosity,
                0.0,
                1.0,
            ),
            conformity=inherited(
                first.conformity,
                second.conformity,
                0.0,
                1.0,
            ),
            vision=int(vision),
        )

    def _remove_agent(self, agent_id: int) -> None:
        agent = self.agents.pop(agent_id, None)
        if agent is None:
            return
        self.total_deaths += 1
        self._record(
            Event(
                self.tick,
                "death",
                (agent_id,),
                (("age", agent.age),),
            )
        )

    def _record(self, event: Event) -> None:
        self.events.append(event)
        if self._event_sink is not None:
            self._event_sink(event)

    def _sample_metrics(self, force: bool = False) -> None:
        if force or self.tick % self.config.metrics_interval == 0:
            metrics = self.measure()
            self.metrics_history.append(metrics)
            if self._metrics_sink is not None:
                self._metrics_sink(metrics)


def _gini(values: List[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(max(value, 0.0) for value in values)
    total = sum(ordered)
    if total == 0.0:
        return 0.0
    count = len(ordered)
    weighted = sum(
        index * value
        for index, value in enumerate(ordered, start=1)
    )
    return (2.0 * weighted) / (count * total) - (count + 1.0) / count
