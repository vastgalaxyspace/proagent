from __future__ import annotations

from pprint import pprint
from uuid import uuid4

from app.tender_agent.graph import build_tender_graph


def main() -> None:
    graph = build_tender_graph()

    thread_id = f"tender-demo-{uuid4()}"

    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    initial_state = {
        "request_id": "request-001",
        "tender_version_id": "tender-version-001",
        "document_ids": ["document-001"],
        "warnings": [],
        "errors": [],
    }

    runtime_context = {
        "tenant_id": "tenant-001",
        "user_id": "user-001",
    }

    result = graph.invoke(
        initial_state,
        config=config,
        context=runtime_context,
    )
    
    print(f"Thread ID: {thread_id}")
    pprint(result)


if __name__ == "__main__":
    main()