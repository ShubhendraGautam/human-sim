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

from .brain import BrainState, Surroundings, choose_action
from . import artifacts as artifact_module
from . import fauna as fauna_module
from . import language
from . import neural
from .config import SimulationConfig
from .entities import EntityKind, EntityRegistry
from .exposure import exposure_energy_cost
from . import knowledge
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
from .memory import PlaceMemory
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
    DeathRecord,
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
        # BUILD_ARTIFACT is appended to the action enum. A disabled run keeps
        # the previous output width, so adding the mechanism does not add a
        # neural weight, a founder RNG draw, or a lifetime preference.
        self._action_outputs = (
            len(ActionKind)
            if self.config.artifacts_enabled
            else len(ActionKind) - 1
        )
        # Built once and handed to the two brain factories. None is the off
        # switch, and with it every brain is issued at full size at birth
        # exactly as it was before brains could grow.
        self._growth_rules = (
            neural.GrowthRules(
                birth_units=self.config.neural_birth_units,
                minimum_ceiling=self.config.neural_minimum_ceiling,
                maximum_ceiling=self.config.neural_maximum_ceiling,
                minimum_rate=self.config.neural_minimum_growth_rate,
                maximum_rate=self.config.neural_maximum_growth_rate,
                ceiling_mutation_rate=(
                    self.config.neural_ceiling_mutation_rate
                ),
                rate_mutation_scale=(
                    self.config.neural_growth_rate_mutation_scale
                ),
            )
            if self.config.neural_growth_enabled
            else None
        )
        self.scenario = scenario or Scenario.default(self.config)
        self.scenario.validate(self.config)
        self.world = World(self.config, self.rng, self.scenario)
        # Everything that occupies the world shares one identity space. People
        # are simply the only kind registered so far; `agents` is the
        # registry's own person store rather than a second copy of it, so the
        # two cannot drift apart. Registration and removal go through the
        # registry; see EntityRegistry.of_kind.
        self.entities = EntityRegistry()
        self.agents: Dict[int, Agent] = self.entities.of_kind(
            EntityKind.PERSON
        )
        # Animals live in the same identity space and the same spatial index
        # as people. The herd owns their behaviour; nothing in it knows that
        # people exist.
        self.herd = fauna_module.Herd(
            self.config,
            self.world,
            self.entities,
            self._stable_uniform,
        )
        self.fauna: Dict[int, fauna_module.Animal] = self.entities.of_kind(
            EntityKind.FAUNA
        )
        self.artifacts: Dict[int, artifact_module.Artifact] = (
            self.entities.of_kind(EntityKind.ARTIFACT)
        )
        self.total_artifacts_built = 0
        self.total_artifacts_decayed = 0
        self.total_artifact_maintenance = 0
        self._artifacts_built_this_tick: Dict[
            int,
            artifact_module.Artifact,
        ] = {}
        self.total_hunts = 0
        self.total_hunt_kills = 0
        self._last_meat_gained = 0.0
        self.tick = 0
        self.total_births = 0
        self.total_conceptions = 0
        self.total_deaths = 0
        self.total_pregnancy_losses = 0
        self.total_inventions = 0
        self.total_sea_crossings = 0
        self.total_infections = 0
        self.total_coinages = 0
        self.total_recoveries = 0
        self._last_food_consumed = 0.0
        self._last_food_spoiled = 0.0
        self._last_food_lost_on_death = 0.0
        self._last_material_consumed = 0.0
        self._last_material_lost_on_death = 0.0
        self._last_environmental_energy_cost = 0.0
        self._last_food_lost_on_artifact_decay = 0.0
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
        # The recently dead, newest last. Bounded like the event log: a long
        # run answers for its recent dead and forgets the rest.
        self.deaths: Dict[int, DeathRecord] = {}
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
        # Seeded after people so that adding animals does not shift the
        # random stream the founding population was drawn from.
        self.herd.seed(self.rng)
        self.world.rebuild_spatial_index(self.entities.placed())
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
        self._last_meat_gained = 0.0
        self._last_environmental_energy_cost = 0.0
        self._last_food_lost_on_artifact_decay = 0.0
        self._artifacts_built_this_tick.clear()
        self._advance_artifacts()
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
        # Voyages resolve before anyone decides anything: a hull that failed
        # this tick has already put its crew ashore or in the water.
        self._advance_voyages()

        self.world.rebuild_spatial_index(self.entities.placed())
        # Animals eat, move and breed before anyone decides anything, so a
        # hunter is choosing against the herd as it actually stands rather
        # than where it was last tick.
        self.herd.advance(self.tick)
        self.world.rebuild_spatial_index(self.entities.placed())
        # Bonds are maintained after the index is current, so proximity is
        # judged on where everyone actually is this tick.
        self._advance_bonds()
        # Deaths and births changed the population, so the decision phase
        # needs a fresh ordering rather than the one shared above.
        actions = [
            self._decide(agent, self._decision_rng(agent.id))
            for agent in self._ordered_agents()
        ]
        self.rng.shuffle(actions)
        self._resolve(actions)
        self.world.regenerate(self.tick)
        self.world.rebuild_spatial_index(self.entities.placed())
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

    def checkpoint(self) -> Dict[str, object]:
        """Return versioned JSON causal state that can resume exactly."""

        from .checkpoint import export_checkpoint

        return export_checkpoint(self)

    @classmethod
    def from_checkpoint(
        cls,
        payload: Dict[str, object],
        event_sink: Optional[EventSink] = None,
        metrics_sink: Optional[MetricsSink] = None,
    ) -> "Simulation":
        """Restore a run from :meth:`checkpoint`."""

        from .checkpoint import restore_checkpoint

        return restore_checkpoint(
            payload,
            event_sink=event_sink,
            metrics_sink=metrics_sink,
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
        agent_id = self._claim_agent_id()
        recurrent_rng = (
            random.Random(self._mixed_seed(agent_id, 0xB4A1))
            if (
                config.neural_brains_enabled
                and config.neural_recurrence_weight != 0.0
            )
            else None
        )
        network = neural.founder_network(
            self.rng,
            config.neural_hidden_units,
            len(ActionKind) - 1,
            config.neural_founder_scale
            if config.neural_brains_enabled
            else 0.0,
            self._growth_rules,
            recurrent_rng,
        )
        if config.artifacts_enabled:
            neural.append_output(
                network,
                random.Random(self._mixed_seed(agent_id, 0xA471)),
                config.neural_founder_scale
                if config.neural_brains_enabled
                else 0.0,
            )
        agent = Agent(
            id=agent_id,
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
            brain=BrainState(
                preferences=array("f", [0.0]) * self._action_outputs,
            ),
            lexicon=language.Lexicon(),
            network=network,
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
        self.entities.register(agent)
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
        return self.entities.claim_id()

    def _scan_exposures(
        self,
        ordered_agents: Sequence[Agent],
        pressure: Optional[Sequence[float]],
        elapsed_years: float,
    ) -> List[int]:
        """Return IDs newly exposed, by local contact or from outside.

        Two doors lead into a susceptible population. Local pressure is the
        modelled one: it needs someone infectious nearby, and it is what makes
        an epidemic an epidemic.

        The other is the environment, standing in for every reservoir this
        model does not yet contain — water, soil, and the animals that are not
        on the canvas. It matters because without it an outbreak that ends,
        ends forever: infection can only ever leave the population, never
        re-enter it, and a founding seed that fizzles at low density leaves a
        world that can never be sick again. The hazard is per person, so
        contact with that reservoir grows with the population rather than
        being handed out as a fixed quota.

        Setting the rate to zero restores exactly the earlier behavior,
        including the draws, which is what makes runs across the change
        comparable when that is what an experiment needs.
        """

        config = self.config
        transmission_rate = config.disease_transmission_rate_per_year
        environmental = (
            annual_hazard_to_tick(
                config.environmental_exposure_rate_per_year,
                elapsed_years,
            )
            if config.environmental_exposure_rate_per_year > 0.0
            else 0.0
        )
        cell_index = self.world.cell_index
        newly_exposed: List[int] = []
        for agent in ordered_agents:
            if agent.infection_stage is not InfectionStage.SUSCEPTIBLE:
                continue
            local_pressure = (
                0.0
                if pressure is None
                else pressure[cell_index(agent.x, agent.y)]
            )
            if local_pressure <= 0.0 and environmental <= 0.0:
                continue
            susceptibility = host_susceptibility(
                agent.age,
                agent.traits.maturity_age,
                agent.traits.immune_strength,
                agent.body_condition,
                agent.frailty,
            )
            probability = (
                transmission_probability(
                    transmission_rate,
                    local_pressure,
                    susceptibility,
                    elapsed_years,
                )
                if local_pressure > 0.0
                else 0.0
            )
            if environmental > 0.0:
                # Independent doors, so the survivor of one still faces the
                # other rather than the larger hazard simply replacing it.
                probability = 1.0 - (1.0 - probability) * (
                    1.0 - environmental * susceptibility
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
        # With nobody infectious the pressure grid is uniformly zero, so it is
        # never allocated. The scan itself still runs whenever the environment
        # can expose someone, since that door does not need a neighbour.
        pressure = None
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
        if pressure is not None or (
            config.environmental_exposure_rate_per_year > 0.0
        ):
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
        brain_upkeep = config.neural_maintenance_cost * tick_scale
        exposure_cost = config.environmental_energy_cost_per_year
        growing = self._growth_rules is not None
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

            # Season used to decide only what grew. It now also costs a body
            # standing in the local extreme: both sides of the annual midpoint
            # require thermoregulation. The formula accepts insulation as a
            # physical input so artifacts can reduce this cost later without
            # either module learning a label such as "house".
            #
            # The guard is the exact off switch. At zero no season lookup,
            # helper call, subtraction, or extra random draw occurs, so old
            # digests remain byte-for-byte reproducible.
            if exposure_cost > 0.0:
                requested = exposure_energy_cost(
                    self.world.season_at(agent.y),
                    exposure_cost,
                    elapsed_years,
                    self._insulation_at(agent.x, agent.y),
                )
                paid = min(requested, agent.energy)
                agent.energy -= paid
                self._last_environmental_energy_cost += paid

            # A brain built over a life rather than issued at birth. The
            # units come online as the person ages, at a rate they inherited,
            # up to a ceiling they inherited. Nothing is chosen here: how
            # fast and how far are both weights in the lineage, and what
            # decides between them is whether their carriers had children.
            if growing:
                network = agent.network
                if network.active < network.units:
                    network.grow_to(
                        config.neural_birth_units
                        + int(agent.age * network.growth_rate)
                    )

            # What the brain costs to keep. Charged on the inherited weights
            # only: what a person was born with is the thing selection can
            # act on, and what they learned within their life already pays
            # its own price at the moment of learning.
            #
            # Guarded rather than multiplied by zero so that a run with the
            # cost off does exactly the arithmetic it did before this
            # existed, down to the last bit.
            if brain_upkeep > 0.0:
                agent.energy = max(
                    0.0,
                    agent.energy - brain_upkeep * agent.network.magnitude,
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
            # Starvation is not an event that starts at zero energy. A body
            # that has been running short is already losing condition, and
            # the damage scales with how far below its needs it has been
            # rather than switching on the moment the last unit is spent.
            # Without the ramp there is no feedback until a population is
            # already doomed: everyone crosses zero within the same few
            # ticks and the crash overshoots to extinction instead of
            # settling at what the land can actually feed.
            nutrition = min(
                agent.body_condition,
                agent.energy / config.maximum_energy,
            )
            shortfall = 0.0
            if agent.energy <= 0.0:
                # Nothing left at all is the full penalty however the ramp
                # is configured. At threshold zero this is the only case
                # that fires, which is exactly the old cliff.
                shortfall = 1.0
            elif nutrition < config.malnutrition_threshold:
                shortfall = (
                    (config.malnutrition_threshold - nutrition)
                    / config.malnutrition_threshold
                )
            if shortfall > 0.0:
                starvation_damage = (
                    config.starvation_damage
                    * tick_scale
                    * shortfall
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
        local_artifacts = self._artifacts_at(agent.x, agent.y)
        stored_food = sum(item.food_stored for item in local_artifacts)
        storage_room = sum(item.storage_room for item in local_artifacts)
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

        # Looked up once here, before anything branches, so that a hunter, a
        # forager and a child all perceive the same world. A brain that saw
        # different senses depending on which options happened to be open to
        # it could not learn anything stable about any of them.
        quarry = (
            self._nearest_quarry(agent) if config.fauna_enabled else None
        )
        remembered = self._remembered_place(agent)
        surroundings = Surroundings(
            food_here=resource_fraction,
            food_nearby=self.world.food_gradient(agent.x, agent.y),
            material_here=min(
                1.0,
                current_material / max(config.material_cell_capacity, 1e-9),
            ),
            season=self.world.season_at(agent.y),
            animal_near=quarry is not None,
            on_coast=self.world.is_coast(agent.x, agent.y),
            remembered_place=(
                0.0 if remembered is None
                else max(0.0, remembered[1] - resource_fraction)
            ),
        )

        options: List[Tuple[float, Action]] = [
            (
                config.rest_utility
                + (random_value() * 2.0 - 1.0) * noise_amplitude,
                Action(ActionKind.REST, agent.id),
            )
        ]

        if (
            (agent.inventory > 0.0 or stored_food > 0.0)
            and agent.energy < config.maximum_energy
        ):
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
                surroundings=surroundings,
            )

        if (
            current_resource > 0.0
            and (
                agent.inventory < config.inventory_capacity
                or storage_room > 0.0
            )
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

        # An animal within reach is worth considering against the ground
        # underfoot. Nothing prefers meat here: the option is weighed on the
        # same scale as gathering, it costs energy whether or not it lands,
        # and a wary animal is a worse bet than a placid one. Which of the
        # two a population lives on is therefore an outcome.
        if (
            agent.inventory < config.inventory_capacity
            and agent.energy > config.hunt_energy_cost
        ):
            if quarry is not None:
                chance = fauna_module.catch_probability(
                    quarry,
                    physical_capacity
                    * knowledge.hunt_multiplier(agent.known_techniques),
                    config,
                )
                expected = (
                    chance
                    * min(
                        fauna_module.meat_yield(quarry, config),
                        config.inventory_capacity - agent.inventory,
                    )
                    / max(config.inventory_capacity, 1e-9)
                )
                options.append(
                    (
                        config.hunt_weight * expected
                        + (random_value() * 2.0 - 1.0) * noise_amplitude,
                        Action(
                            ActionKind.HUNT,
                            agent.id,
                            target_id=quarry.id,
                        ),
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

        if agent.known_techniques:
            teaching_weight = config.teaching_weight
            generosity = self._temperament(agent, "generosity")
            for learner in living_neighbors:
                if not agent.known_techniques & ~learner.known_techniques:
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
            knowledge.opens_water(agent.known_techniques)
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
            config.artifacts_enabled
            and (
                not local_artifacts
                or any(item.durability < 1.0 for item in local_artifacts)
            )
            and agent.material_inventory
            >= (
                config.artifact_maintenance_material_cost
                if local_artifacts
                else config.artifact_material_cost
            )
            and agent.energy
            >= (
                config.artifact_maintenance_energy_cost
                if local_artifacts
                else config.artifact_energy_cost
            )
            and not self.world.is_sea(agent.x, agent.y)
        ):
            insulation = self._insulation_at(agent.x, agent.y)
            exposure_need = abs(surroundings.season) * (1.0 - insulation)
            storage_need = (
                1.0
                if not local_artifacts
                else max(
                    0.0,
                    1.0
                    - sum(item.food_stored for item in local_artifacts)
                    / max(
                        sum(
                            item.storage_capacity
                            for item in local_artifacts
                        ),
                        1e-9,
                    ),
                )
            )
            repair_need = max(
                (1.0 - item.durability for item in local_artifacts),
                default=0.0,
            )
            utility = config.artifact_build_weight * (
                exposure_need
                + config.artifact_storage_weight * storage_need
                + repair_need
            )
            options.append((
                utility
                + (random_value() * 2.0 - 1.0) * noise_amplitude,
                Action(ActionKind.BUILD_ARTIFACT, agent.id),
            ))

        # Anything worth working out here, rather than one named thing at
        # one named kind of place.
        if (
            agent.material_inventory >= config.research_material_cost
            and agent.energy >= config.research_energy_minimum
            and knowledge.discoverable(
                agent.known_techniques,
                self._affordances(agent, quarry=quarry),
            )
            is not None
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

        # Courtship precedes reproduction. It is offered only to the unbonded,
        # and unlike REPRODUCE it does not require the target to have chosen a
        # matching action, so a couple pays the cost of finding each other once
        # rather than once per child.
        if (
            agent.partner_id is None
            and agent.energy >= config.courtship_energy_cost
            and self._age_fecundity(agent) > 0.0
        ):
            courtship_weight = config.courtship_weight
            affiliation = agent.traits.affiliation
            for candidate in living_neighbors:
                if not self._can_court(agent, candidate):
                    continue
                preference, _ = relationship_bonus(candidate)
                candidate_condition = (
                    candidate.body_condition
                    + candidate.health
                    / max(self._health_capacity(candidate), 1e-12)
                ) / 2.0
                append_option((
                    courtship_weight
                    * affiliation
                    * (0.5 + 0.5 * candidate_condition)
                    + preference
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
                    Action(
                        ActionKind.COURT,
                        agent_id,
                        target_id=candidate.id,
                    ),
                ))

        can_reproduce = self._can_reproduce(agent)
        partners = (
            [
                neighbor
                for neighbor in living_neighbors
                if self._can_reproduce(neighbor)
                and self._compatible_for_reproduction(agent, neighbor)
                and not self._closely_related(agent, neighbor)
                and self._reproductively_available(agent, neighbor)
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

        # Somewhere this person has actually been and found worth something.
        # This is the only option in the whole decision that is not a
        # response to what is currently within sight — everything else is a
        # reaction to the present cell and its neighbours. Being able to go
        # back to a place you remember is the difference between foraging
        # and rolling downhill.
        if remembered is not None and config.place_return_weight > 0.0:
            remembered_cell, remembered_quality = remembered
            target_x, target_y = self.world.coordinates(remembered_cell)
            step = self._step_toward_cell(agent, target_x, target_y)
            if step != (agent.x, agent.y):
                append_option((
                    config.place_return_weight
                    * max(remembered_quality - resource_fraction, 0.0)
                    + (random_value() * 2.0 - 1.0) * noise_amplitude,
                    Action(
                        ActionKind.MOVE,
                        agent_id,
                        destination=step,
                    ),
                ))

        # A bond is only useful when the couple is together: measured without
        # this, partners drifted to a median of four cells apart and were
        # adjacent barely a tenth of the time, so bonded reproduction could
        # almost never fire. Reuniting is a preference, not a teleport.
        partner_id = agent.partner_id
        if partner_id is not None:
            partner = self.agents.get(partner_id)
            if partner is not None and not self._are_local(agent, partner):
                step = self._step_toward(agent, partner)
                if step != (agent.x, agent.y):
                    separation = max(
                        abs(agent.x - partner.x),
                        abs(agent.y - partner.y),
                    )
                    append_option((
                        config.bond_movement_weight
                        * agent.traits.affiliation
                        * min(separation / 4.0, 1.0)
                        + (random_value() * 2.0 - 1.0) * noise_amplitude,
                        Action(
                            ActionKind.MOVE,
                            agent_id,
                            destination=step,
                        ),
                    ))

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
            surroundings=surroundings,
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

    @staticmethod
    def _reproductively_available(agent: Agent, other: Agent) -> bool:
        """Enforce bond exclusivity in both directions.

        A bonded agent reproduces only with its partner; an unbonded agent
        cannot reproduce with someone else's partner.
        """
        if agent.partner_id is not None:
            return other.id == agent.partner_id
        return other.partner_id is None

    def _can_court(self, agent: Agent, candidate: Agent) -> bool:
        """Whether ``agent`` may propose a pair bond to ``candidate``.

        Deliberately looser than :meth:`_can_reproduce`: an agent on a
        reproductive cooldown or short of energy for a child may still form a
        bond. Only lasting impediments disqualify a couple.
        """
        return (
            agent.partner_id is None
            and candidate.partner_id is None
            and self._compatible_for_reproduction(agent, candidate)
            and not self._closely_related(agent, candidate)
            and self._age_fecundity(candidate) > 0.0
        )

    def _advance_bonds(self) -> None:
        """Refresh or end existing bonds.

        A bond is not a contract that survives anything. Couples who stay
        together keep it current; couples separated for long enough, or whose
        remembered trust has soured, part.

        Each bond is visited once, from the lower ID, so dissolving one cannot
        disturb the iteration for its partner.
        """
        config = self.config
        separation_limit = round(
            config.bond_separation_years * config.ticks_per_year
        )
        dissolution_trust = config.bond_dissolution_trust
        tick = self.tick
        for agent in self._ordered_agents():
            partner_id = agent.partner_id
            if partner_id is None or partner_id < agent.id:
                continue
            partner = self.agents.get(partner_id)
            if partner is None or partner.partner_id != agent.id:
                self._dissolve_bond(agent, "bond_ended_death")
                continue
            if self._are_local(agent, partner):
                agent.bond_last_together_tick = tick
                partner.bond_last_together_tick = tick
                continue
            if tick - agent.bond_last_together_tick > separation_limit:
                self._dissolve_bond(agent, "bond_ended_separation")
                continue
            view = self.relationships.view(
                agent.relationship_slot,
                partner_id,
                tick,
            )
            if view is not None and view.trust < dissolution_trust:
                self._dissolve_bond(agent, "bond_ended_distrust")

    def _resolve_courtships(
        self,
        action_list: Sequence[Action],
    ) -> Dict[int, bool]:
        """Form pair bonds from one-sided proposals, with consent.

        Unlike reproduction, the target need not have chosen a matching action.
        Acceptance is a deterministic draw weighted by how well the pair
        already knows one another, so removing the double coincidence does not
        make bonding indiscriminate.

        Several agents may court the same target in one tick. Proposals are
        ordered by the same seeded key used for reproduction pairing and taken
        greedily, so contention resolves reproducibly.
        """
        proposals = [
            action
            for action in action_list
            if action.kind is ActionKind.COURT and action.target_id is not None
        ]
        if not proposals:
            return {}

        ordered = sorted(
            proposals,
            key=lambda action: (
                self._pair_rng(
                    action.actor_id,
                    action.target_id,
                    0xC0F,
                ).random(),
                -action.actor_id,
                -action.target_id,
            ),
            reverse=True,
        )
        config = self.config
        results: Dict[int, bool] = {
            action.actor_id: False for action in proposals
        }
        for action in ordered:
            suitor = self.agents.get(action.actor_id)
            candidate = self.agents.get(action.target_id)
            if suitor is None or candidate is None:
                continue
            if not self._can_court(suitor, candidate):
                continue
            if not self._are_local(suitor, candidate):
                continue
            if suitor.energy < config.courtship_energy_cost:
                continue
            suitor.energy -= config.courtship_energy_cost

            # Familiarity raises the chance of acceptance without ever
            # guaranteeing or forbidding it.
            view = self.relationships.view(
                candidate.relationship_slot,
                suitor.id,
                self.tick,
            )
            familiarity = 0.0
            if view is not None:
                encounters = view.encounters
                familiarity = (
                    encounters / (encounters + 3.0)
                ) * max(view.trust, 0.0)
            acceptance = config.bond_acceptance_base * (
                0.5 + 0.5 * candidate.traits.affiliation
            ) * (1.0 + familiarity)
            draw = self._pair_rng(suitor.id, candidate.id, 0xB0D).random()
            if draw >= min(acceptance, 1.0):
                continue

            self._bind_pair(suitor, candidate)
            results[action.actor_id] = True
        return results

    def _bind_pair(self, first: Agent, second: Agent) -> None:
        """Create the symmetric bond and seed mutual acquaintance."""
        first.partner_id = second.id
        second.partner_id = first.id
        first.bond_since_tick = self.tick
        second.bond_since_tick = self.tick
        first.bond_last_together_tick = self.tick
        second.bond_last_together_tick = self.tick
        self.relationships.observe(
            first.relationship_slot,
            second.id,
            self.tick,
        )
        self.relationships.observe(
            second.relationship_slot,
            first.id,
            self.tick,
        )
        self._record(
            Event(self.tick, "bond_formed", (first.id, second.id))
        )

    def _dissolve_bond(self, agent: Agent, kind: str) -> None:
        """Clear a bond from both sides.

        Safe when the partner is already gone, so death cleanup and the
        maintenance rules can share one path. ``kind`` is the event name, which
        records why the bond ended.
        """
        partner_id = agent.partner_id
        agent.partner_id = None
        agent.bond_since_tick = -1
        agent.bond_last_together_tick = -1
        if partner_id is None:
            return
        partner = self.agents.get(partner_id)
        if partner is not None and partner.partner_id == agent.id:
            partner.partner_id = None
            partner.bond_since_tick = -1
            partner.bond_last_together_tick = -1
        self._record(Event(self.tick, kind, (agent.id, partner_id)))

    def _resolve(self, actions: Iterable[Action]) -> None:
        config = self.config
        action_list = list(actions)
        counts: Counter[str] = Counter()
        attempts: Counter[str] = Counter(
            action.kind.value for action in action_list
        )
        failures: Counter[str] = Counter()
        courtship_results = self._resolve_courtships(action_list)
        reproduced = set()
        reproduction_actions = {
            action.actor_id: action
            for action in action_list
            if (
                action.kind is ActionKind.REPRODUCE
                and action.target_id is not None
            )
        }
        # An established couple reproduces on one-sided intent: they have
        # already found each other, so requiring them to choose the same action
        # in the same tick again is what suppressed fertility. Everyone else
        # still needs reciprocal intent.
        candidate_pairs = set()
        for actor_id, action in reproduction_actions.items():
            target_id = action.target_id
            if target_id == actor_id:
                continue
            actor = self.agents.get(actor_id)
            target = self.agents.get(target_id)
            if actor is None or target is None:
                continue
            bonded = (
                actor.partner_id == target_id
                and target.partner_id == actor_id
            )
            if bonded or target_id in reproduction_actions:
                candidate_pairs.add(tuple(sorted((actor_id, target_id))))
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
            elif action.kind is ActionKind.HUNT:
                applied = self._hunt(agent, action.target_id)
            elif action.kind is ActionKind.SHARE:
                applied = self._share(agent, action.target_id)
            elif action.kind is ActionKind.CARE:
                applied = self._care(agent, action.target_id)
            elif action.kind is ActionKind.COMMUNICATE:
                applied = self._communicate(agent, action.target_id)
            elif action.kind is ActionKind.COURT:
                # Already settled in _resolve_courtships, which had to run
                # before reproduction so a new bond is usable this tick.
                applied = courtship_results.get(agent.id, False)
            elif action.kind is ActionKind.RESEARCH:
                applied = self._research(agent)
            elif action.kind is ActionKind.TEACH:
                applied = self._teach(agent, action.target_id)
            elif action.kind is ActionKind.BUILD_VESSEL:
                applied = self._build_vessel(agent)
            elif action.kind is ActionKind.BUILD_ARTIFACT:
                applied = self._build_or_maintain_artifact(agent)
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
            # The same outcome that moves the flat habit vector also moves
            # the network's output layer, but credited to the hidden units
            # that were active when the choice was made. That is what makes
            # it a policy — "this action, in circumstances like these" —
            # rather than the context-free "I like gathering" the habit
            # vector can express. What is learned is never inherited: the
            # overlay lives on BrainState and dies with the person.
            if (
                config.neural_brains_enabled
                and config.plasticity_rate > 0.0
                and agent.energy > config.plasticity_energy_cost
            ):
                # Inherited learning rate enters as a proportion of the
                # fastest learner rather than as a raw multiplier. Used
                # directly it is a number around 0.1, which quietly divided
                # the configured rate by ten and made plasticity a rounding
                # error rather than a mechanism.
                aptitude = (
                    agent.traits.learning_rate
                    / max(config.maximum_learning_rate, 1e-9)
                )
                # How much better this went than this action usually goes,
                # not how well it went. Reinforcing the raw outcome sounds
                # equivalent and is not: almost every action returns
                # something, so raw reward drives every frequently-taken
                # action upward and the brain ends up entrenching whatever
                # it already did most. Measured, that arm was worse than
                # having no brain at all. Subtracting the running average
                # the habit vector already keeps turns it back into
                # learning: beat your own expectation and the disposition
                # moves toward it, fall short and it moves away.
                changed = agent.brain.adapt(
                    learned_action,
                    reward - agent.brain.preference(learned_action),
                    config.plasticity_rate * aptitude,
                    config.plasticity_limit,
                    agent.network.units,
                )
                if changed:
                    # Changing your own mind is not free, or everyone would
                    # do it constantly and it would stop being a trade.
                    agent.energy -= config.plasticity_energy_cost
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
        energy_room = (
            self.config.maximum_energy - agent.energy
        ) / self.config.food_energy
        amount = min(self.config.eat_amount, max(energy_room, 0.0))
        if amount <= 0.0:
            return False
        from_inventory = min(agent.inventory, amount)
        agent.inventory -= from_inventory
        consumed = from_inventory
        remaining = amount - from_inventory
        if remaining > 0.0:
            for artifact in self._artifacts_at(agent.x, agent.y):
                taken = artifact.take_food(remaining)
                consumed += taken
                remaining -= taken
                if remaining <= 0.0:
                    break
        if consumed <= 0.0:
            return False
        self._last_food_consumed += consumed
        agent.energy = min(
            self.config.maximum_energy,
            agent.energy + consumed * self.config.food_energy,
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
        personal_room = self.config.inventory_capacity - agent.inventory
        storage_room = sum(
            artifact.storage_room
            for artifact in self._artifacts_at(agent.x, agent.y)
        )
        requested = min(
            self.config.harvest_amount
            * agent.traits.harvest_skill
            * capability
            * developed_capacity
            * knowledge.harvest_multiplier(agent.known_techniques),
            personal_room + storage_room,
        )
        amount = self.world.harvest(agent.x, agent.y, requested)
        held = min(amount, personal_room)
        agent.inventory += held
        remaining = amount - held
        if remaining > 0.0:
            for artifact in self._artifacts_at(agent.x, agent.y):
                stored = artifact.store(remaining)
                remaining -= stored
                if remaining <= 0.0:
                    break
        if amount > 0.0:
            # What this place was worth, judged by how full it still is
            # rather than by what was taken: a rich cell stays worth coming
            # back to, a cell scraped bare does not.
            self._remember_place(
                agent,
                self.world.food_fraction(agent.x, agent.y),
            )
        elif agent.places is not None:
            # Arrived and found nothing. A memory that has stopped being
            # true stops being acted on.
            cell = self.world.try_cell_index(agent.x, agent.y)
            if cell is not None:
                agent.places.forget(cell)
        return amount > 0.0

    def _remembered_place(
        self,
        agent: Agent,
    ) -> Optional[Tuple[int, float]]:
        """The best place this person still believes in, if any."""

        memory = agent.places
        if memory is None or not memory.places:
            return None
        here = self.world.try_cell_index(agent.x, agent.y)
        return memory.best(
            self.tick,
            self.config.place_memory_half_life_years
            * self.config.ticks_per_year,
            exclude_cell=here,
        )

    def _remember_place(self, agent: Agent, quality: float) -> None:
        """Record that this cell paid out, so it can be returned to.

        Only ever called from somewhere the agent is actually standing and
        has actually taken something from, so a memory is experience rather
        than a readout of the map.
        """

        capacity = self.config.place_memory_capacity
        if capacity <= 0 or quality <= 0.0:
            return
        cell = self.world.try_cell_index(agent.x, agent.y)
        if cell is None:
            return
        if agent.places is None:
            agent.places = PlaceMemory()
        agent.places.remember(cell, quality, self.tick, capacity)

    def _artifacts_at(
        self,
        x: int,
        y: int,
    ) -> Tuple["artifact_module.Artifact", ...]:
        """Live inert objects in this cell, in identity order."""

        if not self.artifacts:
            return ()
        cell = self.world.try_cell_index(x, y)
        if cell is None:
            return ()
        ids = self.world.occupants_of_kind(EntityKind.ARTIFACT).get(cell, ())
        return tuple(
            artifact
            for entity_id in ids
            if (artifact := self.artifacts.get(entity_id)) is not None
        )

    def _insulation_at(self, x: int, y: int) -> float:
        artifacts = self._artifacts_at(x, y)
        if not artifacts:
            return 0.0
        cell = self.world.cell_index(x, y)
        occupants = len(
            self.world.occupants_of_kind(EntityKind.PERSON).get(cell, ())
        )
        return artifact_module.effective_insulation(artifacts, occupants)

    def _advance_artifacts(self) -> None:
        """Decay inert objects and spoil the food physically held in them."""

        if not self.artifacts:
            return
        elapsed_years = 1.0 / self.config.ticks_per_year
        retention = math.exp(
            -self.config.food_spoilage_rate_per_year * elapsed_years
        )
        decay = self.config.artifact_decay_rate_per_year * elapsed_years
        # Registration is monotonic by entity id, so dict insertion order is
        # already identity order. Deregistration never disturbs the survivors.
        for artifact in tuple(self.artifacts.values()):
            if artifact.food_stored > 0.0:
                before = artifact.food_stored
                artifact.food_stored *= retention
                self._last_food_spoiled += before - artifact.food_stored
            if decay <= 0.0:
                continue
            artifact.durability = max(0.0, artifact.durability - decay)
            if artifact.durability > 0.0:
                continue
            self._last_food_lost_on_artifact_decay += artifact.food_stored
            self.entities.deregister(artifact.id)
            self.total_artifacts_decayed += 1
            self._record(Event(
                self.tick,
                "artifact_decayed",
                (artifact.id,),
            ))

    def _nearest_quarry(
        self,
        agent: Agent,
    ) -> Optional["fauna_module.Animal"]:
        """The animal this person could try for, if any.

        Bounded exactly like every other kind of local perception: the cells
        within the interaction radius, and the lowest id in the first cell
        that has one. Animals live in their own bucket of the spatial index,
        so looking for one never walks past a crowd of people.
        """

        if not self.fauna:
            return None
        occupants = self.world.occupants_of_kind(EntityKind.FAUNA)
        if not occupants:
            return None
        for cell in self.world.nearby_cell_indices(
            agent.x,
            agent.y,
            self.config.interaction_radius,
        ):
            for entity_id in occupants.get(cell, ()):
                animal = self.fauna.get(entity_id)
                if animal is not None:
                    return animal
        return None

    def _hunt(self, agent: Agent, target_id: Optional[int]) -> bool:
        """Try for an animal. Pay either way.

        The cost is spent before the outcome is known, which is what makes
        hunting a gamble rather than a better kind of gathering. A failed
        attempt leaves the animal alive and the hunter poorer, and that is
        the only thing stopping a herd from being a free larder.
        """

        config = self.config
        if target_id is None or agent.energy <= config.hunt_energy_cost:
            return False
        animal = self.fauna.get(target_id)
        if animal is None or not self._within_reach(agent, animal):
            return False
        agent.energy -= config.hunt_energy_cost
        self.total_hunts += 1
        chance = fauna_module.catch_probability(
            animal,
            self._capability(agent)
            * knowledge.hunt_multiplier(agent.known_techniques),
            config,
        )
        if (
            self._stable_uniform(agent.id ^ (animal.id << 1), 0xF100)
            >= chance
        ):
            self._record(Event(
                self.tick,
                "hunt_failed",
                (agent.id, animal.id),
            ))
            return False
        meat = min(
            fauna_module.meat_yield(animal, config),
            config.inventory_capacity - agent.inventory,
        )
        self.herd.remove(animal.id, hunted=True)
        agent.inventory += meat
        self._last_meat_gained += meat
        self.total_hunt_kills += 1
        self._record(Event(
            self.tick,
            "hunt_killed",
            (agent.id, animal.id),
            (("meat", meat),),
        ))
        return meat > 0.0

    def _within_reach(
        self,
        agent: Agent,
        animal: "fauna_module.Animal",
    ) -> bool:
        radius = self.config.interaction_radius
        if self.config.wrap_world:
            width = self.config.width
            height = self.config.height
            dx = min(
                (agent.x - animal.x) % width,
                (animal.x - agent.x) % width,
            )
            dy = min(
                (agent.y - animal.y) % height,
                (animal.y - agent.y) % height,
            )
        else:
            dx = abs(agent.x - animal.x)
            dy = abs(agent.y - animal.y)
        return dx <= radius and dy <= radius

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

    def _advance_voyages(self) -> None:
        """Wear vessels at sea and resolve what happens when one fails.

        Time at sea consumes a vessel, not distance: a hull sitting on open
        water is as exposed as one being rowed, so nobody can wait out a
        voyage indefinitely. When a vessel finally fails, its crew is in the
        water and the geography decides. A coast within reach can be waded
        to at a cost; open water cannot, and drowning is the outcome.

        Passengers are carried by whoever holds the working vessel, so a
        dependent riding along neither drowns beside an intact hull nor
        survives one that has just broken up.
        """

        if not self.world.has_sea:
            return
        wear = self.config.sea_vessel_wear_per_tick
        resolved: set[int] = set()
        drowned: List[int] = []
        for agent in self._ordered_agents():
            if agent.id in resolved:
                continue
            if not self.world.is_sea(agent.x, agent.y):
                continue
            if agent.vessel_durability > 0.0:
                agent.vessel_durability = max(
                    0.0,
                    agent.vessel_durability - wear,
                )
            if self._has_passage(agent):
                continue
            party = [agent]
            party.extend(
                dependent
                for dependent in self._passengers(agent)
                if dependent.id not in resolved
            )
            shore = self._shore_within_reach(agent)
            for member in party:
                resolved.add(member.id)
                if shore is None:
                    drowned.append(member.id)
                    continue
                member.x, member.y = shore
                member.voyage_dx = 0
                member.voyage_dy = 0
                member.energy = max(
                    0.0,
                    member.energy - self.config.sea_movement_cost,
                )
            if shore is not None:
                self._record(
                    Event(
                        self.tick,
                        "wrecked_ashore",
                        tuple(member.id for member in party),
                    )
                )
        for agent_id in drowned:
            self._record(Event(self.tick, "drowned", (agent_id,)))
            self._remove_agent(agent_id, cause="drowned")

    def _has_passage(self, agent: Agent) -> bool:
        """Whether the sea is survivable for this person right now."""

        if agent.vessel_durability > 0.0:
            return True
        guardian_id = agent.guardian_id
        if guardian_id is None:
            return False
        guardian = self.agents.get(guardian_id)
        return (
            guardian is not None
            and guardian.vessel_durability > 0.0
            and (guardian.x, guardian.y) == (agent.x, agent.y)
        )

    def _passengers(self, agent: Agent) -> List[Agent]:
        """Dependents sharing this cell, who ride on this person's vessel."""

        passengers = []
        for dependent_id in sorted(
            self.dependents_by_guardian.get(agent.id, ())
        ):
            dependent = self.agents.get(dependent_id)
            if (
                dependent is not None
                and (dependent.x, dependent.y) == (agent.x, agent.y)
            ):
                passengers.append(dependent)
        return passengers

    def _shore_within_reach(
        self,
        agent: Agent,
    ) -> Optional[Tuple[int, int]]:
        for offset_x, offset_y in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            destination = self.world.normalize(
                agent.x + offset_x,
                agent.y + offset_y,
            )
            if destination is not None and not self.world.is_sea(*destination):
                return destination
        return None

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

    def _affordances(
        self,
        agent: Agent,
        quarry: Optional["fauna_module.Animal"] = None,
    ) -> int:
        """What the place this person is standing in makes thinkable.

        This is the whole of the grounding: a problem has to be in front of
        someone before they can work on it. Nobody works out how to cross
        water inland, or how to track animals in an empty valley.
        """

        available = 0
        if self.world.is_coast(agent.x, agent.y):
            available |= 1 << knowledge.Affordance.COAST
        if (
            agent.material_inventory > 0.0
            or self.world.material_at(agent.x, agent.y) > 0.0
        ):
            available |= 1 << knowledge.Affordance.MATERIALS
        if self.config.fauna_enabled and (
            quarry is not None or self._nearest_quarry(agent)
        ):
            available |= 1 << knowledge.Affordance.FAUNA
        return available

    def _research(self, agent: Agent) -> bool:
        """Work at whatever problem this place poses.

        Nothing in here names a technique. The circumstance decides what is
        available to work on, temperament decides how fast it goes, and the
        table in `knowledge` decides when it is done.
        """

        config = self.config
        if (
            agent.material_inventory < config.research_material_cost
            or agent.energy < config.research_energy_minimum
            or agent.energy < config.research_energy_cost
        ):
            return False
        technique = knowledge.discoverable(
            agent.known_techniques,
            self._affordances(agent),
        )
        if technique is None:
            return False
        agent.material_inventory -= config.research_material_cost
        self._last_material_consumed += config.research_material_cost
        agent.energy -= config.research_energy_cost
        if agent.technique_progress is None:
            agent.technique_progress = [0.0] * knowledge.TECHNIQUE_COUNT
        agent.technique_progress[technique.index] += (
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
        if (
            agent.technique_progress[technique.index]
            >= config.discovery_threshold * technique.effort
        ):
            agent.known_techniques = knowledge.with_technique(
                agent.known_techniques,
                technique,
            )
            self.total_inventions += 1
            self._record(Event(
                self.tick,
                "invent",
                (agent.id,),
                (("technique", float(technique.index)),),
            ))
        return True

    def _teach(self, agent: Agent, target_id: Optional[int]) -> bool:
        """Pass on the first thing this person has that the other lacks."""

        if target_id is None or not agent.known_techniques:
            return False
        target = self.agents.get(target_id)
        if (
            target is None
            or target.id == agent.id
            or not self._are_local(agent, target)
        ):
            return False
        technique = knowledge.teachable(
            agent.known_techniques,
            target.known_techniques,
        )
        if technique is None:
            return False
        target.known_techniques = knowledge.with_technique(
            target.known_techniques,
            technique,
        )
        self._record_social_benefit(agent, target, 0.5)
        self._transmit_culture(
            agent,
            target,
            dimensions=("curiosity",),
            allow_belief=True,
            channel=0x7EA,
            signal_values={"curiosity": 1.0},
        )
        self._record(Event(
            self.tick,
            "teach",
            (agent.id, target.id),
            (("technique", float(technique.index)),),
        ))
        return True

    def _build_vessel(self, agent: Agent) -> bool:
        config = self.config
        if (
            not knowledge.opens_water(agent.known_techniques)
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

    def _build_or_maintain_artifact(self, agent: Agent) -> bool:
        """Build here, or repair the most damaged local inert object."""

        config = self.config
        if not config.artifacts_enabled or self.world.is_sea(agent.x, agent.y):
            return False
        cell = self.world.cell_index(agent.x, agent.y)
        local = self._artifacts_at(agent.x, agent.y)
        # Resolution must see an object built earlier in this same action
        # phase; the spatial index is intentionally rebuilt only at phase
        # boundaries. One cell-local entry closes that gap without scanning
        # every object in the world for every attempted build.
        just_built = self._artifacts_built_this_tick.get(cell)
        if just_built is not None and just_built not in local:
            local = local + (just_built,)
        repairable = [
            artifact for artifact in local if artifact.durability < 1.0
        ]
        if repairable:
            target = min(
                repairable,
                key=lambda item: (item.durability, item.id),
            )
            if (
                agent.material_inventory
                < config.artifact_maintenance_material_cost
                or agent.energy < config.artifact_maintenance_energy_cost
            ):
                return False
            agent.material_inventory -= (
                config.artifact_maintenance_material_cost
            )
            self._last_material_consumed += (
                config.artifact_maintenance_material_cost
            )
            agent.energy -= config.artifact_maintenance_energy_cost
            target.durability = min(
                1.0,
                target.durability + config.artifact_maintenance_restore,
            )
            self.total_artifact_maintenance += 1
            self._record(Event(
                self.tick,
                "artifact_maintained",
                (agent.id, target.id),
            ))
            return True
        if local:
            return False
        if (
            agent.material_inventory < config.artifact_material_cost
            or agent.energy < config.artifact_energy_cost
        ):
            return False
        artifact = artifact_module.Artifact(
            id=self.entities.claim_id(),
            x=agent.x,
            y=agent.y,
            durability=1.0,
            insulation=config.artifact_insulation,
            storage_capacity=config.artifact_storage_capacity,
            occupancy_capacity=config.artifact_occupancy_capacity,
        )
        agent.material_inventory -= config.artifact_material_cost
        self._last_material_consumed += config.artifact_material_cost
        agent.energy -= config.artifact_energy_cost
        self.entities.register(artifact, created_by=agent.id)
        self._artifacts_built_this_tick[cell] = artifact
        self.total_artifacts_built += 1
        self._record(Event(
            self.tick,
            "artifact_built",
            (agent.id, artifact.id),
            (
                ("insulation", artifact.insulation),
                ("storage_capacity", artifact.storage_capacity),
                ("occupancy_capacity", float(artifact.occupancy_capacity)),
            ),
        ))
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
        # Handing food over is the act itself standing in front of both of
        # them, which is what lets a sound attach to it. Without a moment
        # like this the meaning is unreachable and no word for it can exist.
        if self.config.language_enabled:
            self._speak(agent, target, language.MEANING_INDEX["give"])
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
        # Feeding a child is the one interaction that reliably puts a
        # speaker and a listener in front of the same thing, repeatedly, for
        # years. Without it a language cannot outlive the people who coined
        # it: every child would start mute and invent its own forms, so
        # vocabulary would reset every generation no matter how well adults
        # agreed among themselves.
        if self.config.language_caregiver_transmission:
            self._speak(agent, target)
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
        spoken = self._speak(agent, target)
        self._record(Event(
            self.tick,
            "communicate",
            (agent.id, target.id),
            spoken,
        ))
        return True

    def _topic(self, agent: Agent, target: Agent) -> int:
        """What this person is in a position to talk about.

        A speaker refers to their own circumstances, so the topic is read off
        the situation rather than chosen freely: someone starving talks about
        hunger, someone at a shore about water, someone carrying a child
        about the child. This is what grounds a word — the listener can see
        the same thing, which is the only reason copying a sound can ever
        converge on a shared meaning.
        """

        config = self.config
        if agent.energy < config.maximum_energy * 0.25:
            return language.MEANING_INDEX["hunger"]
        if self.world.is_coast(agent.x, agent.y) or self.world.is_sea(
            agent.x,
            agent.y,
        ):
            return language.MEANING_INDEX["water"]
        if agent.infection_stage is InfectionStage.INFECTIOUS:
            return language.MEANING_INDEX["sickness"]
        if self.dependents_by_guardian.get(agent.id):
            return language.MEANING_INDEX["child"]
        if agent.partner_id is not None:
            return language.MEANING_INDEX["partner"]
        if agent.inventory > config.harvest_amount:
            return language.MEANING_INDEX["food"]
        if agent.material_inventory > 0.0:
            return language.MEANING_INDEX["stone"]
        if abs(agent.x - target.x) + abs(agent.y - target.y) > 1:
            return language.MEANING_INDEX["far"]
        return language.MEANING_INDEX["person"]

    def _speak(
        self,
        agent: Agent,
        target: Agent,
        situation: Optional[int] = None,
    ) -> Tuple[Tuple[str, float], ...]:
        """Say one thing, and let the listener make of it what they will.

        Nothing here checks whether a word is the "right" one. The speaker
        uses whatever form they hold, the listener copies it or does not, and
        agreement is whatever survives that process across a population.

        ``situation`` names what the speaker is visibly doing, for the cases
        where the act itself is the referent and both parties can see it. It
        is not a richer topic than the speaker's own circumstances, just a
        different way of being in the presence of one.
        """

        config = self.config
        if not config.language_enabled:
            return ()
        meaning = (
            self._topic(agent, target) if situation is None else situation
        )
        # Channels are spaced by the meaning count so that the draw for one
        # meaning can never collide with the draw for another purpose on a
        # neighbouring meaning, which silently correlated invention with
        # adoption while the ranges overlapped.
        span = len(language.MEANINGS)
        word = agent.lexicon.word_for(meaning)
        coined = False
        if word == language.NO_WORD:
            # Someone who has heard others name this has no reason to coin a
            # rival form; they have simply not picked it up yet.
            if agent.lexicon.exposed[meaning]:
                return ()
            if (
                self._stable_uniform(agent.id, 0xC100 + meaning)
                >= config.language_invention_rate
            ):
                return ()
            word = language.coin(
                self._stable_uniform(agent.id, 0xC100 + span + meaning),
                self._stable_uniform(agent.id, 0xC100 + 2 * span + meaning),
            )
            agent.lexicon.learn(
                meaning,
                word,
                config.language_initial_confidence,
            )
            coined = True
            self.total_coinages += 1

        heard = word
        # Willingness to take someone else's word for it is the same
        # disposition that carries any other cultural signal, so it leans on
        # conformity and how much the listener has to gain: a person with no
        # word at all adopts far more readily than one replacing their own.
        receptiveness = (
            target.traits.conformity * (1.0 - config.cultural_influence)
            + target.culture.conformity * config.cultural_influence
        )
        threshold = config.language_adoption_rate * (
            0.55 + 0.45 * receptiveness
        )
        if not target.lexicon.knows(meaning):
            threshold += (
                1.0 - threshold
            ) * config.language_naive_adoption_bonus
        # Being spoken to counts even when the word does not stick: it is
        # how the listener learns that this is a thing people have a sound
        # for, which is what stops them minting a rival one.
        target.lexicon.note_exposure(meaning)
        # Mixed with the speaker so that a listener does not either take
        # every word said to them this tick or none of them.
        listener_channel = target.id ^ (agent.id << 1)
        if (
            self._stable_uniform(listener_channel, 0xC100 + 3 * span + meaning)
            < threshold
        ):
            if (
                self._stable_uniform(
                    listener_channel,
                    0xC100 + 4 * span + meaning,
                )
                < config.language_mutation_rate
            ):
                heard = language.mutate(
                    word,
                    self._stable_uniform(
                        listener_channel,
                        0xC100 + 5 * span + meaning,
                    ),
                    self._stable_uniform(
                        listener_channel,
                        0xC100 + 6 * span + meaning,
                    ),
                )
            target.lexicon.hear(
                meaning,
                heard,
                config.language_initial_confidence,
            )

        return (
            ("meaning", float(meaning)),
            ("word", float(word)),
            ("coined", 1.0 if coined else 0.0),
        )

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
            or not self._reproductively_available(agent, partner)
            or not self._reproductively_available(partner, agent)
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
            # Skipped entirely when brains are off, because recombining
            # them would draw from the pair's generator and shift every
            # later decision in the run. An off switch that still perturbs
            # the random stream is not an off switch.
            network=(
                neural.inherit(
                    agent.network,
                    partner.network,
                    pair_rng,
                    self.config.neural_mutation_rate,
                    self.config.neural_mutation_scale,
                    self.config.neural_weight_limit,
                    self._growth_rules,
                    recurrent=(
                        self.config.neural_recurrence_weight != 0.0
                    ),
                )
                if self.config.neural_brains_enabled
                else neural.Network(
                    self.config.neural_hidden_units,
                    self._action_outputs,
                )
            ),
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
            brain=BrainState(
                preferences=array("f", [0.0]) * self._action_outputs,
            ),
            lexicon=language.Lexicon(),
            network=pregnancy.network,
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
        self.entities.register(child)
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

    def _axis_step(self, current: int, target: int, size: int) -> int:
        """Return -1, 0, or 1: the direction closing distance on one axis."""
        delta = target - current
        if delta == 0:
            return 0
        if self.config.wrap_world:
            if delta > size // 2:
                delta -= size
            elif delta < -(size // 2):
                delta += size
        return 1 if delta > 0 else -1

    def _step_toward_cell(
        self,
        agent: Agent,
        target_x: int,
        target_y: int,
    ) -> Tuple[int, int]:
        """One step toward a place rather than toward a person.

        Same single-step discipline as `_step_toward`: nothing here proposes
        a destination `_move` would refuse, so remembering somewhere never
        becomes a way of getting there faster than walking.
        """

        config = self.config
        step_x = agent.x + self._axis_step(agent.x, target_x, config.width)
        step_y = agent.y + self._axis_step(agent.y, target_y, config.height)
        if config.wrap_world:
            step_x %= config.width
            step_y %= config.height
        if (step_x, step_y) == (agent.x, agent.y):
            return (agent.x, agent.y)
        index = self.world.try_cell_index(step_x, step_y)
        if index is None:
            return (agent.x, agent.y)
        if (
            self.world.terrain[index] == Terrain.SEA
            and agent.vessel_durability <= 0.0
        ):
            return (agent.x, agent.y)
        return (step_x, step_y)

    def _step_toward(
        self,
        agent: Agent,
        target: Agent,
    ) -> Tuple[int, int]:
        """Return the adjacent cell closing distance, or the current cell.

        Movement resolution accepts a single step only, so this never proposes
        a destination that ``_move`` would reject as too far, off-world, or sea
        the agent cannot cross.
        """
        config = self.config
        step_x = agent.x + self._axis_step(agent.x, target.x, config.width)
        step_y = agent.y + self._axis_step(agent.y, target.y, config.height)
        if config.wrap_world:
            step_x %= config.width
            step_y %= config.height
        if (step_x, step_y) == (agent.x, agent.y):
            return (agent.x, agent.y)
        index = self.world.try_cell_index(step_x, step_y)
        if index is None:
            return (agent.x, agent.y)
        if (
            self.world.terrain[index] == Terrain.SEA
            and agent.vessel_durability <= 0.0
        ):
            return (agent.x, agent.y)
        return (step_x, step_y)

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
        agent = self.entities.deregister(agent_id)
        if agent is None:
            return
        self._last_food_lost_on_death += agent.inventory
        self._last_material_lost_on_death += agent.material_inventory
        # The bond is symmetric, so the survivor must be released here or
        # validate_state would find a dangling partner.
        if agent.partner_id is not None:
            self._dissolve_bond(agent, "bond_ended_death")
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
        # Recorded last, once every consequence of the death has been applied,
        # so the record holds the state the person actually died in.
        self._remember_death(agent, cause)
        self._record(
            Event(
                self.tick,
                "death",
                (agent_id,),
                (("age", agent.age),),
            )
        )

    def _remember_death(self, agent: Agent, cause: str) -> None:
        capacity = self.config.death_record_capacity
        if capacity <= 0:
            return
        self.deaths[agent.id] = DeathRecord(
            agent=agent,
            tick=self.tick,
            cause=cause,
        )
        while len(self.deaths) > capacity:
            # Insertion order is death order, so the oldest goes first.
            del self.deaths[next(iter(self.deaths))]

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
