"""BenchmarkExtractorAgent: Extracts datasets, benchmarks, and metrics from papers."""

from __future__ import annotations
import logging
import re
from collections import Counter
from typing import Dict, List

from app.database import get_session, get_papers_with_summaries

logger = logging.getLogger(__name__)

# Common CS/AI dataset names for pattern matching
KNOWN_DATASETS = [
    "ImageNet", "COCO", "CIFAR", "MNIST", "SQuAD", "GLUE", "SuperGLUE",
    "WikiText", "C4", "CommonCrawl", "The Pile", "OpenWebText",
    "MS MARCO", "TREC", "NQ", "TriviaQA", "HotpotQA", "FEVER",
    "Penn Treebank", "CoNLL", "OntoNotes", "ACE",
    "KITTI", "nuScenes", "Waymo", "Cityscapes",
    "LibriSpeech", "VoxCeleb", "AudioSet",
    "ShapeNet", "ModelNet",
    "GSM8K", "MATH", "HumanEval", "MBPP", "BigBench", "MMLU", "HellaSwag",
    "ARC", "WinoGrande", "PIQA", "SocialIQA",
    "Spider", "WikiSQL",
    "RefCOCO", "VQA", "GQA", "NLVR",
    "Atari", "OpenAI Gym", "MuJoCo",
]


class BenchmarkExtractorAgent:
    """
    Extracts benchmark, dataset, and metric information from paper summaries.

    Input:  list of paper dicts (from DB)
    Output: aggregated benchmark statistics dict
    """

    def run(self, limit: int = 200) -> Dict:
        session = get_session()
        try:
            papers = get_papers_with_summaries(session, limit=limit)
        finally:
            session.close()

        if not papers:
            return {}

        all_datasets = []
        all_metrics = []
        all_baselines = []
        dataset_papers = {}  # dataset -> list of paper titles

        for paper in papers:
            datasets = paper.get("datasets_or_benchmarks", [])
            if isinstance(datasets, list):
                for d in datasets:
                    all_datasets.append(d)
                    if d not in dataset_papers:
                        dataset_papers[d] = []
                    dataset_papers[d].append(paper.get("title", "")[:60])

            metrics = paper.get("metrics", [])
            if isinstance(metrics, list):
                all_metrics.extend(metrics)

            baselines = paper.get("baselines", [])
            if isinstance(baselines, list):
                all_baselines.extend(baselines)

            # Also scan abstract for known dataset names
            abstract = paper.get("abstract", "")
            for known in KNOWN_DATASETS:
                if known.lower() in abstract.lower():
                    all_datasets.append(known)

        dataset_freq = dict(Counter(all_datasets).most_common(30))
        metric_freq = dict(Counter(all_metrics).most_common(20))
        baseline_freq = dict(Counter(all_baselines).most_common(20))

        result = {
            "dataset_frequency": dataset_freq,
            "metric_frequency": metric_freq,
            "baseline_frequency": baseline_freq,
            "dataset_papers": {k: v[:5] for k, v in dataset_papers.items()},
            "total_papers_analyzed": len(papers),
            "unique_datasets": len(set(all_datasets)),
            "unique_metrics": len(set(all_metrics)),
        }

        logger.info(
            f"BenchmarkExtractorAgent: {result['unique_datasets']} unique datasets, "
            f"{result['unique_metrics']} unique metrics"
        )
        return result
