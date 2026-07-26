import unittest

from src.simulation import RelationshipStore


class RelationshipStoreTests(unittest.TestCase):
    def test_received_help_changes_only_recipient_trust(self) -> None:
        store = RelationshipStore(
            capacity=2,
            half_life_ticks=10.0,
            balance_limit=2.0,
        )
        giver = store.allocate()
        recipient = store.allocate()

        store.record_given(giver, 2, 0.5, tick=1)
        store.record_received(
            recipient,
            1,
            0.5,
            tick=1,
            learning_rate=0.5,
        )

        giver_view = store.view(giver, 2, tick=1)
        recipient_view = store.view(recipient, 1, tick=1)
        self.assertEqual(giver_view.trust, 0.0)
        self.assertLess(giver_view.balance, 0.0)
        self.assertGreater(recipient_view.trust, 0.0)
        self.assertGreater(recipient_view.balance, 0.0)

    def test_relationship_values_decay_without_read_side_effects(self) -> None:
        store = RelationshipStore(capacity=1, half_life_ticks=10.0)
        row = store.allocate()
        store.record_received(
            row,
            3,
            1.0,
            tick=0,
            learning_rate=1.0,
        )
        raw_before = store.raw_row(row)

        view = store.view(row, 3, tick=10)

        self.assertAlmostEqual(view.trust, 0.5)
        self.assertEqual(store.raw_row(row), raw_before)

    def test_capacity_eviction_and_row_reuse_are_deterministic(self) -> None:
        store = RelationshipStore(capacity=2, half_life_ticks=10.0)
        row = store.allocate()
        store.observe(row, 5, tick=1)
        store.observe(row, 4, tick=1)
        store.observe(row, 6, tick=2)

        contacts = {view.other_id for view in store.views(row, tick=2)}
        self.assertEqual(len(contacts), 2)
        self.assertIn(6, contacts)

        store.release(row)
        reused = store.allocate()
        self.assertEqual(reused, row)
        self.assertEqual(store.views(reused, tick=2), ())


if __name__ == "__main__":
    unittest.main()
