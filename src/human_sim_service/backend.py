"""Backend seam and reference adapter for the Python simulation engine."""

from dataclasses import asdict, dataclass
from typing import Dict, Mapping, Optional, Protocol, Tuple

from src.simulation import (
    CONFIG_SCHEMA_VERSION,
    GENOME_SCHEMA_VERSION,
    ActionKind,
    Scenario,
    Simulation,
    SimulationConfig,
    effective_health_capacity,
)
from src.simulation.engine import MODEL_VERSION, SNAPSHOT_SCHEMA_VERSION


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
    resources: Optional[Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class BackendAgent:
    tick: int
    agent: Mapping[str, object]


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

    def export_snapshot(self) -> Dict[str, object]:
        """Return the backend's full visualization/export snapshot."""


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
            "vessel_durability": [
                agent.vessel_durability for agent in ordered
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
            resources=resources,
        )

    def agent(self, agent_id: int) -> BackendAgent:
        simulation = self._simulation
        try:
            agent = simulation.agents[agent_id]
        except KeyError:
            raise KeyError(agent_id) from None

        health_capacity = _health_capacity(simulation, agent)
        relationship_rows = []
        living_ids = simulation.agents.keys()
        for relationship in simulation.relationships.views(
            agent.relationship_slot,
            simulation.tick,
        ):
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

        pregnancy = simulation.pregnancies.get(agent.id)
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
                ],
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
                "vessel_durability": agent.vessel_durability,
                "voyage_dx": agent.voyage_dx,
                "voyage_dy": agent.voyage_dy,
            },
            "relationships": relationship_rows,
        }
        return BackendAgent(tick=simulation.tick, agent=detail)

    def export_snapshot(self) -> Dict[str, object]:
        return self._simulation.snapshot(
            include_world=True,
            include_agents=True,
            include_relationships=True,
        )


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
