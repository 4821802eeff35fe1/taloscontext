"""Local, zero-cost duplicate detection. Deliberately does not call AI —
see ARCHITECTURE.md §5 / product brief §15. Combines:
  - normalized-text trigram similarity (cheap, catches near-identical text)
  - SimHash over token shingles (catches reordered/paraphrased duplicates)
  - category/tags/angle agreement (catches thematic repeats)
into a single 0..1 duplicate_score.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def shingles(text: str, k: int = 4) -> set[str]:
    tokens = normalize_text(text).split()
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def simhash(text: str, bits: int = 64) -> int:
    tokens = normalize_text(text).split()
    v = [0] * bits
    for token in tokens:
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        for i in range(bits):
            v[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(bits):
        if v[i] > 0:
            out |= 1 << i
    return out


def hamming_similarity(a: int, b: int, bits: int = 64) -> float:
    distance = (a ^ b).bit_count()
    return 1 - (distance / bits)


class DuplicateCandidate:
    def __init__(self, content_item_id: str, title: str, text: str, category: str, tags: list[str]):
        self.content_item_id = content_item_id
        self.title = title
        self.text = text
        self.category = category
        self.tags = set(tags)
        self.shingles = shingles(f"{title} {text}")
        self.simhash = simhash(f"{title} {text}")


class DuplicateDetectionService:
    def score(
        self,
        *,
        candidate_title: str,
        candidate_text: str,
        candidate_category: str,
        candidate_tags: list[str],
        recent_items: list[DuplicateCandidate],
    ) -> tuple[float, str | None]:
        """Returns (best_score, best_match_content_item_id)."""
        candidate_shingles = shingles(f"{candidate_title} {candidate_text}")
        candidate_simhash = simhash(f"{candidate_title} {candidate_text}")
        candidate_tag_set = set(candidate_tags)

        best_score = 0.0
        best_match: str | None = None
        for item in recent_items:
            text_sim = jaccard(candidate_shingles, item.shingles)
            hash_sim = hamming_similarity(candidate_simhash, item.simhash)
            tag_sim = jaccard(candidate_tag_set, item.tags)
            category_bonus = 0.1 if candidate_category == item.category and item.category else 0.0

            score = min(1.0, (0.45 * text_sim) + (0.35 * hash_sim) + (0.1 * tag_sim) + category_bonus)
            if score > best_score:
                best_score = score
                best_match = item.content_item_id

        return round(best_score, 4), best_match


DUPLICATE_WARNING_THRESHOLD_DEFAULT = 0.60
DUPLICATE_BLOCK_THRESHOLD_DEFAULT = 0.80
