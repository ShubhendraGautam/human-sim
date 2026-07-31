"""Safe, versioned, resumable simulation checkpoints.

A visualization snapshot may omit anything a renderer cannot see. A
checkpoint retains every causal field, including random-generator state and
storage slot order, so advancing a restored run is the same computation as
advancing the original.

The contract is plain JSON data. Loading it never imports or executes a class
named by the payload, avoiding the code-execution risk of pickle.
"""

import os
from array import array
from collections import Counter, deque
from dataclasses import asdict, fields
from typing import (
    TYPE_CHECKING,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from . import artifacts
from . import fauna
from .brain import BrainState
from .config import CONFIG_SCHEMA_VERSION, SimulationConfig
from .entities import EntityKind, EntityRegistry
from .genetics import GENOME_SCHEMA_VERSION, Genome
from .health import InfectionStage
from .language import Lexicon
from .memory import PlaceMemory
from .models import (
    Agent,
    BrainKind,
    CultureState,
    DeathRecord,
    Event,
    Metrics,
    Pregnancy,
    ReproductiveRole,
    Traits,
)
from .neural import Network
from .relationships import RawRelationship, RawRow, RelationshipStore
from .scenario import Scenario
from .versions import (
    CHECKPOINT_SCHEMA_VERSION,
    MODEL_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
)

if TYPE_CHECKING:
    from .engine import Simulation


CheckpointSink = Optional[Callable[[object], None]]


def export_checkpoint(simulation: "Simulation") -> Dict[str, object]:
    """Project all resumable state into JSON-compatible values."""

    world = simulation.world
    relationships = [
        [active, [list(entry) for entry in row]]
        for active, row in simulation.relationships.raw_rows()
    ]
    return {
        "checkpoint_kind": "resumable",
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "config_schema_version": CONFIG_SCHEMA_VERSION,
        "genome_schema_version": GENOME_SCHEMA_VERSION,
        "code_revision": os.environ.get(
            "HUMAN_SIM_REVISION",
            "unknown",
        ),
        "definition": {
            "seed": simulation.seed,
            "config": simulation.config.to_dict(),
            "scenario": simulation.scenario.to_dict(),
        },
        "state": {
            "tick": simulation.tick,
            "rng": _json_value(simulation.rng.getstate()),
            "claimed_ids": simulation.entities.claimed_ids,
            "world": {
                "resources": list(world.resources),
                "materials": list(world.materials),
                "last_food_harvested": world.last_food_harvested,
                "last_food_regenerated": world.last_food_regenerated,
                "last_material_harvested": world.last_material_harvested,
                "last_material_regenerated": (
                    world.last_material_regenerated
                ),
                "last_seasonal_productivity": (
                    world.last_seasonal_productivity
                ),
                "last_row_factors": list(world.last_row_factors),
            },
            "agents": [
                _agent_to_data(agent)
                for agent in simulation.agents.values()
            ],
            "fauna": [
                asdict(animal) for animal in simulation.fauna.values()
            ],
            "artifacts": [
                {
                    **asdict(artifact),
                    "created_by": simulation.entities.creator_of(artifact.id),
                }
                for artifact in simulation.artifacts.values()
            ],
            "pregnancies": [
                _pregnancy_to_data(parent_id, pregnancy)
                for parent_id, pregnancy in simulation.pregnancies.items()
            ],
            "dependents_by_guardian": [
                [guardian, sorted(dependents)]
                for guardian, dependents
                in simulation.dependents_by_guardian.items()
            ],
            "relationships": relationships,
            "deaths": [
                {
                    "id": agent_id,
                    "tick": record.tick,
                    "cause": record.cause,
                    "agent": _agent_to_data(record.agent),
                }
                for agent_id, record in simulation.deaths.items()
            ],
            "events": [_event_to_data(event) for event in simulation.events],
            "metrics_history": [
                metric.to_dict() for metric in simulation.metrics_history
            ],
            "counters": _counter_state(simulation),
            "deaths_by_cause": dict(simulation.deaths_by_cause),
            "last_action_counts": dict(simulation._last_action_counts),
            "last_action_attempts": dict(
                simulation._last_action_attempts
            ),
            "last_action_failures": dict(
                simulation._last_action_failures
            ),
            "herd": {
                "last_born": simulation.herd.last_born,
                "last_died": simulation.herd.last_died,
                "last_grazed": simulation.herd.last_grazed,
                "total_born": simulation.herd.total_born,
                "total_died": simulation.herd.total_died,
                "total_starved": simulation.herd.total_starved,
                "total_hunted": simulation.herd.total_hunted,
            },
        },
    }


def restore_checkpoint(
    payload: Mapping[str, object],
    event_sink: CheckpointSink = None,
    metrics_sink: CheckpointSink = None,
) -> "Simulation":
    """Validate and restore one checkpoint."""

    from .engine import Simulation

    config, seed, scenario = checkpoint_definition(payload)
    simulation = Simulation(
        config=config,
        seed=seed,
        scenario=scenario,
        event_sink=event_sink,
        metrics_sink=metrics_sink,
    )
    state = _mapping(payload.get("state"), "state")
    _restore_state(simulation, state)
    simulation.validate_state()
    return simulation


def checkpoint_definition(
    payload: Mapping[str, object],
) -> Tuple[SimulationConfig, int, Scenario]:
    """Read and validate immutable run inputs without constructing a world."""

    _validate_header(payload)
    definition = _mapping(payload.get("definition"), "definition")
    config = SimulationConfig(
        **dict(_mapping(definition.get("config"), "definition.config"))
    )
    seed = _integer(definition.get("seed"), "definition.seed")
    scenario = Scenario.from_dict(
        _mapping(definition.get("scenario"), "definition.scenario")
    )
    scenario.validate(config)
    return config, seed, scenario


def _restore_state(
    simulation: "Simulation",
    state: Mapping[str, object],
) -> None:
    simulation.tick = _integer(state.get("tick"), "state.tick")
    simulation.rng.setstate(
        _tuples(_sequence(state.get("rng"), "state.rng"))
    )
    _restore_world(
        simulation,
        _mapping(state.get("world"), "state.world"),
    )

    registry = EntityRegistry()
    registry.restore_claimed_ids(
        _integer(state.get("claimed_ids"), "state.claimed_ids")
    )
    simulation.entities = registry
    simulation.agents = registry.of_kind(EntityKind.PERSON)
    for value in _sequence(state.get("agents"), "state.agents"):
        registry.register(
            _agent_from_data(
                _mapping(value, "state.agents[]"),
                simulation.config,
            )
        )

    simulation.herd = fauna.Herd(
        simulation.config,
        simulation.world,
        registry,
        simulation._stable_uniform,
    )
    simulation.fauna = registry.of_kind(EntityKind.FAUNA)
    for value in _sequence(state.get("fauna"), "state.fauna"):
        registry.register(
            fauna.Animal(**dict(_mapping(value, "state.fauna[]")))
        )
    simulation.artifacts = registry.of_kind(EntityKind.ARTIFACT)
    for value in _sequence(state.get("artifacts"), "state.artifacts"):
        data = dict(_mapping(value, "state.artifacts[]"))
        created_by = _integer(
            data.pop("created_by", None),
            "artifact.created_by",
        )
        registry.register(
            artifacts.Artifact(**data),
            created_by=created_by,
        )

    simulation.pregnancies = {}
    for value in _sequence(
        state.get("pregnancies"),
        "state.pregnancies",
    ):
        parent_id, pregnancy = _pregnancy_from_data(
            _mapping(value, "state.pregnancies[]"),
        )
        simulation.pregnancies[parent_id] = pregnancy
    simulation.dependents_by_guardian = {}
    for value in _sequence(
        state.get("dependents_by_guardian"),
        "state.dependents_by_guardian",
    ):
        item = _sequence(value, "state.dependents_by_guardian[]")
        if len(item) != 2:
            raise ValueError("invalid guardian/dependent entry")
        simulation.dependents_by_guardian[
            _integer(item[0], "guardian id")
        ] = {
            _integer(dependent, "dependent id")
            for dependent in _sequence(item[1], "dependent ids")
        }

    simulation.relationships = RelationshipStore(
        capacity=simulation.config.maximum_social_bonds,
        half_life_ticks=(
            simulation.config.relationship_half_life_years
            * simulation.config.ticks_per_year
        ),
        balance_limit=simulation.config.relationship_balance_limit,
    )
    simulation.relationships.restore_raw_rows(
        _relationship_rows(
            _sequence(state.get("relationships"), "state.relationships")
        )
    )

    simulation.deaths = {}
    for value in _sequence(state.get("deaths"), "state.deaths"):
        record = _mapping(value, "state.deaths[]")
        agent_id = _integer(record.get("id"), "death id")
        simulation.deaths[agent_id] = DeathRecord(
            agent=_agent_from_data(
                _mapping(record.get("agent"), "death agent"),
                simulation.config,
            ),
            tick=_integer(record.get("tick"), "death tick"),
            cause=_string(record.get("cause"), "death cause"),
        )
    simulation.events = deque(
        (
            _event_from_data(_mapping(value, "state.events[]"))
            for value in _sequence(state.get("events"), "state.events")
        ),
        maxlen=simulation.config.event_log_capacity,
    )
    simulation.metrics_history = deque(
        (
            _metric_from_data(
                _mapping(value, "state.metrics_history[]")
            )
            for value in _sequence(
                state.get("metrics_history"),
                "state.metrics_history",
            )
        ),
        maxlen=simulation.config.metrics_history_capacity,
    )

    counters = _mapping(state.get("counters"), "state.counters")
    for name in _COUNTER_FIELDS:
        setattr(
            simulation,
            name,
            _number(counters.get(name), f"state.counters.{name}"),
        )
    simulation.deaths_by_cause = Counter(
        _string_counter(state.get("deaths_by_cause"), "deaths_by_cause")
    )
    simulation._last_action_counts = Counter(
        _string_counter(
            state.get("last_action_counts"),
            "last_action_counts",
        )
    )
    simulation._last_action_attempts = Counter(
        _string_counter(
            state.get("last_action_attempts"),
            "last_action_attempts",
        )
    )
    simulation._last_action_failures = Counter(
        _string_counter(
            state.get("last_action_failures"),
            "last_action_failures",
        )
    )
    herd = _mapping(state.get("herd"), "state.herd")
    for name in (
        "last_born",
        "last_died",
        "last_grazed",
        "total_born",
        "total_died",
        "total_starved",
        "total_hunted",
    ):
        setattr(simulation.herd, name, _number(herd.get(name), name))
    simulation.world.rebuild_spatial_index(simulation.entities.placed())


def _restore_world(
    simulation: "Simulation",
    payload: Mapping[str, object],
) -> None:
    world = simulation.world
    cells = simulation.config.width * simulation.config.height
    resources = _float_list(payload.get("resources"), "world.resources")
    materials = _float_list(payload.get("materials"), "world.materials")
    if len(resources) != cells or len(materials) != cells:
        raise ValueError("checkpoint world layers have the wrong size")
    world.resources = array("d", resources)
    world.materials = array("d", materials)
    for name in (
        "last_food_harvested",
        "last_food_regenerated",
        "last_material_harvested",
        "last_material_regenerated",
        "last_seasonal_productivity",
    ):
        setattr(world, name, _number(payload.get(name), f"world.{name}"))
    row_factors = _float_list(
        payload.get("last_row_factors"),
        "world.last_row_factors",
    )
    if len(row_factors) != simulation.config.height:
        raise ValueError("checkpoint seasonal rows have the wrong size")
    world.last_row_factors = row_factors


_AGENT_SCALARS = (
    "id",
    "x",
    "y",
    "age",
    "energy",
    "health",
    "inventory",
    "material_inventory",
    "birth_country_id",
    "belief_id",
    "known_techniques",
    "vessel_durability",
    "voyage_dx",
    "voyage_dy",
    "generation",
    "birth_tick",
    "last_reproduction_tick",
    "guardian_id",
    "body_condition",
    "development_index",
    "development_exposure_years",
    "frailty",
    "next_reproduction_tick",
    "relationship_slot",
    "partner_id",
    "bond_since_tick",
    "bond_last_together_tick",
    "infection_ticks_remaining",
)


def _agent_to_data(agent: Agent) -> Dict[str, object]:
    payload = {name: getattr(agent, name) for name in _AGENT_SCALARS}
    payload.update({
        "genome": [
            agent.genome.haplotype_a,
            agent.genome.haplotype_b,
        ],
        "culture": asdict(agent.culture),
        "traits": {
            **asdict(agent.traits),
            "brain_kind": agent.traits.brain_kind.value,
        },
        "brain": _brain_to_data(agent.brain),
        "lexicon": _lexicon_to_data(agent.lexicon),
        "network": _network_to_data(agent.network),
        "reproductive_role": agent.reproductive_role.value,
        "technique_progress": agent.technique_progress,
        "places": (
            None
            if agent.places is None
            else [list(place) for place in agent.places.places]
        ),
        "parents": (
            None if agent.parents is None else list(agent.parents)
        ),
        "grandparent_ids": list(agent.grandparent_ids),
        "infection_stage": agent.infection_stage.name,
    })
    return payload


def _agent_from_data(
    payload: Mapping[str, object],
    config: SimulationConfig,
) -> Agent:
    genome_values = _sequence(payload.get("genome"), "agent.genome")
    if len(genome_values) != 2:
        raise ValueError("agent genome must contain two haplotypes")
    genome = Genome(
        _integer(genome_values[0], "haplotype_a"),
        _integer(genome_values[1], "haplotype_b"),
    )
    values = {name: payload.get(name) for name in _AGENT_SCALARS}
    values.update({
        "genome": genome,
        "traits": _traits_from_data(
            _mapping(payload.get("traits"), "agent.traits")
        ),
        "culture": CultureState(
            **dict(_mapping(payload.get("culture"), "agent.culture"))
        ),
        "brain": _brain_from_data(
            _mapping(payload.get("brain"), "agent.brain")
        ),
        "lexicon": _lexicon_from_data(
            _mapping(payload.get("lexicon"), "agent.lexicon")
        ),
        "network": _network_from_data(
            _mapping(payload.get("network"), "agent.network")
        ),
        "reproductive_role": ReproductiveRole(
            payload.get("reproductive_role")
        ),
        "technique_progress": _optional_float_list(
            payload.get("technique_progress"),
            "agent.technique_progress",
        ),
        "places": _places_from_data(payload.get("places")),
        "parents": _optional_int_tuple(payload.get("parents"), "parents"),
        "grandparent_ids": tuple(
            _integer(value, "grandparent id")
            for value in _sequence(
                payload.get("grandparent_ids"),
                "agent.grandparent_ids",
            )
        ),
        "infection_stage": InfectionStage[
            _string(payload.get("infection_stage"), "infection stage")
        ],
    })
    return Agent(**values)


def _traits_from_data(payload: Mapping[str, object]) -> Traits:
    values = dict(payload)
    values["brain_kind"] = BrainKind(values["brain_kind"])
    return Traits(**values)


def _brain_to_data(brain: BrainState) -> Dict[str, object]:
    return {
        "preferences": list(brain.preferences),
        "plastic": brain.plastic,
        "last_activations": brain.last_activations,
        "last_action": brain.last_action,
        "last_success": brain.last_success,
        "last_target_id": brain.last_target_id,
        "last_action_tick": brain.last_action_tick,
    }


def _brain_from_data(payload: Mapping[str, object]) -> BrainState:
    return BrainState(
        preferences=array(
            "f",
            _float_list(payload.get("preferences"), "brain.preferences"),
        ),
        plastic=_optional_matrix(payload.get("plastic"), "brain.plastic"),
        last_activations=_optional_float_list(
            payload.get("last_activations"),
            "brain.last_activations",
        ),
        last_action=_string(payload.get("last_action"), "last_action"),
        last_success=_number(payload.get("last_success"), "last_success"),
        last_target_id=_integer(
            payload.get("last_target_id"),
            "last_target_id",
        ),
        last_action_tick=_integer(
            payload.get("last_action_tick"),
            "last_action_tick",
        ),
    )


def _network_to_data(network: Network) -> Dict[str, object]:
    return {
        "units": network.units,
        "outputs": network.outputs,
        "active": network.active,
        "growth_rate": network.growth_rate,
        "hidden": network.hidden,
        "output": network.output,
        "recurrent": network.recurrent,
    }


def _network_from_data(payload: Mapping[str, object]) -> Network:
    units = _integer(payload.get("units"), "network.units")
    outputs = _integer(payload.get("outputs"), "network.outputs")
    recurrent = _matrix(payload.get("recurrent"), "network.recurrent")
    network = Network(
        units,
        outputs,
        active=_integer(payload.get("active"), "network.active"),
        growth_rate=_number(
            payload.get("growth_rate"),
            "network.growth_rate",
        ),
        recurrent=bool(recurrent),
    )
    network.hidden = _matrix(payload.get("hidden"), "network.hidden")
    network.output = _matrix(payload.get("output"), "network.output")
    network.recurrent = recurrent
    network.refresh_magnitude()
    return network


def _lexicon_to_data(lexicon: Lexicon) -> Dict[str, object]:
    return {
        "words": list(lexicon.words),
        "confidence": list(lexicon.confidence),
        "exposed": list(lexicon.exposed),
        "challenger": list(lexicon.challenger),
        "challenger_count": list(lexicon.challenger_count),
    }


def _lexicon_from_data(payload: Mapping[str, object]) -> Lexicon:
    lexicon = Lexicon()
    lexicon.words = list(
        _sequence(payload.get("words"), "lexicon.words")
    )
    lexicon.confidence = list(
        _sequence(payload.get("confidence"), "lexicon.confidence")
    )
    lexicon.exposed = list(
        _sequence(payload.get("exposed"), "lexicon.exposed")
    )
    lexicon.challenger = list(
        _sequence(payload.get("challenger"), "lexicon.challenger")
    )
    lexicon.challenger_count = list(
        _sequence(
            payload.get("challenger_count"),
            "lexicon.challenger_count",
        )
    )
    return lexicon


def _places_from_data(value: object) -> Optional[PlaceMemory]:
    if value is None:
        return None
    memory = PlaceMemory()
    memory.places = [
        (
            _integer(item[0], "place cell"),
            _number(item[1], "place quality"),
            _integer(item[2], "place tick"),
        )
        for item in (
            _sequence(entry, "place")
            for entry in _sequence(value, "agent.places")
        )
    ]
    return memory


def _pregnancy_to_data(
    parent_id: int,
    pregnancy: Pregnancy,
) -> Dict[str, object]:
    return {
        "parent_id": parent_id,
        "gestational_parent_id": pregnancy.gestational_parent_id,
        "other_parent_id": pregnancy.other_parent_id,
        "genome": [
            pregnancy.genome.haplotype_a,
            pregnancy.genome.haplotype_b,
        ],
        "culture": asdict(pregnancy.culture),
        "reproductive_role": pregnancy.reproductive_role.value,
        "belief_id": pregnancy.belief_id,
        "generation": pregnancy.generation,
        "network": _network_to_data(pregnancy.network),
        "conception_tick": pregnancy.conception_tick,
        "due_tick": pregnancy.due_tick,
        "grandparent_ids": list(pregnancy.grandparent_ids),
        "prenatal_condition": pregnancy.prenatal_condition,
        "prenatal_exposure_years": pregnancy.prenatal_exposure_years,
        "invested_energy": pregnancy.invested_energy,
    }


def _pregnancy_from_data(
    payload: Mapping[str, object],
) -> Tuple[int, Pregnancy]:
    genome = _sequence(payload.get("genome"), "pregnancy.genome")
    if len(genome) != 2:
        raise ValueError("pregnancy genome must contain two haplotypes")
    pregnancy = Pregnancy(
        gestational_parent_id=_integer(
            payload.get("gestational_parent_id"),
            "gestational_parent_id",
        ),
        other_parent_id=_integer(
            payload.get("other_parent_id"),
            "other_parent_id",
        ),
        genome=Genome(
            _integer(genome[0], "haplotype_a"),
            _integer(genome[1], "haplotype_b"),
        ),
        culture=CultureState(
            **dict(_mapping(payload.get("culture"), "pregnancy.culture"))
        ),
        reproductive_role=ReproductiveRole(
            payload.get("reproductive_role")
        ),
        belief_id=_integer(payload.get("belief_id"), "belief_id"),
        generation=_integer(payload.get("generation"), "generation"),
        network=_network_from_data(
            _mapping(payload.get("network"), "pregnancy.network")
        ),
        conception_tick=_integer(
            payload.get("conception_tick"),
            "conception_tick",
        ),
        due_tick=_integer(payload.get("due_tick"), "due_tick"),
        grandparent_ids=tuple(
            _integer(value, "grandparent id")
            for value in _sequence(
                payload.get("grandparent_ids"),
                "pregnancy.grandparent_ids",
            )
        ),
        prenatal_condition=_number(
            payload.get("prenatal_condition"),
            "prenatal_condition",
        ),
        prenatal_exposure_years=_number(
            payload.get("prenatal_exposure_years"),
            "prenatal_exposure_years",
        ),
        invested_energy=_number(
            payload.get("invested_energy"),
            "invested_energy",
        ),
    )
    return _integer(payload.get("parent_id"), "parent_id"), pregnancy


def _event_to_data(event: Event) -> Dict[str, object]:
    return {
        "tick": event.tick,
        "kind": event.kind,
        "actors": list(event.actors),
        "details": [list(item) for item in event.details],
    }


def _event_from_data(payload: Mapping[str, object]) -> Event:
    return Event(
        tick=_integer(payload.get("tick"), "event.tick"),
        kind=_string(payload.get("kind"), "event.kind"),
        actors=tuple(
            _integer(value, "event actor")
            for value in _sequence(payload.get("actors"), "event.actors")
        ),
        details=tuple(
            (
                _string(item[0], "event detail name"),
                _number(item[1], "event detail value"),
            )
            for item in (
                _sequence(value, "event detail")
                for value in _sequence(
                    payload.get("details"),
                    "event.details",
                )
            )
        ),
    )


def _metric_from_data(payload: Mapping[str, object]) -> Metrics:
    values = dict(payload)
    for name in ("country_population", "belief_population"):
        values[name] = {
            int(key): value
            for key, value in _mapping(values.get(name), name).items()
        }
    expected = {field.name for field in fields(Metrics)}
    if set(values) != expected:
        raise ValueError("checkpoint metric fields do not match this model")
    return Metrics(**values)


_COUNTER_FIELDS = (
    "total_hunts",
    "total_hunt_kills",
    "_last_meat_gained",
    "total_births",
    "total_conceptions",
    "total_deaths",
    "total_pregnancy_losses",
    "total_inventions",
    "total_sea_crossings",
    "total_infections",
    "total_coinages",
    "total_recoveries",
    "total_artifacts_built",
    "total_artifacts_decayed",
    "total_artifact_maintenance",
    "_last_food_consumed",
    "_last_food_spoiled",
    "_last_food_lost_on_death",
    "_last_material_consumed",
    "_last_material_lost_on_death",
    "_last_environmental_energy_cost",
    "_last_food_lost_on_artifact_decay",
)


def _counter_state(simulation: "Simulation") -> Dict[str, object]:
    return {name: getattr(simulation, name) for name in _COUNTER_FIELDS}


def _relationship_rows(
    values: Sequence[object],
) -> Tuple[Tuple[bool, RawRow], ...]:
    rows: List[Tuple[bool, RawRow]] = []
    for value in values:
        row = _sequence(value, "relationship row")
        if len(row) != 2 or not isinstance(row[0], bool):
            raise ValueError("invalid relationship row")
        entries: List[RawRelationship] = []
        for entry_value in _sequence(row[1], "relationship entries"):
            entry = _sequence(entry_value, "relationship entry")
            if len(entry) != 6:
                raise ValueError("invalid relationship entry")
            entries.append((
                _integer(entry[0], "other id"),
                _number(entry[1], "trust"),
                _number(entry[2], "balance"),
                _integer(entry[3], "encounters"),
                _integer(entry[4], "value tick"),
                _integer(entry[5], "last seen tick"),
            ))
        rows.append((row[0], tuple(entries)))
    return tuple(rows)


def _validate_header(payload: Mapping[str, object]) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError("checkpoint must contain an object")
    if payload.get("checkpoint_kind") != "resumable":
        raise ValueError("not a resumable checkpoint")
    checks = (
        ("schema_version", CHECKPOINT_SCHEMA_VERSION),
        ("model_version", MODEL_VERSION),
        ("config_schema_version", CONFIG_SCHEMA_VERSION),
        ("genome_schema_version", GENOME_SCHEMA_VERSION),
    )
    for name, expected in checks:
        if payload.get(name) != expected:
            raise ValueError(
                f"checkpoint {name} {payload.get(name)!r} is incompatible; "
                f"this engine requires {expected!r}"
            )


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must contain an object")
    return value


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must contain an array")
    return value


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    return value


def _number(value: object, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not float("-inf") < float(value) < float("inf")
    ):
        raise TypeError(f"{name} must be a finite number")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _float_list(value: object, name: str) -> List[float]:
    return [
        float(_number(item, name))
        for item in _sequence(value, name)
    ]


def _optional_float_list(
    value: object,
    name: str,
) -> Optional[List[float]]:
    return None if value is None else _float_list(value, name)


def _matrix(value: object, name: str) -> List[List[float]]:
    return [
        _float_list(row, name)
        for row in _sequence(value, name)
    ]


def _optional_matrix(
    value: object,
    name: str,
) -> Optional[List[List[float]]]:
    return None if value is None else _matrix(value, name)


def _optional_int_tuple(
    value: object,
    name: str,
) -> Optional[Tuple[int, ...]]:
    if value is None:
        return None
    return tuple(
        _integer(item, name) for item in _sequence(value, name)
    )


def _string_counter(value: object, name: str) -> Dict[str, int]:
    return {
        str(key): _integer(count, name)
        for key, count in _mapping(value, name).items()
    }


def _json_value(value: object) -> object:
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _tuples(value: object) -> object:
    if isinstance(value, list):
        return tuple(_tuples(item) for item in value)
    return value
