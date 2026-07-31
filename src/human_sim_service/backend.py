"""Backend seam and reference adapter for the Python simulation engine."""

from dataclasses import asdict, dataclass
from typing import Dict, Mapping, Optional, Protocol, Tuple

from src.simulation import knowledge
from src.simulation import language
from src.simulation import (
    CHECKPOINT_SCHEMA_VERSION,
    CONFIG_SCHEMA_VERSION,
    GENOME_SCHEMA_VERSION,
    ActionKind,
    Scenario,
    Simulation,
    SimulationConfig,
    effective_health_capacity,
)
from src.simulation.engine import MODEL_VERSION, SNAPSHOT_SCHEMA_VERSION
from src.simulation.entities import EntityKind


@dataclass(frozen=True, slots=True)
class BackendManifest:
    seed: int
    tick: int
    year: float
    population: int
    model: Mapping[str, object]
    config: Mapping[str, object]
    scenario: Mapping[str, object]
    world: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class BackendFrame:
    tick: int
    year: float
    metrics: Mapping[str, object]
    agents: Mapping[str, object]
    # Animals are their own payload rather than more agent columns: they
    # are a different kind of thing and they come and go far faster.
    fauna: Mapping[str, object]
    artifacts: Mapping[str, object]
    resources: Optional[Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class BackendAgent:
    tick: int
    agent: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class BackendEvents:
    """A window onto the engine's bounded event log.

    The log keeps a fixed number of recent events, so a reader that stops
    asking for a while will miss some. ``oldest_retained_tick`` is what lets
    that reader notice rather than silently show a gap as continuity.
    """

    tick: int
    year: float
    events: Tuple[Mapping[str, object], ...]
    oldest_retained_tick: int
    dropped: bool


class SimulationBackend(Protocol):
    """Minimum interface a Python, native, or remote engine must implement."""

    def advance(self, ticks: int) -> None:
        """Advance causal state by exactly ``ticks`` simulation ticks."""

    def manifest(self) -> BackendManifest:
        """Return static world data plus current run metadata."""

    def frame(self, include_resources: bool = False) -> BackendFrame:
        """Return the current compact render projection."""

    def agent(self, agent_id: int) -> BackendAgent:
        """Return deep data for one living agent or raise ``KeyError``."""

    def events(self, since_tick: int = -1, limit: int = 200) -> BackendEvents:
        """Return recent events, newest first."""

    def export_snapshot(self) -> Dict[str, object]:
        """Return the backend's full visualization/export snapshot."""

    def export_checkpoint(self) -> Dict[str, object]:
        """Return complete causal state for deterministic resumption."""


class SimulationBackendFactory(Protocol):
    """Injectable constructor used by sessions and future engine backends."""

    def __call__(
        self,
        *,
        config: SimulationConfig,
        seed: int,
        scenario: Scenario,
    ) -> SimulationBackend:
        ...


class PythonSimulationBackend:
    """Adapter for the deterministic reference :class:`Simulation` engine."""

    def __init__(
        self,
        *,
        config: SimulationConfig,
        seed: int,
        scenario: Scenario,
    ) -> None:
        self._simulation = Simulation(
            config=config,
            seed=seed,
            scenario=scenario,
        )

    @classmethod
    def from_checkpoint(
        cls,
        payload: Mapping[str, object],
    ) -> "PythonSimulationBackend":
        backend = cls.__new__(cls)
        backend._simulation = Simulation.from_checkpoint(dict(payload))
        return backend

    def advance(self, ticks: int) -> None:
        for _ in range(ticks):
            self._simulation.step()

    def manifest(self) -> BackendManifest:
        simulation = self._simulation
        world = simulation.world
        return BackendManifest(
            seed=simulation.seed,
            tick=simulation.tick,
            year=simulation.year,
            population=len(simulation.agents),
            model={
                "model_version": MODEL_VERSION,
                "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
                "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
                "config_schema_version": CONFIG_SCHEMA_VERSION,
                "genome_schema_version": GENOME_SCHEMA_VERSION,
            },
            config=simulation.config.to_dict(),
            scenario=simulation.scenario.to_dict(),
            world={
                "width": simulation.config.width,
                "height": simulation.config.height,
                "wrap_world": simulation.config.wrap_world,
                "terrain": list(world.terrain),
                "country": list(world.country),
                "food_capacity": list(world.capacity),
                "food_productivity": list(world.productivity),
                "seasonal_amplitude": list(world.seasonal_amplitude),
                "seasonal_phase": list(world.seasonal_phase),
                "material_capacity": list(world.material_capacity),
                "material_productivity": list(
                    world.material_productivity
                ),
            },
        )

    def frame(self, include_resources: bool = False) -> BackendFrame:
        simulation = self._simulation
        config = simulation.config
        ordered = tuple(
            sorted(simulation.agents.values(), key=lambda item: item.id)
        )
        agents: Dict[str, object] = {
            "id": [str(agent.id) for agent in ordered],
            "x": [agent.x for agent in ordered],
            "y": [agent.y for agent in ordered],
            "birth_country": [
                agent.birth_country_id for agent in ordered
            ],
            "belief": [agent.belief_id for agent in ordered],
            "age": [agent.age for agent in ordered],
            "energy_fraction": [
                _fraction(agent.energy, config.maximum_energy)
                for agent in ordered
            ],
            "health_fraction": [
                _fraction(
                    agent.health,
                    _health_capacity(simulation, agent),
                )
                for agent in ordered
            ],
            "body_condition": [
                agent.body_condition for agent in ordered
            ],
            "frailty": [agent.frailty for agent in ordered],
            "brain_kind": [
                agent.traits.brain_kind.value for agent in ordered
            ],
            "last_action": [
                agent.brain.last_action for agent in ordered
            ],
            "last_action_success": [
                agent.brain.last_success for agent in ordered
            ],
            "infection_stage": [
                agent.infection_stage.name.lower() for agent in ordered
            ],
            "knows_seafaring": [
                agent.knows_seafaring for agent in ordered
            ],
            "known_techniques": [
                agent.known_techniques for agent in ordered
            ],
            "vessel_durability": [
                agent.vessel_durability for agent in ordered
            ],
        }
        herd = sorted(
            simulation.fauna.values(),
            key=lambda animal: animal.id,
        )
        fauna = {
            "id": [animal.id for animal in herd],
            "x": [animal.x for animal in herd],
            "y": [animal.y for animal in herd],
            "energy": [animal.energy for animal in herd],
            "vigilance": [animal.vigilance for animal in herd],
        }
        structures = sorted(
            simulation.artifacts.values(),
            key=lambda artifact: artifact.id,
        )
        person_cells = simulation.world.occupants_of_kind(EntityKind.PERSON)
        artifacts = {
            "id": [artifact.id for artifact in structures],
            "x": [artifact.x for artifact in structures],
            "y": [artifact.y for artifact in structures],
            "durability": [artifact.durability for artifact in structures],
            "insulation": [artifact.insulation for artifact in structures],
            "storage_capacity": [
                artifact.storage_capacity for artifact in structures
            ],
            "food_stored": [
                artifact.food_stored for artifact in structures
            ],
            "occupancy_capacity": [
                artifact.occupancy_capacity for artifact in structures
            ],
            "occupancy": [
                len(person_cells.get(
                    simulation.world.cell_index(artifact.x, artifact.y),
                    (),
                ))
                for artifact in structures
            ],
        }
        resources: Optional[Mapping[str, object]] = None
        if include_resources:
            resources = {
                "food": list(simulation.world.resources),
                "materials": list(simulation.world.materials),
            }
        return BackendFrame(
            tick=simulation.tick,
            year=simulation.year,
            metrics=_current_metrics(simulation),
            agents=agents,
            fauna=fauna,
            artifacts=artifacts,
            resources=resources,
        )

    def agent(self, agent_id: int) -> BackendAgent:
        simulation = self._simulation
        agent = simulation.agents.get(agent_id)
        death = None if agent is not None else simulation.deaths.get(agent_id)
        if agent is None:
            if death is None:
                raise KeyError(agent_id)
            agent = death.agent

        health_capacity = _health_capacity(simulation, agent)
        relationship_rows = []
        living_ids = simulation.agents.keys()
        # A dead person's relationship row was released back to the store and
        # may already belong to someone else, so their memories are gone with
        # them rather than misread from a stranger's row.
        views = (
            ()
            if death is not None
            else simulation.relationships.views(
                agent.relationship_slot,
                simulation.tick,
            )
        )
        for relationship in views:
            if relationship.other_id not in living_ids:
                continue
            relationship_rows.append({
                "agent_id": str(relationship.other_id),
                "trust": relationship.trust,
                "balance": relationship.balance,
                "encounters": relationship.encounters,
                "last_seen_tick": relationship.last_seen_tick,
            })
        relationship_rows.sort(key=lambda item: int(item["agent_id"]))

        pregnancy = (
            None if death is not None else simulation.pregnancies.get(agent.id)
        )
        pregnancy_payload: Optional[Dict[str, object]] = None
        if pregnancy is not None:
            pregnancy_payload = {
                "other_parent_id": str(pregnancy.other_parent_id),
                "conception_tick": pregnancy.conception_tick,
                "due_tick": pregnancy.due_tick,
                "prenatal_condition": pregnancy.prenatal_condition,
                "prenatal_exposure_years": (
                    pregnancy.prenatal_exposure_years
                ),
                "invested_energy": pregnancy.invested_energy,
            }

        detail: Dict[str, object] = {
            "id": str(agent.id),
            "status": "living" if death is None else "deceased",
            "death": None if death is None else {
                "tick": death.tick,
                "year": death.tick / simulation.config.ticks_per_year,
                "cause": death.cause,
                "age": death.agent.age,
            },
            "biography": (
                None if death is None
                else _biography(simulation, agent, death)
            ),
            "location": {
                "x": agent.x,
                "y": agent.y,
                "current_country": simulation.world.country_at(
                    agent.x,
                    agent.y,
                ),
            },
            "identity": {
                "birth_country": agent.birth_country_id,
                "belief": agent.belief_id,
                "reproductive_role": agent.reproductive_role.value,
                "generation": agent.generation,
                "parents": _optional_ids(agent.parents),
                "guardian_id": _optional_id(agent.guardian_id),
                "grandparents": [
                    str(value) for value in agent.grandparent_ids
                ],
                "dependents": [
                    str(value)
                    for value in sorted(
                        simulation.dependents_by_guardian.get(
                            agent.id,
                            (),
                        )
                    )
                ] if death is None else [],
            },
            "life": {
                "age": agent.age,
                "birth_tick": agent.birth_tick,
                "energy": agent.energy,
                "energy_fraction": _fraction(
                    agent.energy,
                    simulation.config.maximum_energy,
                ),
                "health": agent.health,
                "effective_maximum_health": health_capacity,
                "health_fraction": _fraction(
                    agent.health,
                    health_capacity,
                ),
                "body_condition": agent.body_condition,
                "development": agent.development_index,
                "development_exposure_years": (
                    agent.development_exposure_years
                ),
                "frailty": agent.frailty,
            },
            "inventories": {
                "food": agent.inventory,
                "materials": agent.material_inventory,
            },
            "biology": {
                "genome": {
                    "schema_version": GENOME_SCHEMA_VERSION,
                    "haplotype_a": (
                        f"{agent.genome.haplotype_a:016x}"
                    ),
                    "haplotype_b": (
                        f"{agent.genome.haplotype_b:016x}"
                    ),
                    "heterozygosity": agent.genome.heterozygosity(),
                    "expressed": agent.genome.expressed_values(),
                },
                "traits": _traits_payload(agent.traits),
            },
            "brain": {
                "kind": agent.traits.brain_kind.value,
                "preferences": {
                    action.value: value
                    for action, value in zip(
                        ActionKind,
                        agent.brain.preferences,
                    )
                },
                "last_action": agent.brain.last_action,
                "last_success": agent.brain.last_success,
                "last_target_id": (
                    None
                    if agent.brain.last_target_id < 0
                    else str(agent.brain.last_target_id)
                ),
                "last_action_tick": agent.brain.last_action_tick,
                "policy_teacher_id": (
                    None
                    if agent.brain.policy_teacher_id < 0
                    else str(agent.brain.policy_teacher_id)
                ),
                "policy_origin_id": (
                    None
                    if agent.brain.policy_origin_id < 0
                    else str(agent.brain.policy_origin_id)
                ),
                "policy_generation": agent.brain.policy_generation,
                "policy_taught_tick": agent.brain.policy_taught_tick,
            },
            "culture": asdict(agent.culture),
            "disease": {
                "stage": agent.infection_stage.name.lower(),
                "ticks_remaining": agent.infection_ticks_remaining,
            },
            "reproduction": {
                "last_reproduction_tick": (
                    agent.last_reproduction_tick
                ),
                "next_reproduction_tick": (
                    agent.next_reproduction_tick
                ),
                "pregnancy": pregnancy_payload,
            },
            "technology": {
                "research_progress": agent.research_progress,
                "knows_seafaring": agent.knows_seafaring,
                "known_techniques": list(
                    knowledge.names(agent.known_techniques)
                ),
                "vessel_durability": agent.vessel_durability,
                "voyage_dx": agent.voyage_dx,
                "voyage_dy": agent.voyage_dy,
            },
            "relationships": relationship_rows,
        }
        return BackendAgent(tick=simulation.tick, agent=detail)

    def events(
        self,
        since_tick: int = -1,
        limit: int = 200,
    ) -> BackendEvents:
        simulation = self._simulation
        log = simulation.events
        capped = max(0, int(limit))
        selected = []
        # Newest first, and stop as soon as the window is full: a caller
        # polling every tick reads a handful of entries rather than walking
        # the whole log each time.
        for event in reversed(log):
            if event.tick <= since_tick or len(selected) >= capped:
                break
            details = {name: value for name, value in event.details}
            record = {
                "tick": event.tick,
                "year": event.tick / simulation.config.ticks_per_year,
                "kind": event.kind,
                "actors": [str(actor) for actor in event.actors],
                "details": details,
            }
            # An utterance is stored as numbers because the event log is
            # numeric. Spelling it out is a reading, not a translation: the
            # sounds are whatever was coined, and the meaning is the situation
            # both speakers could see.
            word = details.get("word")
            if word is not None:
                record["said"] = language.spell(int(word))
                record["about"] = language.MEANINGS[
                    int(details.get("meaning", 0)) % len(language.MEANINGS)
                ]
                record["coined"] = bool(details.get("coined", 0.0))
            selected.append(record)
        oldest = log[0].tick if log else simulation.tick
        return BackendEvents(
            tick=simulation.tick,
            year=simulation.tick / simulation.config.ticks_per_year,
            events=tuple(selected),
            oldest_retained_tick=oldest,
            # The caller asked for everything after a tick the log no longer
            # reaches back to, so something happened it will never see.
            dropped=(
                since_tick >= 0 and bool(log) and oldest > since_tick + 1
            ),
        )

    def export_snapshot(self) -> Dict[str, object]:
        return self._simulation.snapshot(
            include_world=True,
            include_agents=True,
            include_relationships=True,
        )

    def export_checkpoint(self) -> Dict[str, object]:
        return self._simulation.checkpoint()


def python_backend_factory(
    *,
    config: SimulationConfig,
    seed: int,
    scenario: Scenario,
) -> SimulationBackend:
    return PythonSimulationBackend(
        config=config,
        seed=seed,
        scenario=scenario,
    )


def python_checkpoint_backend_factory(
    payload: Mapping[str, object],
) -> SimulationBackend:
    return PythonSimulationBackend.from_checkpoint(payload)


def _biography(
    simulation: Simulation,
    agent: object,
    death: object,
) -> Dict[str, object]:
    """What can honestly be said about a life once it has ended.

    Everything here is read off state the engine already kept, not a
    narrative the engine maintained for the sake of telling one. Two of the
    values are deliberately about survivors rather than the person: how many
    of their children outlived them, and how much of the population now
    descends from them. Those are the only marks a life leaves that the model
    can still see after the fact — the person's own memories went back to the
    relationship store when they died.
    """

    ticks_per_year = simulation.config.ticks_per_year
    agent_id = agent.id
    living_children = 0
    living_grandchildren = 0
    for other in simulation.agents.values():
        parents = other.parents
        if parents is not None and agent_id in parents:
            living_children += 1
        if agent_id in other.grandparent_ids:
            living_grandchildren += 1

    moments = [
        {
            "tick": event.tick,
            "year": event.tick / ticks_per_year,
            "kind": event.kind,
            "actors": [str(actor) for actor in event.actors],
        }
        for event in simulation.events
        if agent_id in event.actors
    ]
    log = simulation.events
    earliest_remembered = log[0].tick if log else death.tick

    died_year = death.tick / ticks_per_year
    # Founders are seeded at an assortment of ages, so their birth_tick is
    # when the run started rather than when they were born. Deriving birth
    # from age keeps the arithmetic true for everyone, and a negative year is
    # not an error — it says this person was already alive at tick zero.
    born_year = died_year - agent.age

    return {
        "born_year": born_year,
        "founder": born_year < 0.0,
        "died_year": died_year,
        "age_at_death": agent.age,
        "cause": death.cause,
        "generation": agent.generation,
        "birth_country": agent.birth_country_id,
        "died_in_country": simulation.world.country_at(agent.x, agent.y),
        "living_children": living_children,
        "living_grandchildren": living_grandchildren,
        "had_partner_at_death": agent.partner_id is not None,
        "bonded_years": (
            None if agent.bond_since_tick < 0
            else (death.tick - agent.bond_since_tick) / ticks_per_year
        ),
        "knew_seafaring": agent.knows_seafaring,
        "childhood_development": agent.development_index,
        "body_condition_at_death": agent.body_condition,
        "frailty_at_death": agent.frailty,
        "infection_at_death": agent.infection_stage.name.lower(),
        "moments": moments,
        # The log is bounded, so a long-lived person's early years may have
        # scrolled out of it. Say so rather than let a partial record read as
        # a complete one.
        "moments_complete": earliest_remembered <= agent.birth_tick,
    }


def _fraction(value: float, maximum: float) -> float:
    if maximum <= 0.0:
        return 0.0
    return min(1.0, max(0.0, value / maximum))


def _current_metrics(simulation: Simulation) -> Dict[str, object]:
    """Reuse an engine sample when it already describes the current tick."""

    if (
        simulation.metrics_history
        and simulation.metrics_history[-1].tick == simulation.tick
    ):
        return simulation.metrics_history[-1].to_dict()
    return simulation.measure().to_dict()


def _health_capacity(simulation: Simulation, agent: object) -> float:
    config = simulation.config
    return effective_health_capacity(
        genetic_health_capacity=agent.traits.maximum_health,
        development=agent.development_index,
        frailty=agent.frailty,
        developmental_floor=config.minimum_development_health_fraction,
        maximum_frailty_loss=config.frailty_health_capacity_loss,
    )


def _optional_id(value: Optional[int]) -> Optional[str]:
    return None if value is None else str(value)


def _optional_ids(
    values: Optional[Tuple[int, int]],
) -> Optional[list]:
    if values is None:
        return None
    return [str(value) for value in values]


def _traits_payload(traits: object) -> Dict[str, object]:
    result = asdict(traits)
    result["brain_kind"] = traits.brain_kind.value
    return result
