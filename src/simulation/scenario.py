import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from .config import SimulationConfig


@dataclass(frozen=True, slots=True)
class Rectangle:
    x: int
    y: int
    width: int
    height: int

    @classmethod
    def from_value(cls, value: Iterable[int]) -> "Rectangle":
        values = tuple(value)
        if len(values) != 4:
            raise ValueError("region must contain [x, y, width, height]")
        return cls(*values)

    def cells(self) -> Iterable[Tuple[int, int]]:
        for y in range(self.y, self.y + self.height):
            for x in range(self.x, self.x + self.width):
                yield x, y

    def validate(self, config: SimulationConfig) -> None:
        for name in ("x", "y", "width", "height"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"region {name} must be an integer")
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("regions must have positive in-world dimensions")
        if self.x + self.width > config.width:
            raise ValueError("region exceeds world width")
        if self.y + self.height > config.height:
            raise ValueError("region exceeds world height")

    def to_list(self) -> list:
        return [self.x, self.y, self.width, self.height]


@dataclass(frozen=True, slots=True)
class CountrySpec:
    id: int
    name: str
    region: Rectangle
    population: int
    religion: str = "none"
    generosity_mean: float = 0.5
    exploration_mean: float = 0.5
    curiosity_mean: float = 0.5
    conformity_mean: float = 0.5
    metabolism_mean: float = 0.5
    harvest_mean: float = 0.5
    fertility_mean: float = 0.5
    constitution_mean: float = 0.5
    longevity_mean: float = 0.5
    maturation_mean: float = 0.5
    learning_mean: float = 0.5
    brain_style_mean: float = 0.5
    risk_mean: float = 0.5
    immunity_mean: float = 0.5
    affiliation_mean: float = 0.5
    starting_energy_multiplier: float = 1.0
    food_multiplier: float = 1.0
    material_multiplier: float = 1.0
    initial_exposed_fraction: Optional[float] = None

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "CountrySpec":
        data = dict(values)
        data["region"] = Rectangle.from_value(data["region"])
        return cls(**data)

    def validate(self, config: SimulationConfig) -> None:
        if not isinstance(self.id, int) or isinstance(self.id, bool):
            raise ValueError("country id must be an integer")
        if not isinstance(self.population, int) or isinstance(
            self.population,
            bool,
        ):
            raise ValueError("country population must be an integer")
        if self.id < 0:
            raise ValueError("country id cannot be negative")
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("country name cannot be empty")
        if not isinstance(self.religion, str) or not self.religion:
            raise ValueError("country religion must be a nonempty string")
        if self.population < 0:
            raise ValueError("country population cannot be negative")
        self.region.validate(config)
        for name in (
            "generosity_mean",
            "exploration_mean",
            "curiosity_mean",
            "conformity_mean",
            "metabolism_mean",
            "harvest_mean",
            "fertility_mean",
            "constitution_mean",
            "longevity_mean",
            "maturation_mean",
            "learning_mean",
            "brain_style_mean",
            "risk_mean",
            "immunity_mean",
            "affiliation_mean",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValueError(f"{name} must be between 0 and 1")
        for name in (
            "starting_energy_multiplier",
            "food_multiplier",
            "material_multiplier",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0.0
            ):
                raise ValueError(f"{name} cannot be negative")
        if (
            self.initial_exposed_fraction is not None
            and (
                not isinstance(
                    self.initial_exposed_fraction,
                    (int, float),
                )
                or isinstance(self.initial_exposed_fraction, bool)
                or not math.isfinite(self.initial_exposed_fraction)
                or not 0.0 <= self.initial_exposed_fraction <= 1.0
            )
        ):
            raise ValueError(
                "initial_exposed_fraction must be between 0 and 1"
            )

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "region": self.region.to_list(),
            "population": self.population,
            "religion": self.religion,
            "generosity_mean": self.generosity_mean,
            "exploration_mean": self.exploration_mean,
            "curiosity_mean": self.curiosity_mean,
            "conformity_mean": self.conformity_mean,
            "metabolism_mean": self.metabolism_mean,
            "harvest_mean": self.harvest_mean,
            "fertility_mean": self.fertility_mean,
            "constitution_mean": self.constitution_mean,
            "longevity_mean": self.longevity_mean,
            "maturation_mean": self.maturation_mean,
            "learning_mean": self.learning_mean,
            "brain_style_mean": self.brain_style_mean,
            "risk_mean": self.risk_mean,
            "immunity_mean": self.immunity_mean,
            "affiliation_mean": self.affiliation_mean,
            "starting_energy_multiplier": self.starting_energy_multiplier,
            "food_multiplier": self.food_multiplier,
            "material_multiplier": self.material_multiplier,
            "initial_exposed_fraction": self.initial_exposed_fraction,
        }


@dataclass(frozen=True, slots=True)
class Scenario:
    countries: Tuple[CountrySpec, ...]
    seas: Tuple[Rectangle, ...] = ()

    @classmethod
    def default(cls, config: SimulationConfig) -> "Scenario":
        return cls(
            countries=(
                CountrySpec(
                    id=0,
                    name="Founders",
                    region=Rectangle(0, 0, config.width, config.height),
                    population=config.initial_population,
                ),
            )
        )

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "Scenario":
        return cls(
            countries=tuple(
                CountrySpec.from_dict(country)
                for country in values.get("countries", ())
            ),
            seas=tuple(
                Rectangle.from_value(region)
                for region in values.get("seas", ())
            ),
        )

    def validate(self, config: SimulationConfig) -> None:
        if not self.countries:
            raise ValueError("scenario must contain at least one country")
        ids = [country.id for country in self.countries]
        if len(ids) != len(set(ids)):
            raise ValueError("country ids must be unique")
        for country in self.countries:
            country.validate(config)
        for sea in self.seas:
            sea.validate(config)

    def belief_id_for(self, country: CountrySpec) -> int:
        religions = []
        for item in self.countries:
            if item.religion not in religions:
                religions.append(item.religion)
        return religions.index(country.religion)

    def to_dict(self) -> Dict[str, object]:
        return {
            "countries": [country.to_dict() for country in self.countries],
            "seas": [sea.to_list() for sea in self.seas],
            "beliefs": [
                {"id": belief_id, "name": religion}
                for belief_id, religion in enumerate(dict.fromkeys(
                    country.religion for country in self.countries
                ))
            ],
        }
