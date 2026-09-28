import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from publish import PublicationError, evaluate, main, render_markdown


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_ablation.json"


class PublicationTests(unittest.TestCase):
    def report(self):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def publish(self):
        source = FIXTURE.read_bytes()
        return evaluate(
            json.loads(source),
            source,
            "PR #175 commit a6c525f, experiments/wp11_4/reports/synthetic_ablation.json",
        )

    def evaluate_changed(self, report):
        source = json.dumps(report, sort_keys=True).encode("utf-8")
        return evaluate(report, source, "immutable test reference")

    def test_recommendation_fails_closed(self):
        publication = self.publish()
        self.assertEqual(publication["recommendation"], "do-not-promote")
        self.assertEqual(publication["scientific_status"], "exploratory-only")
        self.assertEqual(publication["evidence_class"], "synthetic-fixture")

    def test_publication_is_deterministic(self):
        self.assertEqual(self.publish(), self.publish())
        self.assertEqual(render_markdown(self.publish()), render_markdown(self.publish()))

    def test_rejects_promoted_upstream_status(self):
        report = self.report()
        report["scientific_status"] = "promoted"
        with self.assertRaisesRegex(PublicationError, "exploratory-not-promoted"):
            self.evaluate_changed(report)

    def test_requires_limitations(self):
        report = self.report()
        report["limitations"] = []
        with self.assertRaisesRegex(PublicationError, "limitations"):
            self.evaluate_changed(report)

    def test_requires_complete_comparison_classes(self):
        report = self.report()
        report["variants"] = [item for item in report["variants"] if item["kind"] != "feature_ablation"]
        with self.assertRaisesRegex(PublicationError, "feature_ablation"):
            self.evaluate_changed(report)

    def test_rejects_non_finite_metrics(self):
        report = self.report()
        report["variants"][0]["metrics"]["rmse_m"] = float("nan")
        with self.assertRaisesRegex(PublicationError, "finite and non-negative"):
            self.evaluate_changed(report)

    def test_hashed_bytes_must_match_evaluated_report(self):
        with self.assertRaisesRegex(PublicationError, "exactly represent"):
            evaluate(self.report(), b"{}", "reference")

    def test_requires_positive_sample_count(self):
        report = self.report()
        report["sample_count"] = 0
        with self.assertRaisesRegex(PublicationError, "positive integer"):
            self.evaluate_changed(report)

    def test_requires_exactly_one_model_variant(self):
        report = self.report()
        duplicate = dict(report["variants"][1])
        duplicate["variant_id"] = "second_model"
        report["variants"].append(duplicate)
        with self.assertRaisesRegex(PublicationError, "exactly one full model"):
            self.evaluate_changed(report)

    def test_markdown_states_claim_boundary(self):
        markdown = render_markdown(self.publish())
        self.assertIn("**DO NOT PROMOTE.**", markdown)
        self.assertIn("Prohibited:", markdown)
        self.assertIn("synthetic-fixture", markdown)

    def test_cli_writes_both_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_json = Path(temporary) / "publication.json"
            output_markdown = Path(temporary) / "publication.md"
            previous = sys.argv
            try:
                sys.argv = [
                    "publish.py",
                    str(FIXTURE),
                    "--upstream-reference",
                    "PR #175 commit a6c525f synthetic report",
                    "--output-json",
                    str(output_json),
                    "--output-markdown",
                    str(output_markdown),
                ]
                self.assertEqual(main(), 0)
            finally:
                sys.argv = previous
            self.assertEqual(json.loads(output_json.read_text())["recommendation"], "do-not-promote")
            self.assertIn("DO NOT PROMOTE", output_markdown.read_text())


if __name__ == "__main__":
    unittest.main()
