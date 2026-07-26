import random
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, Mapping, Tuple

from .config import SimulationConfig
from .models import BrainKind, Traits


class Gene(IntEnum):
    METABOLISM = 0
    HARVEST = 1
    FERTILITY = 2
    CONSTITUTION = 3
    LONGEVITY = 4
    MATURATION = 5
    VISION = 6
    GENEROSITY = 7
    EXPLORATION = 8
    CURIOSITY = 9
    CONFORMITY = 10
    LEARNING = 11
    COGNITIVE_STYLE = 12
    RISK = 13


GENE_COUNT = len(Gene)


@dataclass(frozen=True, slots=True)
class Genome:
    """Compact diploid genome: two normalized alleles per modeled locus."""

    alleles: Tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.alleles) != GENE_COUNT * 2:
            raise ValueError("genome contains the wrong number of alleles")
        if any(not 0.0 <= allele <= 1.0 for allele in self.alleles):
            raise ValueError("alleles must be between 0 and 1")

    def expressed(self, gene: Gene) -> float:
        offset = int(gene) * 2
        return (self.alleles[offset] + self.alleles[offset + 1]) / 2.0

    @classmethod
    def founder(
        cls,
        rng: random.Random,
        variation: float,
        centers: Mapping[Gene, float],
    ) -> "Genome":
        alleles = []
        for gene in Gene:
            center = centers.get(gene, 0.5)
            for _ in range(2):
                alleles.append(_clamp(rng.uniform(
                    center - variation,
                    center + variation,
                )))
        return cls(tuple(alleles))

    @classmethod
    def recombine(
        cls,
        first: "Genome",
        second: "Genome",
        rng: random.Random,
        mutation_probability: float,
        mutation_scale: float,
    ) -> "Genome":
        """Create one gamete from each parent, then mutate per copied allele."""

        child = []
        for gene in Gene:
            offset = int(gene) * 2
            first_allele = first.alleles[offset + rng.randrange(2)]
            second_allele = second.alleles[offset + rng.randrange(2)]
            child.append(_mutate(
                first_allele,
                rng,
                mutation_probability,
                mutation_scale,
            ))
            child.append(_mutate(
                second_allele,
                rng,
                mutation_probability,
                mutation_scale,
            ))
        return cls(tuple(child))

    def expressed_values(self) -> Dict[str, float]:
        return {gene.name.lower(): self.expressed(gene) for gene in Gene}


def express_traits(
    genome: Genome,
    config: SimulationConfig,
) -> Traits:
    learning = genome.expressed(Gene.LEARNING)
    vision_gene = genome.expressed(Gene.VISION)
    base_metabolism = _lerp(
        config.base_metabolism_minimum,
        config.base_metabolism_maximum,
        genome.expressed(Gene.METABOLISM),
    )
    metabolism = base_metabolism * (
        1.0
        + learning * config.learning_metabolic_cost
        + vision_gene * config.vision_metabolic_cost
    )
    cognitive_style = genome.expressed(Gene.COGNITIVE_STYLE)
    brain_index = min(int(cognitive_style * len(BrainKind)), len(BrainKind) - 1)

    return Traits(
        metabolism=metabolism,
        harvest_skill=_lerp(
            config.harvest_skill_minimum,
            config.harvest_skill_maximum,
            genome.expressed(Gene.HARVEST),
        ),
        generosity=genome.expressed(Gene.GENEROSITY),
        fertility=genome.expressed(Gene.FERTILITY),
        exploration=genome.expressed(Gene.EXPLORATION),
        curiosity=genome.expressed(Gene.CURIOSITY),
        conformity=genome.expressed(Gene.CONFORMITY),
        constitution=genome.expressed(Gene.CONSTITUTION),
        maximum_health=config.maximum_health * _lerp(
            config.minimum_health_fraction,
            config.maximum_health_fraction,
            genome.expressed(Gene.CONSTITUTION),
        ),
        lifespan=_lerp(
            config.minimum_lifespan,
            config.maximum_age,
            genome.expressed(Gene.LONGEVITY),
        ),
        maturity_age=_lerp(
            config.minimum_maturity_age,
            config.maximum_maturity_age,
            genome.expressed(Gene.MATURATION),
        ),
        learning_rate=_lerp(
            config.minimum_learning_rate,
            config.maximum_learning_rate,
            learning,
        ),
        risk_tolerance=genome.expressed(Gene.RISK),
        brain_kind=tuple(BrainKind)[brain_index],
        vision=round(_lerp(
            float(config.vision_minimum),
            float(config.vision_maximum),
            vision_gene,
        )),
    )


def genetic_distance(first: Genome, second: Genome) -> float:
    return sum(
        abs(left - right)
        for left, right in zip(first.alleles, second.alleles)
    ) / len(first.alleles)


def _mutate(
    allele: float,
    rng: random.Random,
    probability: float,
    scale: float,
) -> float:
    if rng.random() < probability:
        return _clamp(allele + rng.gauss(0.0, scale))
    return allele


def _lerp(minimum: float, maximum: float, value: float) -> float:
    return minimum + (maximum - minimum) * value


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
