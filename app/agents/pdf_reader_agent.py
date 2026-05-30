"""PDFReaderAgent: Downloads and extracts text from arXiv paper PDFs."""

from __future__ import annotations
import io
import logging
import os
import re
import tempfile
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class PDFReaderAgent:
    """
    Downloads a PDF from arXiv and extracts clean text.

    Input:  pdf_url (str)
    Output: extracted text (str)
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def download_pdf(self, pdf_url: str) -> Optional[bytes]:
        """Download PDF bytes."""
        try:
            headers = {"User-Agent": "ArXivResearchDashboard/1.0"}
            resp = requests.get(pdf_url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            if "application/pdf" not in resp.headers.get("Content-Type", ""):
                logger.warning(f"Unexpected content type: {resp.headers.get('Content-Type')}")
            return resp.content
        except Exception as e:
            logger.error(f"PDFReaderAgent: download failed for {pdf_url}: {e}")
            return None

    def extract_text(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes using PyMuPDF (fitz)."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            texts = []
            for page in doc:
                texts.append(page.get_text())
            doc.close()
            full_text = "\n".join(texts)
            return self._clean_text(full_text)
        except ImportError:
            logger.error("PyMuPDF (fitz) not installed. Run: pip install pymupdf")
            return ""
        except Exception as e:
            logger.error(f"PDFReaderAgent: text extraction failed: {e}")
            return ""

    def _clean_text(self, text: str) -> str:
        """Remove common PDF artifacts."""
        # Remove excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        # Remove page numbers (lines that are just a number)
        text = re.sub(r"^\d+\s*$", "", text, flags=re.MULTILINE)
        # Remove hyphenation at line breaks
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        return text.strip()

    def extract_sections(self, text: str) -> dict:
        """Attempt to extract named sections (Abstract, Introduction, etc.)."""
        section_headers = [
            "abstract", "introduction", "related work", "background",
            "method", "methodology", "approach", "model", "experiments",
            "results", "discussion", "conclusion", "limitations",
            "future work", "references"
        ]
        sections = {}
        lines = text.split("\n")
        current_section = "preamble"
        current_lines = []

        for line in lines:
            stripped = line.strip().lower()
            matched_section = None
            for header in section_headers:
                if re.match(rf"^(\d+\.?\s+)?{re.escape(header)}s?\s*$", stripped, re.IGNORECASE):
                    matched_section = header
                    break

            if matched_section:
                if current_lines:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = matched_section
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            sections[current_section] = "\n".join(current_lines).strip()

        return sections

    def run(self, pdf_url: str) -> str:
        """Download PDF and extract text."""
        logger.info(f"PDFReaderAgent: downloading {pdf_url}")
        pdf_bytes = self.download_pdf(pdf_url)
        if not pdf_bytes:
            return ""
        text = self.extract_text(pdf_bytes)
        logger.info(f"PDFReaderAgent: extracted {len(text)} characters")
        return text
