"""Prompt templates for trend analysis."""

SYSTEM_PROMPT = """You are a senior AI research analyst specializing in identifying trends
and research directions across large collections of academic papers.
Return ONLY valid JSON. No text before or after."""

def build_trend_prompt(summaries_text: str) -> list:
    user_content = f"""Analyze the following collection of research paper summaries and identify research trends.

Paper summaries:
{summaries_text[:6000]}

Return a JSON object with these exact keys:
{{
  "dominant_themes": ["theme1", "theme2", "theme3"],
  "emerging_topics": ["topic1", "topic2"],
  "saturated_areas": ["area1", "area2"],
  "underexplored_gaps": ["gap1", "gap2"],
  "fastest_growing": ["topic1", "topic2"],
  "method_trends": ["trend1", "trend2"],
  "benchmark_trends": ["benchmark1", "benchmark2"],
  "architecture_trends": ["arch1", "arch2"],
  "summary": "2-3 paragraph prose summary of where CS/AI research is heading",
  "where_research_is_going": "Concise forward-looking statement about research directions"
}}

Return ONLY the JSON."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
