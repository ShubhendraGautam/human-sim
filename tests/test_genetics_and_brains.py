import random
import unittest
from dataclasses import replace

from src.simulation import (
    BrainKind,
    BrainState,
    Gene,
    Genome,
    ReproductiveRole,
    Simulation,
    SimulationConfig,
)
from src.simulation.brain import ACTION_INDEX, choose_action
from src.simulation.genetics import GENOME_MASK, express_traits
from src.simulation.models import Action, ActionKind


class GeneticsTests(unittest.TestCase):
    def test_child_loci_come_from_each_parent_without_mutation(self) -> None:
        first = Genome(0x0F0F0F0F0F0F0F & GENOME_MASK, 0x33333333333333)
        second = Genome(0x55555555555555, 0x00FF00FF00FF00)

        child = Genome.recombine(
            first,
            second,
            random.Random(10),
            mutation_probability=0.0,
            crossover_probability=1.0,
        )

        self._assert_gamete_uses_parental_alleles(
            child.haplotype_a,
            first,
        )
        self._assert_gamete_uses_parental_alleles(
            child.haplotype_b,
            second,
        )

    def test_forced_mutation_flips_every_transmitted_locus(self) -> None:
        empty = Genome(0, 0)

        child = Genome.recombine(
            empty,
            empty,
            random.Random(11),
            mutation_probability=1.0,
            crossover_probability=0.0,
        )

        self.assertEqual(child.haplotype_a, GENOME_MASK)
        self.assertEqual(child.haplotype_b, GENOME_MASK)

    def test_genome_is_compact_and_phenotypes_stay_bounded(self) -> None:
        config = SimulationConfig()
        low = express_traits(Genome(0, 0), config)
        high = express_traits(Genome(GENOME_MASK, GENOME_MASK), config)

        self.assertLess(low.maximum_health, high.maximum_health)
        self.assertLess(low.lifespan, high.lifespan)
        self.assertGreaterEqual(low.vision, config.vision_minimum)
        self.assertLessEqual(high.vision, config.vision_maximum)
        self.assertGreater(high.metabolism, low.metabolism)

    @staticmethod
    def _assert_gamete_uses_parental_alleles(
        gamete: int,
        parent: Genome,
    ) -> None:
        both_zero = ~(parent.haplotype_a | parent.haplotype_b) & GENOME_MASK
        both_one = parent.haplotype_a & parent.haplotype_b
        self_has_novel_one = gamete & both_zero
        self_has_novel_zero = (~gamete) & both_one & GENOME_MASK
        if self_has_novel_one or self_has_novel_zero:
            raise AssertionError("gamete contains a non-parental allele")


class BrainTests(unittest.TestCase):
    def test_habitual_brain_can_learn_a_different_choice(self) -> None:
        simulation = Simulation(
            SimulationConfig(initial_population=1),
            seed=12,
        )
        agent = next(iter(simulation.agents.values()))
        agent.traits = express_traits(
            _genome_for_brain_style(0.6),
            simulation.config,
        )
        self.assertEqual(agent.traits.brain_kind, BrainKind.HABITUAL)
        agent.brain.preferences[ACTION_INDEX[ActionKind.MOVE]] = 2.0
        options = [
            (1.0, Action(ActionKind.REST, agent.id)),
            (0.0, Action(ActionKind.MOVE, agent.id, destination=(0, 0))),
        ]

        choice = choose_action(
            options,
            agent,
            (),
            random.Random(1),
            simulation.config,
        )

        self.assertEqual(choice.kind, ActionKind.MOVE)

    def test_lifetime_learning_is_not_shared_or_inherited_state(self) -> None:
        first = BrainState()
        second = BrainState()
        action = Action(ActionKind.GATHER, 1)

        first.learn(action, 1.0, 0.5, 1.0, 2.0)

        self.assertNotEqual(first.preferences, second.preferences)
        self.assertTrue(all(value == 0.0 for value in second.preferences))


class ReproductionTests(unittest.TestCase):
    def test_resolution_enforces_role_locality_and_fresh_child_state(
        self,
    ) -> None:
        config = SimulationConfig(
            width=5,
            height=5,
            initial_population=2,
            initial_energy_minimum=100.0,
            initial_energy_maximum=100.0,
            reproduction_energy=10.0,
            reproduction_cost=2.0,
            maximum_conception_probability=1.0,
            gene_mutation_probability=0.0,
            gestation_years=1.0 / 12.0,
        )
        simulation = Simulation(config, seed=13)
        first, second = simulation.agents.values()
        first.traits = replace(first.traits, fertility=1.0, maturity_age=1.0)
        second.traits = replace(second.traits, fertility=1.0, maturity_age=1.0)
        first.age = second.age = 20.0
        first.reproductive_role = ReproductiveRole.OVA
        second.reproductive_role = ReproductiveRole.OVA
        first.x, first.y = 0, 0
        second.x, second.y = 0, 1

        self.assertFalse(simulation._reproduce(first, second.id, set()))

        second.reproductive_role = ReproductiveRole.SPERM
        second.x, second.y = 4, 4
        self.assertFalse(simulation._reproduce(first, second.id, set()))

        second.x, second.y = 0, 1
        self.assertTrue(simulation._reproduce(first, second.id, set()))
        self.assertEqual(len(simulation.pregnancies), 1)
        self.assertEqual(len(simulation.agents), 2)
        simulation.tick = next(iter(simulation.pregnancies.values())).due_tick
        simulation._advance_pregnancies()
        child = max(simulation.agents.values(), key=lambda agent: agent.id)

        self.assertEqual(child.parents, (first.id, second.id))
        self.assertEqual(child.guardian_id, first.id)
        self.assertFalse(child.knows_seafaring)
        self.assertTrue(all(value == 0.0 for value in child.brain.preferences))
        self.assertLessEqual(
            child.energy,
            2.0 * config.reproduction_cost
            + config.gestation_energy_cost_per_tick
            + config.birth_energy_cost,
        )
        GeneticsTests._assert_gamete_uses_parental_alleles(
            child.genome.haplotype_a,
            first.genome,
        )
        GeneticsTests._assert_gamete_uses_parental_alleles(
            child.genome.haplotype_b,
            second.genome,
        )
        self.assertTrue(simulation._care(first, child.id))
        self.assertGreater(child.inventory, 0.0)

    def test_gestational_parent_death_loses_pregnancy(self) -> None:
        config = SimulationConfig(
            initial_population=2,
            initial_energy_minimum=100.0,
            initial_energy_maximum=100.0,
            reproduction_energy=10.0,
            reproduction_cost=2.0,
            maximum_conception_probability=1.0,
        )
        simulation = Simulation(config, seed=14)
        first, second = simulation.agents.values()
        first.reproductive_role = ReproductiveRole.OVA
        second.reproductive_role = ReproductiveRole.SPERM
        first.x = second.x = 0
        first.y = second.y = 0
        first.age = second.age = 30.0
        first.traits = replace(first.traits, fertility=1.0, maturity_age=1.0)
        second.traits = replace(second.traits, fertility=1.0, maturity_age=1.0)

        self.assertTrue(simulation._reproduce(first, second.id, set()))
        simulation._remove_agent(first.id)

        self.assertEqual(len(simulation.pregnancies), 0)
        self.assertEqual(simulation.total_pregnancy_losses, 1)
        self.assertEqual(simulation.total_births, 0)


def _genome_for_brain_style(value: float) -> Genome:
    active = round(value * 8)
    shift = int(Gene.COGNITIVE_STYLE) * 4
    first_count = min(active, 4)
    second_count = max(0, active - 4)
    first = ((1 << first_count) - 1) << shift
    second = ((1 << second_count) - 1) << shift
    return Genome(first, second)


if __name__ == "__main__":
    unittest.main()
