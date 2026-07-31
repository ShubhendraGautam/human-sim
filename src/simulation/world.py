import math
import random
from array import array
from dataclasses import dataclass
from typing import (
    Dict,
    Iterable,
    List,
    MutableSequence,
    Optional,
    Sequence,
    Tuple,
)

from .config import SimulationConfig
from .entities import EntityKind, Placeable
from .models import Agent, Terrain
from .scenario import Scenario


@dataclass(frozen=True, slots=True)
class LocalConditions:
    """One objective reading of the physical cell under an organism.

    This is not perception and contains no organism-specific judgement. A
    person, grazer, and future plant at the same coordinates receive the same
    values; physiology and behavior decide what those values mean to each.
    Keeping amounts beside capacities also avoids baking a preferred
    normalization into the world.
    """

    terrain: Terrain
    food: float
    food_capacity: float
    material: float
    material_capacity: float
    season: float

    @property
    def food_fraction(self) -> float:
        return (
            self.food / self.food_capacity
            if self.food_capacity > 0.0
            else 0.0
        )

    @property
    def material_fraction(self) -> float:
        return (
            self.material / self.material_capacity
            if self.material_capacity > 0.0
            else 0.0
        )


class World:
    """Contiguous world layers plus a local population index."""

    __slots__ = (
        "config",
        "scenario",
        "terrain",
        "country",
        "capacity",
        "productivity",
        "renewal_rate",
        "seasonal_amplitude",
        "seasonal_phase",
        "resources",
        "material_capacity",
        "material_productivity",
        "material_renewal_rate",
        "materials",
        "has_sea",
        "country_land_cells",
        "_row_productive_counts",
        "_productive_cells",
        "_fastest_renewal",
        "_fastest_material_renewal",
        "_occupants",
        "_occupants_by_kind",
        "_interior_offsets",
        "last_food_harvested",
        "last_food_regenerated",
        "last_material_harvested",
        "last_material_regenerated",
        "last_seasonal_productivity",
        "last_row_factors",
        "_coast",
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
                raise ValueError(
                    f"country {spec.name!r} has no habitable cells"
                )

        specs = {spec.id: spec for spec in scenario.countries}
        self.capacity = array("d", [0.0]) * cell_count
        self.productivity = array("d", [0.0]) * cell_count
        self.seasonal_amplitude = array("d", [0.0]) * cell_count
        self.seasonal_phase = array("d", [0.0]) * cell_count
        self.resources = array("d", [0.0]) * cell_count
        self.material_capacity = array("d", [0.0]) * cell_count
        self.material_productivity = array("d", [0.0]) * cell_count
        self.materials = array("d", [0.0]) * cell_count
        for index in range(cell_count):
            y = index // config.width
            latitude = (
                0.0
                if config.height <= 1
                else 1.0 - 2.0 * y / (config.height - 1)
            )
            self.seasonal_amplitude[index] = (
                config.seasonality_strength
                * (
                    config.seasonal_equator_fraction
                    + (1.0 - config.seasonal_equator_fraction)
                    * abs(latitude)
                )
            )
            self.seasonal_phase[index] = (
                0.0 if latitude >= 0.0 else math.pi
            )
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
            self.productivity[index] = (
                self.capacity[index] * config.resource_regeneration
            )
            self.material_capacity[index] = (
                config.material_cell_capacity
                * fertility
                * material_multiplier
            )
            self.material_productivity[index] = (
                self.material_capacity[index] * config.material_regeneration
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
        # Regeneration is a fraction of the remaining deficit, and that
        # fraction is a property of the cell rather than of its stock. Storing
        # it directly keeps the per-tick sweep free of a division, and leaves
        # room for biomes that renew at genuinely different speeds.
        self.renewal_rate = array("d", [0.0]) * cell_count
        self.material_renewal_rate = array("d", [0.0]) * cell_count
        row_counts = [0] * config.height
        for index in range(cell_count):
            capacity = self.capacity[index]
            if capacity > 0.0:
                self.renewal_rate[index] = self.productivity[index] / capacity
                row_counts[index // config.width] += 1
            material_capacity = self.material_capacity[index]
            if material_capacity > 0.0:
                self.material_renewal_rate[index] = (
                    self.material_productivity[index] / material_capacity
                )
        self._row_productive_counts = row_counts
        self._productive_cells = sum(row_counts)
        self._fastest_renewal = max(self.renewal_rate, default=0.0)
        self._fastest_material_renewal = max(
            self.material_renewal_rate,
            default=0.0,
        )

        self._occupants_by_kind: Dict[EntityKind, Dict[int, List[int]]] = {
            kind: {} for kind in EntityKind
        }
        # The person bucket by another name: local perception reads it on the
        # hot path, so it stays a direct attribute rather than a lookup.
        self._occupants: Dict[int, List[int]] = self._occupants_by_kind[
            EntityKind.PERSON
        ]
        self._interior_offsets: Dict[int, Tuple[int, ...]] = {}
        self.last_food_harvested = 0.0
        self.last_food_regenerated = 0.0
        self.last_material_harvested = 0.0
        self.last_material_regenerated = 0.0
        self.last_seasonal_productivity = 1.0
        # The season as each row of the map is currently experiencing it.
        # Cached from the last regeneration so an agent can feel the season
        # where it is standing without anyone recomputing it per agent.
        self.last_row_factors: List[float] = [1.0] * config.height
        # Terrain is fixed for a run, so where the coast is can be settled
        # once instead of rediscovered by every agent that looks around.
        self._coast = self._build_coast_mask()

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
        """Whether this land cell touches open water.

        Read from a mask built once when the world is made. Terrain never
        changes during a run, so recomputing it was four bounds-checked
        lookups per asking — affordable when only research asked, and not
        once every agent's perception asks every tick.
        """

        index = self.try_cell_index(x, y)
        return index is not None and bool(self._coast[index])

    def _build_coast_mask(self) -> array:
        mask = array("b", bytes(self.config.width * self.config.height))
        if not self.has_sea:
            return mask
        for index in range(len(mask)):
            if self.terrain[index] == Terrain.SEA:
                continue
            x, y = self.coordinates(index)
            for offset_x, offset_y in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                neighbour = self.try_cell_index(x + offset_x, y + offset_y)
                if (
                    neighbour is not None
                    and self.terrain[neighbour] == Terrain.SEA
                ):
                    mask[index] = 1
                    break
        return mask

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

    def local_conditions(self, x: int, y: int) -> LocalConditions:
        """Return physical conditions without interpreting them for a kind."""

        index = self.cell_index(x, y)
        _, normalized_y = self.coordinates(index)
        return LocalConditions(
            terrain=Terrain(self.terrain[index]),
            food=self.resources[index],
            food_capacity=self.capacity[index],
            material=self.materials[index],
            material_capacity=self.material_capacity[index],
            season=self.season_at(normalized_y),
        )

    def harvest(self, x: int, y: int, requested: float) -> float:
        amount = self._harvest_layer(self.resources, x, y, requested)
        self.last_food_harvested += amount
        return amount

    def harvest_material(self, x: int, y: int, requested: float) -> float:
        amount = self._harvest_layer(self.materials, x, y, requested)
        self.last_material_harvested += amount
        return amount

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

    def food_fraction(self, x: int, y: int) -> float:
        """How full this cell is, as a share of what it could hold."""

        index = self.try_cell_index(x, y)
        if index is None:
            return 0.0
        capacity = self.capacity[index]
        return self.resources[index] / capacity if capacity > 0.0 else 0.0

    def food_gradient(self, x: int, y: int) -> float:
        """How much better the best adjacent cell is than this one.

        Four orthogonal neighbours only. This is a sense rather than a plan:
        it says which way the ground improves, not where to go, and it costs
        four array reads instead of the wider search movement uses.
        """

        here = self.food_fraction(x, y)
        best = here
        for offset_x, offset_y in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            index = self.try_cell_index(x + offset_x, y + offset_y)
            if index is None:
                continue
            capacity = self.capacity[index]
            if capacity <= 0.0:
                continue
            value = self.resources[index] / capacity
            if value > best:
                best = value
        return best - here

    def season_at(self, y: int) -> float:
        """The season this row is in, centred on zero."""

        if 0 <= y < len(self.last_row_factors):
            return self.last_row_factors[y] - 1.0
        return 0.0

    def begin_tick(self) -> None:
        self.last_food_harvested = 0.0
        self.last_food_regenerated = 0.0
        self.last_material_harvested = 0.0
        self.last_material_regenerated = 0.0

    def regenerate(self, tick: int = 0) -> None:
        elapsed_years = 1.0 / self.config.ticks_per_year
        row_factors = self._seasonal_row_factors(tick)
        self.last_food_regenerated = self._grow_layer(
            self.resources,
            self.capacity,
            self.renewal_rate,
            self._fastest_renewal,
            elapsed_years,
            row_factors,
        )
        self.last_row_factors = list(row_factors)
        self.last_seasonal_productivity = self._seasonal_mean(row_factors)
        if self.config.materials_renewable:
            self.last_material_regenerated = self._grow_layer(
                self.materials,
                self.material_capacity,
                self.material_renewal_rate,
                self._fastest_material_renewal,
                elapsed_years,
                None,
            )

    def _seasonal_mean(self, row_factors: Sequence[float]) -> float:
        """Average season over productive cells, without visiting them.

        Which cells are productive is fixed when the world is built, so the
        average is a weighted sum over rows rather than a sweep of the map.
        """

        if not self._productive_cells:
            return 1.0
        weighted = 0.0
        for y, count in enumerate(self._row_productive_counts):
            if count:
                weighted += row_factors[y] * count
        return weighted / self._productive_cells

    def _grow_layer(
        self,
        values: array,
        capacities: Sequence[float],
        rates: Sequence[float],
        fastest_rate: float,
        elapsed_years: float,
        row_factors: Optional[Sequence[float]],
    ) -> float:
        """Regrow one layer toward capacity, a row at a time.

        Growth is a share of the remaining deficit, so a full cell grows by
        nothing and needs no special case, and a cell with no capacity — sea —
        stays at zero on its own. Working per row hoists the season out of the
        inner expression and lets the row be read, grown, and written as three
        bulk operations instead of a few thousand indexed ones. The cost is
        still linear in the map, but with a much smaller constant.
        """

        width = self.config.width
        total_growth = 0.0
        # A share of a deficit cannot overshoot unless the share exceeds the
        # whole, which the default physics never approaches. Pay for the clamp
        # only when a configuration makes overshoot arithmetically possible.
        overshoot_possible = fastest_rate * elapsed_years * max(
            row_factors or (1.0,)
        ) > 1.0
        for y in range(self.config.height):
            start = y * width
            end = start + width
            season = 1.0 if row_factors is None else row_factors[y]
            step = elapsed_years * season
            current = values[start:end]
            row_capacity = capacities[start:end]
            row_rate = rates[start:end]
            if overshoot_possible:
                growth = [
                    min(
                        capacity - value,
                        max(rate * step * (capacity - value), 0.0),
                    )
                    for value, capacity, rate
                    in zip(current, row_capacity, row_rate)
                ]
            else:
                growth = [
                    rate * step * (capacity - value)
                    for value, capacity, rate
                    in zip(current, row_capacity, row_rate)
                ]
            total_growth += sum(growth)
            values[start:end] = array(
                "d",
                [value + gained for value, gained in zip(current, growth)],
            )
        return total_growth

    def _seasonal_row_factors(self, tick: int) -> List[float]:
        angle = 2.0 * math.pi * (
            (tick % self.config.ticks_per_year)
            / self.config.ticks_per_year
        )
        width = self.config.width
        return [
            1.0
            + self.seasonal_amplitude[y * width]
            * math.sin(angle + self.seasonal_phase[y * width])
            for y in range(self.config.height)
        ]

    def _seasonal_factors(self, tick: int) -> array:
        row_factors = self._seasonal_row_factors(tick)
        return array(
            "d",
            (
                row_factors[index // self.config.width]
                for index in range(self.config.width * self.config.height)
            ),
        )

    def rebuild_spatial_index(self, entities: Iterable[Placeable]) -> None:
        """Index everything the world holds, keeping the kinds apart.

        Separate buckets mean a query for people never walks past plants or
        structures, so local perception keeps costing what it costs today no
        matter how much else is standing in the same cell.
        """

        buckets: Dict[EntityKind, Dict[int, List[int]]] = {
            kind: {} for kind in EntityKind
        }
        for entity in entities:
            index = self.cell_index(entity.x, entity.y)
            buckets[entity.kind].setdefault(index, []).append(entity.id)
        for bucket in buckets.values():
            for entity_ids in bucket.values():
                entity_ids.sort()
        self._occupants_by_kind = buckets
        self._occupants = buckets[EntityKind.PERSON]

    def occupants_of_kind(
        self,
        kind: EntityKind,
    ) -> Dict[int, List[int]]:
        """Cell index to sorted entity ids, for one kind."""

        return self._occupants_by_kind[kind]

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

    def sample_nearby_agent_ids(
        self,
        x: int,
        y: int,
        radius: int,
        exclude: int,
        limit: int,
        rng: random.Random,
        preselected: Sequence[int] = (),
    ) -> List[int]:
        """Sample bounded local attention without materializing a crowd.

        At most ``limit`` IDs are returned even when a cell contains thousands
        of agents. Callers may reserve slots for dependents or remembered
        contacts through ``preselected``.
        """

        if limit <= 0:
            return []
        cells = self.nearby_cell_indices(x, y, radius)
        occupant_lists = []
        for cell in cells:
            occupants = self._occupants.get(cell)
            if occupants:
                occupant_lists.append(occupants)
        total = sum(len(items) for items in occupant_lists)
        if total == 0:
            return []
        if (
            total == 1
            and not preselected
            and occupant_lists[0][0] == exclude
        ):
            return []

        selected: List[int] = []
        selected_set = {exclude}
        for agent_id in preselected:
            if agent_id not in selected_set:
                selected.append(agent_id)
                selected_set.add(agent_id)
                if len(selected) >= limit:
                    return sorted(selected)

        if total <= limit * 4:
            candidates = []
            for items in occupant_lists:
                for candidate in items:
                    if candidate not in selected_set:
                        candidates.append(candidate)
            remaining = limit - len(selected)
            if len(candidates) > remaining:
                candidates.sort()
                candidates = rng.sample(candidates, remaining)
            selected.extend(candidates)
            return sorted(selected)

        attempts = 0
        maximum_attempts = max(limit * 12, 24)
        while len(selected) < limit and attempts < maximum_attempts:
            ordinal = rng.randrange(total)
            candidate = exclude
            for items in occupant_lists:
                if ordinal < len(items):
                    candidate = items[ordinal]
                    break
                ordinal -= len(items)
            if candidate not in selected_set:
                selected.append(candidate)
                selected_set.add(candidate)
            attempts += 1

        return sorted(selected)

    def _offsets(self, radius: int) -> Tuple[int, ...]:
        """Return row-major offsets for an unclipped square neighborhood."""
        cached = self._interior_offsets.get(radius)
        if cached is None:
            width = self.config.width
            cached = tuple(
                row * width + column
                for row in range(-radius, radius + 1)
                for column in range(-radius, radius + 1)
            )
            self._interior_offsets[radius] = cached
        return cached

    def nearby_cell_indices(
        self,
        x: int,
        y: int,
        radius: int,
    ) -> Sequence[int]:
        if not self.config.wrap_world:
            width = self.config.width
            height = self.config.height
            # Agents away from every edge share one offset pattern, so the
            # common case becomes a flat shift instead of a nested loop.
            if radius <= x < width - radius and radius <= y < height - radius:
                base = y * width + x
                return [base + offset for offset in self._offsets(radius)]
            minimum_x = max(0, x - radius)
            maximum_x = min(width - 1, x + radius)
            minimum_y = max(0, y - radius)
            maximum_y = min(height - 1, y + radius)
            return [
                row * width + column
                for row in range(minimum_y, maximum_y + 1)
                for column in range(minimum_x, maximum_x + 1)
            ]
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
        exploration: float,
    ) -> Tuple[int, int]:
        agent_x = agent.x
        agent_y = agent.y
        best_score = float("-inf")
        best_step = (agent_x, agent_y)
        config = self.config
        width = config.width
        height = config.height
        wraps = config.wrap_world
        visited = set() if wraps else None
        vision = agent.traits.vision

        # This loop runs up to (2 * vision + 1) ** 2 times per agent per tick
        # and dominates the decision phase, so every value it reads is bound
        # to a local before entering it.
        resources = self.resources
        materials = self.materials
        terrain = self.terrain
        occupants_get = self._occupants.get
        material_weight = config.material_attraction_weight
        crowding_weight = config.crowding_weight
        blocks_sea = self.has_sea and not can_cross_sea
        sea = Terrain.SEA
        random_value = rng.random

        for offset_y in range(-vision, vision + 1):
            target_y = agent_y + offset_y
            if wraps:
                target_y %= height
            elif target_y < 0 or target_y >= height:
                continue
            row = target_y * width
            step_y = agent_y + (offset_y > 0) - (offset_y < 0)
            if wraps:
                step_y %= height
            elif step_y < 0 or step_y >= height:
                continue
            step_row = step_y * width
            for offset_x in range(-vision, vision + 1):
                target_x = agent_x + offset_x
                if wraps:
                    target_x %= width
                elif target_x < 0 or target_x >= width:
                    continue
                cell = row + target_x
                if visited is not None:
                    if cell in visited:
                        continue
                    visited.add(cell)

                step_x = agent_x + (offset_x > 0) - (offset_x < 0)
                if wraps:
                    step_x %= width
                elif step_x < 0 or step_x >= width:
                    continue
                step_index = step_row + step_x
                if blocks_sea and terrain[step_index] == sea:
                    continue
                crowd = occupants_get(cell)
                score = (
                    resources[cell]
                    + materials[cell]
                    * material_weight
                    - (len(crowd) if crowd else 0)
                    * crowding_weight
                    + random_value() * exploration
                )
                if score > best_score:
                    best_score = score
                    best_step = (step_x, step_y)

        return best_step

    def total_resources(self) -> float:
        return sum(self.resources)

    def total_materials(self) -> float:
        return sum(self.materials)
