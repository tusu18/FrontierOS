"""Prompt templates for paper summarization."""

SYSTEM_PROMPT = """You are an expert AI research scientist and paper analyst.
Your task is to read the given arXiv paper information and produce a structured JSON analysis.
Always return ONLY valid JSON. Do not include any text before or after the JSON object."""

def build_summarize_prompt(title: str, abstract: str, full_text: str = "") -> list:
    text_section = ""
    if full_text:
        text_section = f"\n\nFull text excerpt:\n{full_text[:3000]}"

    user_content = f"""Analyze the following research paper and return a JSON object with EXACTLY these fields:

Paper Title: {title}
Abstract: {abstract}{text_section}

Return JSON with these exact keys:
{{
  "one_line_summary": "One sentence describing the paper",
  "problem": "What problem does this paper solve?",
  "method": "What method or approach do they use?",
  "main_contribution": "What is the main contribution?",
  "datasets_or_benchmarks": ["list", "of", "datasets"],
  "results_or_claims": "What are the key results or claims?",
  "limitations": "What are the limitations?",
  "future_work": "What future work do they suggest?",
  "research_area": "Primary research area (e.g. NLP, CV, Agents, RAG, Robotics)",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "trend_tags": ["tag1", "tag2", "tag3"],
  "model_architectures": ["transformer", "etc"],
  "methods": ["method1", "method2"],
  "metrics": ["accuracy", "F1", "etc"],
  "baselines": ["GPT-4", "etc"],
  "novelty_score": 7,
  "impact_score": 6,
  "technical_depth_score": 7,
  "implementation_difficulty_score": 6,
  "reproducibility_score": 5,
  "code_generation_potential": 7
}}

All score fields must be integers 1-10. Return ONLY the JSON, nothing else."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
