import math
from dataclasses import dataclass, fields
from typing import Any, Dict

CONFIG_SCHEMA_VERSION = 2


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
    seasonality_strength: float = 0.35
    seasonal_equator_fraction: float = 0.10
    food_spoilage_rate_per_year: float = 0.08
    material_cell_capacity: float = 10.0
    material_regeneration: float = 0.04
    materials_renewable: bool = False

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
    care_amount: float = 1.5

    starvation_damage: float = 4.0
    health_recovery: float = 0.15
    health_recovery_energy_cost: float = 0.08
    aging_damage_per_year: float = 1.8
    maximum_age: float = 105.0
    minimum_lifespan: float = 55.0
    absolute_maximum_age: float = 125.0
    nutrition_memory_years: float = 0.5
    founder_development_minimum: float = 0.78
    founder_development_maximum: float = 1.0
    minimum_development_health_fraction: float = 0.65
    development_harvest_influence: float = 0.25
    development_fertility_influence: float = 0.30
    frailty_accumulation_per_year: float = 0.035
    frailty_age_acceleration: float = 4.0
    frailty_constitution_protection: float = 0.50
    frailty_condition_penalty: float = 0.75
    frailty_health_capacity_loss: float = 0.55
    frailty_recovery_penalty: float = 0.85
    baseline_mortality_rate_per_year: float = 0.001
    frailty_mortality_rate_per_year: float = 0.25
    initial_exposed_fraction: float = 0.02
    disease_contact_radius: int = 1
    disease_transmission_rate_per_year: float = 0.35
    disease_incubation_years: float = 0.25
    disease_infectious_years: float = 0.5
    disease_immunity_years: float = 3.0
    disease_health_damage_per_year: float = 8.0
    disease_energy_cost_per_year: float = 2.0
    vertical_transmission_probability: float = 0.02
    maternal_immunity_years: float = 0.5

    minimum_maturity_age: float = 14.0
    maximum_maturity_age: float = 20.0
    initial_age_minimum: float = 16.0
    initial_age_maximum: float = 42.0
    reproduction_energy: float = 72.0
    reproduction_cost: float = 24.0
    reproduction_cooldown_years: float = 1.5
    newborn_energy: float = 35.0
    gestation_years: float = 0.75
    gestation_energy_cost_per_tick: float = 0.15
    birth_energy_cost: float = 4.0
    minimum_gestation_health_fraction: float = 0.25
    minimum_reproductive_body_condition: float = 0.45
    fecundity_maturation_ramp_years: float = 2.0
    ova_fecundity_decline_age: float = 32.0
    ova_reproductive_end_age: float = 52.0
    sperm_fecundity_decline_age: float = 45.0
    sperm_reproductive_end_age: float = 80.0
    postpartum_cooldown_years: float = 1.0
    pregnancy_loss_base_rate_per_year: float = 0.06
    pregnancy_loss_condition_rate_per_year: float = 0.45
    birth_health_cost: float = 2.0
    dependent_age: float = 6.0
    juvenile_metabolism_fraction: float = 0.6
    juvenile_capability_floor: float = 0.15
    dependent_movement_energy_cost: float = 0.03
    vessel_passenger_capacity: int = 4

    base_metabolism_minimum: float = 0.70
    base_metabolism_maximum: float = 1.25
    harvest_skill_minimum: float = 0.70
    harvest_skill_maximum: float = 1.30
    vision_minimum: int = 1
    vision_maximum: int = 4
    gene_mutation_probability: float = 0.015
    gene_crossover_probability: float = 0.65
    founder_genetic_variation: float = 0.25
    minimum_learning_rate: float = 0.02
    maximum_learning_rate: float = 0.22
    learning_metabolic_cost: float = 0.12
    vision_metabolic_cost: float = 0.08
    constitution_metabolic_cost: float = 0.10
    longevity_metabolic_cost: float = 0.08
    fertility_metabolic_cost: float = 0.10
    harvest_metabolic_cost: float = 0.08
    immunity_metabolic_cost: float = 0.08
    affiliation_metabolic_cost: float = 0.02
    early_maturation_health_cost: float = 0.15
    early_maturation_lifespan_cost: float = 0.12
    cultural_trait_variation: float = 0.25
    cultural_influence: float = 0.5
    cultural_inheritance_noise: float = 0.04
    interaction_radius: int = 1

    hunger_weight: float = 4.0
    gather_weight: float = 2.4
    gather_inventory_emphasis: float = 0.55
    sharing_weight: float = 1.8
    care_weight: float = 4.0
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
    maximum_social_neighbors: int = 16
    maximum_social_bonds: int = 12
    relationship_half_life_years: float = 8.0
    relationship_learning_rate: float = 0.25
    relationship_balance_limit: float = 4.0
    relationship_preference_weight: float = 0.55
    communication_weight: float = 0.55
    communication_energy_cost: float = 0.08
    social_success_memory_years: float = 1.0

    metrics_interval: int = 10
    metrics_history_capacity: int = 10_000
    event_log_capacity: int = 1_000

    def __post_init__(self) -> None:
        integer_fields = (
            "width",
            "height",
            "initial_population",
            "ticks_per_year",
            "disease_contact_radius",
            "vision_minimum",
            "vision_maximum",
            "interaction_radius",
            "vessel_passenger_capacity",
            "maximum_social_neighbors",
            "maximum_social_bonds",
            "metrics_interval",
            "metrics_history_capacity",
            "event_log_capacity",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be an integer")
        for name in ("wrap_world", "materials_renewable"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        for item in fields(self):
            value = getattr(self, item.name)
            if (
                item.name not in integer_fields
                and item.name not in ("wrap_world", "materials_renewable")
                and (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                )
            ):
                raise ValueError(f"{item.name} must be numeric")
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and not math.isfinite(value)
            ):
                raise ValueError(f"{item.name} must be finite")
        positive = (
            "width",
            "height",
            "ticks_per_year",
            "cell_capacity",
            "maximum_energy",
            "maximum_health",
            "inventory_capacity",
            "food_energy",
            "eat_amount",
            "harvest_amount",
            "share_amount",
            "material_cell_capacity",
            "material_inventory_capacity",
            "material_harvest_amount",
            "vessel_durability",
            "exploratory_temperature",
            "learned_preference_limit",
            "maximum_social_neighbors",
            "maximum_social_bonds",
            "relationship_half_life_years",
            "relationship_balance_limit",
            "social_success_memory_years",
            "gestation_years",
            "care_amount",
            "dependent_age",
            "vessel_passenger_capacity",
            "nutrition_memory_years",
            "absolute_maximum_age",
            "fecundity_maturation_ramp_years",
            "disease_incubation_years",
            "disease_infectious_years",
            "disease_immunity_years",
            "maternal_immunity_years",
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
            "seasonality_strength",
            "seasonal_equator_fraction",
            "food_spoilage_rate_per_year",
            "initial_inventory",
            "starvation_damage",
            "health_recovery",
            "health_recovery_energy_cost",
            "aging_damage_per_year",
            "frailty_accumulation_per_year",
            "frailty_age_acceleration",
            "frailty_constitution_protection",
            "frailty_condition_penalty",
            "frailty_health_capacity_loss",
            "frailty_recovery_penalty",
            "baseline_mortality_rate_per_year",
            "frailty_mortality_rate_per_year",
            "initial_exposed_fraction",
            "disease_contact_radius",
            "disease_transmission_rate_per_year",
            "disease_health_damage_per_year",
            "disease_energy_cost_per_year",
            "vertical_transmission_probability",
            "reproduction_cost",
            "reproduction_cooldown_years",
            "gene_mutation_probability",
            "gene_crossover_probability",
            "founder_genetic_variation",
            "minimum_learning_rate",
            "maximum_learning_rate",
            "learning_metabolic_cost",
            "vision_metabolic_cost",
            "constitution_metabolic_cost",
            "longevity_metabolic_cost",
            "fertility_metabolic_cost",
            "harvest_metabolic_cost",
            "immunity_metabolic_cost",
            "affiliation_metabolic_cost",
            "early_maturation_health_cost",
            "early_maturation_lifespan_cost",
            "cultural_trait_variation",
            "cultural_influence",
            "cultural_inheritance_noise",
            "interaction_radius",
            "hunger_weight",
            "gather_weight",
            "sharing_weight",
            "care_weight",
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
            "habit_preference_weight",
            "social_imitation_weight",
            "material_welfare_value",
            "sharing_intrinsic_reward",
            "reproduction_intrinsic_reward",
            "research_intrinsic_reward",
            "teaching_intrinsic_reward",
            "movement_intrinsic_reward",
            "maximum_conception_probability",
            "minimum_reproductive_health_fraction",
            "aging_starts_fraction",
            "gestation_energy_cost_per_tick",
            "birth_energy_cost",
            "minimum_gestation_health_fraction",
            "minimum_reproductive_body_condition",
            "postpartum_cooldown_years",
            "pregnancy_loss_base_rate_per_year",
            "pregnancy_loss_condition_rate_per_year",
            "birth_health_cost",
            "juvenile_metabolism_fraction",
            "juvenile_capability_floor",
            "dependent_movement_energy_cost",
            "early_maturation_health_cost",
            "early_maturation_lifespan_cost",
            "relationship_learning_rate",
            "relationship_preference_weight",
            "communication_weight",
            "communication_energy_cost",
            "metrics_history_capacity",
            "event_log_capacity",
        )
        for name in nonnegative:
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if not 0.0 <= self.initial_resource_fraction <= 1.0:
            raise ValueError(
                "initial_resource_fraction must be between 0 and 1"
            )
        fractions = (
            "initial_resource_variation",
            "seasonality_strength",
            "seasonal_equator_fraction",
            "food_spoilage_rate_per_year",
            "initial_exposed_fraction",
            "vertical_transmission_probability",
            "gather_inventory_emphasis",
            "movement_scarcity_emphasis",
            "cultural_transmission_rate",
            "cultural_trait_variation",
            "cultural_influence",
            "gene_mutation_probability",
            "gene_crossover_probability",
            "founder_genetic_variation",
            "maximum_conception_probability",
            "minimum_reproductive_health_fraction",
            "aging_starts_fraction",
            "minimum_gestation_health_fraction",
            "minimum_reproductive_body_condition",
            "juvenile_metabolism_fraction",
            "juvenile_capability_floor",
            "founder_development_minimum",
            "founder_development_maximum",
            "minimum_development_health_fraction",
            "development_harvest_influence",
            "development_fertility_influence",
            "frailty_constitution_protection",
            "frailty_condition_penalty",
            "frailty_health_capacity_loss",
            "frailty_recovery_penalty",
            "early_maturation_health_cost",
            "early_maturation_lifespan_cost",
            "relationship_learning_rate",
            "relationship_preference_weight",
        )
        for name in fractions:
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if (
            self.vision_minimum < 0
            or self.vision_maximum < self.vision_minimum
        ):
            raise ValueError("invalid vision range")
        if self.initial_age_maximum < self.initial_age_minimum:
            raise ValueError("invalid initial age range")
        if (
            self.initial_age_minimum < 0.0
            or self.initial_age_maximum >= self.absolute_maximum_age
        ):
            raise ValueError(
                "founder ages must be within the simulated lifespan"
            )
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
            raise ValueError(
                "initial inventory cannot exceed inventory_capacity"
            )
        if self.reproduction_cost > self.reproduction_energy:
            raise ValueError(
                "reproduction_cost cannot exceed reproduction_energy"
            )
        if self.research_gain_maximum < self.research_gain_minimum:
            raise ValueError("invalid research gain range")
        if self.minimum_health_fraction <= 0.0:
            raise ValueError("minimum_health_fraction must be positive")
        if self.maximum_health_fraction < self.minimum_health_fraction:
            raise ValueError("invalid health fraction range")
        if (
            self.minimum_lifespan <= 0.0
            or self.maximum_age <= self.minimum_lifespan
        ):
            raise ValueError("invalid lifespan range")
        if (
            self.minimum_maturity_age < 0.0
            or self.maximum_maturity_age < self.minimum_maturity_age
            or self.maximum_maturity_age >= self.minimum_lifespan
        ):
            raise ValueError("invalid maturity range")
        if self.maximum_learning_rate < self.minimum_learning_rate:
            raise ValueError("invalid learning-rate range")
        if self.base_metabolism_minimum <= 0.0:
            raise ValueError("base metabolism must be positive")
        if self.base_metabolism_maximum < self.base_metabolism_minimum:
            raise ValueError("invalid metabolism range")
        if self.harvest_skill_minimum < 0.0:
            raise ValueError("harvest skill cannot be negative")
        if self.harvest_skill_maximum < self.harvest_skill_minimum:
            raise ValueError("invalid harvest-skill range")
        if self.initial_energy_minimum < 0.0 or self.newborn_energy < 0.0:
            raise ValueError("initial and newborn energy cannot be negative")
        if (
            self.founder_development_maximum
            < self.founder_development_minimum
        ):
            raise ValueError("invalid founder development range")
        if self.absolute_maximum_age <= self.maximum_age:
            raise ValueError("absolute_maximum_age must exceed maximum_age")
        if not (
            self.ova_fecundity_decline_age
            < self.ova_reproductive_end_age
            <= self.absolute_maximum_age
        ):
            raise ValueError("invalid ova fecundity ages")
        if not (
            self.sperm_fecundity_decline_age
            < self.sperm_reproductive_end_age
            <= self.absolute_maximum_age
        ):
            raise ValueError("invalid sperm fecundity ages")
        if self.maximum_maturity_age >= min(
            self.ova_reproductive_end_age,
            self.sperm_reproductive_end_age,
        ):
            raise ValueError("reproductive end ages must follow maturity")
        if self.dependent_age >= self.minimum_maturity_age:
            raise ValueError("dependent_age must precede maturity")
        if (
            self.maximum_maturity_age
            + self.fecundity_maturation_ramp_years
            > min(
                self.ova_fecundity_decline_age,
                self.sperm_fecundity_decline_age,
            )
        ):
            raise ValueError(
                "fecundity decline must follow the maturation ramp"
            )
        if (
            self.early_maturation_health_cost >= 1.0
            or self.early_maturation_lifespan_cost >= 1.0
        ):
            raise ValueError("maturation costs must leave viable phenotypes")
        if self.research_energy_minimum < self.research_energy_cost:
            raise ValueError(
                "research_energy_minimum cannot be below research_energy_cost"
            )
        if self.maximum_social_bonds > 255:
            raise ValueError("maximum_social_bonds cannot exceed 255")

    def to_dict(self) -> Dict[str, Any]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
        }
