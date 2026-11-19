from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.tender_agent.problem_report import (
    build_problem_report,
    write_problem_report,
)
from app.tender_agent.tracking import tracked_node


class ProblemReportTests(unittest.TestCase):
    def test_report_preserves_node_and_severity(self) -> None:
        operation_id = uuid4()
        tender_version_id = uuid4()
        result = {
            "workflow_status": "failed",
            "problem_events": [
                {
                    "node": "inventory",
                    "severity": "warning",
                    "message": "Missing optional metadata.",
                    "recorded_at": "2026-11-19T12:00:00+00:00",
                },
                {
                    "node": "retrieval",
                    "severity": "error",
                    "message": "Indexing failed.",
                    "recorded_at": "2026-11-19T12:01:00+00:00",
                },
            ],
        }

        report = build_problem_report(
            operation_id=operation_id,
            thread_id="thread-1",
            request_id="request-1",
            tender_version_id=tender_version_id,
            operation_status="failed",
            result=result,
        )

        self.assertEqual(report["summary"]["problem_count"], 2)
        self.assertEqual(report["summary"]["warning_count"], 1)
        self.assertEqual(report["summary"]["error_count"], 1)
        self.assertEqual(report["problems"][1]["node"], "retrieval")

    def test_report_is_written_as_one_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_problem_report(
                report_root=Path(directory),
                operation_id=uuid4(),
                thread_id="thread-1",
                request_id="request-1",
                tender_version_id=uuid4(),
                operation_status="succeeded",
                result={"warnings": ["One warning."], "errors": []},
            )

            self.assertTrue(path.is_file())
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 1)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["problems"][0]["message"], "One warning.")

    def test_tracked_node_labels_problem_messages(self) -> None:
        def example_node(_state, _runtime):
            return {
                "workflow_status": "ready",
                "warnings": ["Review this value."],
                "errors": [],
            }

        wrapped = tracked_node("example_node", example_node)
        result = wrapped({}, SimpleNamespace(context={}))

        self.assertEqual(
            result["problem_events"][0]["node"],
            "example_node",
        )
        self.assertEqual(
            result["problem_events"][0]["severity"],
            "warning",
        )


if __name__ == "__main__":
    unittest.main()
