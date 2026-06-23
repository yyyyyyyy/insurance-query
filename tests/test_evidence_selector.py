"""Evidence selector boundary tests."""

from runtime.evidence.canonical import CanonicalEvidence, CanonicalEvidenceSet
from runtime.evidence.selector import select_evidence_for_answer


def _item(eid: str, score: float, source: str = "tool") -> CanonicalEvidence:
    return CanonicalEvidence(
        canonical_id=eid,
        source=source,
        relevance_score=score,
        payload={"content": f"content-{eid}"},
    )


class TestEvidenceSelector:
    def test_threshold_filters_low_scores(self):
        ces = CanonicalEvidenceSet()
        ces.add_candidates([_item("e1", 0.9), _item("e2", 0.05)])
        accepted, rejected = select_evidence_for_answer(ces, evidence_threshold=0.2)
        assert "e1" in accepted
        assert "e2" in rejected

    def test_force_accept_sources(self):
        ces = CanonicalEvidenceSet()
        ces.add_candidates([
            CanonicalEvidence(
                canonical_id="r1",
                source="rule",
                relevance_score=0.01,
                provenance={"matched": True},
            ),
        ])
        accepted, _ = select_evidence_for_answer(
            ces, evidence_threshold=0.5, force_accept_sources={"rule"},
        )
        assert "r1" in accepted
