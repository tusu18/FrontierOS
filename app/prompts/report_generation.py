"""Prompt templates for research report generation."""

SYSTEM_PROMPT = """You are a senior AI research analyst writing professional research reports.
Write in clear, professional English. Structure the report with Markdown headings.
Be specific and cite paper titles where relevant."""

def build_report_prompt(report_type: str, papers_text: str, category: str = "") -> list:
    category_note = f" focused on {category}" if category else ""
    user_content = f"""Generate a {report_type} research report{category_note} based on the following papers.

Papers data:
{papers_text[:7000]}

Write a comprehensive Markdown report with these sections:

# {report_type.title()} Research Report{category_note}

## Executive Summary
(2-3 paragraphs summarizing key findings)

## Top Papers
(List top 5-10 most impactful papers with brief descriptions)

## Key Trends
(What themes are dominant this period?)

## Important Methods
(What techniques are appearing frequently?)

## Datasets and Benchmarks
(What datasets and benchmarks are being used?)

## Research Gaps
(What problems remain unsolved? What's underexplored?)

## Research Opportunities
(Specific ideas for new research projects)

## Recommended Project Ideas
(3-5 concrete project suggestions with brief implementation notes)

## Paper Citations
(List all referenced papers with arXiv links)

Make the report insightful and actionable for an ML researcher."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_whats_next_prompt(papers_text: str, user_background: str = "") -> list:
    bg = f"\nMy research background: {user_background}" if user_background else ""
    user_content = f"""Based on the current research papers below, suggest what I should work on next.{bg}

Papers:
{papers_text[:5000]}

Write a Markdown report with:
## What Should You Work On Next?

### Your Best Opportunities
(3-5 specific research directions with high novelty + low competition)

### Quick Win Projects
(Projects you could start today and complete in 1-3 months)

### Medium-Term Research Directions
(6-12 month research directions)

### Long-Term Bets
(High-risk, high-reward research bets)

### Resources to Study
(Papers, codebases, datasets to review)

Be specific and actionable."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
