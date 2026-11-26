"""Drops near-duplicate stories within one run (the same news from two outlets).

Plain text similarity, no embeddings: the larger of a character-sequence ratio and word overlap
(Jaccard) between titles. Above 0.85 counts as the same story. Pure Python, so it runs anywhere.
Stories already published on earlier days are caught separately, by link, in memory (store.py).
"""
import difflib

THRESHOLD = 0.85


def similarity(a, b):
    a, b = a.lower().strip(), b.lower().strip()
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    wa, wb = set(a.split()), set(b.split())
    jaccard = len(wa & wb) / len(wa | wb) if wa and wb else 0.0
    return max(ratio, jaccard)


class Deduplicator:
    def __init__(self):
        self.items = []

    def add_item_if_not_duplicate(self, item):
        """Keep the item unless its link or its title matches one already kept this run."""
        text = item.get("text_to_embed") or item.get("title", "")
        for kept in self.items:
            if item.get("url") and item.get("url") == kept.get("url"):
                return False
            if similarity(text, kept.get("text_to_embed") or kept.get("title", "")) > THRESHOLD:
                return False
        self.items.append(item)
        return True
