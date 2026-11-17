"""Tests for passive and active key expiration."""

import random
import time
import unittest
from unittest.mock import patch

from kuyil.store import Store


class StoreExpiryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Store()

    def test_get_passively_deletes_expired_key(self) -> None:
        self.store.set("expired", "value", expires_at=time.time() - 1)

        self.assertIsNone(self.store.get("expired"))
        self.assertNotIn("expired", self.store._data)
        self.assertNotIn("expired", self.store._expires)

    def test_active_cycle_deletes_unaccessed_expired_keys(self) -> None:
        self.store.set("old-a", "a", expires_at=time.time() - 2)
        self.store.set("old-b", "b", expires_at=time.time() - 1)
        self.store.set("live", "c", expires_at=time.time() + 60)

        with patch.object(
            random, "sample", side_effect=lambda population, count: list(population)[:count]
        ):
            sampled, expired, _ = self.store.active_expire_cycle(time_budget=1)

        self.assertEqual(expired, 2)
        self.assertGreaterEqual(sampled, 2)
        self.assertNotIn("old-a", self.store._data)
        self.assertNotIn("old-b", self.store._data)
        self.assertIsNotNone(self.store.get("live"))

    def test_cycle_stops_when_expired_share_is_at_most_ten_percent(self) -> None:
        self.store.set("expired", "value", expires_at=time.time() - 1)
        for index in range(9):
            self.store.set(
                f"live-{index}", index, expires_at=time.time() + 60
            )

        with patch.object(
            random, "sample", side_effect=lambda population, count: list(population)[:count]
        ):
            sampled, expired, _ = self.store.active_expire_cycle(time_budget=1)

        self.assertEqual(sampled, 10)
        self.assertEqual(expired, 1)
        self.assertEqual(len(self.store._expires), 9)

    def test_expiry_update_does_not_duplicate_sampling_entry(self) -> None:
        self.store.set("key", "value", expires_at=time.time() + 10)
        self.store.set_expiry("key", time.time() + 20)

        self.assertEqual(len(self.store._expiry_keys), 1)
        self.assertEqual(self.store._expiry_positions["key"], 0)

    def test_overwrite_without_ttl_clears_previous_expiry(self) -> None:
        self.store.set("key", "old", expires_at=time.time() + 10)
        self.store.set("key", "new")

        self.assertIsNone(self.store.get_expiry("key"))
        self.assertEqual(self.store._expiry_keys, [])
        self.assertEqual(self.store.get("key").value, "new")

    def test_delete_removes_expiry_index_entry(self) -> None:
        self.store.set("first", 1, expires_at=time.time() + 10)
        self.store.set("second", 2, expires_at=time.time() + 10)

        self.assertTrue(self.store.delete("first"))

        self.assertNotIn("first", self.store._expiry_positions)
        self.assertEqual(self.store._expiry_keys, ["second"])
        self.assertEqual(self.store._expiry_positions["second"], 0)


if __name__ == "__main__":
    unittest.main()
