from dataclasses import dataclass, fields
from typing import Any, Dict


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """All tunable rules for a simulation run.

    Keeping policy here makes experiments explicit and prevents behavior from
    being hidden in entry points or UI code.
    """

    width: int = 64
    height: int = 64
    wrap_world: bool = False
    initial_population: int = 200
    ticks_per_year: int = 12

    cell_capacity: float = 24.0
    initial_resource_fraction: float = 0.65
    initial_resource_variation: float = 0.25
    resource_regeneration: float = 0.18
    minimum_cell_fertility: float = 0.55
    maximum_cell_fertility: float = 1.45
    material_cell_capacity: float = 10.0
    material_regeneration: float = 0.04

    maximum_energy: float = 100.0
    initial_energy_minimum: float = 45.0
    initial_energy_maximum: float = 80.0
    maximum_health: float = 100.0
    minimum_health_fraction: float = 0.75
    maximum_health_fraction: float = 1.25
    inventory_capacity: float = 12.0
    material_inventory_capacity: float = 10.0
    initial_inventory: float = 2.0
    food_energy: float = 9.0
    eat_amount: float = 2.0
    harvest_amount: float = 2.2
    material_harvest_amount: float = 1.2
    share_amount: float = 1.5

    starvation_damage: float = 4.0
    health_recovery: float = 0.15
    aging_starts_at: float = 65.0
    aging_damage_per_year: float = 1.8
    maximum_age: float = 105.0
    minimum_lifespan: float = 55.0

    maturity_age: float = 16.0
    minimum_maturity_age: float = 14.0
    maximum_maturity_age: float = 20.0
    initial_age_minimum: float = 16.0
    initial_age_maximum: float = 42.0
    reproduction_energy: float = 72.0
    reproduction_cost: float = 24.0
    reproduction_cooldown_years: float = 1.5
    newborn_energy: float = 35.0

    base_metabolism_minimum: float = 0.70
    base_metabolism_maximum: float = 1.25
    harvest_skill_minimum: float = 0.70
    harvest_skill_maximum: float = 1.30
    vision_minimum: int = 1
    vision_maximum: int = 4
    gene_mutation_probability: float = 0.015
    gene_mutation_scale: float = 0.08
    founder_genetic_variation: float = 0.25
    minimum_learning_rate: float = 0.02
    maximum_learning_rate: float = 0.22
    learning_metabolic_cost: float = 0.12
    vision_metabolic_cost: float = 0.08
    cultural_trait_variation: float = 0.25
    interaction_radius: int = 1

    hunger_weight: float = 4.0
    gather_weight: float = 2.4
    gather_inventory_emphasis: float = 0.55
    sharing_weight: float = 1.8
    reproduction_weight: float = 2.0
    movement_weight: float = 1.2
    movement_energy_cost: float = 0.10
    movement_scarcity_emphasis: float = 0.65
    crowding_weight: float = 0.18
    decision_noise: float = 0.20
    rest_utility: float = 0.05
    material_gather_weight: float = 0.8
    material_attraction_weight: float = 0.35

    research_weight: float = 1.4
    research_energy_minimum: float = 55.0
    research_energy_cost: float = 2.0
    research_material_cost: float = 0.5
    seafaring_discovery_threshold: float = 8.0
    research_gain_minimum: float = 0.5
    research_gain_maximum: float = 1.5
    teaching_weight: float = 1.2
    cultural_transmission_rate: float = 0.15
    vessel_build_weight: float = 3.0
    vessel_material_cost: float = 6.0
    vessel_energy_cost: float = 4.0
    vessel_durability: float = 30.0
    sea_movement_cost: float = 1.0
    sea_exploration_weight: float = 2.2
    voyage_weight: float = 3.0

    exploratory_temperature: float = 0.7
    habit_preference_weight: float = 1.0
    social_imitation_weight: float = 0.8
    learned_preference_limit: float = 2.0
    successful_action_reward: float = 0.1
    failed_action_reward: float = -0.2
    material_welfare_value: float = 0.5
    sharing_intrinsic_reward: float = 0.3
    reproduction_intrinsic_reward: float = 0.8
    research_intrinsic_reward: float = 0.5
    teaching_intrinsic_reward: float = 0.3
    movement_intrinsic_reward: float = 0.1

    maximum_conception_probability: float = 0.85
    minimum_reproductive_health_fraction: float = 0.5
    aging_starts_fraction: float = 0.65

    metrics_interval: int = 10
    metrics_history_capacity: int = 10_000
    event_log_capacity: int = 1_000

    def __post_init__(self) -> None:
        positive = (
            "width",
            "height",
            "ticks_per_year",
            "cell_capacity",
            "maximum_energy",
            "maximum_health",
            "inventory_capacity",
            "food_energy",
            "material_cell_capacity",
            "material_inventory_capacity",
            "material_harvest_amount",
            "vessel_durability",
            "metrics_interval",
        )
        for name in positive:
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.initial_population < 0:
            raise ValueError("initial_population cannot be negative")
        nonnegative = (
            "resource_regeneration",
            "material_regeneration",
            "initial_inventory",
            "starvation_damage",
            "health_recovery",
            "aging_damage_per_year",
            "reproduction_cost",
            "reproduction_cooldown_years",
            "mutation_rate",
            "cultural_trait_variation",
            "interaction_radius",
            "hunger_weight",
            "gather_weight",
            "sharing_weight",
            "reproduction_weight",
            "movement_weight",
            "movement_energy_cost",
            "crowding_weight",
            "decision_noise",
            "rest_utility",
            "material_gather_weight",
            "material_attraction_weight",
            "research_weight",
            "research_energy_minimum",
            "research_energy_cost",
            "research_material_cost",
            "seafaring_discovery_threshold",
            "research_gain_minimum",
            "research_gain_maximum",
            "teaching_weight",
            "cultural_transmission_rate",
            "vessel_build_weight",
            "vessel_material_cost",
            "vessel_energy_cost",
            "vessel_durability",
            "sea_movement_cost",
            "sea_exploration_weight",
            "voyage_weight",
            "metrics_history_capacity",
            "event_log_capacity",
        )
        for name in nonnegative:
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if not 0.0 <= self.initial_resource_fraction <= 1.0:
            raise ValueError("initial_resource_fraction must be between 0 and 1")
        fractions = (
            "initial_resource_variation",
            "gather_inventory_emphasis",
            "movement_scarcity_emphasis",
            "cultural_transmission_rate",
            "cultural_trait_variation",
        )
        for name in fractions:
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.vision_minimum < 0 or self.vision_maximum < self.vision_minimum:
            raise ValueError("invalid vision range")
        if self.initial_age_maximum < self.initial_age_minimum:
            raise ValueError("invalid initial age range")
        if self.initial_energy_maximum < self.initial_energy_minimum:
            raise ValueError("invalid initial energy range")
        if self.maximum_cell_fertility < self.minimum_cell_fertility:
            raise ValueError("invalid cell fertility range")
        if self.minimum_cell_fertility <= 0.0:
            raise ValueError("cell fertility must be positive")
        if self.initial_energy_maximum > self.maximum_energy:
            raise ValueError("initial energy cannot exceed maximum_energy")
        if self.newborn_energy > self.maximum_energy:
            raise ValueError("newborn_energy cannot exceed maximum_energy")
        if self.initial_inventory > self.inventory_capacity:
            raise ValueError("initial inventory cannot exceed inventory_capacity")
        if self.reproduction_cost > self.reproduction_energy:
            raise ValueError("reproduction_cost cannot exceed reproduction_energy")
        if self.maximum_age <= self.aging_starts_at:
            raise ValueError("maximum_age must be greater than aging_starts_at")
        if self.maturity_age >= self.maximum_age:
            raise ValueError("maturity_age must be less than maximum_age")
        if self.research_gain_maximum < self.research_gain_minimum:
            raise ValueError("invalid research gain range")

    def to_dict(self) -> Dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in fields(self)}
