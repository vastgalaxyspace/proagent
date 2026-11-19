from __future__ import annotations

import operator
from types import SimpleNamespace
from typing import Annotated

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.tender_agent.replay import (
    current_checkpoint_lineage,
    find_replay_point,
    replay_points_from_history,
)


class TraceState(TypedDict):
    trace: Annotated[list[str], operator.add]


def test_historical_checkpoint_reruns_selected_node_and_descendants() -> None:
    executions = {"a": 0, "b": 0, "c": 0}
    builder = StateGraph(TraceState)

    def node(name: str):
        def run(_state: TraceState) -> TraceState:
            executions[name] += 1
            return {"trace": [name]}

        return run

    builder.add_node("a", node("a"))
    builder.add_node("b", node("b"))
    builder.add_node("c", node("c"))
    builder.add_edge(START, "a")
    builder.add_edge("a", "b")
    builder.add_edge("b", "c")
    builder.add_edge("c", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "replay-test"}}

    assert graph.invoke({"trace": []}, config=config)["trace"] == [
        "a",
        "b",
        "c",
    ]

    replay_point = find_replay_point(
        graph.get_state_history(config),
        "b",
    )
    assert replay_point is not None

    replayed = graph.invoke(None, config=replay_point.config)

    assert replayed["trace"] == ["a", "b", "c"]
    assert executions == {"a": 1, "b": 2, "c": 2}


def test_parallel_checkpoint_is_not_offered_as_single_node_replay() -> None:
    snapshot = SimpleNamespace(
        next=("node_b", "node_c"),
        config={
            "configurable": {
                "thread_id": "thread-1",
                "checkpoint_id": "checkpoint-1",
            }
        },
    )

    assert replay_points_from_history([snapshot]) == []


def test_latest_checkpoint_for_a_node_is_selected() -> None:
    def snapshot(checkpoint_id: str):
        return SimpleNamespace(
            next=("node_b",),
            config={
                "configurable": {
                    "thread_id": "thread-1",
                    "checkpoint_id": checkpoint_id,
                }
            },
        )

    points = replay_points_from_history(
        [snapshot("newest"), snapshot("older")]
    )

    assert len(points) == 1
    assert points[0].checkpoint_id == "newest"


def test_current_lineage_excludes_abandoned_branch() -> None:
    def snapshot(checkpoint_id: str, parent_id: str | None):
        return SimpleNamespace(
            config={
                "configurable": {
                    "thread_id": "thread-1",
                    "checkpoint_id": checkpoint_id,
                }
            },
            parent_config=(
                {
                    "configurable": {
                        "thread_id": "thread-1",
                        "checkpoint_id": parent_id,
                    }
                }
                if parent_id
                else None
            ),
        )

    root = snapshot("root", None)
    abandoned = snapshot("old-branch", "root")
    current = snapshot("new-branch", "root")

    lineage = current_checkpoint_lineage(
        [current, abandoned, root],
        "new-branch",
    )

    assert [item.config["configurable"]["checkpoint_id"] for item in lineage] == [
        "new-branch",
        "root",
    ]
