from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ReplayPoint:
    node_name: str
    checkpoint_id: str
    config: dict[str, Any]


def checkpoint_id_from_config(
    config: dict[str, Any] | None,
) -> str | None:
    checkpoint_id = (
        (config or {}).get("configurable", {}).get("checkpoint_id")
    )
    return str(checkpoint_id) if checkpoint_id else None


def current_checkpoint_lineage(
    history: Iterable[Any],
    head_checkpoint_id: str,
) -> list[Any]:
    """Keep only checkpoints that are ancestors of the current head."""

    snapshots = list(history)
    by_id = {
        checkpoint_id: snapshot
        for snapshot in snapshots
        if (
            checkpoint_id := checkpoint_id_from_config(
                snapshot.config
            )
        )
    }
    lineage: list[Any] = []
    checkpoint_id: str | None = head_checkpoint_id

    while checkpoint_id is not None:
        snapshot = by_id.get(checkpoint_id)
        if snapshot is None:
            break
        lineage.append(snapshot)
        checkpoint_id = checkpoint_id_from_config(
            snapshot.parent_config
        )

    return lineage


def replay_points_from_history(
    history: Iterable[Any],
) -> list[ReplayPoint]:
    """Return the latest unambiguous checkpoint before each node."""

    points: list[ReplayPoint] = []
    seen: set[str] = set()

    for snapshot in history:
        next_nodes = tuple(snapshot.next or ())
        if len(next_nodes) != 1:
            # Replaying one member of a parallel superstep would also rerun
            # its siblings. Do not present that as a single-node replay.
            continue

        node_name = str(next_nodes[0])
        if node_name in seen:
            continue

        configurable = dict((snapshot.config or {}).get("configurable", {}))
        checkpoint_id = checkpoint_id_from_config(snapshot.config)
        if not checkpoint_id:
            continue

        points.append(
            ReplayPoint(
                node_name=node_name,
                checkpoint_id=str(checkpoint_id),
                config={
                    **dict(snapshot.config or {}),
                    "configurable": configurable,
                },
            )
        )
        seen.add(node_name)

    return points


def find_replay_point(
    history: Iterable[Any],
    node_name: str,
) -> ReplayPoint | None:
    return next(
        (
            point
            for point in replay_points_from_history(history)
            if point.node_name == node_name
        ),
        None,
    )
