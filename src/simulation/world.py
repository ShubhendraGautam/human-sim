import random
from array import array
from typing import Dict, Iterable, List, MutableSequence, Optional, Sequence, Tuple

from .config import SimulationConfig
from .models import Agent, Terrain
from .scenario import Scenario


class World:
    """Contiguous world layers plus a local population index."""

    __slots__ = (
        "config",
        "scenario",
        "terrain",
        "country",
        "capacity",
        "resources",
        "material_capacity",
        "materials",
        "has_sea",
        "country_land_cells",
        "_occupants",
    )

    def __init__(
        self,
        config: SimulationConfig,
        rng: random.Random,
        scenario: Scenario,
    ):
        self.config = config
        self.scenario = scenario
        cell_count = config.width * config.height
        self.terrain = bytearray([Terrain.LAND] * cell_count)
        self.country = array("i", [-1]) * cell_count

        for sea in scenario.seas:
            for x, y in sea.cells():
                self.terrain[self.cell_index(x, y)] = Terrain.SEA
        self.has_sea = bool(scenario.seas)

        self.country_land_cells: Dict[int, List[int]] = {
            spec.id: [] for spec in scenario.countries
        }
        for spec in scenario.countries:
            for x, y in spec.region.cells():
                index = self.cell_index(x, y)
                if self.terrain[index] == Terrain.SEA:
                    continue
                if self.country[index] != -1:
                    raise ValueError("country land regions cannot overlap")
                self.country[index] = spec.id
                self.country_land_cells[spec.id].append(index)
            if spec.population and not self.country_land_cells[spec.id]:
                raise ValueError(f"country {spec.name!r} has no habitable cells")

        specs = {spec.id: spec for spec in scenario.countries}
        self.capacity = array("d", [0.0]) * cell_count
        self.resources = array("d", [0.0]) * cell_count
        self.material_capacity = array("d", [0.0]) * cell_count
        self.materials = array("d", [0.0]) * cell_count
        for index in range(cell_count):
            if self.terrain[index] == Terrain.SEA:
                continue
            spec = specs.get(self.country[index])
            food_multiplier = spec.food_multiplier if spec else 1.0
            material_multiplier = spec.material_multiplier if spec else 1.0
            fertility = rng.uniform(
                config.minimum_cell_fertility,
                config.maximum_cell_fertility,
            )
            self.capacity[index] = (
                config.cell_capacity * fertility * food_multiplier
            )
            self.material_capacity[index] = (
                config.material_cell_capacity
                * fertility
                * material_multiplier
            )
            variation = rng.uniform(
                1.0 - config.initial_resource_variation,
                1.0,
            )
            self.resources[index] = (
                self.capacity[index]
                * config.initial_resource_fraction
                * variation
            )
            self.materials[index] = (
                self.material_capacity[index]
                * config.initial_resource_fraction
                * variation
            )
        self._occupants: Dict[int, List[int]] = {}

    def normalize(self, x: int, y: int) -> Optional[Tuple[int, int]]:
        if self.config.wrap_world:
            return x % self.config.width, y % self.config.height
        if 0 <= x < self.config.width and 0 <= y < self.config.height:
            return x, y
        return None

    def cell_index(self, x: int, y: int) -> int:
        normalized = self.normalize(x, y)
        if normalized is None:
            raise IndexError("coordinates are outside the world")
        normalized_x, normalized_y = normalized
        return normalized_y * self.config.width + normalized_x

    def try_cell_index(self, x: int, y: int) -> Optional[int]:
        normalized = self.normalize(x, y)
        if normalized is None:
            return None
        normalized_x, normalized_y = normalized
        return normalized_y * self.config.width + normalized_x

    def coordinates(self, index: int) -> Tuple[int, int]:
        return index % self.config.width, index // self.config.width

    def is_sea(self, x: int, y: int) -> bool:
        return self.terrain[self.cell_index(x, y)] == Terrain.SEA

    def is_coast(self, x: int, y: int) -> bool:
        if not self.has_sea or self.is_sea(x, y):
            return False
        for offset_x, offset_y in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            index = self.try_cell_index(x + offset_x, y + offset_y)
            if index is not None and self.terrain[index] == Terrain.SEA:
                return True
        return False

    def adjacent_sea_destinations(
        self,
        x: int,
        y: int,
    ) -> List[Tuple[int, int]]:
        destinations = []
        for offset_x, offset_y in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            normalized = self.normalize(x + offset_x, y + offset_y)
            if (
                normalized is not None
                and self.terrain[self.cell_index(*normalized)] == Terrain.SEA
            ):
                destinations.append(normalized)
        return destinations

    def country_at(self, x: int, y: int) -> int:
        return self.country[self.cell_index(x, y)]

    def resource_at(self, x: int, y: int) -> float:
        return self.resources[self.cell_index(x, y)]

    def material_at(self, x: int, y: int) -> float:
        return self.materials[self.cell_index(x, y)]

    def harvest(self, x: int, y: int, requested: float) -> float:
        return self._harvest_layer(self.resources, x, y, requested)

    def harvest_material(self, x: int, y: int, requested: float) -> float:
        return self._harvest_layer(self.materials, x, y, requested)

    def _harvest_layer(
        self,
        layer: MutableSequence[float],
        x: int,
        y: int,
        requested: float,
    ) -> float:
        index = self.cell_index(x, y)
        amount = min(max(requested, 0.0), layer[index])
        layer[index] -= amount
        return amount

    def regenerate(self) -> None:
        self._regenerate_layer(
            self.resources,
            self.capacity,
            self.config.resource_regeneration,
        )
        self._regenerate_layer(
            self.materials,
            self.material_capacity,
            self.config.material_regeneration,
        )

    @staticmethod
    def _regenerate_layer(
        values: MutableSequence[float],
        capacities: Sequence[float],
        rate: float,
    ) -> None:
        for index, current in enumerate(values):
            capacity = capacities[index]
            if capacity > 0.0 and current < capacity:
                growth = rate * (1.0 - current / capacity)
                values[index] = min(capacity, current + growth)

    def rebuild_spatial_index(self, agents: Iterable[Agent]) -> None:
        occupants: Dict[int, List[int]] = {}
        for agent in agents:
            index = self.cell_index(agent.x, agent.y)
            occupants.setdefault(index, []).append(agent.id)
        self._occupants = occupants

    def nearby_agent_ids(
        self,
        x: int,
        y: int,
        radius: int,
        exclude: int,
    ) -> List[int]:
        result: List[int] = []
        for cell in self.nearby_cell_indices(x, y, radius):
            result.extend(
                agent_id
                for agent_id in self._occupants.get(cell, ())
                if agent_id != exclude
            )
        return result

    def nearby_cell_indices(
        self,
        x: int,
        y: int,
        radius: int,
    ) -> Sequence[int]:
        cells = []
        visited = set()
        for offset_y in range(-radius, radius + 1):
            for offset_x in range(-radius, radius + 1):
                index = self.try_cell_index(x + offset_x, y + offset_y)
                if index is not None and index not in visited:
                    visited.add(index)
                    cells.append(index)
        return cells

    def best_neighbor(
        self,
        agent: Agent,
        rng: random.Random,
        can_cross_sea: bool,
    ) -> Tuple[int, int]:
        best_score = float("-inf")
        best_step = (agent.x, agent.y)
        width = self.config.width
        height = self.config.height
        wraps = self.config.wrap_world
        visited = set() if wraps else None
        vision = agent.traits.vision

        for offset_y in range(-vision, vision + 1):
            target_y = agent.y + offset_y
            if wraps:
                target_y %= height
            elif target_y < 0 or target_y >= height:
                continue
            for offset_x in range(-vision, vision + 1):
                target_x = agent.x + offset_x
                if wraps:
                    target_x %= width
                elif target_x < 0 or target_x >= width:
                    continue
                cell = target_y * width + target_x
                if visited is not None:
                    if cell in visited:
                        continue
                    visited.add(cell)

                step_x = agent.x + (offset_x > 0) - (offset_x < 0)
                step_y = agent.y + (offset_y > 0) - (offset_y < 0)
                if wraps:
                    step_x %= width
                    step_y %= height
                elif (
                    step_x < 0
                    or step_x >= width
                    or step_y < 0
                    or step_y >= height
                ):
                    continue
                step_index = step_y * width + step_x
                if (
                    self.has_sea
                    and self.terrain[step_index] == Terrain.SEA
                    and not can_cross_sea
                ):
                    continue
                score = (
                    self.resources[cell]
                    + self.materials[cell]
                    * self.config.material_attraction_weight
                    - len(self._occupants.get(cell, ()))
                    * self.config.crowding_weight
                    + rng.random() * agent.traits.exploration
                )
                if score > best_score:
                    best_score = score
                    best_step = (step_x, step_y)

        return best_step

    def total_resources(self) -> float:
        return sum(self.resources)

    def total_materials(self) -> float:
        return sum(self.materials)
