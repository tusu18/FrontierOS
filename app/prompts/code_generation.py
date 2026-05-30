"""Prompt templates for code generation from papers."""

SYSTEM_PROMPT = """You are an expert ML research engineer who implements research papers.
Generate practical, runnable Python/PyTorch code based on paper descriptions.
If implementation details are missing from the paper, clearly state what is unknown.
Return clean Markdown with proper code blocks."""

def build_code_prompt(
    title: str,
    abstract: str,
    method: str,
    main_contribution: str,
    datasets_or_benchmarks: str,
    full_text_excerpt: str,
    code_mode: str,
) -> list:
    user_content = f"""You are an expert ML research engineer.
Given the following research paper information, generate a practical implementation.

Paper title: {title}

Abstract: {abstract}

Method summary: {method}

Main contribution: {main_contribution}

Datasets or benchmarks: {datasets_or_benchmarks}

Full text excerpt (if available): {full_text_excerpt[:2000] if full_text_excerpt else 'Not available'}

User requested code mode: {code_mode}

Generate the following in clean Markdown:
1. Short explanation of what can realistically be implemented
2. Assumptions made (since papers often omit details)
3. Architecture diagram in ASCII/text form
4. Step-by-step implementation plan
5. Python/PyTorch code skeleton (with comments)
6. Dataset preparation notes
7. Training loop if applicable
8. Evaluation metrics and how to compute them
9. Limitations of this generated code
10. Next steps to fully reproduce the paper

Important: Do not hallucinate unavailable details. If the paper does not provide
enough implementation detail, clearly state what is missing.
Return clean Markdown with code blocks."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
