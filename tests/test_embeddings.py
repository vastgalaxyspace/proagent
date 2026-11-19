from __future__ import annotations

from dataclasses import dataclass
import unittest

from app.infrastructure.providers.embeddings import (
    _order_embedding_items,
)


@dataclass
class EmbeddingItem:
    index: int | None
    embedding: list[float]


class OrderEmbeddingItemsTests(unittest.TestCase):
    def test_orders_complete_provider_indexes(self) -> None:
        items = [
            EmbeddingItem(index=1, embedding=[2.0]),
            EmbeddingItem(index=0, embedding=[1.0]),
        ]

        ordered = _order_embedding_items(
            items,
            expected_count=2,
        )

        self.assertEqual(
            [item.embedding for item in ordered],
            [[1.0], [2.0]],
        )

    def test_preserves_order_when_indexes_are_missing(self) -> None:
        items = [
            EmbeddingItem(index=0, embedding=[1.0]),
            EmbeddingItem(index=None, embedding=[2.0]),
        ]

        with self.assertLogs(
            "app.infrastructure.providers.embeddings",
            level="WARNING",
        ):
            ordered = _order_embedding_items(
                items,
                expected_count=2,
            )

        self.assertEqual(ordered, items)

    def test_rejects_incomplete_batches(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "incomplete batch",
        ):
            _order_embedding_items(
                [EmbeddingItem(index=0, embedding=[1.0])],
                expected_count=2,
            )

    def test_rejects_duplicate_indexes(self) -> None:
        items = [
            EmbeddingItem(index=0, embedding=[1.0]),
            EmbeddingItem(index=0, embedding=[2.0]),
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "invalid response indexes",
        ):
            _order_embedding_items(
                items,
                expected_count=2,
            )


if __name__ == "__main__":
    unittest.main()
