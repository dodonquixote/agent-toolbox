import unittest
from unittest import mock

from agent_toolbox import registry
from agent_toolbox.tools import citations
from agent_toolbox.tools.citations import (
    extract_content_terms,
    score_support,
    verdict_for,
)

SOURCE_TEXT = (
    "The Eiffel Tower is a wrought-iron lattice tower in Paris, France. "
    "Construction started in 1887 and the tower opened to the public in 1889. "
    "It was designed by Gustave Eiffel and stands 330 metres tall."
)

SUPPORTED_CLAIM = "The Eiffel Tower in Paris opened in 1889."
WEAK_CLAIM = "The Eiffel Tower in Paris was built by Roman engineers in 1066."
UNSUPPORTED_CLAIM = "The wooden bridge in Tokyo carries trains daily."


class TestContentTerms(unittest.TestCase):
    def test_stopwords_and_short_words_dropped(self):
        terms = extract_content_terms("The quick brown fox jumps over the lazy dog")
        self.assertEqual(terms, ["quick", "brown", "fox", "jumps", "lazy", "dog"])

    def test_deduplicated_and_lowercased(self):
        terms = extract_content_terms("Paris Paris PARIS tower")
        self.assertEqual(terms, ["paris", "tower"])


class TestScoreSupport(unittest.TestCase):
    def test_supported_claim_scores_high(self):
        result = score_support(SUPPORTED_CLAIM, SOURCE_TEXT)
        self.assertGreaterEqual(result["score"], 0.6)
        self.assertIn("paris", result["matched_terms"])
        self.assertIn("1889", result["matched_terms"])

    def test_unsupported_claim_scores_zero(self):
        result = score_support(UNSUPPORTED_CLAIM, SOURCE_TEXT)
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["matched_terms"], [])

    def test_weak_claim_partial_overlap(self):
        result = score_support(WEAK_CLAIM, SOURCE_TEXT)
        self.assertGreater(result["score"], 0.0)
        self.assertLess(result["score"], 0.6)
        self.assertIn("paris", result["matched_terms"])
        self.assertIn("roman", result["missing_terms"])

    def test_claim_with_no_content_terms(self):
        result = score_support("It is the", SOURCE_TEXT)
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["claim_terms"], [])


class TestVerdictFor(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(verdict_for(1.0), "supported")
        self.assertEqual(verdict_for(0.6), "supported")
        self.assertEqual(verdict_for(0.59), "weak")
        self.assertEqual(verdict_for(0.3), "weak")
        self.assertEqual(verdict_for(0.29), "unsupported")
        self.assertEqual(verdict_for(0.0), "unsupported")


class TestVerifyCitations(unittest.TestCase):
    def _run_with_stub(self, fetch_map):
        def fake_fetch(url, max_chars):
            if url in fetch_map:
                return fetch_map[url]
            raise ValueError("bad url")

        with mock.patch.object(citations, "_fetch_source", side_effect=fake_fetch):
            return citations.verify_citations([
                {"claim": SUPPORTED_CLAIM, "url": "https://example.test/paris"},
                {"claim": WEAK_CLAIM, "url": "https://example.test/paris"},
                {"claim": UNSUPPORTED_CLAIM, "url": "https://example.test/paris"},
                {"claim": SUPPORTED_CLAIM, "url": "https://example.test/dead"},
            ])

    def test_verdicts_and_summary(self):
        result = self._run_with_stub({
            "https://example.test/paris": {"title": "Eiffel Tower", "text": SOURCE_TEXT},
        })
        verdicts = [r["verdict"] for r in result["results"]]
        self.assertEqual(verdicts, ["supported", "weak", "unsupported", "unreachable"])
        self.assertEqual(result["summary"], {
            "total": 4, "supported": 1, "weak": 1,
            "unsupported": 1, "unreachable": 1,
        })

    def test_unreachable_records_error(self):
        result = self._run_with_stub({})
        entry = result["results"][0]
        self.assertEqual(entry["verdict"], "unreachable")
        self.assertIn("ValueError", entry["error"])
        self.assertIsNone(entry["source_title"])

    def test_supported_entry_carries_title_and_terms(self):
        result = self._run_with_stub({
            "https://example.test/paris": {"title": "Eiffel Tower", "text": SOURCE_TEXT},
        })
        entry = result["results"][0]
        self.assertEqual(entry["source_title"], "Eiffel Tower")
        self.assertIsNone(entry["error"])
        self.assertIn("paris", entry["matched_terms"])

    def test_invalid_citation_rejected(self):
        with self.assertRaises(ValueError):
            citations.verify_citations([{"claim": "no url here"}])

    def test_registered_in_registry(self):
        self.assertIn("verify_citations", registry.names())
        defs = {d["function"]["name"]: d for d in registry.function_definitions()}
        self.assertEqual(defs["verify_citations"]["function"]["parameters"]["required"],
                         ["citations"])

    def test_callable_via_registry(self):
        # Invalid scheme fails inside fetch_url before any network use.
        result = registry.call("verify_citations", {
            "citations": [{"claim": SUPPORTED_CLAIM, "url": "ftp://example.test/x"}]})
        self.assertEqual(result["results"][0]["verdict"], "unreachable")


if __name__ == "__main__":
    unittest.main()
