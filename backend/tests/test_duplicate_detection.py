from app.services.content.duplicate_detection import DuplicateCandidate, DuplicateDetectionService


def test_identical_text_scores_high():
    service = DuplicateDetectionService()
    candidate = DuplicateCandidate(
        content_item_id="1", title="5 ways to improve CTR", text="Some practical media buying tips here",
        category="educational", tags=["ctr", "tips"],
    )
    score, match = service.score(
        candidate_title="5 ways to improve CTR",
        candidate_text="Some practical media buying tips here",
        candidate_category="educational",
        candidate_tags=["ctr", "tips"],
        recent_items=[candidate],
    )
    assert score >= 0.8
    assert match == "1"


def test_unrelated_text_scores_low():
    service = DuplicateDetectionService()
    candidate = DuplicateCandidate(
        content_item_id="1", title="5 ways to improve CTR", text="Some practical media buying tips here",
        category="educational", tags=["ctr", "tips"],
    )
    score, match = service.score(
        candidate_title="Quarterly recruiting update",
        candidate_text="We are hiring three new account managers in Berlin this quarter",
        candidate_category="recruiting",
        candidate_tags=["hiring"],
        recent_items=[candidate],
    )
    assert score < 0.3


def test_no_recent_items_scores_zero():
    service = DuplicateDetectionService()
    score, match = service.score(
        candidate_title="Anything", candidate_text="Anything", candidate_category="x",
        candidate_tags=[], recent_items=[],
    )
    assert score == 0.0
    assert match is None
