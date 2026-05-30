"""Paper clustering using TF-IDF and K-means (no GPU required)."""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def cluster_papers(
    papers: List[Dict],
    n_clusters: int = 8,
    use_sentence_transformers: bool = False,
) -> Tuple[List[Dict], List[str]]:
    """
    Cluster papers by abstract/summary using TF-IDF + K-means.

    Returns:
        papers: enriched with 'cluster_id' and 'cluster_label'
        cluster_labels: list of cluster label strings
    """
    if len(papers) < n_clusters:
        n_clusters = max(2, len(papers) // 2)

    texts = []
    for p in papers:
        text = (
            p.get("title", "") + " " +
            p.get("abstract", "") + " " +
            p.get("one_line_summary", "") + " " +
            " ".join(p.get("keywords", []))
        )
        texts.append(text.strip())

    if not texts:
        return papers, []

    embeddings = None

    if use_sentence_transformers:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            embeddings = model.encode(texts, show_progress_bar=False)
            logger.info("clustering: using SentenceTransformer embeddings")
        except Exception as e:
            logger.warning(f"SentenceTransformer failed: {e}. Falling back to TF-IDF.")

    if embeddings is None:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            vectorizer = TfidfVectorizer(max_features=1000, stop_words="english")
            embeddings = vectorizer.fit_transform(texts).toarray()
            logger.info("clustering: using TF-IDF embeddings")
        except Exception as e:
            logger.error(f"TF-IDF failed: {e}")
            return papers, []

    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import normalize
        emb_norm = normalize(embeddings)
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(emb_norm)
    except Exception as e:
        logger.error(f"KMeans failed: {e}")
        return papers, []

    # Generate cluster labels from most common keywords
    cluster_keyword_map: Dict[int, List[str]] = {i: [] for i in range(n_clusters)}
    for paper, label in zip(papers, labels):
        kws = paper.get("keywords", []) + paper.get("trend_tags", [])
        cluster_keyword_map[int(label)].extend(kws)

    from collections import Counter
    cluster_labels = []
    for i in range(n_clusters):
        kws = cluster_keyword_map[i]
        if kws:
            top = [kw for kw, _ in Counter(kws).most_common(3)]
            cluster_labels.append(", ".join(top))
        else:
            cluster_labels.append(f"Cluster {i+1}")

    for paper, label in zip(papers, labels):
        paper["cluster_id"] = int(label)
        paper["cluster_label"] = cluster_labels[int(label)]

    return papers, cluster_labels


def get_cluster_summary(papers: List[Dict]) -> Dict[str, List[str]]:
    """Summarize papers by cluster."""
    clusters: Dict[str, List[str]] = {}
    for p in papers:
        label = p.get("cluster_label", "Unknown")
        title = p.get("title", "")
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(title)
    return clusters
