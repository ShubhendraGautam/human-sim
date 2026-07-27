from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple, TYPE_CHECKING

from .entities import EntityKind
from .health import InfectionStage

if TYPE_CHECKING:
    from .brain import BrainState
    from .genetics import Genome


class Terrain(int, Enum):
    LAND = 0
    SEA = 1


class BrainKind(str, Enum):
    DELIBERATIVE = "deliberative"
    EXPLORATORY = "exploratory"
    HABITUAL = "habitual"
    SOCIAL = "social"


class ReproductiveRole(str, Enum):
    OVA = "ova"
    SPERM = "sperm"


class ActionKind(str, Enum):
    EAT = "eat"
    GATHER = "gather"
    GATHER_MATERIAL = "gather_material"
    SHARE = "share"
    COURT = "court"
    REPRODUCE = "reproduce"
    MOVE = "move"
    RESEARCH = "research"
    TEACH = "teach"
    BUILD_VESSEL = "build_vessel"
    CARE = "care"
    COMMUNICATE = "communicate"
    REST = "rest"


@dataclass(frozen=True, slots=True)
class Traits:
    metabolism: float
    harvest_skill: float
    generosity: float
    fertility: float
    exploration: float
    curiosity: float
    conformity: float
    constitution: float
    maximum_health: float
    lifespan: float
    maturity_age: float
    learning_rate: float
    risk_tolerance: float
    immune_strength: float
    affiliation: float
    brain_kind: BrainKind
    vision: int


@dataclass(frozen=True, slots=True)
class CultureState:
    generosity: float
    exploration: float
    curiosity: float
    conformity: float


@dataclass(slots=True)
class Pregnancy:
    gestational_parent_id: int
    other_parent_id: int
    genome: "Genome"
    culture: CultureState
    reproductive_role: ReproductiveRole
    belief_id: int
    generation: int
    conception_tick: int
    due_tick: int
    grandparent_ids: Tuple[int, ...] = ()
    prenatal_condition: float = 1.0
    prenatal_exposure_years: float = 0.0
    invested_energy: float = 0.0


@dataclass(slots=True)
class Agent:
    # Deliberately unannotated: a person's kind is fixed, so it is a class
    # attribute rather than a field. Plain attribute lookup keeps the spatial
    # rebuild, which reads it once per entity per tick, as cheap as it was
    # when the index could only hold people.
    kind = EntityKind.PERSON

    id: int
    x: int
    y: int
    age: float
    energy: float
    health: float
    inventory: float
    material_inventory: float
    genome: "Genome"
    traits: Traits
    culture: CultureState
    brain: "BrainState"
    reproductive_role: ReproductiveRole
    birth_country_id: int
    belief_id: int
    research_progress: float = 0.0
    knows_seafaring: bool = False
    vessel_durability: float = 0.0
    voyage_dx: int = 0
    voyage_dy: int = 0
    generation: int = 0
    parents: Optional[Tuple[int, int]] = None
    birth_tick: int = 0
    last_reproduction_tick: int = -1_000_000_000
    guardian_id: Optional[int] = None
    grandparent_ids: Tuple[int, ...] = ()
    body_condition: float = 1.0
    development_index: float = 1.0
    development_exposure_years: float = 0.0
    frailty: float = 0.0
    next_reproduction_tick: int = -1_000_000_000
    relationship_slot: int = -1
    # A pair bond is symmetric and exclusive: whenever ``partner_id`` names
    # a living agent, that agent's ``partner_id`` names this one. The
    # invariant is checked in validate_state, so no central index is needed.
    partner_id: Optional[int] = None
    bond_since_tick: int = -1
    bond_last_together_tick: int = -1
    infection_stage: InfectionStage = InfectionStage.SUSCEPTIBLE
    infection_ticks_remaining: int = 0


@dataclass(frozen=True, slots=True)
class DeathRecord:
    """What remains of someone once they stop occupying the world.

    Death is a transition, not a disappearance. The dead leave the registry
    and stop acting, but an observer must still be able to ask what became of
    a particular person, so their final causal state is kept verbatim rather
    than summarized. Nothing reads these records back into behavior: they are
    an observation surface, and the engine never consults them when deciding.

    The store is bounded, so a long run remembers recent deaths and forgets
    old ones. A forgotten person is not a living one, and callers must not
    confuse the two.
    """

    agent: "Agent"
    tick: int
    cause: str


@dataclass(frozen=True, slots=True)
class Action:
    kind: ActionKind
    actor_id: int
    target_id: Optional[int] = None
    destination: Optional[Tuple[int, int]] = None


@dataclass(frozen=True, slots=True)
class Event:
    tick: int
    kind: str
    actors: Tuple[int, ...]
    details: Tuple[Tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class Metrics:
    tick: int
    year: float
    population: int
    births: int
    conceptions: int
    pregnancies: int
    pregnancy_losses: int
    deaths: int
    total_resources: float
    total_materials: float
    mean_energy: float
    mean_health: float
    mean_inventory: float
    mean_age: float
    mean_health_fraction: float
    mean_body_condition: float
    mean_development: float
    mean_frailty: float
    juvenile_population: int
    age_bands: Dict[str, int]
    maximum_generation: int
    energy_gini: float
    resource_fraction: float
    food_per_capita: float
    total_food_inventory: float
    total_material_inventory: float
    food_harvested: float
    food_regenerated: float
    food_consumed: float
    food_spoiled: float
    food_lost_on_death: float
    material_harvested: float
    material_regenerated: float
    material_consumed: float
    material_lost_on_death: float
    seasonal_productivity: float
    seafaring_population: int
    vessels: int
    inventions: int
    sea_crossings: int
    country_population: Dict[int, int]
    belief_population: Dict[int, int]
    brain_population: Dict[str, int]
    reproductive_roles: Dict[str, int]
    mean_heterozygosity: float
    genetic_diversity: float
    action_entropy: float
    actions: Dict[str, int]
    attempted_actions: Dict[str, int]
    failed_actions: Dict[str, int]
    deaths_by_cause: Dict[str, int]
    infections: int
    recoveries: int
    disease_population: Dict[str, int]
    mean_remembered_connections: float
    mean_social_connections: float
    mean_trust: float
    isolated_population: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "tick": self.tick,
            "year": self.year,
            "population": self.population,
            "births": self.births,
            "conceptions": self.conceptions,
            "pregnancies": self.pregnancies,
            "pregnancy_losses": self.pregnancy_losses,
            "deaths": self.deaths,
            "total_resources": self.total_resources,
            "total_materials": self.total_materials,
            "mean_energy": self.mean_energy,
            "mean_health": self.mean_health,
            "mean_inventory": self.mean_inventory,
            "mean_age": self.mean_age,
            "mean_health_fraction": self.mean_health_fraction,
            "mean_body_condition": self.mean_body_condition,
            "mean_development": self.mean_development,
            "mean_frailty": self.mean_frailty,
            "juvenile_population": self.juvenile_population,
            "age_bands": dict(self.age_bands),
            "maximum_generation": self.maximum_generation,
            "energy_gini": self.energy_gini,
            "resource_fraction": self.resource_fraction,
            "food_per_capita": self.food_per_capita,
            "total_food_inventory": self.total_food_inventory,
            "total_material_inventory": self.total_material_inventory,
            "food_harvested": self.food_harvested,
            "food_regenerated": self.food_regenerated,
            "food_consumed": self.food_consumed,
            "food_spoiled": self.food_spoiled,
            "food_lost_on_death": self.food_lost_on_death,
            "material_harvested": self.material_harvested,
            "material_regenerated": self.material_regenerated,
            "material_consumed": self.material_consumed,
            "material_lost_on_death": self.material_lost_on_death,
            "seasonal_productivity": self.seasonal_productivity,
            "seafaring_population": self.seafaring_population,
            "vessels": self.vessels,
            "inventions": self.inventions,
            "sea_crossings": self.sea_crossings,
            "country_population": dict(self.country_population),
            "belief_population": dict(self.belief_population),
            "brain_population": dict(self.brain_population),
            "reproductive_roles": dict(self.reproductive_roles),
            "mean_heterozygosity": self.mean_heterozygosity,
            "genetic_diversity": self.genetic_diversity,
            "action_entropy": self.action_entropy,
            "actions": dict(self.actions),
            "attempted_actions": dict(self.attempted_actions),
            "failed_actions": dict(self.failed_actions),
            "deaths_by_cause": dict(self.deaths_by_cause),
            "infections": self.infections,
            "recoveries": self.recoveries,
            "disease_population": dict(self.disease_population),
            "mean_remembered_connections": (
                self.mean_remembered_connections
            ),
            "mean_social_connections": self.mean_social_connections,
            "mean_trust": self.mean_trust,
            "isolated_population": self.isolated_population,
        }
