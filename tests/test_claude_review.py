#!/usr/bin/env python3
"""Regression tests for the structured PR review agent."""
from __future__ import annotations

import pathlib
import runpy
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "claude-review"

module_globals = runpy.run_path(str(MODULE_PATH))
claude_review = SimpleNamespace(**module_globals)


class ClaudeReviewTests(unittest.TestCase):
    def test_parse_pr_url_accepts_canonical_github_url(self) -> None:
        self.assertEqual(
            claude_review.parse_pr_url("https://github.com/example/project/pull/42"),
            ("example", "project", 42),
        )

    def test_parse_pr_url_rejects_invalid_url(self) -> None:
        with self.assertRaises(SystemExit):
            claude_review.parse_pr_url("https://github.com/example/project/issues/42")

    def test_agent_definition_documents_cli_usage(self) -> None:
        agent = (ROOT / ".claude" / "agents" / "pr-reviewer.md").read_text(encoding="utf-8")

        self.assertIn("name: pr-reviewer", agent)
        self.assertIn("python3 claude-review --pr", agent)
        self.assertIn("Summary of changes", agent)
        self.assertIn("Confidence score", agent)

    def test_build_review_includes_required_sections_and_confidence(self) -> None:
        pr = {
            "title": "Add workflow automation",
            "additions": 25,
            "deletions": 4,
        }
        files = [
            claude_review.FileChange(
                filename=".github/workflows/review.yml",
                additions=20,
                deletions=1,
                status="modified",
                patch="+token: ${{ secrets.GITHUB_TOKEN }}",
            ),
            claude_review.FileChange(
                filename="tests/test_review.py",
                additions=5,
                deletions=3,
                status="added",
                patch="+def test_review(): pass",
            ),
        ]

        original_fetch_pr = claude_review.build_review.__globals__["fetch_pr"]
        claude_review.build_review.__globals__["fetch_pr"] = mock.Mock(return_value=(pr, files))
        try:
            review = claude_review.build_review("https://github.com/example/project/pull/42")
        finally:
            claude_review.build_review.__globals__["fetch_pr"] = original_fetch_pr

        self.assertIn("## Claude PR Review", review)
        self.assertIn("### Summary of changes", review)
        self.assertIn("### Identified risks", review)
        self.assertIn("### Improvement suggestions", review)
        self.assertIn("### Confidence score", review)
        self.assertIn("Workflow or CI changes", review)
        self.assertIn("credential-related terms", review)
        self.assertRegex(review, r"\*\*(Low|Medium|High)\*\*")


if __name__ == "__main__":
    unittest.main()
