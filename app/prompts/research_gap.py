"""Prompt templates for research gap analysis."""

SYSTEM_PROMPT = """You are an expert AI research strategist who identifies research gaps
and opportunities in academic literature. Return ONLY valid JSON."""

def build_gap_prompt(summaries_text: str) -> list:
    user_content = f"""Analyze the following research paper summaries and identify underexplored research gaps.

Summaries:
{summaries_text[:6000]}

Return JSON with these keys:
{{
  "underexplored_areas": [
    {{
      "area": "Area name",
      "reason": "Why it's underexplored",
      "opportunity": "What could be done",
      "difficulty": "easy/medium/hard",
      "novelty": "high/medium/low"
    }}
  ],
  "publishable_directions": [
    {{
      "title": "Proposed project title",
      "idea": "Brief description",
      "gap_addressed": "What gap this fills",
      "approach": "Suggested approach",
      "datasets": ["dataset1"],
      "expected_contribution": "What this would contribute"
    }}
  ],
  "saturated_topics": ["topic1", "topic2"],
  "frontier_questions": ["question1", "question2"],
  "cross_domain_opportunities": ["opportunity1", "opportunity2"]
}}

Return ONLY the JSON."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_deep_analysis_prompt(title: str, abstract: str, summary_data: dict) -> list:
    user_content = f"""Provide a deep technical analysis of this research paper.

Title: {title}
Abstract: {abstract}
Existing analysis: {str(summary_data)[:2000]}

Return a detailed Markdown analysis with:

## Deep Technical Analysis

### Problem Statement
### Proposed Solution
### Technical Method Details
### Key Innovations
### Experimental Setup
### Results Analysis
### Why This Paper Matters
### Connections to Related Work
### Possible Research Extensions
### Implementation Difficulty Assessment
### Reproducibility Notes
### Questions This Paper Raises"""

    return [
        {"role": "system", "content": "You are an expert AI/ML research scientist. Write detailed technical analysis."},
        {"role": "user", "content": user_content},
    ]
