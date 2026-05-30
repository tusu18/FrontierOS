"""Export utilities: CSV, JSON, TXT, Markdown."""

from __future__ import annotations
import csv
import io
import json
import os
from datetime import date
from typing import Dict, List


def papers_to_csv(papers: List[Dict]) -> str:
    """Convert paper list to CSV string."""
    if not papers:
        return ""
    fields = [
        "arxiv_id", "title", "authors", "primary_category", "published_date",
        "one_line_summary", "novelty_score", "impact_score", "technical_depth_score",
        "research_area", "arxiv_url", "pdf_url",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for p in papers:
        row = {k: p.get(k, "") for k in fields}
        if isinstance(row.get("authors"), list):
            row["authors"] = "; ".join(row["authors"])
        writer.writerow(row)
    return buf.getvalue()


def papers_to_json(papers: List[Dict]) -> str:
    """Convert paper list to JSON string."""
    return json.dumps(papers, indent=2, default=str)


def report_to_txt(report_md: str) -> str:
    """Strip basic Markdown from report for plain text export."""
    import re
    text = re.sub(r"#{1,6}\s+", "", report_md)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"---+", "---", text)
    return text


def save_to_file(content: str, filename: str, exports_dir: str = "exports") -> str:
    """Save content to exports directory. Returns file path."""
    os.makedirs(exports_dir, exist_ok=True)
    path = os.path.join(exports_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def make_export_filename(prefix: str, ext: str) -> str:
    today = date.today().isoformat()
    return f"{prefix}_{today}.{ext}"


def code_to_py(markdown: str, title: str = "implementation") -> str:
    """Extract Python code blocks from markdown and save as .py file."""
    import re
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", markdown, re.DOTALL)
    header = f'"""\nGenerated implementation for: {title}\n"""\n\n'
    if blocks:
        return header + "\n\n# ---\n\n".join(blocks)
    # If no code blocks, return the full markdown as a comment
    return header + "# " + markdown.replace("\n", "\n# ")
