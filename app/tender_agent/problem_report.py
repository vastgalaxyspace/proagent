from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID


def problem_report_path(
    report_root: Path,
    operation_id: UUID,
) -> Path:
    return report_root / f"{operation_id}-problems.json"


def build_problem_report(
    *,
    operation_id: UUID,
    thread_id: str,
    request_id: str,
    tender_version_id: UUID,
    operation_status: str,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    state = dict(result or {})
    problems = list(state.get("problem_events") or [])

    # Older checkpoints do not contain structured problem events. Preserve
    # their accumulated warning/error messages in the downloadable report.
    if not problems:
        recorded_at = datetime.now(timezone.utc).isoformat()
        problems.extend(
            {
                "node": None,
                "severity": "warning",
                "message": str(message),
                "recorded_at": recorded_at,
            }
            for message in state.get("warnings", [])
        )
        problems.extend(
            {
                "node": state.get("failed_node"),
                "severity": "error",
                "message": str(message),
                "recorded_at": recorded_at,
            }
            for message in state.get("errors", [])
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "operation_id": str(operation_id),
        "thread_id": thread_id,
        "request_id": request_id,
        "tender_version_id": str(tender_version_id),
        "operation_status": operation_status,
        "workflow_status": state.get("workflow_status"),
        "summary": {
            "problem_count": len(problems),
            "warning_count": sum(
                item.get("severity") == "warning"
                for item in problems
            ),
            "error_count": sum(
                item.get("severity") == "error"
                for item in problems
            ),
        },
        "problems": problems,
    }


def write_problem_report(
    *,
    report_root: Path,
    operation_id: UUID,
    thread_id: str,
    request_id: str,
    tender_version_id: UUID,
    operation_status: str,
    result: dict[str, Any] | None,
) -> Path:
    report = build_problem_report(
        operation_id=operation_id,
        thread_id=thread_id,
        request_id=request_id,
        tender_version_id=tender_version_id,
        operation_status=operation_status,
        result=result,
    )
    path = problem_report_path(report_root, operation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path
