import math
import random
from collections import Counter, deque
from statistics import fmean
from typing import Callable, Deque, Dict, Iterable, List, Optional, Tuple

from .brain import BrainState, choose_action
from .config import SimulationConfig
from .genetics import LOCUS_COUNT, Gene, Genome, express_traits
from .models import (
    Action,
    ActionKind,
    Agent,
    CultureState,
    Event,
    Metrics,
    Pregnancy,
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
        self.total_conceptions = 0
        self.total_deaths = 0
        self.total_pregnancy_losses = 0
        self.total_inventions = 0
        self.total_sea_crossings = 0
        self._next_agent_id = 0
        self.pregnancies: Dict[int, Pregnancy] = {}
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
        self._advance_pregnancies()

        self.world.rebuild_spatial_index(self.agents.values())
        actions = [
            self._decide(agent, self._decision_rng(agent.id))
            for agent in self.agents.values()
        ]
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
                agent.genome.heterozygosity() for agent in agents
            )
            genetic_diversity = _population_genetic_diversity(agents)
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
            genetic_diversity = 0.0

        return Metrics(
            tick=self.tick,
            year=self.year,
            population=population,
            births=self.total_births,
            conceptions=self.total_conceptions,
            pregnancies=len(self.pregnancies),
            pregnancy_losses=self.total_pregnancy_losses,
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
            genetic_diversity=genetic_diversity,
            action_entropy=_entropy(self._last_action_counts.values()),
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
                agent.genome.haplotype_a,
                agent.genome.haplotype_b,
                agent.traits,
                agent.culture,
                agent.reproductive_role,
                tuple(round(value, 8) for value in agent.brain.preferences),
                agent.brain.last_action,
                agent.birth_country_id,
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
                agent.guardian_id,
            )
            for agent in sorted(self.agents.values(), key=lambda item: item.id)
        )
        resources = tuple(round(value, 8) for value in self.world.resources)
        materials = tuple(round(value, 8) for value in self.world.materials)
        return (
            self.tick,
            self.total_births,
            self.total_conceptions,
            self.total_deaths,
            self.total_pregnancy_losses,
            self.total_inventions,
            self.total_sea_crossings,
            agents,
            resources,
            materials,
            tuple(sorted(
                (
                    parent_id,
                    pregnancy.other_parent_id,
                    pregnancy.genome.haplotype_a,
                    pregnancy.genome.haplotype_b,
                    pregnancy.culture,
                    pregnancy.reproductive_role,
                    pregnancy.belief_id,
                    pregnancy.generation,
                    pregnancy.due_tick,
                )
                for parent_id, pregnancy in self.pregnancies.items()
            )),
        )

    def snapshot(
        self,
        include_world: bool = True,
        include_agents: bool = True,
    ) -> Dict[str, object]:
        """Return a versioned, JSON-serializable state for UIs and recorders."""

        result: Dict[str, object] = {
            "schema_version": 2,
            "tick": self.tick,
            "year": self.year,
            "metrics": self.measure().to_dict(),
            "scenario": self.scenario.to_dict(),
            "pregnancies": [
                {
                    "gestational_parent_id": pregnancy.gestational_parent_id,
                    "other_parent_id": pregnancy.other_parent_id,
                    "conception_tick": pregnancy.conception_tick,
                    "due_tick": pregnancy.due_tick,
                }
                for pregnancy in self.pregnancies.values()
            ],
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
                "birth_country": [
                    agent.birth_country_id for agent in ordered
                ],
                "belief": [agent.belief_id for agent in ordered],
                "energy": [agent.energy for agent in ordered],
                "health": [agent.health for agent in ordered],
                "food_inventory": [
                    agent.inventory for agent in ordered
                ],
                "material_inventory": [
                    agent.material_inventory for agent in ordered
                ],
                "age": [agent.age for agent in ordered],
                "generation": [agent.generation for agent in ordered],
                "parents": [agent.parents for agent in ordered],
                "guardian_id": [agent.guardian_id for agent in ordered],
                "genome_a": [
                    f"{agent.genome.haplotype_a:014x}" for agent in ordered
                ],
                "genome_b": [
                    f"{agent.genome.haplotype_b:014x}" for agent in ordered
                ],
                "reproductive_role": [
                    agent.reproductive_role.value for agent in ordered
                ],
                "brain_kind": [
                    agent.traits.brain_kind.value for agent in ordered
                ],
                "last_action": [
                    agent.brain.last_action for agent in ordered
                ],
                "learned_preferences": [
                    list(agent.brain.preferences) for agent in ordered
                ],
                "fertility": [
                    agent.traits.fertility for agent in ordered
                ],
                "constitution": [
                    agent.traits.constitution for agent in ordered
                ],
                "maximum_health": [
                    agent.traits.maximum_health for agent in ordered
                ],
                "lifespan": [
                    agent.traits.lifespan for agent in ordered
                ],
                "maturity_age": [
                    agent.traits.maturity_age for agent in ordered
                ],
                "learning_rate": [
                    agent.traits.learning_rate for agent in ordered
                ],
                "culture_generosity": [
                    agent.culture.generosity for agent in ordered
                ],
                "culture_exploration": [
                    agent.culture.exploration for agent in ordered
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

    def validate_state(self) -> None:
        """Raise AssertionError when a core simulation invariant is broken."""

        config = self.config
        for agent_id, agent in self.agents.items():
            assert agent.id == agent_id
            assert self.world.normalize(agent.x, agent.y) == (agent.x, agent.y)
            assert 0.0 <= agent.energy <= config.maximum_energy
            assert 0.0 < agent.health <= agent.traits.maximum_health
            assert 0.0 <= agent.inventory <= config.inventory_capacity
            assert (
                0.0
                <= agent.material_inventory
                <= config.material_inventory_capacity
            )
            assert 0.0 <= agent.genome.heterozygosity() <= 1.0
            assert len(agent.brain.preferences) == len(ActionKind)
            assert all(
                0.0 <= getattr(agent.culture, name) <= 1.0
                for name in (
                    "generosity",
                    "exploration",
                    "curiosity",
                    "conformity",
                )
            )
            if agent.guardian_id is not None:
                assert agent.guardian_id in self.agents
                assert agent.guardian_id != agent.id
        for parent_id, pregnancy in self.pregnancies.items():
            assert parent_id in self.agents
            assert pregnancy.gestational_parent_id == parent_id
            assert (
                self.agents[parent_id].reproductive_role
                is ReproductiveRole.OVA
            )
            assert pregnancy.due_tick > pregnancy.conception_tick
        for value, capacity in zip(
            self.world.resources,
            self.world.capacity,
        ):
            assert 0.0 <= value <= capacity
        for value, capacity in zip(
            self.world.materials,
            self.world.material_capacity,
        ):
            assert 0.0 <= value <= capacity

    def _add_founder(self, country: CountrySpec) -> Agent:
        config = self.config
        genome = Genome.founder(
            self.rng,
            config.founder_genetic_variation,
            {
                Gene.METABOLISM: country.metabolism_mean,
                Gene.HARVEST: country.harvest_mean,
                Gene.FERTILITY: country.fertility_mean,
                Gene.CONSTITUTION: country.constitution_mean,
                Gene.LONGEVITY: country.longevity_mean,
                Gene.MATURATION: country.maturation_mean,
                Gene.LEARNING: country.learning_mean,
                Gene.COGNITIVE_STYLE: country.brain_style_mean,
                Gene.RISK: country.risk_mean,
            },
        )
        traits = express_traits(genome, config)
        culture = CultureState(
            generosity=self._founder_cultural_trait(country.generosity_mean),
            exploration=self._founder_cultural_trait(
                country.exploration_mean
            ),
            curiosity=self._founder_cultural_trait(country.curiosity_mean),
            conformity=self._founder_cultural_trait(country.conformity_mean),
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
            health=traits.maximum_health,
            inventory=config.initial_inventory,
            material_inventory=0.0,
            genome=genome,
            traits=traits,
            culture=culture,
            brain=BrainState(),
            reproductive_role=self.rng.choice(tuple(ReproductiveRole)),
            birth_country_id=country.id,
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

    def _temperament(self, agent: Agent, name: str) -> float:
        cultural_weight = self.config.cultural_influence
        return (
            getattr(agent.traits, name) * (1.0 - cultural_weight)
            + getattr(agent.culture, name) * cultural_weight
        )

    def _claim_agent_id(self) -> int:
        agent_id = self._next_agent_id
        self._next_agent_id += 1
        return agent_id

    def _apply_time_and_metabolism(self) -> List[int]:
        config = self.config
        elapsed_years = 1.0 / config.ticks_per_year
        deaths = []
        for agent in self.agents.values():
            if agent.age < config.dependent_age and agent.guardian_id is not None:
                guardian = self.agents.get(agent.guardian_id)
                if guardian is not None:
                    agent.x, agent.y = guardian.x, guardian.y
            agent.age += elapsed_years
            metabolism = agent.traits.metabolism
            if agent.age < config.dependent_age:
                development = agent.age / config.dependent_age
                metabolism *= (
                    config.juvenile_metabolism_fraction
                    + (1.0 - config.juvenile_metabolism_fraction)
                    * development
                )
            agent.energy = max(
                0.0,
                agent.energy
                - metabolism
                - (
                    config.gestation_energy_cost_per_tick
                    if agent.id in self.pregnancies
                    else 0.0
                ),
            )
            if agent.energy <= 0.0:
                agent.health -= config.starvation_damage * (
                    1.25 - 0.5 * agent.traits.constitution
                )
            else:
                agent.health = min(
                    agent.traits.maximum_health,
                    agent.health + config.health_recovery,
                )
            aging_starts_at = (
                agent.traits.lifespan * config.aging_starts_fraction
            )
            if agent.age > aging_starts_at:
                age_pressure = (
                    (agent.age - aging_starts_at)
                    / max(
                        agent.traits.lifespan - aging_starts_at,
                        elapsed_years,
                    )
                )
                agent.health -= (
                    config.aging_damage_per_year
                    * elapsed_years
                    * max(age_pressure, 0.0)
                )
            if agent.health <= 0.0 or agent.age >= agent.traits.lifespan:
                deaths.append(agent.id)
        return deaths

    def _decide(self, agent: Agent, rng: random.Random) -> Action:
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
                config.rest_utility + self._noise(rng),
                Action(ActionKind.REST, agent.id),
            )
        ]

        if agent.inventory > 0.0 and agent.energy < config.maximum_energy:
            options.append(
                (
                    config.hunger_weight * max(hunger, 0.0)
                    + self._noise(rng),
                    Action(ActionKind.EAT, agent.id),
                )
            )

        if agent.age < config.dependent_age:
            return choose_action(options, agent, (), rng, config)

        if current_resource > 0.0 and agent.inventory < config.inventory_capacity:
            gather_utility = config.gather_weight * (
                config.gather_inventory_emphasis
                * max(inventory_space, 0.0)
                + (1.0 - config.gather_inventory_emphasis)
                * resource_fraction
            )
            options.append(
                (
                    gather_utility + self._noise(rng),
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
                    + self._noise(rng),
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
        if len(living_neighbors) > config.maximum_social_neighbors:
            dependents = sorted(
                (
                    neighbor
                    for neighbor in living_neighbors
                    if (
                        neighbor.guardian_id == agent.id
                        and neighbor.age < config.dependent_age
                    )
                ),
                key=lambda child: (child.energy, child.id),
            )[:config.maximum_social_neighbors]
            dependent_ids = {child.id for child in dependents}
            others = [
                neighbor
                for neighbor in living_neighbors
                if neighbor.id not in dependent_ids
            ]
            remaining = config.maximum_social_neighbors - len(dependents)
            living_neighbors = dependents + rng.sample(
                others,
                min(remaining, len(others)),
            )

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
                * self._temperament(agent, "generosity")
                * max(recipient_need, 0.0)
            )
            options.append(
                (
                    share_utility + self._noise(rng),
                    Action(
                        ActionKind.SHARE,
                        agent.id,
                        target_id=recipient.id,
                    ),
                )
            )

        dependents = [
            neighbor
            for neighbor in living_neighbors
            if (
                neighbor.guardian_id == agent.id
                and neighbor.age < config.dependent_age
            )
        ]
        if agent.inventory >= config.care_amount and dependents:
            dependent = min(
                dependents,
                key=lambda child: (child.energy, child.id),
            )
            need = 1.0 - dependent.energy / config.maximum_energy
            options.append(
                (
                    config.care_weight * max(need, 0.0) + self._noise(rng),
                    Action(ActionKind.CARE, agent.id, target_id=dependent.id),
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
                key=lambda neighbor: (
                    self._temperament(neighbor, "curiosity"),
                    -neighbor.id,
                ),
            )
            options.append(
                (
                    config.teaching_weight
                    * self._temperament(agent, "generosity")
                    * self._temperament(learner, "curiosity")
                    + self._noise(rng),
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
                    config.vessel_build_weight + self._noise(rng),
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
                    * self._temperament(agent, "curiosity")
                    * self._temperament(agent, "exploration")
                    + self._noise(rng),
                    Action(ActionKind.RESEARCH, agent.id),
                )
            )

        if agent.vessel_durability > 0.0:
            if self.world.is_sea(agent.x, agent.y):
                voyage = self._voyage_destination(agent, rng)
                if voyage != (agent.x, agent.y):
                    options.append(
                        (
                            config.voyage_weight + self._noise(rng),
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
                    destination = rng.choice(sea_destinations)
                    options.append(
                        (
                            config.sea_exploration_weight
                            * self._temperament(agent, "curiosity")
                            * self._temperament(agent, "exploration")
                            + self._noise(rng),
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
            and self._compatible_for_reproduction(agent, neighbor)
        ]
        if self._can_reproduce(agent) and partners:
            partner = max(
                partners,
                key=lambda candidate: (
                    candidate.energy,
                    -candidate.id,
                ),
            )
            surplus_energy = (
                agent.energy - config.reproduction_energy
            ) / max(
                config.maximum_energy - config.reproduction_energy,
                1.0,
            )
            reproduction_utility = (
                config.reproduction_weight
                * agent.traits.fertility
                * max(surplus_energy, 0.0)
            )
            options.append(
                (
                    reproduction_utility + self._noise(rng),
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
                rng,
                can_cross_sea=agent.vessel_durability > 0.0,
                exploration=self._temperament(agent, "exploration"),
            )
        else:
            destination = (agent.x, agent.y)
        if destination != (agent.x, agent.y):
            scarcity = 1.0 - resource_fraction
            movement_utility = config.movement_weight * (
                config.movement_scarcity_emphasis
                * max(scarcity, 0.0)
                + (1.0 - config.movement_scarcity_emphasis)
                * self._temperament(agent, "exploration")
            )
            options.append(
                (
                    movement_utility + self._noise(rng),
                    Action(
                        ActionKind.MOVE,
                        agent.id,
                        destination=destination,
                    ),
                )
            )

        return choose_action(
            options,
            agent,
            living_neighbors,
            rng,
            config,
        )

    def _noise(self, rng: random.Random) -> float:
        return rng.uniform(
            -self.config.decision_noise,
            self.config.decision_noise,
        )

    def _decision_rng(self, agent_id: int) -> random.Random:
        value = (
            (self.seed & 0xFFFFFFFFFFFFFFFF)
            ^ (self.tick * 0x9E3779B97F4A7C15)
            ^ (agent_id * 0xBF58476D1CE4E5B9)
        ) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 30
        value = (value * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 27
        value = (value * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 31
        return random.Random(value)

    def _can_reproduce(self, agent: Agent) -> bool:
        config = self.config
        cooldown = int(
            config.reproduction_cooldown_years * config.ticks_per_year
        )
        return (
            agent.age >= agent.traits.maturity_age
            and agent.energy >= config.reproduction_energy
            and (
                agent.health / agent.traits.maximum_health
                >= config.minimum_reproductive_health_fraction
            )
            and not (
                agent.reproductive_role is ReproductiveRole.OVA
                and agent.id in self.pregnancies
            )
            and self.tick - agent.last_reproduction_tick >= cooldown
        )

    @staticmethod
    def _compatible_for_reproduction(first: Agent, second: Agent) -> bool:
        return (
            first.id != second.id
            and first.reproductive_role is not second.reproductive_role
        )

    def _resolve(self, actions: Iterable[Action]) -> None:
        counts: Counter[str] = Counter()
        reproduced = set()

        for action in actions:
            agent = self.agents.get(action.actor_id)
            if agent is None:
                continue

            welfare_before = self._welfare(agent)
            applied = False
            if action.kind is ActionKind.EAT:
                applied = self._eat(agent)
            elif action.kind is ActionKind.GATHER:
                applied = self._gather(agent)
            elif action.kind is ActionKind.GATHER_MATERIAL:
                applied = self._gather_material(agent)
            elif action.kind is ActionKind.SHARE:
                applied = self._share(agent, action.target_id)
            elif action.kind is ActionKind.CARE:
                applied = self._care(agent, action.target_id)
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
                reward = (
                    self.config.successful_action_reward
                    + (self._welfare(agent) - welfare_before)
                    / self.config.maximum_energy
                    + self._intrinsic_reward(agent, action)
                )
            else:
                reward = self.config.failed_action_reward
            agent.brain.learn(
                action,
                reward,
                agent.traits.learning_rate,
                multiplier=1.0,
                limit=self.config.learned_preference_limit,
            )
            if applied:
                counts[action.kind.value] += 1

        self._last_action_counts = counts

    def _welfare(self, agent: Agent) -> float:
        return (
            agent.energy
            + agent.health
            + agent.inventory * self.config.food_energy
            + agent.material_inventory * self.config.material_welfare_value
        )

    def _intrinsic_reward(self, agent: Agent, action: Action) -> float:
        kind = action.kind
        if kind in (ActionKind.SHARE, ActionKind.CARE):
            return (
                self.config.sharing_intrinsic_reward
                * self._temperament(agent, "generosity")
            )
        if kind is ActionKind.REPRODUCE:
            return (
                self.config.reproduction_intrinsic_reward
                * agent.traits.fertility
            )
        if kind is ActionKind.RESEARCH:
            return (
                self.config.research_intrinsic_reward
                * self._temperament(agent, "curiosity")
            )
        if kind is ActionKind.TEACH:
            return (
                self.config.teaching_intrinsic_reward
                * self._temperament(agent, "generosity")
            )
        if kind is ActionKind.MOVE:
            return (
                self.config.movement_intrinsic_reward
                * self._temperament(agent, "exploration")
            )
        return 0.0

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

    def _voyage_destination(
        self,
        agent: Agent,
        rng: random.Random,
    ) -> Tuple[int, int]:
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
        destination, _, _ = rng.choice(candidates)
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
            self._temperament(agent, "curiosity")
            * self._temperament(agent, "exploration")
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
        if (
            target is None
            or target.id == agent.id
            or not self._are_local(agent, target)
            or target.knows_seafaring
        ):
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
        if (
            target is None
            or target.id == agent.id
            or not self._are_local(agent, target)
        ):
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

    def _care(self, agent: Agent, target_id: Optional[int]) -> bool:
        if target_id is None:
            return False
        target = self.agents.get(target_id)
        if (
            target is None
            or target.guardian_id != agent.id
            or target.age >= self.config.dependent_age
            or not self._are_local(agent, target)
        ):
            return False
        amount = min(
            self.config.care_amount,
            agent.inventory,
            self.config.inventory_capacity - target.inventory,
        )
        if amount <= 0.0:
            return False
        agent.inventory -= amount
        target.inventory += amount
        self._record(Event(self.tick, "care", (agent.id, target.id)))
        return True

    def _transmit_belief(self, source: Agent, target: Agent) -> None:
        probability = (
            self.config.cultural_transmission_rate
            * self._temperament(target, "conformity")
        )
        if source.belief_id != target.belief_id and self.rng.random() < probability:
            target.belief_id = source.belief_id
        target.culture = CultureState(
            generosity=_blend(
                target.culture.generosity,
                source.culture.generosity,
                probability,
            ),
            exploration=_blend(
                target.culture.exploration,
                source.culture.exploration,
                probability,
            ),
            curiosity=_blend(
                target.culture.curiosity,
                source.culture.curiosity,
                probability,
            ),
            conformity=_blend(
                target.culture.conformity,
                source.culture.conformity,
                probability,
            ),
        )

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
            or not self._compatible_for_reproduction(agent, partner)
            or not self._are_local(agent, partner)
            or self._closely_related(agent, partner)
            or not self._can_reproduce(agent)
            or not self._can_reproduce(partner)
        ):
            return False
        reproduced.update((agent.id, partner.id))

        first_condition = agent.health / agent.traits.maximum_health
        second_condition = partner.health / partner.traits.maximum_health
        probability = min(
            1.0,
            self.config.maximum_conception_probability
            * math.sqrt(
                agent.traits.fertility * partner.traits.fertility
            )
            * first_condition
            * second_condition,
        )
        if self.rng.random() >= probability:
            return False

        agent.energy -= self.config.reproduction_cost
        partner.energy -= self.config.reproduction_cost
        agent.last_reproduction_tick = self.tick
        partner.last_reproduction_tick = self.tick
        genome = Genome.recombine(
            agent.genome,
            partner.genome,
            self.rng,
            self.config.gene_mutation_probability,
            self.config.gene_crossover_probability,
        )
        culture = self._inherit_culture(agent.culture, partner.culture)
        gestational_parent = (
            agent
            if agent.reproductive_role is ReproductiveRole.OVA
            else partner
        )
        other_parent = partner if gestational_parent is agent else agent
        gestation_ticks = max(
            1,
            round(
                self.config.gestation_years
                * self.config.ticks_per_year
            ),
        )
        pregnancy = Pregnancy(
            gestational_parent_id=gestational_parent.id,
            other_parent_id=other_parent.id,
            genome=genome,
            culture=culture,
            reproductive_role=self.rng.choice(tuple(ReproductiveRole)),
            belief_id=self.rng.choice(
                (agent.belief_id, partner.belief_id)
            ),
            generation=max(agent.generation, partner.generation) + 1,
            conception_tick=self.tick,
            due_tick=self.tick + gestation_ticks,
        )
        self.pregnancies[gestational_parent.id] = pregnancy
        self.total_conceptions += 1
        self._record(
            Event(
                self.tick,
                "conception",
                (agent.id, partner.id),
                (("due_tick", float(pregnancy.due_tick)),),
            )
        )
        return True

    def _advance_pregnancies(self) -> None:
        for parent_id, pregnancy in tuple(self.pregnancies.items()):
            gestational_parent = self.agents.get(parent_id)
            if gestational_parent is None:
                continue
            health_fraction = (
                gestational_parent.health
                / gestational_parent.traits.maximum_health
            )
            if (
                health_fraction
                < self.config.minimum_gestation_health_fraction
            ):
                self.pregnancies.pop(parent_id, None)
                self.total_pregnancy_losses += 1
                self._record(
                    Event(
                        self.tick,
                        "pregnancy_loss",
                        (parent_id, pregnancy.other_parent_id),
                    )
                )
            elif self.tick >= pregnancy.due_tick:
                self.pregnancies.pop(parent_id, None)
                self._deliver(gestational_parent, pregnancy)

    def _deliver(
        self,
        gestational_parent: Agent,
        pregnancy: Pregnancy,
    ) -> Agent:
        config = self.config
        gestational_parent.energy = max(
            0.0,
            gestational_parent.energy - config.birth_energy_cost,
        )
        traits = express_traits(pregnancy.genome, config)
        region = self.world.country_at(
            gestational_parent.x,
            gestational_parent.y,
        )
        if region < 0:
            other_parent = self.agents.get(pregnancy.other_parent_id)
            region = (
                other_parent.birth_country_id
                if other_parent is not None
                else gestational_parent.birth_country_id
            )
        gestation_ticks = pregnancy.due_tick - pregnancy.conception_tick
        invested_energy = (
            config.reproduction_cost * 2.0
            + config.gestation_energy_cost_per_tick * gestation_ticks
            + config.birth_energy_cost
        )
        child = Agent(
            id=self._claim_agent_id(),
            x=gestational_parent.x,
            y=gestational_parent.y,
            age=0.0,
            energy=min(config.newborn_energy, invested_energy),
            health=traits.maximum_health,
            inventory=0.0,
            material_inventory=0.0,
            genome=pregnancy.genome,
            traits=traits,
            culture=pregnancy.culture,
            brain=BrainState(),
            reproductive_role=pregnancy.reproductive_role,
            birth_country_id=region,
            belief_id=pregnancy.belief_id,
            generation=pregnancy.generation,
            parents=(
                pregnancy.gestational_parent_id,
                pregnancy.other_parent_id,
            ),
            birth_tick=self.tick,
            guardian_id=pregnancy.gestational_parent_id,
        )
        self.agents[child.id] = child
        self.total_births += 1
        self._record(
            Event(
                self.tick,
                "birth",
                (*child.parents, child.id),
                (("generation", float(child.generation)),),
            )
        )
        return child

    def _are_local(self, first: Agent, second: Agent) -> bool:
        distance_x = abs(first.x - second.x)
        distance_y = abs(first.y - second.y)
        if self.config.wrap_world:
            distance_x = min(distance_x, self.config.width - distance_x)
            distance_y = min(distance_y, self.config.height - distance_y)
        return max(distance_x, distance_y) <= self.config.interaction_radius

    @staticmethod
    def _closely_related(first: Agent, second: Agent) -> bool:
        if first.parents and second.id in first.parents:
            return True
        if second.parents and first.id in second.parents:
            return True
        return bool(
            first.parents
            and second.parents
            and set(first.parents).intersection(second.parents)
        )

    def _inherit_culture(
        self,
        first: CultureState,
        second: CultureState,
    ) -> CultureState:
        noise = self.config.cultural_inheritance_noise

        def inherit(left: float, right: float) -> float:
            return _clamp(
                (left + right) / 2.0 + self.rng.gauss(0.0, noise)
            )

        return CultureState(
            generosity=inherit(first.generosity, second.generosity),
            exploration=inherit(first.exploration, second.exploration),
            curiosity=inherit(first.curiosity, second.curiosity),
            conformity=inherit(first.conformity, second.conformity),
        )

    def _remove_agent(self, agent_id: int) -> None:
        agent = self.agents.pop(agent_id, None)
        if agent is None:
            return
        pregnancy = self.pregnancies.pop(agent_id, None)
        if pregnancy is not None:
            self.total_pregnancy_losses += 1
            self._record(
                Event(
                    self.tick,
                    "pregnancy_loss",
                    (agent_id, pregnancy.other_parent_id),
                )
            )
        for child in self.agents.values():
            if child.guardian_id == agent_id:
                alternative = next(
                    (
                        parent_id
                        for parent_id in child.parents or ()
                        if parent_id != agent_id and parent_id in self.agents
                    ),
                    None,
                )
                child.guardian_id = alternative
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


def _blend(current: float, observed: float, rate: float) -> float:
    return _clamp(current + rate * (observed - current))


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _population_genetic_diversity(agents: Iterable[Agent]) -> float:
    counts = [0] * LOCUS_COUNT
    population = 0
    for agent in agents:
        population += 1
        for locus in range(LOCUS_COUNT):
            mask = 1 << locus
            counts[locus] += bool(agent.genome.haplotype_a & mask)
            counts[locus] += bool(agent.genome.haplotype_b & mask)
    if population == 0:
        return 0.0
    allele_count = population * 2
    return fmean(
        2.0 * (count / allele_count) * (1.0 - count / allele_count)
        for count in counts
    )


def _entropy(counts: Iterable[int]) -> float:
    values = [count for count in counts if count > 0]
    total = sum(values)
    if total == 0 or len(values) <= 1:
        return 0.0
    return -sum(
        (count / total) * math.log(count / total)
        for count in values
    ) / math.log(len(values))
