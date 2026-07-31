import math
from dataclasses import dataclass, fields
from typing import Any, Dict

CONFIG_SCHEMA_VERSION = 8


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
    # Energy per year at one full unit of local seasonal departure. The
    # season itself is already locally observable; charging for its absolute
    # departure makes both hot and cold extremes physical rather than merely
    # colors on the food-renewal layer. At zero the pre-exposure model is
    # recovered exactly, including its arithmetic and random streams.
    environmental_energy_cost_per_year: float = 8.0
    food_spoilage_rate_per_year: float = 0.08
    material_cell_capacity: float = 10.0
    material_regeneration: float = 0.04
    materials_renewable: bool = False

    # Inert, material-built objects. Their properties are effects, never
    # labels: insulation, food capacity, occupancy capacity, and condition.
    # At false the legacy action-space width is retained, so the switch also
    # reproduces pre-artifact neural genomes and random streams exactly.
    artifacts_enabled: bool = True
    artifact_material_cost: float = 6.0
    artifact_energy_cost: float = 3.0
    artifact_build_weight: float = 4.0
    artifact_storage_weight: float = 0.35
    artifact_insulation: float = 0.75
    artifact_storage_capacity: float = 18.0
    artifact_occupancy_capacity: int = 6
    artifact_decay_rate_per_year: float = 0.08
    artifact_maintenance_material_cost: float = 1.0
    artifact_maintenance_energy_cost: float = 0.5
    artifact_maintenance_restore: float = 0.30

    # Animals. They graze the same layer people harvest, so a herd is both
    # competition for food and food itself, and neither of those is written
    # anywhere as a rule about people. There is no spawner: a population
    # hunted to nothing stays nothing. At density zero the world has no
    # animals in it and runs reproduce the model from before it did.
    fauna_enabled: bool = True
    initial_fauna_density: float = 0.10
    fauna_metabolism: float = 16.0
    fauna_graze_amount: float = 0.55
    fauna_forage_energy: float = 5.0
    fauna_energy_maximum: float = 22.0
    fauna_birth_energy: float = 7.0
    fauna_reproduction_energy: float = 15.0
    fauna_reproduction_cost: float = 6.0
    fauna_birth_rate: float = 0.18
    fauna_maturity_age: float = 2.0
    fauna_maximum_age: float = 14.0
    fauna_mortality_rate_per_year: float = 0.12
    fauna_wander_rate: float = 0.25
    fauna_trait_variation: float = 0.25
    fauna_mutation_scale: float = 0.05
    fauna_vigilance: float = 0.5
    fauna_fecundity: float = 0.6
    # How much harder a wary animal is to catch than a placid one. This is
    # what turns hunting pressure into selection rather than subtraction.
    fauna_vigilance_weight: float = 2.0
    fauna_meat_per_energy: float = 0.55

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
    # How far nutrition has to fall before a body starts paying for it. At
    # zero the damage is the old cliff at spent energy and nothing warns a
    # population before it collapses.
    malnutrition_threshold: float = 0.30
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
    # Standing in for reservoirs this model does not contain yet: water,
    # soil, and the animals not on the canvas. Without a way back in, one
    # outbreak that fizzles leaves a world that can never be sick again.
    environmental_exposure_rate_per_year: float = 0.004
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

    # Hunting. An attempt costs energy whether or not it succeeds, which is
    # what makes it a gamble against gathering rather than a better version
    # of it, and what leaves room for it to be the wrong choice.
    hunt_weight: float = 2.6
    hunt_energy_cost: float = 0.8
    hunt_success_base: float = 0.55

    research_weight: float = 1.4
    research_energy_minimum: float = 55.0
    research_energy_cost: float = 2.0
    research_material_cost: float = 0.5
    # Base work a discovery takes. Each technique scales it by its own
    # effort, so this is one knob for how hard the world is to work out
    # rather than a threshold belonging to any single skill.
    discovery_threshold: float = 8.0
    research_gain_minimum: float = 0.5
    research_gain_maximum: float = 1.5
    teaching_weight: float = 1.2
    cultural_transmission_rate: float = 0.15
    vessel_build_weight: float = 3.0
    vessel_material_cost: float = 6.0
    vessel_energy_cost: float = 4.0
    vessel_durability: float = 30.0
    # A vessel is consumed by time at sea rather than by distance, so nobody
    # can idle on open water indefinitely.
    sea_vessel_wear_per_tick: float = 1.0
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
    # Language. A population starts mute; these decide how readily a word is
    # coined when one is missing, copied when one is heard, and misheard when
    # it is copied. At rate zero nobody ever speaks a word and runs reproduce
    # exactly as they did before language existed.
    # Inherited decision networks. At weight zero the network is evaluated
    # but contributes nothing, and runs reproduce the model from before
    # brains were heritable; that is the arm every experiment compares to.
    neural_brains_enabled: bool = True
    neural_hidden_units: int = 6
    # How loudly the brain speaks in a decision. It was 0.35, which put the
    # whole network at about 0.05 utility units against a decision_noise of
    # 0.20 — the brain was quieter than the dice, and on/off runs were
    # indistinguishable. Raised so that a brain which has *learned*
    # something can be heard; a newborn's inherited weights are small enough
    # that it still starts out roughly as noisy as it always was.
    neural_output_weight: float = 1.2
    neural_founder_scale: float = 0.12
    neural_mutation_rate: float = 0.06
    neural_mutation_scale: float = 0.09
    neural_weight_limit: float = 3.0
    # Temporal neural memory. At zero the inherited network is the original
    # feed-forward brain. Above zero, hidden activations from the previous
    # decision feed into the next through inherited, mutable recurrent
    # connections. The state itself lives only for one lifetime.
    #
    # Off until measured. Recurrence can express history-dependent policies,
    # but capability is not usefulness, and it adds one active_units-squared
    # matrix evaluation to every decision. Founder recurrent weights use an
    # independent deterministic stream, so zero and nonzero arms still start
    # with the same bodies and world.
    neural_recurrence_weight: float = 0.0
    # What a brain costs to keep, per year, per unit of mean absolute
    # inherited weight.
    #
    # Zero, and off, because it is unproven. It exists because the measured
    # behaviour of the current model is that mean network magnitude climbs
    # from 0.106 to 0.148 over 1500 years *identically* whether or not the
    # network is allowed to influence a decision — mutation inflates it and
    # nothing pushes back. A brain that is free has no reason to be small,
    # so its size is a random walk rather than a trade-off.
    #
    # In living things neural tissue is among the most expensive to run, and
    # that expense is exactly what makes brain size something evolution has
    # to decide rather than accumulate. Charging for it gives selection a
    # reason to discard opinions that are not earning their keep, and makes
    # a strong opinion something a person pays for.
    #
    # Not a claim that this improves anything. It is an arm to compare, and
    # the honest outcome may be that it costs population for nothing, in
    # which case it stays at zero like lifetime plasticity did.
    neural_maintenance_cost: float = 0.0

    # A brain that is built over a life rather than issued at birth.
    #
    # Off, because `neural_hidden_units` being a number somebody chose is a
    # real limitation but an unproven one. With it on, two things become
    # heritable that were previously fixed: the ceiling a brain may reach,
    # and how fast it grows toward it. Neither is the brain itself — a child
    # is born at `neural_birth_units` however developed its parents became,
    # for the same reason learned weights are not passed on.
    #
    # Selection then acts on something it could not reach before: whether
    # building a large brain is worth what it costs. That question only has
    # teeth alongside `neural_maintenance_cost`, which is why the two arrived
    # together and why either alone is a partial experiment.
    neural_growth_enabled: bool = False
    neural_birth_units: int = 2
    neural_minimum_ceiling: int = 3
    neural_maximum_ceiling: int = 10
    neural_minimum_growth_rate: float = 0.05
    neural_maximum_growth_rate: float = 0.60
    neural_ceiling_mutation_rate: float = 0.08
    neural_growth_rate_mutation_scale: float = 0.05
    # Lifetime plasticity. Inherited weights are where a brain starts; this
    # is how far it can move within one life. Changing your own mind costs
    # energy, because a free one is strictly dominant and would be taken by
    # everybody for no reason.
    #
    # **Off by default, on measured evidence.** Six seeds in a scarce world:
    # no learning finished at 23.7 people, learning at 17.8, and learning
    # with the energy price removed at 21.7 — at best neutral, at worst a
    # quarter of the population. The mechanism is correct and tested and the
    # world may simply not reward it yet (see C4 in the design checklist),
    # but shipping it on would be shipping decoration as fact. Raise it to
    # experiment; the interesting question is what has to become true about
    # the world before it starts paying.
    plasticity_rate: float = 0.0
    plasticity_energy_cost: float = 0.02
    plasticity_limit: float = 1.5
    # Remembering places. At capacity zero nobody remembers anywhere and
    # foraging is the pure local gradient it was before.
    place_memory_capacity: int = 4
    place_memory_half_life_years: float = 2.0
    place_return_weight: float = 1.6

    language_enabled: bool = True
    language_invention_rate: float = 0.04
    language_adoption_rate: float = 0.8
    language_mutation_rate: float = 0.002
    # How much credit a freshly taken-up word gets. At one, adoption is a
    # voter process: whatever you heard last wins, everyone overwrites
    # everyone, and no form ever becomes common enough to be a language.
    language_initial_confidence: int = 2
    # Someone who has no word at all has nothing to lose by taking yours.
    # Replacing a form you already use is a different matter, so the two are
    # not equally likely; this is how much readier the empty case is.
    language_naive_adoption_bonus: float = 0.6
    # Whether a caregiver's speech reaches the dependent they are feeding.
    # This is the channel that carries a language across a generation: at
    # zero, every child starts mute and re-invents, and vocabulary cannot
    # accumulate past a single lifetime.
    language_caregiver_transmission: bool = True
    social_success_memory_years: float = 1.0

    # Pair bonding. Courtship is one-sided with consent, so a couple pays the
    # cost of finding each other once rather than once per child.
    courtship_weight: float = 1.2
    courtship_energy_cost: float = 0.10
    bond_acceptance_base: float = 0.55
    bond_separation_years: float = 3.0
    bond_dissolution_trust: float = -0.45
    bond_movement_weight: float = 2.5

    metrics_interval: int = 10
    metrics_history_capacity: int = 10_000
    event_log_capacity: int = 1_000
    # How many of the recently dead stay answerable to an observer.
    death_record_capacity: int = 1_000

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
            "artifact_occupancy_capacity",
            "maximum_social_neighbors",
            "maximum_social_bonds",
            "metrics_interval",
            "metrics_history_capacity",
            "event_log_capacity",
            "death_record_capacity",
            "neural_hidden_units",
            "language_initial_confidence",
            "place_memory_capacity",
            "neural_birth_units",
            "neural_minimum_ceiling",
            "neural_maximum_ceiling",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be an integer")
        for name in ("wrap_world", "materials_renewable",
                     "neural_growth_enabled",
                     "language_enabled", "neural_brains_enabled",
                     "language_caregiver_transmission",
                     "fauna_enabled", "artifacts_enabled"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        for item in fields(self):
            value = getattr(self, item.name)
            if (
                item.name not in integer_fields
                and item.name not in (
                    "wrap_world",
                    "materials_renewable",
                    "language_enabled",
                    "neural_brains_enabled",
                    "neural_growth_enabled",
                    "language_caregiver_transmission",
                    "fauna_enabled",
                    "artifacts_enabled",
                )
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
            "artifact_storage_capacity",
            "artifact_occupancy_capacity",
            "fauna_forage_energy",
            "fauna_energy_maximum",
            "fauna_maximum_age",
            "vessel_durability",
            "exploratory_temperature",
            "learned_preference_limit",
            "maximum_social_neighbors",
            "maximum_social_bonds",
            "relationship_half_life_years",
            "relationship_balance_limit",
            "social_success_memory_years",
            "bond_separation_years",
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
            "environmental_energy_cost_per_year",
            "artifact_material_cost",
            "artifact_energy_cost",
            "artifact_build_weight",
            "artifact_storage_weight",
            "artifact_decay_rate_per_year",
            "artifact_maintenance_material_cost",
            "artifact_maintenance_energy_cost",
            "artifact_maintenance_restore",
            "food_spoilage_rate_per_year",
            "initial_inventory",
            "starvation_damage",
            "malnutrition_threshold",
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
            "hunt_weight",
            "hunt_energy_cost",
            "hunt_success_base",
            "initial_fauna_density",
            "fauna_metabolism",
            "fauna_graze_amount",
            "fauna_birth_energy",
            "fauna_reproduction_energy",
            "fauna_reproduction_cost",
            "fauna_birth_rate",
            "fauna_maturity_age",
            "fauna_mortality_rate_per_year",
            "fauna_wander_rate",
            "fauna_trait_variation",
            "fauna_mutation_scale",
            "fauna_vigilance",
            "fauna_fecundity",
            "fauna_vigilance_weight",
            "fauna_meat_per_energy",
            "research_weight",
            "research_energy_minimum",
            "research_energy_cost",
            "research_material_cost",
            "discovery_threshold",
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
            "bond_acceptance_base",
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
            "artifact_insulation",
            "communication_weight",
            "communication_energy_cost",
            "neural_output_weight",
            "neural_founder_scale",
            "neural_mutation_rate",
            "neural_mutation_scale",
            "neural_weight_limit",
            "neural_recurrence_weight",
            "neural_maintenance_cost",
            "neural_birth_units",
            "neural_minimum_ceiling",
            "neural_maximum_ceiling",
            "neural_minimum_growth_rate",
            "neural_maximum_growth_rate",
            "neural_ceiling_mutation_rate",
            "neural_growth_rate_mutation_scale",
            "language_invention_rate",
            "language_adoption_rate",
            "language_mutation_rate",
            "language_naive_adoption_bonus",
            "plasticity_rate",
            "plasticity_energy_cost",
            "plasticity_limit",
            "place_memory_capacity",
            "place_memory_half_life_years",
            "place_return_weight",
            "courtship_weight",
            "courtship_energy_cost",
            "bond_movement_weight",
            "metrics_history_capacity",
            "event_log_capacity",
            "death_record_capacity",
            "neural_hidden_units",
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
            "bond_acceptance_base",
            "minimum_reproductive_health_fraction",
            "aging_starts_fraction",
            "minimum_gestation_health_fraction",
            "minimum_reproductive_body_condition",
            "juvenile_metabolism_fraction",
            "juvenile_capability_floor",
            "malnutrition_threshold",
            "fauna_wander_rate",
            "fauna_trait_variation",
            "fauna_vigilance",
            "fauna_fecundity",
            "fauna_birth_rate",
            "hunt_success_base",
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
        if not -1.0 <= self.bond_dissolution_trust <= 1.0:
            raise ValueError(
                "bond_dissolution_trust must lie within remembered trust range"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
        }
