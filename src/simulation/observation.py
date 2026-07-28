"""Read-only projections of simulation state.

Nothing in this module mutates a simulation. The architecture rule that
metrics are observations which never feed back into behavior is therefore
structural here rather than a convention: an observer that needs to write
state would have to reach through the ``simulation`` argument to do it, which
is visible in review.

``Simulation`` keeps thin delegating methods so existing callers are
unaffected.
"""

import math
from collections import Counter
from statistics import fmean
from typing import TYPE_CHECKING, Dict, Iterable, List, Sequence, Set, Tuple

from . import knowledge
from . import language
from .config import CONFIG_SCHEMA_VERSION
from .entities import INERT_KINDS, EntityKind
from .genetics import GENOME_SCHEMA_VERSION, LOCUS_COUNT
from .health import InfectionStage
from .models import ActionKind, Agent, Metrics, ReproductiveRole
from .versions import MODEL_VERSION, SNAPSHOT_SCHEMA_VERSION

if TYPE_CHECKING:  # pragma: no cover - import cycle guard for type checkers
    from .engine import Simulation


def measure(simulation: "Simulation") -> Metrics:
    population = len(simulation.agents)
    agents = tuple(
        sorted(
            simulation.agents.values(),
            key=lambda item: item.id,
        )
    )
    if population:
        energies = [agent.energy for agent in agents]
        # values() is a reusable view; subsequent comprehensions are safe.
        mean_energy = fmean(energies)
        mean_health = fmean(agent.health for agent in agents)
        total_food_inventory = sum(
            agent.inventory for agent in agents
        )
        total_material_inventory = sum(
            agent.material_inventory for agent in agents
        )
        mean_inventory = total_food_inventory / population
        mean_age = fmean(agent.age for agent in agents)
        mean_health_fraction = fmean(
            agent.health / max(simulation._health_capacity(agent), 1e-12)
            for agent in agents
        )
        mean_body_condition = fmean(
            agent.body_condition for agent in agents
        )
        mean_development = fmean(
            agent.development_index for agent in agents
        )
        mean_frailty = fmean(agent.frailty for agent in agents)
        juvenile_population = sum(
            agent.age < agent.traits.maturity_age for agent in agents
        )
        age_bands = Counter()
        for agent in agents:
            if agent.age < simulation.config.dependent_age:
                age_bands["dependent"] += 1
            elif agent.age < agent.traits.maturity_age:
                age_bands["juvenile"] += 1
            elif (
                agent.age
                < agent.traits.lifespan
                * simulation.config.aging_starts_fraction
            ):
                age_bands["adult"] += 1
            else:
                age_bands["older"] += 1
        maximum_generation = max(
            agent.generation for agent in agents
        )
        energy_gini = _gini(energies)
        seafaring_population = sum(
            agent.knows_seafaring for agent in agents
        )
        vessels = sum(agent.vessel_durability > 0.0 for agent in agents)
        country_population = Counter(
            simulation.world.country_at(agent.x, agent.y)
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
        disease_population = Counter(
            agent.infection_stage.name.lower() for agent in agents
        )
        mean_heterozygosity = fmean(
            agent.genome.heterozygosity() for agent in agents
        )
        genetic_diversity = _population_genetic_diversity(agents)
        remembered_connection_counts = []
        connection_counts = []
        trust_values = []
        living_ids = simulation.agents.keys()
        active_relationship_ticks = max(
            1,
            round(
                simulation.config.relationship_half_life_years
                * simulation.config.ticks_per_year
            ),
        )
        for agent in agents:
            remembered_views = [
                view
                for view in simulation.relationships.views(
                    agent.relationship_slot,
                    simulation.tick,
                )
                if view.other_id in living_ids
            ]
            views = [
                view
                for view in remembered_views
                if (
                    simulation.tick - view.last_seen_tick
                    <= active_relationship_ticks
                )
            ]
            remembered_connection_counts.append(
                len(remembered_views)
            )
            connection_counts.append(len(views))
            trust_values.extend(view.trust for view in views)
        mean_remembered_connections = fmean(
            remembered_connection_counts
        )
        mean_social_connections = fmean(connection_counts)
        mean_trust = fmean(trust_values) if trust_values else 0.0
        isolated_population = sum(
            count == 0 for count in connection_counts
        )
        (
            mean_network_magnitude,
            mean_plasticity,
            policy_diversity,
            mean_remembered_places,
        ) = _minds(agents)
        (
            mean_vocabulary,
            language_agreement,
            language_global_agreement,
            distinct_words,
            speaking_population,
        ) = _language(agents)
    else:
        mean_energy = 0.0
        mean_health = 0.0
        mean_inventory = 0.0
        total_food_inventory = 0.0
        total_material_inventory = 0.0
        mean_age = 0.0
        mean_health_fraction = 0.0
        mean_body_condition = 0.0
        mean_development = 0.0
        mean_frailty = 0.0
        juvenile_population = 0
        age_bands = Counter()
        maximum_generation = 0
        energy_gini = 0.0
        seafaring_population = 0
        vessels = 0
        country_population = Counter()
        belief_population = Counter()
        brain_population = Counter()
        reproductive_roles = Counter()
        disease_population = Counter()
        mean_heterozygosity = 0.0
        genetic_diversity = 0.0
        mean_remembered_connections = 0.0
        mean_social_connections = 0.0
        mean_trust = 0.0
        isolated_population = 0
        mean_network_magnitude = 0.0
        mean_plasticity = 0.0
        policy_diversity = 0.0
        mean_remembered_places = 0.0
        mean_vocabulary = 0.0
        language_agreement = 0.0
        language_global_agreement = 0.0
        distinct_words = 0
        speaking_population = 0

    (
        fauna_population,
        fauna_mean_energy,
        fauna_mean_vigilance,
        fauna_mean_age,
    ) = simulation.herd.statistics()

    total_capacity = sum(simulation.world.capacity)
    total_resources = simulation.world.total_resources()
    resource_fraction = (
        total_resources / total_capacity if total_capacity else 0.0
    )

    return Metrics(
        tick=simulation.tick,
        year=simulation.year,
        population=population,
        births=simulation.total_births,
        conceptions=simulation.total_conceptions,
        pregnancies=len(simulation.pregnancies),
        pregnancy_losses=simulation.total_pregnancy_losses,
        deaths=simulation.total_deaths,
        total_resources=total_resources,
        total_materials=simulation.world.total_materials(),
        mean_energy=mean_energy,
        mean_health=mean_health,
        mean_inventory=mean_inventory,
        mean_age=mean_age,
        mean_health_fraction=mean_health_fraction,
        mean_body_condition=mean_body_condition,
        mean_development=mean_development,
        mean_frailty=mean_frailty,
        juvenile_population=juvenile_population,
        age_bands=dict(age_bands),
        maximum_generation=maximum_generation,
        energy_gini=energy_gini,
        resource_fraction=resource_fraction,
        food_per_capita=(
            total_resources / population if population else 0.0
        ),
        total_food_inventory=total_food_inventory,
        total_material_inventory=total_material_inventory,
        food_harvested=simulation.world.last_food_harvested,
        food_regenerated=simulation.world.last_food_regenerated,
        food_consumed=simulation._last_food_consumed,
        food_spoiled=simulation._last_food_spoiled,
        food_lost_on_death=simulation._last_food_lost_on_death,
        material_harvested=simulation.world.last_material_harvested,
        material_regenerated=simulation.world.last_material_regenerated,
        material_consumed=simulation._last_material_consumed,
        material_lost_on_death=(
            simulation._last_material_lost_on_death
        ),
        seasonal_productivity=simulation.world.last_seasonal_productivity,
        seafaring_population=seafaring_population,
        vessels=vessels,
        inventions=simulation.total_inventions,
        sea_crossings=simulation.total_sea_crossings,
        country_population=dict(country_population),
        belief_population=dict(belief_population),
        brain_population=dict(brain_population),
        reproductive_roles=dict(reproductive_roles),
        mean_heterozygosity=mean_heterozygosity,
        genetic_diversity=genetic_diversity,
        action_entropy=_entropy(
            simulation._last_action_counts.values(),
            len(ActionKind),
        ),
        actions=dict(simulation._last_action_counts),
        attempted_actions=dict(simulation._last_action_attempts),
        failed_actions=dict(simulation._last_action_failures),
        deaths_by_cause=dict(simulation.deaths_by_cause),
        infections=simulation.total_infections,
        recoveries=simulation.total_recoveries,
        disease_population=dict(disease_population),
        mean_remembered_connections=mean_remembered_connections,
        mean_social_connections=mean_social_connections,
        mean_trust=mean_trust,
        isolated_population=isolated_population,
        mean_vocabulary=mean_vocabulary,
        language_agreement=language_agreement,
        language_global_agreement=language_global_agreement,
        distinct_words=distinct_words,
        speaking_population=speaking_population,
        coinages=simulation.total_coinages,
        fauna_population=fauna_population,
        fauna_mean_energy=fauna_mean_energy,
        fauna_mean_vigilance=fauna_mean_vigilance,
        fauna_mean_age=fauna_mean_age,
        fauna_born=simulation.herd.last_born,
        fauna_died=simulation.herd.last_died,
        fauna_grazed=simulation.herd.last_grazed,
        hunts=simulation.total_hunts,
        hunt_kills=simulation.total_hunt_kills,
        meat_gained=simulation._last_meat_gained,
        mean_network_magnitude=mean_network_magnitude,
        mean_plasticity=mean_plasticity,
        policy_diversity=policy_diversity,
        mean_remembered_places=mean_remembered_places,
    )


def _minds(agents: Sequence["Agent"]) -> Tuple[float, float, float, float]:
    """What the population's brains look like, without judging them.

    ``policy_diversity`` is the mean spread of inherited output weights
    across the population. It answers the question the design notes ask of
    any self-modification: whether everyone converged on one way of
    behaving, which would say the world has a single problem, or whether
    distinct policies coexist.
    """

    if not agents:
        return (0.0, 0.0, 0.0, 0.0)
    magnitude = fmean(agent.network.magnitude for agent in agents)
    plasticity = fmean(
        agent.brain.plasticity_magnitude for agent in agents
    )
    places = fmean(
        0 if agent.places is None else len(agent.places)
        for agent in agents
    )
    # Spread of the output layer, averaged over its entries. A population of
    # clones scores zero however strong its opinions are.
    first = agents[0].network
    spread = 0.0
    entries = 0
    for action in range(first.outputs):
        for unit in range(first.units):
            column = [
                agent.network.output[action][unit] for agent in agents
            ]
            if len(column) > 1:
                mean = fmean(column)
                spread += (
                    sum((value - mean) ** 2 for value in column)
                    / len(column)
                ) ** 0.5
            entries += 1
    return (
        magnitude,
        plasticity,
        spread / entries if entries else 0.0,
        places,
    )


#: How wide a patch of world counts as "people who talk to each other", for
#: reporting only. Nothing in the engine reads this; it is the window an
#: observer looks through, chosen to be a few steps across so that it spans
#: the people an agent actually meets rather than the whole map.
NEIGHBOURHOOD_SPAN = 4


def _language(
    agents: Sequence["Agent"],
) -> Tuple[float, float, float, int, int]:
    """How much of a shared language the population actually has.

    Two agreement numbers, because they answer different questions and a
    single one is actively misleading.

    *Local* agreement is the share of speakers in the same patch of world who
    hold the same form, which is what "these people have a language" means.
    *Global* agreement asks the same of the whole population at once.

    The gap between them is the interesting quantity. A population split into
    dialects that each agree internally scores high locally and low globally,
    and that is a success, not a failure — it is exactly what the mechanism
    should produce where contact is thin. Reporting only the global number
    cannot tell that case apart from everyone babbling separately, which is
    why both are here.

    Neither is pairwise: pairwise is quadratic, and the question worth asking
    is whether a form has become common, not how any two individuals compare.
    """

    global_totals = 0
    global_top = 0
    local_totals = 0
    local_top = 0
    distinct: Set[int] = set()
    vocabulary = 0
    speaking = 0
    for meaning in range(len(language.MEANINGS)):
        forms: Counter = Counter()
        patches: Dict[Tuple[int, int], Counter] = {}
        for agent in agents:
            word = agent.lexicon.words[meaning]
            if word == language.NO_WORD:
                continue
            forms[word] += 1
            patch = (
                agent.x // NEIGHBOURHOOD_SPAN,
                agent.y // NEIGHBOURHOOD_SPAN,
            )
            bucket = patches.get(patch)
            if bucket is None:
                bucket = patches[patch] = Counter()
            bucket[word] += 1
        if not forms:
            continue
        distinct.update(forms)
        global_totals += sum(forms.values())
        global_top += forms.most_common(1)[0][1]
        for bucket in patches.values():
            held = sum(bucket.values())
            # One speaker in a patch agrees with nobody; counting them as
            # perfect agreement would report a scattered population as
            # having the most unanimous language in the world.
            if held < 2:
                continue
            local_totals += held
            local_top += bucket.most_common(1)[0][1]
    for agent in agents:
        size = agent.lexicon.size
        vocabulary += size
        if size:
            speaking += 1
    return (
        vocabulary / len(agents) if agents else 0.0,
        local_top / local_totals if local_totals else 0.0,
        global_top / global_totals if global_totals else 0.0,
        len(distinct),
        speaking,
    )


def state_digest(simulation: "Simulation") -> Tuple[object, ...]:
    """Compact stable state used for reproducibility checks."""

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
            round(agent.brain.last_success, 8),
            agent.brain.last_target_id,
            agent.brain.last_action_tick,
            agent.birth_country_id,
            agent.belief_id,
            round(agent.research_progress, 8),
            agent.known_techniques,
            round(agent.vessel_durability, 8),
            agent.voyage_dx,
            agent.voyage_dy,
            agent.generation,
            agent.parents,
            agent.birth_tick,
            agent.last_reproduction_tick,
            agent.guardian_id,
            agent.grandparent_ids,
            round(agent.body_condition, 8),
            round(agent.development_index, 8),
            round(agent.development_exposure_years, 8),
            round(agent.frailty, 8),
            agent.next_reproduction_tick,
            agent.relationship_slot,
            agent.partner_id,
            agent.bond_since_tick,
            agent.bond_last_together_tick,
            int(agent.infection_stage),
            agent.infection_ticks_remaining,
        )
        for agent in sorted(
            simulation.agents.values(), key=lambda item: item.id
        )
    )
    resources = tuple(round(value, 8) for value in simulation.world.resources)
    materials = tuple(round(value, 8) for value in simulation.world.materials)
    return (
        simulation.tick,
        simulation.total_births,
        simulation.total_conceptions,
        simulation.total_deaths,
        simulation.total_pregnancy_losses,
        simulation.total_inventions,
        simulation.total_sea_crossings,
        simulation.total_infections,
        simulation.total_recoveries,
        tuple(sorted(simulation.deaths_by_cause.items())),
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
                pregnancy.grandparent_ids,
                round(pregnancy.prenatal_condition, 8),
                round(pregnancy.prenatal_exposure_years, 8),
                round(pregnancy.invested_energy, 8),
            )
            for parent_id, pregnancy in simulation.pregnancies.items()
        )),
        tuple(
            (guardian_id, tuple(sorted(dependent_ids)))
            for guardian_id, dependent_ids
            in sorted(simulation.dependents_by_guardian.items())
        ),
        simulation.relationships.raw_rows(),
        tuple(sorted(simulation._last_action_counts.items())),
        tuple(sorted(simulation._last_action_attempts.items())),
        tuple(sorted(simulation._last_action_failures.items())),
        round(simulation.world.last_food_harvested, 8),
        round(simulation.world.last_food_regenerated, 8),
        round(simulation._last_food_consumed, 8),
        round(simulation._last_food_spoiled, 8),
        round(simulation._last_food_lost_on_death, 8),
        round(simulation.world.last_material_harvested, 8),
        round(simulation.world.last_material_regenerated, 8),
        round(simulation._last_material_consumed, 8),
        round(simulation._last_material_lost_on_death, 8),
        round(simulation.world.last_seasonal_productivity, 8),
    )


def snapshot(
    simulation: "Simulation",
    include_world: bool = True,
    include_agents: bool = True,
    include_relationships: bool = True,
) -> Dict[str, object]:
    """Return versioned JSON state for UIs and recorders."""

    result: Dict[str, object] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_kind": "visualization",
        "model_version": MODEL_VERSION,
        "config_schema_version": CONFIG_SCHEMA_VERSION,
        "genome_schema_version": GENOME_SCHEMA_VERSION,
        "seed": simulation.seed,
        "tick": simulation.tick,
        "year": simulation.year,
        "config": simulation.config.to_dict(),
        "action_preference_order": [
            kind.value for kind in ActionKind
        ],
        "metrics": simulation.measure().to_dict(),
        "scenario": simulation.scenario.to_dict(),
        "pregnancies": [
            {
                "gestational_parent_id": pregnancy.gestational_parent_id,
                "other_parent_id": pregnancy.other_parent_id,
                "conception_tick": pregnancy.conception_tick,
                "due_tick": pregnancy.due_tick,
                "prenatal_condition": pregnancy.prenatal_condition,
                "prenatal_exposure_years": (
                    pregnancy.prenatal_exposure_years
                ),
                "invested_energy": pregnancy.invested_energy,
            }
            for pregnancy in sorted(
                simulation.pregnancies.values(),
                key=lambda item: item.gestational_parent_id,
            )
        ],
        "techniques": [
            {
                "index": technique.index,
                "name": technique.name,
                "affordance": technique.affordance.name.lower(),
            }
            for technique in knowledge.TECHNIQUES
        ],
    }
    # Animals are their own columnar payload rather than extra columns on
    # the agent one: they are a different kind of thing, they come and go at
    # a different rate, and a UI that only draws people should not have to
    # download a herd to find that out.
    fauna_ordered = sorted(
        simulation.fauna.values(),
        key=lambda animal: animal.id,
    )
    result["fauna"] = {
        "id": [animal.id for animal in fauna_ordered],
        "x": [animal.x for animal in fauna_ordered],
        "y": [animal.y for animal in fauna_ordered],
        "age": [animal.age for animal in fauna_ordered],
        "energy": [animal.energy for animal in fauna_ordered],
        "vigilance": [animal.vigilance for animal in fauna_ordered],
    }
    if include_world:
        result["world"] = {
            "width": simulation.config.width,
            "height": simulation.config.height,
            "terrain": list(simulation.world.terrain),
            "country": list(simulation.world.country),
            "food": list(simulation.world.resources),
            "food_capacity": list(simulation.world.capacity),
            "food_productivity": list(simulation.world.productivity),
            "seasonal_amplitude": list(
                simulation.world.seasonal_amplitude
            ),
            "seasonal_phase": list(simulation.world.seasonal_phase),
            "materials": list(simulation.world.materials),
            "material_capacity": list(simulation.world.material_capacity),
            "material_productivity": list(
                simulation.world.material_productivity
            ),
        }
    if include_agents:
        ordered = sorted(
            simulation.agents.values(), key=lambda agent: agent.id
        )
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
            "partner_id": [agent.partner_id for agent in ordered],
            "bond_since_tick": [
                agent.bond_since_tick for agent in ordered
            ],
            "grandparents": [
                agent.grandparent_ids for agent in ordered
            ],
            "genome_a": [
                f"{agent.genome.haplotype_a:016x}" for agent in ordered
            ],
            "genome_b": [
                f"{agent.genome.haplotype_b:016x}" for agent in ordered
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
            "last_action_success": [
                agent.brain.last_success for agent in ordered
            ],
            "last_action_target": [
                agent.brain.last_target_id for agent in ordered
            ],
            "last_action_tick": [
                agent.brain.last_action_tick for agent in ordered
            ],
            "learned_preferences": [
                list(agent.brain.preferences) for agent in ordered
            ],
            "metabolism": [
                agent.traits.metabolism for agent in ordered
            ],
            "harvest_skill": [
                agent.traits.harvest_skill for agent in ordered
            ],
            "inherited_generosity": [
                agent.traits.generosity for agent in ordered
            ],
            "inherited_exploration": [
                agent.traits.exploration for agent in ordered
            ],
            "inherited_curiosity": [
                agent.traits.curiosity for agent in ordered
            ],
            "inherited_conformity": [
                agent.traits.conformity for agent in ordered
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
            "immune_strength": [
                agent.traits.immune_strength for agent in ordered
            ],
            "affiliation": [
                agent.traits.affiliation for agent in ordered
            ],
            "risk_tolerance": [
                agent.traits.risk_tolerance for agent in ordered
            ],
            "vision": [agent.traits.vision for agent in ordered],
            "body_condition": [
                agent.body_condition for agent in ordered
            ],
            "development": [
                agent.development_index for agent in ordered
            ],
            "development_exposure_years": [
                agent.development_exposure_years
                for agent in ordered
            ],
            "frailty": [agent.frailty for agent in ordered],
            "effective_maximum_health": [
                simulation._health_capacity(agent) for agent in ordered
            ],
            "next_reproduction_tick": [
                agent.next_reproduction_tick for agent in ordered
            ],
            "last_reproduction_tick": [
                agent.last_reproduction_tick for agent in ordered
            ],
            "birth_tick": [agent.birth_tick for agent in ordered],
            "infection_stage": [
                agent.infection_stage.name.lower()
                for agent in ordered
            ],
            "infection_ticks_remaining": [
                agent.infection_ticks_remaining for agent in ordered
            ],
            "culture_generosity": [
                agent.culture.generosity for agent in ordered
            ],
            "culture_exploration": [
                agent.culture.exploration for agent in ordered
            ],
            "culture_curiosity": [
                agent.culture.curiosity for agent in ordered
            ],
            "culture_conformity": [
                agent.culture.conformity for agent in ordered
            ],
            "research_progress": [
                agent.research_progress for agent in ordered
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
            "voyage_dx": [agent.voyage_dx for agent in ordered],
            "voyage_dy": [agent.voyage_dy for agent in ordered],
        }
    if include_agents and include_relationships:
        ordered = sorted(
            simulation.agents.values(),
            key=lambda agent: agent.id,
        )
        edges = []
        living_ids = simulation.agents.keys()
        for agent in ordered:
            for relationship in simulation.relationships.views(
                agent.relationship_slot,
                simulation.tick,
            ):
                if relationship.other_id in living_ids:
                    edges.append((
                        agent.id,
                        relationship.other_id,
                        relationship.trust,
                        relationship.balance,
                        relationship.encounters,
                        relationship.last_seen_tick,
                    ))
        edges.sort(key=lambda edge: (edge[0], edge[1]))
        result["relationships"] = {
            "source": [edge[0] for edge in edges],
            "target": [edge[1] for edge in edges],
            "trust": [edge[2] for edge in edges],
            "balance": [edge[3] for edge in edges],
            "encounters": [edge[4] for edge in edges],
            "last_seen_tick": [edge[5] for edge in edges],
        }
    return result


def _validate_entities(simulation: "Simulation") -> None:
    """Check that the world's registry and its contents agree.

    The registry is the only authority for what exists, so the population is
    the person store rather than a copy of it, and every id ever used came
    from the one identity space.
    """

    registry = simulation.entities
    assert simulation.agents is registry.of_kind(EntityKind.PERSON)
    for kind in EntityKind:
        for entity_id, entity in registry.of_kind(kind).items():
            assert entity.id == entity_id
            assert entity.kind is kind
            assert registry.kind_of(entity_id) is kind
            assert entity_id < registry.claimed_ids
            assert simulation.world.normalize(entity.x, entity.y) == (
                entity.x,
                entity.y,
            )
            creator = registry.creator_of(entity_id)
            if kind in INERT_KINDS:
                # Something made it, and that provenance survives the maker.
                assert creator is not None
                assert creator < registry.claimed_ids
            else:
                assert creator is None
    assert len(registry) == sum(
        len(registry.of_kind(kind)) for kind in EntityKind
    )
    # The spatial index is a snapshot taken at fixed points in the tick, so
    # something that died since the last rebuild may still be listed. What may
    # never happen is an identity appearing under a kind that is not its own,
    # which would let a structure read as a person to local perception.
    indexed_kinds: Dict[int, EntityKind] = {}
    for kind in EntityKind:
        for entity_ids in simulation.world.occupants_of_kind(kind).values():
            for entity_id in entity_ids:
                assert entity_id < registry.claimed_ids
                assert entity_id not in indexed_kinds
                indexed_kinds[entity_id] = kind
                current = registry.kind_of(entity_id)
                assert current is None or current is kind


def validate_state(simulation: "Simulation") -> None:
    """Raise AssertionError when a core simulation invariant is broken."""

    config = simulation.config
    assert sum(simulation.deaths_by_cause.values()) == simulation.total_deaths
    assert all(
        math.isfinite(value) and value >= 0.0
        for value in (
            simulation.world.last_food_harvested,
            simulation.world.last_food_regenerated,
            simulation._last_food_consumed,
            simulation._last_food_spoiled,
            simulation._last_food_lost_on_death,
            simulation.world.last_material_harvested,
            simulation.world.last_material_regenerated,
            simulation._last_material_consumed,
            simulation._last_material_lost_on_death,
        )
    )
    _validate_entities(simulation)
    relationship_slots = set()
    expected_dependents: Dict[int, set[int]] = {}
    for agent_id, agent in simulation.agents.items():
        assert agent.id == agent_id
        assert simulation.world.normalize(agent.x, agent.y) == (
            agent.x,
            agent.y,
        )
        assert 0.0 <= agent.energy <= config.maximum_energy
        assert 0.0 < agent.health <= simulation._health_capacity(agent) + 1e-9
        assert 0.0 <= agent.inventory <= config.inventory_capacity
        assert (
            0.0
            <= agent.material_inventory
            <= config.material_inventory_capacity
        )
        assert 0.0 <= agent.genome.heterozygosity() <= 1.0
        assert all(math.isfinite(value) for value in (
            agent.age,
            agent.energy,
            agent.health,
            agent.inventory,
            agent.material_inventory,
            agent.body_condition,
            agent.development_index,
            agent.development_exposure_years,
            agent.frailty,
        ))
        assert 0.0 <= agent.age < config.absolute_maximum_age
        assert 0.0 <= agent.body_condition <= 1.0
        assert 0.0 <= agent.development_index <= 1.0
        assert agent.development_exposure_years >= 0.0
        assert 0.0 <= agent.frailty <= 1.0
        assert isinstance(agent.infection_stage, InfectionStage)
        if agent.infection_stage is InfectionStage.SUSCEPTIBLE:
            assert agent.infection_ticks_remaining == 0
        else:
            assert agent.infection_ticks_remaining > 0
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
            assert agent.guardian_id in simulation.agents
            assert agent.guardian_id != agent.id
            assert agent.age < config.dependent_age
            expected_dependents.setdefault(
                agent.guardian_id,
                set(),
            ).add(agent.id)
        if agent.partner_id is not None:
            # A bond is symmetric, exclusive, and never points at a corpse or
            # at the agent itself. Because it is stored on both agents rather
            # than in a central index, this is the only thing keeping the two
            # copies consistent.
            assert agent.partner_id != agent.id
            partner = simulation.agents.get(agent.partner_id)
            assert partner is not None
            assert partner.partner_id == agent.id
            assert partner.reproductive_role is not agent.reproductive_role
            assert agent.bond_since_tick >= 0
            assert agent.bond_since_tick == partner.bond_since_tick
            assert agent.bond_last_together_tick >= agent.bond_since_tick
        else:
            assert agent.bond_since_tick == -1
            assert agent.bond_last_together_tick == -1
        assert len(agent.grandparent_ids) <= 4
        assert len(set(agent.grandparent_ids)) == len(
            agent.grandparent_ids
        )
        assert agent.id not in agent.grandparent_ids
        assert simulation.relationships.row_is_active(
            agent.relationship_slot
        )
        assert agent.relationship_slot not in relationship_slots
        relationship_slots.add(agent.relationship_slot)
        relationships = simulation.relationships.views(
            agent.relationship_slot,
            simulation.tick,
        )
        assert len(relationships) <= config.maximum_social_bonds
        assert all(item.other_id != agent.id for item in relationships)
    assert expected_dependents == simulation.dependents_by_guardian
    assert len(relationship_slots) == len(simulation.relationships)
    for parent_id, pregnancy in simulation.pregnancies.items():
        assert parent_id in simulation.agents
        assert pregnancy.gestational_parent_id == parent_id
        assert (
            simulation.agents[parent_id].reproductive_role
            is ReproductiveRole.OVA
        )
        assert pregnancy.due_tick > pregnancy.conception_tick
        assert 0.0 <= pregnancy.prenatal_condition <= 1.0
        assert (
            math.isfinite(pregnancy.prenatal_exposure_years)
            and pregnancy.prenatal_exposure_years >= 0.0
        )
        assert pregnancy.invested_energy >= 0.0
        assert len(pregnancy.grandparent_ids) <= 4
    for value, capacity in zip(
        simulation.world.resources,
        simulation.world.capacity,
    ):
        assert 0.0 <= value <= capacity
    for value, capacity in zip(
        simulation.world.materials,
        simulation.world.material_capacity,
    ):
        assert 0.0 <= value <= capacity


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


def _population_genetic_diversity(agents: Iterable[Agent]) -> float:
    counts = [0] * LOCUS_COUNT
    population = 0
    for agent in agents:
        population += 1
        for haplotype in (
            agent.genome.haplotype_a,
            agent.genome.haplotype_b,
        ):
            remaining = haplotype
            while remaining:
                allele = remaining & -remaining
                counts[allele.bit_length() - 1] += 1
                remaining ^= allele
    if population == 0:
        return 0.0
    allele_count = population * 2
    return fmean(
        2.0 * (count / allele_count) * (1.0 - count / allele_count)
        for count in counts
    )


def _entropy(counts: Iterable[int], category_count: int) -> float:
    values = [count for count in counts if count > 0]
    total = sum(values)
    if total == 0 or category_count <= 1:
        return 0.0
    return -sum(
        (count / total) * math.log(count / total)
        for count in values
    ) / math.log(category_count)
