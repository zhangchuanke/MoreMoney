"""
news_filter internal implementation: ChromaDB dedup + filter logic.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from signal_filter.news_filter import (
    CREDIBILITY_THRESHOLD,
    DUPLICATE_SIMILARITY_THRESHOLD,
    DUPLICATE_WINDOW_DAYS,
    OFFICIAL_DISCLOSURE_SOURCES,
    SOURCE_CREDIBILITY,
    FilteredNewsResult,
    NewsItem,
)

logger = logging.getLogger(__name__)


def _content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _get_credibility(source: str) -> float:
    for key, score in SOURCE_CREDIBILITY.items():
        if key in source:
            return score
    return 0.40


def _is_official(source: str) -> bool:
    return any(s in source for s in OFFICIAL_DISCLOSURE_SOURCES)


class _DuplicateDetector:
    """
    Detects duplicate/recycled news via ChromaDB vector similarity.
    Gracefully degrades to MD5 hash dedup when ChromaDB is unavailable.
    """

    def __init__(self) -> None:
        self._collection = None
        self._chroma_ok  = False
        self._hash_seen: Dict[str, str] = {}
        self._try_init_chroma()

    def _try_init_chroma(self) -> None:
        try:
            import chromadb  # type: ignore
            from chromadb.utils import embedding_functions  # type: ignore
            client = chromadb.Client()
            emb_fn = embedding_functions.DefaultEmbeddingFunction()
            self._collection = client.get_or_create_collection(
                name="news_history",
                embedding_function=emb_fn,
                metadata={"hnsw:space": "cosine"},
            )
            self._chroma_ok = True
            logger.info("[NewsFilter] ChromaDB ready, vector dedup enabled")
        except Exception as exc:
            logger.warning("[NewsFilter] ChromaDB unavailable (%s), hash dedup only", exc)

    def is_duplicate(self, item: NewsItem) -> Tuple[bool, float, str]:
        h = item.content_hash
        if h in self._hash_seen:
            return True, 1.0, self._hash_seen[h]

        if self._chroma_ok and self._collection is not None:
            try:
                text    = f"{item.title} {item.content[:200]}"
                results = self._collection.query(query_texts=[text], n_results=1)
                if results and results.get("distances"):
                    dist = results["distances"][0]
                    if dist:
                        similarity = 1.0 - float(dist[0])
                        if similarity >= DUPLICATE_SIMILARITY_THRESHOLD:
                            docs = results.get("documents", [[]])[0]
                            return True, similarity, docs[0] if docs else ""
            except Exception as exc:
                logger.debug("[NewsFilter] ChromaDB query error: %s", exc)

        return False, 0.0, ""

    def add_to_history(self, item: NewsItem) -> None:
        self._hash_seen[item.content_hash] = item.title
        if self._chroma_ok and self._collection is not None:
            try:
                text = f"{item.title} {item.content[:200]}"
                self._collection.upsert(
                    ids=[item.content_hash],
                    documents=[text],
                    metadatas=[{
                        "title":    item.title,
                        "source":   item.source,
                        "pub_time": item.pub_time,
                        "symbol":   item.symbol,
                    }],
                )
            except Exception as exc:
                logger.debug("[NewsFilter] ChromaDB upsert error: %s", exc)


_detector = _DuplicateDetector()


def filter_news_items(
    raw_items: List[Dict],
    symbol: str,
    official_only: bool = False,
) -> FilteredNewsResult:
    """
    Run the full filter pipeline on a list of raw news dicts.

    Pipeline:
      1. Credibility gate  (source whitelist / score threshold)
      2. Duplicate gate    (ChromaDB vector sim or MD5 hash)

    Args:
        raw_items:     list of raw news dicts from NewsCrawler / AnnouncementParser
        symbol:        stock code
        official_only: if True, only accept CSRC-designated disclosure media
    """
    result = FilteredNewsResult(symbol=symbol, original_count=len(raw_items))

    for raw in raw_items:
        item = NewsItem(
            title=raw.get("title", ""),
            content=raw.get("content", ""),
            source=raw.get("source", ""),
            pub_time=raw.get("pub_time", ""),
            url=raw.get("url", ""),
            symbol=symbol,
        )
        item.content_hash = _content_hash(item.title + item.content[:100])
        item.credibility  = _get_credibility(item.source)
        item.is_official  = _is_official(item.source)

        # Gate 1: credibility
        if official_only and not item.is_official:
            result.rejected_low_credibility.append(item)
            continue
        if not official_only and item.credibility < CREDIBILITY_THRESHOLD:
            result.rejected_noise.append(item)
            continue

        # Gate 2: duplicate detection
        is_dup, sim_score, dup_title = _detector.is_duplicate(item)
        if is_dup:
            item.is_duplicate     = True
            item.similarity_score = sim_score
            item.duplicate_of     = dup_title
            result.rejected_duplicate.append(item)
            continue

        _detector.add_to_history(item)
        result.accepted.append(item)

    logger.info(
        "[NewsFilter] %s: total=%d accepted=%d low_cred=%d dup=%d noise=%d",
        symbol,
        result.original_count,
        result.accepted_count,
        len(result.rejected_low_credibility),
        len(result.rejected_duplicate),
        len(result.rejected_noise),
    )
    return result
