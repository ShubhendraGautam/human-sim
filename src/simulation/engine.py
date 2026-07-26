import math
import random
from array import array
from collections import Counter, deque
from operator import attrgetter
from typing import (
    Callable,
    Deque,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
)

from .brain import BrainState, choose_action
from .config import SimulationConfig
from .genetics import (
    Gene,
    Genome,
    express_traits,
)
from .health import (
    InfectionStage,
    disease_severity,
    duration_ticks,
    host_susceptibility,
    transmission_probability,
)
from .life_history import (
    annual_hazard_to_tick,
    effective_health_capacity,
)
from . import observation
from .models import (
    Action,
    ActionKind,
    Agent,
    BrainKind,
    CultureState,
    Event,
    Metrics,
    Pregnancy,
    ReproductiveRole,
    Terrain,
)
from .relationships import RelationshipStore
from .scenario import CountrySpec, Scenario
from .versions import (  # noqa: F401  (re-exported for existing importers)
    MODEL_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
)
from .world import World

EventSink = Callable[[Event], None]
MetricsSink = Callable[[Metrics], None]
REFERENCE_TICKS_PER_YEAR = 12.0

# Sorting the population by ID happens several times per tick; a C-level
# attribute getter is measurably cheaper than an equivalent lambda.
_agent_id = attrgetter("id")


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
        self.total_infections = 0
        self.total_recoveries = 0
        self._last_food_consumed = 0.0
        self._last_food_spoiled = 0.0
        self._last_food_lost_on_death = 0.0
        self._last_material_consumed = 0.0
        self._last_material_lost_on_death = 0.0
        self._next_agent_id = 0
        self.pregnancies: Dict[int, Pregnancy] = {}
        self.dependents_by_guardian: Dict[int, set[int]] = {}
        self.relationships = RelationshipStore(
            capacity=self.config.maximum_social_bonds,
            half_life_ticks=(
                self.config.relationship_half_life_years
                * self.config.ticks_per_year
            ),
            balance_limit=self.config.relationship_balance_limit,
        )
        self.deaths_by_cause: Counter[str] = Counter()
        self._event_sink = event_sink
        self._metrics_sink = metrics_sink
        self.events: Deque[Event] = deque(
            maxlen=self.config.event_log_capacity
        )
        self.metrics_history: Deque[Metrics] = deque(
            maxlen=self.config.metrics_history_capacity
        )
        self._last_action_counts: Counter[str] = Counter()
        self._last_action_attempts: Counter[str] = Counter()
        self._last_action_failures: Counter[str] = Counter()

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
        self.world.begin_tick()
        self._last_food_consumed = 0.0
        self._last_food_spoiled = 0.0
        self._last_food_lost_on_death = 0.0
        self._last_material_consumed = 0.0
        self._last_material_lost_on_death = 0.0
        # Disease and metabolism observe the same agent set, so they share one
        # deterministic ordering instead of sorting the population twice.
        ordered_agents = self._ordered_agents()
        disease_damage = self._advance_disease(ordered_agents)
        deaths = self._apply_time_and_metabolism(
            disease_damage,
            ordered_agents,
        )
        for agent_id, cause in deaths:
            self._remove_agent(agent_id, cause=cause)
        self._advance_pregnancies()

        self.world.rebuild_spatial_index(self.agents.values())
        # Deaths and births changed the population, so the decision phase
        # needs a fresh ordering rather than the one shared above.
        actions = [
            self._decide(agent, self._decision_rng(agent.id))
            for agent in self._ordered_agents()
        ]
        self.rng.shuffle(actions)
        self._resolve(actions)
        self.world.regenerate(self.tick)
        self.world.rebuild_spatial_index(self.agents.values())
        self._sample_metrics()

    def measure(self) -> Metrics:
        """Return current aggregate metrics. See :mod:`.observation`."""

        return observation.measure(self)

    def state_digest(self) -> Tuple[object, ...]:
        """Compact stable state used for reproducibility checks."""

        return observation.state_digest(self)

    def snapshot(
        self,
        include_world: bool = True,
        include_agents: bool = True,
        include_relationships: bool = True,
    ) -> Dict[str, object]:
        """Return versioned JSON state for UIs and recorders."""

        return observation.snapshot(
            self,
            include_world=include_world,
            include_agents=include_agents,
            include_relationships=include_relationships,
        )

    def validate_state(self) -> None:
        """Raise if any cross-structure invariant is violated."""

        observation.validate_state(self)

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
                Gene.IMMUNITY: country.immunity_mean,
                Gene.AFFILIATION: country.affiliation_mean,
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
        energy = min(
            config.maximum_energy,
            self.rng.uniform(
                config.initial_energy_minimum,
                config.initial_energy_maximum,
            )
            * country.starting_energy_multiplier,
        )
        body_condition = min(1.0, energy / config.maximum_energy)
        development = self.rng.uniform(
            config.founder_development_minimum,
            config.founder_development_maximum,
        )
        age = self.rng.uniform(
            config.initial_age_minimum,
            config.initial_age_maximum,
        )
        health_capacity = effective_health_capacity(
            traits.maximum_health,
            development,
            0.0,
            config.minimum_development_health_fraction,
            config.frailty_health_capacity_loss,
        )
        agent = Agent(
            id=self._claim_agent_id(),
            x=x,
            y=y,
            age=age,
            energy=energy,
            health=health_capacity,
            inventory=config.initial_inventory,
            material_inventory=0.0,
            genome=genome,
            traits=traits,
            culture=culture,
            brain=BrainState(),
            reproductive_role=self.rng.choice(tuple(ReproductiveRole)),
            birth_country_id=country.id,
            belief_id=self.scenario.belief_id_for(country),
            body_condition=body_condition,
            development_index=development,
            development_exposure_years=min(
                age,
                traits.maturity_age,
            ),
            relationship_slot=self.relationships.allocate(),
        )
        exposed_fraction = (
            country.initial_exposed_fraction
            if country.initial_exposed_fraction is not None
            else config.initial_exposed_fraction
        )
        if self.rng.random() < exposed_fraction:
            agent.infection_stage = InfectionStage.EXPOSED
            agent.infection_ticks_remaining = duration_ticks(
                config.disease_incubation_years,
                config.ticks_per_year,
            )
            self.total_infections += 1
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

    def _scan_exposures(
        self,
        ordered_agents: Sequence[Agent],
        pressure: Sequence[float],
        elapsed_years: float,
    ) -> List[int]:
        """Return IDs newly exposed by local infectious pressure."""
        config = self.config
        transmission_rate = config.disease_transmission_rate_per_year
        cell_index = self.world.cell_index
        newly_exposed: List[int] = []
        for agent in ordered_agents:
            if agent.infection_stage is not InfectionStage.SUSCEPTIBLE:
                continue
            local_pressure = pressure[cell_index(agent.x, agent.y)]
            if local_pressure <= 0.0:
                continue
            susceptibility = host_susceptibility(
                agent.age,
                agent.traits.maturity_age,
                agent.traits.immune_strength,
                agent.body_condition,
                agent.frailty,
            )
            probability = transmission_probability(
                transmission_rate,
                local_pressure,
                susceptibility,
                elapsed_years,
            )
            if self._stable_uniform(agent.id, 0xD15) < probability:
                newly_exposed.append(agent.id)
        return newly_exposed

    def _advance_disease(
        self,
        ordered_agents: Optional[Sequence[Agent]] = None,
    ) -> Dict[int, float]:
        """Advance one generic local SEIR process in O(N + occupied cells)."""

        if not self.agents:
            return {}
        config = self.config
        elapsed_years = 1.0 / config.ticks_per_year
        health_damage: Dict[int, float] = {}
        if ordered_agents is None:
            ordered_agents = self._ordered_agents()
        infectious_cells: Counter[int] = Counter(
            self.world.cell_index(agent.x, agent.y)
            for agent in ordered_agents
            if agent.infection_stage is InfectionStage.INFECTIOUS
        )

        newly_exposed = []
        # With nobody infectious the pressure grid is uniformly zero, so the
        # exposure scan cannot expose anyone. Skip both rather than allocating
        # and reading a full-world array every tick.
        if infectious_cells:
            cell_count = config.width * config.height
            pressure = array("f", [0.0]) * cell_count
            for source_cell, count in infectious_cells.items():
                x, y = self.world.coordinates(source_cell)
                for target_cell in self.world.nearby_cell_indices(
                    x,
                    y,
                    config.disease_contact_radius,
                ):
                    pressure[target_cell] += count
            newly_exposed = self._scan_exposures(
                ordered_agents,
                pressure,
                elapsed_years,
            )
        for agent in ordered_agents:
            stage = agent.infection_stage
            if stage is InfectionStage.EXPOSED:
                agent.infection_ticks_remaining -= 1
                if agent.infection_ticks_remaining <= 0:
                    duration_multiplier = (
                        (1.25 - 0.50 * agent.traits.immune_strength)
                        * (1.10 - 0.20 * agent.body_condition)
                    )
                    agent.infection_stage = InfectionStage.INFECTIOUS
                    agent.infection_ticks_remaining = duration_ticks(
                        config.disease_infectious_years,
                        config.ticks_per_year,
                        duration_multiplier,
                    )
                    self._record(Event(
                        self.tick,
                        "became_infectious",
                        (agent.id,),
                    ))
            elif stage is InfectionStage.INFECTIOUS:
                severity = disease_severity(
                    agent.traits.immune_strength,
                    agent.body_condition,
                    agent.frailty,
                )
                agent.energy = max(
                    0.0,
                    agent.energy
                    - config.disease_energy_cost_per_year
                    * elapsed_years
                    * severity,
                )
                damage = (
                    config.disease_health_damage_per_year
                    * elapsed_years
                    * severity
                )
                agent.health -= damage
                if damage > 0.0:
                    health_damage[agent.id] = damage
                agent.infection_ticks_remaining -= 1
                if (
                    agent.infection_ticks_remaining <= 0
                    and agent.health > 0.0
                ):
                    agent.infection_stage = InfectionStage.RECOVERED
                    agent.infection_ticks_remaining = duration_ticks(
                        config.disease_immunity_years,
                        config.ticks_per_year,
                        0.75
                        + 0.50 * agent.traits.immune_strength,
                    )
                    self.total_recoveries += 1
                    self._record(Event(
                        self.tick,
                        "infection_recovery",
                        (agent.id,),
                    ))
            elif stage is InfectionStage.RECOVERED:
                agent.infection_ticks_remaining -= 1
                if agent.infection_ticks_remaining <= 0:
                    agent.infection_stage = InfectionStage.SUSCEPTIBLE
                    agent.infection_ticks_remaining = 0

        for agent_id in newly_exposed:
            agent = self.agents.get(agent_id)
            if (
                agent is None
                or agent.infection_stage is not InfectionStage.SUSCEPTIBLE
            ):
                continue
            agent.infection_stage = InfectionStage.EXPOSED
            agent.infection_ticks_remaining = duration_ticks(
                config.disease_incubation_years,
                config.ticks_per_year,
            )
            self.total_infections += 1
            self._record(Event(self.tick, "infection", (agent.id,)))
        return health_damage

    def _health_capacity(self, agent: Agent) -> float:
        developmental_multiplier = (
            self.config.minimum_development_health_fraction
            + (
                1.0
                - self.config.minimum_development_health_fraction
            )
            * agent.development_index
        )
        return (
            agent.traits.maximum_health
            * developmental_multiplier
            * (
                1.0
                - self.config.frailty_health_capacity_loss
                * agent.frailty
            )
        )

    def _capability(self, agent: Agent) -> float:
        onset = self.config.dependent_age
        maturity = agent.traits.maturity_age
        if maturity <= onset or agent.age >= maturity:
            return 1.0
        floor = self.config.juvenile_capability_floor
        if agent.age <= onset:
            return floor
        position = (agent.age - onset) / (maturity - onset)
        progress = position * position * (3.0 - 2.0 * position)
        return floor + (1.0 - floor) * progress

    def _ordered_agents(self) -> List[Agent]:
        """Return living agents in ascending ID order.

        Every phase iterates through this rather than dict order so that
        results never depend on insertion history.
        """
        return sorted(self.agents.values(), key=_agent_id)

    def _apply_time_and_metabolism(
        self,
        disease_damage: Optional[Dict[int, float]] = None,
        ordered_agents: Optional[Sequence[Agent]] = None,
    ) -> List[Tuple[int, str]]:
        config = self.config
        disease_damage = disease_damage or {}
        elapsed_years = 1.0 / config.ticks_per_year
        tick_scale = REFERENCE_TICKS_PER_YEAR / config.ticks_per_year
        condition_retention = math.exp(
            -elapsed_years / config.nutrition_memory_years
        )
        spoilage_retention = math.exp(
            -config.food_spoilage_rate_per_year * elapsed_years
        )
        deaths: List[Tuple[int, str]] = []
        if ordered_agents is None:
            ordered_agents = self._ordered_agents()
        for agent in ordered_agents:
            damage_by_cause: Dict[str, float] = {}
            infection_damage = disease_damage.get(agent.id, 0.0)
            if infection_damage > 0.0:
                damage_by_cause["infection"] = infection_damage
            if agent.health <= 0.0:
                deaths.append((
                    agent.id,
                    "infection" if infection_damage > 0.0 else "other",
                ))
                continue

            age_before = agent.age
            agent.age += elapsed_years

            if (
                age_before < config.dependent_age
                and agent.age >= config.dependent_age
            ):
                self._set_guardian(agent, None)

            if agent.inventory > 0.0:
                inventory_before_spoilage = agent.inventory
                agent.inventory *= spoilage_retention
                self._last_food_spoiled += (
                    inventory_before_spoilage - agent.inventory
                )

            metabolism = agent.traits.metabolism
            if agent.age < config.dependent_age:
                development = agent.age / config.dependent_age
                metabolism *= (
                    config.juvenile_metabolism_fraction
                    + (1.0 - config.juvenile_metabolism_fraction)
                    * development
                )
            metabolism *= tick_scale
            agent.energy = max(
                0.0,
                agent.energy - metabolism,
            )

            pregnancy = self.pregnancies.get(agent.id)
            if pregnancy is not None:
                requested_investment = (
                    config.gestation_energy_cost_per_tick * tick_scale
                )
                actual_investment = min(
                    requested_investment,
                    agent.energy,
                )
                agent.energy -= actual_investment
                pregnancy.invested_energy += actual_investment

            condition_target = agent.energy / config.maximum_energy
            agent.body_condition = (
                condition_target
                + (agent.body_condition - condition_target)
                * condition_retention
            )
            developmental_years = min(
                elapsed_years,
                max(agent.traits.maturity_age - age_before, 0.0),
            )
            if developmental_years > 0.0:
                total_exposure = (
                    agent.development_exposure_years
                    + developmental_years
                )
                agent.development_index = (
                    agent.development_index
                    * agent.development_exposure_years
                    + agent.body_condition * developmental_years
                ) / total_exposure
                agent.development_exposure_years = total_exposure

            onset_age = (
                agent.traits.lifespan
                * config.aging_starts_fraction
            )
            exposed_start = max(age_before, onset_age)
            exposed_end = max(agent.age, onset_age)
            exposed_years = exposed_end - exposed_start
            if (
                exposed_years > 0.0
                and config.frailty_accumulation_per_year > 0.0
            ):
                start_fraction = (
                    (exposed_start - onset_age)
                    / agent.traits.lifespan
                )
                if config.frailty_age_acceleration == 0.0:
                    age_integral = exposed_years
                else:
                    interval_fraction = (
                        exposed_years / agent.traits.lifespan
                    )
                    age_integral = (
                        agent.traits.lifespan
                        * math.exp(
                            config.frailty_age_acceleration
                            * start_fraction
                        )
                        * math.expm1(
                            config.frailty_age_acceleration
                            * interval_fraction
                        )
                        / config.frailty_age_acceleration
                    )
                vulnerability = (
                    (
                        1.0
                        - config.frailty_constitution_protection
                        * agent.traits.constitution
                    )
                    * (
                        1.0
                        + config.frailty_condition_penalty
                        * (1.0 - agent.body_condition)
                    )
                )
                agent.frailty = min(
                    1.0,
                    agent.frailty
                    + config.frailty_accumulation_per_year
                    * age_integral
                    * vulnerability,
                )

            health_capacity = self._health_capacity(agent)
            capacity_loss = max(agent.health - health_capacity, 0.0)
            if capacity_loss > 0.0:
                damage_by_cause["frailty"] = capacity_loss
            agent.health = min(agent.health, health_capacity)
            if agent.energy <= 0.0:
                starvation_damage = (
                    config.starvation_damage
                    * tick_scale
                    * (1.25 - 0.5 * agent.traits.constitution)
                )
                agent.health -= starvation_damage
                damage_by_cause["starvation"] = starvation_damage

            aging_damage = (
                config.aging_damage_per_year
                * elapsed_years
                * agent.frailty
                * (
                    1.0
                    + config.frailty_condition_penalty
                    * (1.0 - agent.body_condition)
                )
            )
            agent.health -= aging_damage
            if aging_damage > 0.0:
                damage_by_cause["frailty"] = (
                    damage_by_cause.get("frailty", 0.0)
                    + aging_damage
                )

            if agent.age >= config.absolute_maximum_age:
                deaths.append((agent.id, "old_age"))
                continue
            if agent.health <= 0.0:
                cause = (
                    max(
                        damage_by_cause.items(),
                        key=lambda item: item[1],
                    )[0]
                    if damage_by_cause
                    else "other"
                )
                deaths.append((agent.id, cause))
                continue

            if agent.energy > 0.0:
                recovery = min(
                    max(health_capacity - agent.health, 0.0),
                    config.health_recovery
                    * tick_scale
                    * agent.body_condition
                    * (
                        1.0
                        - config.frailty_recovery_penalty
                        * agent.frailty
                    )
                    * (0.75 + 0.25 * agent.traits.immune_strength),
                )
                energy_needed = (
                    recovery * config.health_recovery_energy_cost
                )
                if energy_needed > agent.energy and energy_needed > 0.0:
                    recovery *= agent.energy / energy_needed
                    energy_needed = agent.energy
                agent.energy -= energy_needed
                agent.health = min(
                    health_capacity,
                    agent.health + recovery,
                )

            annual_hazard = (
                config.baseline_mortality_rate_per_year
                + config.frailty_mortality_rate_per_year
                * agent.frailty
                * agent.frailty
            )
            mortality_probability = annual_hazard_to_tick(
                annual_hazard,
                elapsed_years,
            )
            if (
                self._stable_uniform(agent.id, 0xA61)
                < mortality_probability
            ):
                deaths.append((
                    agent.id,
                    "frailty" if agent.frailty > 0.25 else "other",
                ))
        return deaths

    def _decide(self, agent: Agent, rng: random.Random) -> Action:
        config = self.config
        random_value = rng.random
        noise_amplitude = config.decision_noise
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
        capability = self._capability(agent)
        physical_capacity = capability * (
            1.0
            - config.development_harvest_influence
            + config.development_harvest_influence
            * agent.development_index
        )

        options: List[Tuple[float, Action]] = [
            (
                config.rest_utility
                + (random_value() * 2.0 - 1.0) * noise_amplitude,
                Action(ActionKind.REST, agent.id),
            )
        ]

        if agent.inventory > 0.0 and agent.energy < config.maximum_energy:
            options.append(
                (
                    config.hunger_weight * max(hunger, 0.0)
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
                    Action(ActionKind.EAT, agent.id),
                )
            )

        if agent.age < config.dependent_age:
            return choose_action(
                options,
                agent,
                (),
                rng,
                config,
                current_tick=self.tick,
            )

        if (
            current_resource > 0.0
            and agent.inventory < config.inventory_capacity
        ):
            gather_utility = config.gather_weight * (
                config.gather_inventory_emphasis
                * max(inventory_space, 0.0)
                + (1.0 - config.gather_inventory_emphasis)
                * resource_fraction
            ) * physical_capacity
            options.append(
                (
                    gather_utility
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
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
                    * physical_capacity
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
                    Action(ActionKind.GATHER_MATERIAL, agent.id),
                )
            )

        relationship_views = (
            {
                view.other_id: view
                for view in self.relationships.views(
                    agent.relationship_slot,
                    self.tick,
                )
            }
            if self.relationships.contact_count(
                agent.relationship_slot
            )
            else {}
        )
        mandatory_ids = [
            dependent_id
            for dependent_id in sorted(
                self.dependents_by_guardian.get(agent.id, ())
            )
            if (
                dependent_id in self.agents
                and self._are_local(agent, self.agents[dependent_id])
            )
        ]
        remembered_ids = [
            view.other_id
            for view in sorted(
                relationship_views.values(),
                key=lambda item: (
                    -abs(item.trust),
                    -item.encounters,
                    -item.last_seen_tick,
                    item.other_id,
                ),
            )
            if (
                view.other_id in self.agents
                and self._are_local(agent, self.agents[view.other_id])
                and view.other_id not in mandatory_ids
            )
        ]
        preselected = (
            mandatory_ids + remembered_ids
        )[:config.maximum_social_neighbors]
        neighbor_ids = self.world.sample_nearby_agent_ids(
            agent.x,
            agent.y,
            radius=config.interaction_radius,
            exclude=agent.id,
            limit=config.maximum_social_neighbors,
            rng=rng,
            preselected=preselected,
        )
        living_neighbors = [
            self.agents[neighbor_id]
            for neighbor_id in neighbor_ids
            if neighbor_id in self.agents
        ]

        view_for = relationship_views.get
        preference_scale = (
            config.relationship_preference_weight * agent.traits.affiliation
        )
        balance_limit = config.relationship_balance_limit

        def relationship_bonus(other: Agent) -> Tuple[float, float]:
            view = view_for(other.id)
            if view is None:
                return 0.0, 0.0
            encounters = view.encounters
            confidence = encounters / (encounters + 3.0)
            preference = (
                preference_scale
                * confidence
                * (view.trust + view.balance / balance_limit)
            )
            return preference, confidence

        # Each of these loops runs once per attended neighbor, so values that
        # depend only on the deciding agent are computed once above them.
        maximum_energy = config.maximum_energy
        inventory_capacity = config.inventory_capacity
        agent_id = agent.id
        append_option = options.append

        if agent.inventory >= config.share_amount:
            sharing_weight = config.sharing_weight
            generosity = self._temperament(agent, "generosity")
            for recipient in living_neighbors:
                if recipient.inventory >= inventory_capacity:
                    continue
                recipient_need = max(
                    1.0 - recipient.energy / maximum_energy,
                    0.0,
                )
                preference, _ = relationship_bonus(recipient)
                share_utility = (
                    sharing_weight
                    * generosity
                    * recipient_need
                    + preference
                )
                append_option((
                    share_utility
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
                    Action(
                        ActionKind.SHARE,
                        agent_id,
                        target_id=recipient.id,
                    ),
                ))

        if agent.inventory >= config.care_amount:
            dependent_age = config.dependent_age
            care_weight = config.care_weight
            for dependent in living_neighbors:
                if (
                    dependent.age >= dependent_age
                    or dependent.inventory >= inventory_capacity
                    or not (
                        dependent.guardian_id == agent_id
                        or agent_id in (dependent.parents or ())
                    )
                ):
                    continue
                need = max(
                    1.0 - dependent.energy / maximum_energy,
                    0.0,
                )
                append_option((
                    care_weight * need
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
                    Action(
                        ActionKind.CARE,
                        agent_id,
                        target_id=dependent.id,
                    ),
                ))

        if agent.knows_seafaring:
            teaching_weight = config.teaching_weight
            generosity = self._temperament(agent, "generosity")
            for learner in living_neighbors:
                if learner.knows_seafaring:
                    continue
                preference, _ = relationship_bonus(learner)
                append_option((
                    teaching_weight
                    * generosity
                    * self._temperament(learner, "curiosity")
                    + preference
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
                    Action(
                        ActionKind.TEACH,
                        agent_id,
                        target_id=learner.id,
                    ),
                ))

        if agent.energy >= config.communication_energy_cost:
            communication_scale = (
                config.communication_weight * agent.traits.affiliation
            )
            for neighbor in living_neighbors:
                _, confidence = relationship_bonus(neighbor)
                append_option((
                    communication_scale
                    * (0.25 + 0.75 * (1.0 - confidence))
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
                    Action(
                        ActionKind.COMMUNICATE,
                        agent_id,
                        target_id=neighbor.id,
                    ),
                ))

        if (
            agent.knows_seafaring
            and agent.vessel_durability <= 0.0
            and agent.material_inventory >= config.vessel_material_cost
            and agent.energy >= config.vessel_energy_cost
            and not self.world.is_sea(agent.x, agent.y)
        ):
            options.append(
                (
                    config.vessel_build_weight
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
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
                    * capability
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
                    Action(ActionKind.RESEARCH, agent.id),
                )
            )

        if agent.vessel_durability > 0.0:
            if self.world.is_sea(agent.x, agent.y):
                voyage = self._voyage_destination(agent, rng)
                if voyage != (agent.x, agent.y):
                    options.append(
                        (
                            config.voyage_weight
                            + (random_value() * 2.0 - 1.0)
                            * noise_amplitude,
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
                            + (random_value() * 2.0 - 1.0)
                            * noise_amplitude,
                            Action(
                                ActionKind.MOVE,
                                agent.id,
                                destination=destination,
                            ),
                        )
                    )

        can_reproduce = self._can_reproduce(agent)
        partners = (
            [
                neighbor
                for neighbor in living_neighbors
                if self._can_reproduce(neighbor)
                and self._compatible_for_reproduction(agent, neighbor)
                and not self._closely_related(agent, neighbor)
            ]
            if can_reproduce
            else []
        )
        if partners:
            surplus_energy = (
                agent.energy - config.reproduction_energy
            ) / max(
                config.maximum_energy - config.reproduction_energy,
                1.0,
            )
            for partner in partners:
                preference, _ = relationship_bonus(partner)
                partner_condition = (
                    partner.body_condition
                    + partner.health
                    / max(self._health_capacity(partner), 1e-12)
                ) / 2.0
                reproduction_utility = (
                    config.reproduction_weight
                    * agent.traits.fertility
                    * max(surplus_energy, 0.0)
                    * (0.5 + 0.5 * partner_condition)
                    + preference
                )
                options.append((
                    reproduction_utility
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
                    Action(
                        ActionKind.REPRODUCE,
                        agent.id,
                        target_id=partner.id,
                    ),
                ))

        # Avoid the most expensive perception query when movement cannot beat
        # an action already available to the agent.
        movement_upper_bound = (
            config.movement_weight + config.decision_noise
        )
        if agent.traits.brain_kind is BrainKind.HABITUAL:
            movement_upper_bound += (
                config.habit_preference_weight
                * config.learned_preference_limit
            )
        elif agent.traits.brain_kind is BrainKind.SOCIAL:
            movement_upper_bound += (
                config.social_imitation_weight
                * (0.5 + agent.traits.affiliation)
                * self._temperament(agent, "conformity")
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
                    movement_utility
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
                    Action(
                        ActionKind.MOVE,
                        agent.id,
                        destination=destination,
                    ),
                )
            )

        social_weights = {}
        for neighbor in living_neighbors:
            view = relationship_views.get(neighbor.id)
            if view is None:
                social_weights[neighbor.id] = 0.05
                continue
            confidence = view.encounters / (view.encounters + 3.0)
            social_weights[neighbor.id] = (
                0.05
                + 0.95
                * confidence
                * max(0.0, (1.0 + view.trust) / 2.0)
            )

        return choose_action(
            options,
            agent,
            living_neighbors,
            rng,
            config,
            social_weights=social_weights,
            current_tick=self.tick,
        )

    def _decision_rng(self, agent_id: int) -> random.Random:
        return random.Random(self._mixed_seed(agent_id, 0xD3C1))

    def _mixed_seed(self, agent_id: int, channel: int) -> int:
        value = (
            (self.seed & 0xFFFFFFFFFFFFFFFF)
            ^ (self.tick * 0x9E3779B97F4A7C15)
            ^ (agent_id * 0xBF58476D1CE4E5B9)
            ^ (channel * 0xD6E8FEB86659FD93)
        ) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 30
        value = (value * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 27
        value = (value * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 31
        return value

    def _stable_uniform(self, agent_id: int, channel: int) -> float:
        value = self._mixed_seed(agent_id, channel)
        return (value >> 11) * (1.0 / (1 << 53))

    def _pair_rng(
        self,
        first_id: int,
        second_id: int,
        channel: int,
    ) -> random.Random:
        lower, upper = sorted((first_id, second_id))
        pair_id = (
            lower * 0x9E3779B1
            ^ upper * 0x85EBCA77
        ) & 0xFFFFFFFFFFFFFFFF
        return random.Random(self._mixed_seed(pair_id, channel))

    def _age_fecundity(self, agent: Agent) -> float:
        config = self.config
        age = agent.age
        maturity = agent.traits.maturity_age
        peak_age = (
            maturity
            + config.fecundity_maturation_ramp_years
        )
        if agent.reproductive_role is ReproductiveRole.OVA:
            decline_age = config.ova_fecundity_decline_age
            end_age = config.ova_reproductive_end_age
        else:
            decline_age = config.sperm_fecundity_decline_age
            end_age = config.sperm_reproductive_end_age
        if age <= maturity or age >= end_age:
            return 0.0
        if age < peak_age:
            rise_position = (age - maturity) / (peak_age - maturity)
            rise = (
                rise_position
                * rise_position
                * (3.0 - 2.0 * rise_position)
            )
        else:
            rise = 1.0
        if age <= decline_age:
            return rise
        decline_position = (
            (age - decline_age) / (end_age - decline_age)
        )
        decline = 1.0 - (
            decline_position
            * decline_position
            * (3.0 - 2.0 * decline_position)
        )
        return rise * decline

    def _can_reproduce(self, agent: Agent) -> bool:
        config = self.config
        if (
            agent.energy < config.reproduction_energy
            or agent.body_condition
            < config.minimum_reproductive_body_condition
            or self.tick < agent.next_reproduction_tick
            or (
                agent.reproductive_role is ReproductiveRole.OVA
                and agent.id in self.pregnancies
            )
        ):
            return False
        if (
            agent.health / max(self._health_capacity(agent), 1e-12)
            < config.minimum_reproductive_health_fraction
        ):
            return False
        return self._age_fecundity(agent) > 0.0

    @staticmethod
    def _compatible_for_reproduction(first: Agent, second: Agent) -> bool:
        return (
            first.id != second.id
            and first.reproductive_role is not second.reproductive_role
        )

    def _resolve(self, actions: Iterable[Action]) -> None:
        action_list = list(actions)
        counts: Counter[str] = Counter()
        attempts: Counter[str] = Counter(
            action.kind.value for action in action_list
        )
        failures: Counter[str] = Counter()
        reproduced = set()
        reproduction_actions = {
            action.actor_id: action
            for action in action_list
            if (
                action.kind is ActionKind.REPRODUCE
                and action.target_id is not None
            )
        }
        candidate_pairs = {
            tuple(sorted((actor_id, action.target_id)))
            for actor_id, action in reproduction_actions.items()
            if (
                action.target_id in reproduction_actions
                and action.target_id != actor_id
            )
        }
        ordered_pairs = sorted(
            candidate_pairs,
            key=lambda pair: (
                self._pair_rng(
                    pair[0],
                    pair[1],
                    0xA11,
                ).random(),
                -pair[0],
                -pair[1],
            ),
            reverse=True,
        )
        reproduction_results: Dict[int, bool] = {
            actor_id: False for actor_id in reproduction_actions
        }
        reproduction_partners: Dict[int, int] = {}
        reproduction_welfare_before: Dict[int, float] = {}
        reproduction_welfare_change: Dict[int, float] = {}
        for first_id, second_id in ordered_pairs:
            if first_id in reproduced or second_id in reproduced:
                continue
            first = self.agents.get(first_id)
            second = self.agents.get(second_id)
            if first is None or second is None:
                continue
            reproduction_welfare_before[first_id] = self._welfare(first)
            reproduction_welfare_before[second_id] = self._welfare(second)
            applied = self._reproduce(
                first,
                second_id,
                reproduced,
            )
            reproduction_results[first_id] = applied
            reproduction_results[second_id] = applied
            reproduction_welfare_change[first_id] = (
                self._welfare(first)
                - reproduction_welfare_before[first_id]
            )
            reproduction_welfare_change[second_id] = (
                self._welfare(second)
                - reproduction_welfare_before[second_id]
            )
            if first_id in reproduced and second_id in reproduced:
                reproduction_partners[first_id] = second_id
                reproduction_partners[second_id] = first_id

        for action in action_list:
            agent = self.agents.get(action.actor_id)
            if agent is None:
                continue

            welfare_before = (
                reproduction_welfare_before[agent.id]
                if agent.id in reproduction_welfare_before
                else self._welfare(agent)
            )
            applied = False
            learned_action = action
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
            elif action.kind is ActionKind.COMMUNICATE:
                applied = self._communicate(agent, action.target_id)
            elif action.kind is ActionKind.RESEARCH:
                applied = self._research(agent)
            elif action.kind is ActionKind.TEACH:
                applied = self._teach(agent, action.target_id)
            elif action.kind is ActionKind.BUILD_VESSEL:
                applied = self._build_vessel(agent)
            elif action.kind is ActionKind.REPRODUCE:
                applied = reproduction_results.get(agent.id, False)
                partner_id = reproduction_partners.get(agent.id)
                if partner_id is not None:
                    learned_action = Action(
                        ActionKind.REPRODUCE,
                        agent.id,
                        target_id=partner_id,
                    )
            elif action.kind is ActionKind.MOVE:
                if action.destination is not None:
                    applied = self._move(agent, action.destination)
            else:
                applied = True

            if applied:
                welfare_change = (
                    reproduction_welfare_change.get(agent.id, 0.0)
                    if action.kind is ActionKind.REPRODUCE
                    else self._welfare(agent) - welfare_before
                )
                reward = (
                    self.config.successful_action_reward
                    + welfare_change / self.config.maximum_energy
                    + self._intrinsic_reward(agent, learned_action)
                )
            else:
                reward = self.config.failed_action_reward
            agent.brain.learn(
                learned_action,
                reward,
                agent.traits.learning_rate,
                multiplier=1.0,
                limit=self.config.learned_preference_limit,
                tick=self.tick,
                success=applied,
            )
            if applied:
                counts[action.kind.value] += 1
            else:
                failures[action.kind.value] += 1

        self._last_action_counts = counts
        self._last_action_attempts = attempts
        self._last_action_failures = failures

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
        self._last_food_consumed += amount
        agent.energy = min(
            self.config.maximum_energy,
            agent.energy + amount * self.config.food_energy,
        )
        return True

    def _gather(self, agent: Agent) -> bool:
        capability = self._capability(agent)
        developed_capacity = (
            1.0
            - self.config.development_harvest_influence
            + self.config.development_harvest_influence
            * agent.development_index
        )
        requested = min(
            self.config.harvest_amount
            * agent.traits.harvest_skill
            * capability
            * developed_capacity,
            self.config.inventory_capacity - agent.inventory,
        )
        amount = self.world.harvest(agent.x, agent.y, requested)
        agent.inventory += amount
        return amount > 0.0

    def _gather_material(self, agent: Agent) -> bool:
        capability = self._capability(agent)
        developed_capacity = (
            1.0
            - self.config.development_harvest_influence
            + self.config.development_harvest_influence
            * agent.development_index
        )
        requested = min(
            self.config.material_harvest_amount
            * agent.traits.harvest_skill
            * capability
            * developed_capacity,
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
        dependents = [
            self.agents[dependent_id]
            for dependent_id in sorted(
                self.dependents_by_guardian.get(agent.id, ())
            )
            if (
                dependent_id in self.agents
                and self.agents[dependent_id].age
                < self.config.dependent_age
                and (self.agents[dependent_id].x, self.agents[dependent_id].y)
                == (agent.x, agent.y)
            )
        ]
        if current_is_sea or destination_is_sea:
            if agent.vessel_durability <= 0.0:
                return False
            if len(dependents) > self.config.vessel_passenger_capacity:
                return False
            cost += self.config.sea_movement_cost
        cost += (
            len(dependents)
            * self.config.dependent_movement_energy_cost
        )
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
        for dependent in dependents:
            dependent.x, dependent.y = destination
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
            or agent.energy < config.research_energy_minimum
            or agent.energy < config.research_energy_cost
        ):
            return False
        agent.material_inventory -= config.research_material_cost
        self._last_material_consumed += config.research_material_cost
        agent.energy -= config.research_energy_cost
        agent.research_progress += (
            self._temperament(agent, "curiosity")
            * self._temperament(agent, "exploration")
            * (
                config.research_gain_minimum
                + (
                    config.research_gain_maximum
                    - config.research_gain_minimum
                )
                * self._stable_uniform(agent.id, 0xE51)
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
        self._record_social_benefit(agent, target, 0.5)
        self._transmit_culture(
            agent,
            target,
            dimensions=("curiosity",),
            allow_belief=True,
            channel=0x7EA,
            signal_values={"curiosity": 1.0},
        )
        self._record(
            Event(self.tick, "teach_seafaring", (agent.id, target.id))
        )
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
        self._last_material_consumed += config.vessel_material_cost
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
        self._record_social_benefit(
            agent,
            target,
            amount * self.config.food_energy / self.config.maximum_energy,
        )
        self._transmit_culture(
            agent,
            target,
            dimensions=("generosity",),
            allow_belief=False,
            channel=0x5A2,
            signal_values={"generosity": 1.0},
        )
        self._record(Event(self.tick, "share", (agent.id, target.id)))
        return True

    def _care(self, agent: Agent, target_id: Optional[int]) -> bool:
        if target_id is None:
            return False
        target = self.agents.get(target_id)
        if (
            target is None
            or not (
                target.guardian_id == agent.id
                or agent.id in (target.parents or ())
            )
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
        self._record_social_benefit(
            agent,
            target,
            amount * self.config.food_energy / self.config.maximum_energy,
        )
        self._transmit_culture(
            agent,
            target,
            dimensions=("generosity",),
            allow_belief=False,
            channel=0xCA2,
            signal_values={"generosity": 1.0},
        )
        self._record(Event(self.tick, "care", (agent.id, target.id)))
        return True

    def _communicate(
        self,
        agent: Agent,
        target_id: Optional[int],
    ) -> bool:
        if target_id is None:
            return False
        target = self.agents.get(target_id)
        if (
            target is None
            or target.id == agent.id
            or not self._are_local(agent, target)
            or agent.energy < self.config.communication_energy_cost
        ):
            return False
        agent.energy -= self.config.communication_energy_cost
        self.relationships.observe(
            agent.relationship_slot,
            target.id,
            self.tick,
        )
        self.relationships.observe(
            target.relationship_slot,
            agent.id,
            self.tick,
        )
        dimensions = (
            "generosity",
            "exploration",
            "curiosity",
            "conformity",
        )
        signal_index = int(
            self._stable_uniform(
                agent.id ^ (target.id << 1),
                0xC01,
            )
            * len(dimensions)
        )
        self._transmit_culture(
            agent,
            target,
            dimensions=(dimensions[min(signal_index, len(dimensions) - 1)],),
            allow_belief=True,
            channel=0xC02,
        )
        self._record(Event(
            self.tick,
            "communicate",
            (agent.id, target.id),
        ))
        return True

    def _record_social_benefit(
        self,
        source: Agent,
        target: Agent,
        normalized_benefit: float,
    ) -> None:
        benefit = max(normalized_benefit, 0.0)
        self.relationships.record_given(
            source.relationship_slot,
            target.id,
            benefit,
            self.tick,
        )
        self.relationships.record_received(
            target.relationship_slot,
            source.id,
            benefit,
            self.tick,
            self.config.relationship_learning_rate,
        )

    def _transmit_culture(
        self,
        source: Agent,
        target: Agent,
        dimensions: Tuple[str, ...],
        allow_belief: bool,
        channel: int,
        signal_values: Optional[Dict[str, float]] = None,
    ) -> None:
        relationship = self.relationships.view(
            target.relationship_slot,
            source.id,
            self.tick,
        )
        confidence = (
            relationship.encounters / (relationship.encounters + 3.0)
            if relationship is not None
            else 0.0
        )
        trust = relationship.trust if relationship is not None else 0.0
        probability = (
            self.config.cultural_transmission_rate
            * self._temperament(target, "conformity")
            * target.traits.learning_rate
            / max(self.config.maximum_learning_rate, 1e-12)
            * (0.10 + 0.90 * confidence * max(trust, 0.0))
        )
        rng = self._pair_rng(source.id, target.id, channel)
        if (
            allow_belief
            and source.belief_id != target.belief_id
            and rng.random() < probability
        ):
            target.belief_id = source.belief_id
        values = {
            "generosity": target.culture.generosity,
            "exploration": target.culture.exploration,
            "curiosity": target.culture.curiosity,
            "conformity": target.culture.conformity,
        }
        for name in dimensions:
            observed_value = (
                signal_values[name]
                if signal_values is not None and name in signal_values
                else getattr(source.culture, name)
            )
            values[name] = _blend(
                values[name],
                observed_value,
                probability,
            )
        target.culture = CultureState(**values)

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

        first_condition = agent.health / max(
            self._health_capacity(agent),
            1e-12,
        )
        second_condition = partner.health / max(
            self._health_capacity(partner),
            1e-12,
        )
        first_development = (
            1.0
            - self.config.development_fertility_influence
            + self.config.development_fertility_influence
            * agent.development_index
        )
        second_development = (
            1.0
            - self.config.development_fertility_influence
            + self.config.development_fertility_influence
            * partner.development_index
        )
        probability = min(
            1.0,
            self.config.maximum_conception_probability
            * math.sqrt(
                agent.traits.fertility * partner.traits.fertility
            )
            * first_condition
            * second_condition
            * self._age_fecundity(agent)
            * self._age_fecundity(partner)
            * agent.body_condition
            * partner.body_condition
            * first_development
            * second_development,
        )
        pair_rng = self._pair_rng(agent.id, partner.id, 0xB17)
        if pair_rng.random() >= probability:
            return False

        agent.energy -= self.config.reproduction_cost
        partner.energy -= self.config.reproduction_cost
        agent.last_reproduction_tick = self.tick
        partner.last_reproduction_tick = self.tick
        cooldown_ticks = max(
            1,
            round(
                self.config.reproduction_cooldown_years
                * self.config.ticks_per_year
            ),
        )
        agent.next_reproduction_tick = self.tick + cooldown_ticks
        partner.next_reproduction_tick = self.tick + cooldown_ticks
        genome = Genome.recombine(
            agent.genome,
            partner.genome,
            pair_rng,
            self.config.gene_mutation_probability,
            self.config.gene_crossover_probability,
        )
        culture = self._inherit_culture(
            agent.culture,
            partner.culture,
            pair_rng,
        )
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
            reproductive_role=pair_rng.choice(tuple(ReproductiveRole)),
            belief_id=pair_rng.choice(
                (agent.belief_id, partner.belief_id)
            ),
            generation=max(agent.generation, partner.generation) + 1,
            conception_tick=self.tick,
            due_tick=self.tick + gestation_ticks,
            grandparent_ids=tuple(sorted(set(
                (agent.parents or ()) + (partner.parents or ())
            )))[:4],
            prenatal_condition=gestational_parent.body_condition,
            prenatal_exposure_years=0.0,
            invested_energy=2.0 * self.config.reproduction_cost,
        )
        self.pregnancies[gestational_parent.id] = pregnancy
        self.total_conceptions += 1
        self.relationships.observe(
            agent.relationship_slot,
            partner.id,
            self.tick,
        )
        self.relationships.observe(
            partner.relationship_slot,
            agent.id,
            self.tick,
        )
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
        for parent_id, pregnancy in sorted(self.pregnancies.items()):
            gestational_parent = self.agents.get(parent_id)
            if gestational_parent is None:
                continue
            health_fraction = (
                gestational_parent.health
                / max(self._health_capacity(gestational_parent), 1e-12)
            )
            elapsed_years = 1.0 / self.config.ticks_per_year
            total_exposure = (
                pregnancy.prenatal_exposure_years + elapsed_years
            )
            pregnancy.prenatal_condition = (
                pregnancy.prenatal_condition
                * pregnancy.prenatal_exposure_years
                + gestational_parent.body_condition * elapsed_years
            ) / total_exposure
            pregnancy.prenatal_exposure_years = total_exposure
            loss_hazard = (
                self.config.pregnancy_loss_base_rate_per_year
                + self.config.pregnancy_loss_condition_rate_per_year
                * (
                    (1.0 - gestational_parent.body_condition) ** 2
                    + (1.0 - health_fraction) ** 2
                )
            )
            stochastic_loss = (
                self._stable_uniform(parent_id, 0x1055)
                < annual_hazard_to_tick(
                    loss_hazard,
                    1.0 / self.config.ticks_per_year,
                )
            )
            if (
                health_fraction
                < self.config.minimum_gestation_health_fraction
                or stochastic_loss
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
        birth_investment = min(
            gestational_parent.energy,
            config.birth_energy_cost,
        )
        gestational_parent.energy -= birth_investment
        pregnancy.invested_energy += birth_investment
        gestational_parent.health -= config.birth_health_cost
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
        development = _clamp(pregnancy.prenatal_condition)
        health_capacity = effective_health_capacity(
            traits.maximum_health,
            development,
            0.0,
            config.minimum_development_health_fraction,
            config.frailty_health_capacity_loss,
        )
        child = Agent(
            id=self._claim_agent_id(),
            x=gestational_parent.x,
            y=gestational_parent.y,
            age=0.0,
            energy=min(config.newborn_energy, pregnancy.invested_energy),
            health=health_capacity,
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
            guardian_id=None,
            grandparent_ids=pregnancy.grandparent_ids,
            body_condition=development,
            development_index=development,
            development_exposure_years=(
                pregnancy.prenatal_exposure_years
            ),
            relationship_slot=self.relationships.allocate(),
        )
        vertically_infected = False
        if (
            gestational_parent.infection_stage
            is InfectionStage.INFECTIOUS
            and self._stable_uniform(child.id, 0xB0A)
            < config.vertical_transmission_probability
        ):
            child.infection_stage = InfectionStage.EXPOSED
            child.infection_ticks_remaining = duration_ticks(
                config.disease_incubation_years,
                config.ticks_per_year,
            )
            self.total_infections += 1
            vertically_infected = True
        elif gestational_parent.infection_stage in (
            InfectionStage.INFECTIOUS,
            InfectionStage.RECOVERED,
        ):
            child.infection_stage = InfectionStage.RECOVERED
            child.infection_ticks_remaining = duration_ticks(
                config.maternal_immunity_years,
                config.ticks_per_year,
                0.75 + 0.50 * gestational_parent.traits.immune_strength,
            )
        self.agents[child.id] = child
        self._set_guardian(child, pregnancy.gestational_parent_id)
        for parent_id in child.parents:
            parent = self.agents.get(parent_id)
            if parent is None:
                continue
            self.relationships.observe(
                child.relationship_slot,
                parent.id,
                self.tick,
            )
            self.relationships.observe(
                parent.relationship_slot,
                child.id,
                self.tick,
            )
        gestational_parent.next_reproduction_tick = max(
            gestational_parent.next_reproduction_tick,
            self.tick + max(
                1,
                round(
                    config.postpartum_cooldown_years
                    * config.ticks_per_year
                ),
            ),
        )
        self.total_births += 1
        self._record(
            Event(
                self.tick,
                "birth",
                (*child.parents, child.id),
                (("generation", float(child.generation)),),
            )
        )
        if vertically_infected:
            self._record(Event(
                self.tick,
                "vertical_infection",
                (gestational_parent.id, child.id),
            ))
        if gestational_parent.health <= 0.0:
            self._remove_agent(
                gestational_parent.id,
                cause="childbirth",
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
        first_parents = set(first.parents or ())
        second_parents = set(second.parents or ())
        first_grandparents = set(first.grandparent_ids)
        second_grandparents = set(second.grandparent_ids)
        first_ancestors = first_parents | first_grandparents
        second_ancestors = second_parents | second_grandparents
        if second.id in first_ancestors:
            return True
        if first.id in second_ancestors:
            return True
        return bool(
            first_parents.intersection(second_parents)
            or first_grandparents.intersection(second_grandparents)
            or first_parents.intersection(second_grandparents)
            or second_parents.intersection(first_grandparents)
        )

    def _inherit_culture(
        self,
        first: CultureState,
        second: CultureState,
        rng: random.Random,
    ) -> CultureState:
        noise = self.config.cultural_inheritance_noise

        def inherit(left: float, right: float) -> float:
            return _clamp(
                (left + right) / 2.0 + rng.gauss(0.0, noise)
            )

        return CultureState(
            generosity=inherit(first.generosity, second.generosity),
            exploration=inherit(first.exploration, second.exploration),
            curiosity=inherit(first.curiosity, second.curiosity),
            conformity=inherit(first.conformity, second.conformity),
        )

    def _set_guardian(
        self,
        child: Agent,
        guardian_id: Optional[int],
    ) -> None:
        previous_id = child.guardian_id
        if previous_id == guardian_id:
            return
        if previous_id is not None:
            previous_dependents = self.dependents_by_guardian.get(
                previous_id
            )
            if previous_dependents is not None:
                previous_dependents.discard(child.id)
                if not previous_dependents:
                    self.dependents_by_guardian.pop(previous_id, None)
        if (
            guardian_id is None
            or guardian_id not in self.agents
            or guardian_id == child.id
            or child.age >= self.config.dependent_age
        ):
            child.guardian_id = None
            return
        child.guardian_id = guardian_id
        self.dependents_by_guardian.setdefault(
            guardian_id,
            set(),
        ).add(child.id)

    def _remove_agent(
        self,
        agent_id: int,
        cause: str = "unknown",
    ) -> None:
        agent = self.agents.pop(agent_id, None)
        if agent is None:
            return
        self._last_food_lost_on_death += agent.inventory
        self._last_material_lost_on_death += agent.material_inventory
        if agent.guardian_id is not None:
            guardian_dependents = self.dependents_by_guardian.get(
                agent.guardian_id
            )
            if guardian_dependents is not None:
                guardian_dependents.discard(agent_id)
                if not guardian_dependents:
                    self.dependents_by_guardian.pop(
                        agent.guardian_id,
                        None,
                    )
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
        dependent_ids = tuple(
            self.dependents_by_guardian.pop(agent_id, ())
        )
        for child_id in dependent_ids:
            child = self.agents.get(child_id)
            if child is None:
                continue
            child.guardian_id = None
            alternative = next(
                (
                    parent_id
                    for parent_id in child.parents or ()
                    if parent_id != agent_id and parent_id in self.agents
                ),
                None,
            )
            self._set_guardian(child, alternative)
        if self.relationships.row_is_active(agent.relationship_slot):
            self.relationships.release(agent.relationship_slot)
        self.total_deaths += 1
        self.deaths_by_cause[cause] += 1
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


def _blend(current: float, observed: float, rate: float) -> float:
    return _clamp(current + rate * (observed - current))


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
