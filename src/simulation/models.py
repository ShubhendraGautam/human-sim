from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple, TYPE_CHECKING

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
    REPRODUCE = "reproduce"
    MOVE = "move"
    RESEARCH = "research"
    TEACH = "teach"
    BUILD_VESSEL = "build_vessel"
    CARE = "care"
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
    brain_kind: BrainKind
    vision: int


@dataclass(frozen=True, slots=True)
class CultureState:
    generosity: float
    exploration: float
    curiosity: float
    conformity: float


@dataclass(frozen=True, slots=True)
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


@dataclass(slots=True)
class Agent:
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
    maximum_generation: int
    energy_gini: float
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
            "maximum_generation": self.maximum_generation,
            "energy_gini": self.energy_gini,
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
        }
