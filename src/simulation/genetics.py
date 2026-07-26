import random
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, Mapping

from .config import SimulationConfig
from .models import BrainKind, Traits

GENOME_SCHEMA_VERSION = 1
LOCI_PER_GENE = 4
LOCI_PER_CHROMOSOME = 8


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


LOCUS_COUNT = len(Gene) * LOCI_PER_GENE
CHROMOSOME_COUNT = LOCUS_COUNT // LOCI_PER_CHROMOSOME
GENOME_MASK = (1 << LOCUS_COUNT) - 1


@dataclass(frozen=True, slots=True)
class Genome:
    """Two packed haplotypes containing linked, synthetic biallelic loci."""

    haplotype_a: int
    haplotype_b: int

    def __post_init__(self) -> None:
        if (
            self.haplotype_a < 0
            or self.haplotype_b < 0
            or self.haplotype_a & ~GENOME_MASK
            or self.haplotype_b & ~GENOME_MASK
        ):
            raise ValueError("genome has alleles outside its schema")

    def expressed(self, gene: Gene) -> float:
        shift = int(gene) * LOCI_PER_GENE
        mask = ((1 << LOCI_PER_GENE) - 1) << shift
        dosage = (
            (self.haplotype_a & mask).bit_count()
            + (self.haplotype_b & mask).bit_count()
        )
        return dosage / (LOCI_PER_GENE * 2)

    def heterozygosity(self) -> float:
        return (
            (self.haplotype_a ^ self.haplotype_b).bit_count()
            / LOCUS_COUNT
        )

    @classmethod
    def founder(
        cls,
        rng: random.Random,
        variation: float,
        centers: Mapping[Gene, float],
    ) -> "Genome":
        haplotypes = [0, 0]
        for gene in Gene:
            center = centers.get(gene, 0.5)
            for locus in range(LOCI_PER_GENE):
                bit = int(gene) * LOCI_PER_GENE + locus
                for haplotype in range(2):
                    probability = _clamp(
                        center + rng.uniform(-variation, variation)
                    )
                    if rng.random() < probability:
                        haplotypes[haplotype] |= 1 << bit
        return cls(*haplotypes)

    @classmethod
    def recombine(
        cls,
        first: "Genome",
        second: "Genome",
        rng: random.Random,
        mutation_probability: float,
        crossover_probability: float,
    ) -> "Genome":
        return cls(
            _make_gamete(
                first,
                rng,
                mutation_probability,
                crossover_probability,
            ),
            _make_gamete(
                second,
                rng,
                mutation_probability,
                crossover_probability,
            ),
        )

    def expressed_values(self) -> Dict[str, float]:
        return {gene.name.lower(): self.expressed(gene) for gene in Gene}


def express_traits(
    genome: Genome,
    config: SimulationConfig,
) -> Traits:
    learning = genome.expressed(Gene.LEARNING)
    vision_gene = genome.expressed(Gene.VISION)
    constitution = genome.expressed(Gene.CONSTITUTION)
    longevity = genome.expressed(Gene.LONGEVITY)
    fertility = genome.expressed(Gene.FERTILITY)
    harvest = genome.expressed(Gene.HARVEST)
    maturation = genome.expressed(Gene.MATURATION)
    base_metabolism = _lerp(
        config.base_metabolism_minimum,
        config.base_metabolism_maximum,
        genome.expressed(Gene.METABOLISM),
    )
    metabolism = base_metabolism * (
        1.0
        + learning * config.learning_metabolic_cost
        + vision_gene * config.vision_metabolic_cost
        + constitution * config.constitution_metabolic_cost
        + longevity * config.longevity_metabolic_cost
        + fertility * config.fertility_metabolic_cost
        + harvest * config.harvest_metabolic_cost
    )
    cognitive_style = genome.expressed(Gene.COGNITIVE_STYLE)
    brain_index = min(int(cognitive_style * len(BrainKind)), len(BrainKind) - 1)

    return Traits(
        metabolism=metabolism,
        harvest_skill=_lerp(
            config.harvest_skill_minimum,
            config.harvest_skill_maximum,
            harvest,
        ),
        generosity=genome.expressed(Gene.GENEROSITY),
        fertility=fertility,
        exploration=genome.expressed(Gene.EXPLORATION),
        curiosity=genome.expressed(Gene.CURIOSITY),
        conformity=genome.expressed(Gene.CONFORMITY),
        constitution=constitution,
        maximum_health=(
            config.maximum_health
            * _lerp(
                config.minimum_health_fraction,
                config.maximum_health_fraction,
                constitution,
            )
            * (
                1.0
                - (1.0 - maturation)
                * config.early_maturation_health_cost
            )
        ),
        lifespan=(
            _lerp(
                config.minimum_lifespan,
                config.maximum_age,
                longevity,
            )
            * (
                1.0
                - (1.0 - maturation)
                * config.early_maturation_lifespan_cost
            )
        ),
        maturity_age=_lerp(
            config.minimum_maturity_age,
            config.maximum_maturity_age,
            maturation,
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
    different = (
        (first.haplotype_a ^ second.haplotype_a).bit_count()
        + (first.haplotype_b ^ second.haplotype_b).bit_count()
    )
    return different / (LOCUS_COUNT * 2)


def _make_gamete(
    genome: Genome,
    rng: random.Random,
    mutation_probability: float,
    crossover_probability: float,
) -> int:
    gamete = 0
    chromosome_mask = (1 << LOCI_PER_CHROMOSOME) - 1
    for chromosome in range(CHROMOSOME_COUNT):
        shift = chromosome * LOCI_PER_CHROMOSOME
        first = (genome.haplotype_a >> shift) & chromosome_mask
        second = (genome.haplotype_b >> shift) & chromosome_mask
        if rng.random() < crossover_probability:
            crossover = rng.randrange(1, LOCI_PER_CHROMOSOME)
            lower_mask = (1 << crossover) - 1
            if rng.randrange(2):
                segment = (first & lower_mask) | (second & ~lower_mask)
            else:
                segment = (second & lower_mask) | (first & ~lower_mask)
        else:
            segment = first if rng.randrange(2) == 0 else second
        gamete |= (segment & chromosome_mask) << shift

    for locus in range(LOCUS_COUNT):
        if rng.random() < mutation_probability:
            gamete ^= 1 << locus
    return gamete & GENOME_MASK


def _lerp(minimum: float, maximum: float, value: float) -> float:
    return minimum + (maximum - minimum) * value


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
