"""Pydantic models for structured data validation."""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class PaperSummary(BaseModel):
    one_line_summary: str = ""
    problem: str = ""
    method: str = ""
    main_contribution: str = ""
    datasets_or_benchmarks: List[str] = Field(default_factory=list)
    results_or_claims: str = ""
    limitations: str = ""
    future_work: str = ""
    research_area: str = ""
    keywords: List[str] = Field(default_factory=list)
    trend_tags: List[str] = Field(default_factory=list)
    model_architectures: List[str] = Field(default_factory=list)
    methods: List[str] = Field(default_factory=list)
    metrics: List[str] = Field(default_factory=list)
    baselines: List[str] = Field(default_factory=list)
    novelty_score: int = Field(default=5, ge=1, le=10)
    impact_score: int = Field(default=5, ge=1, le=10)
    technical_depth_score: int = Field(default=5, ge=1, le=10)
    implementation_difficulty_score: int = Field(default=5, ge=1, le=10)
    reproducibility_score: int = Field(default=5, ge=1, le=10)
    code_generation_potential: int = Field(default=5, ge=1, le=10)


class PaperMeta(BaseModel):
    arxiv_id: str
    title: str
    authors: List[str] = Field(default_factory=list)
    abstract: str = ""
    categories: List[str] = Field(default_factory=list)
    primary_category: str = ""
    published_date: Optional[str] = None
    updated_date: Optional[str] = None
    pdf_url: str = ""
    arxiv_url: str = ""


class ReportContent(BaseModel):
    title: str
    executive_summary: str = ""
    top_papers: List[str] = Field(default_factory=list)
    key_trends: List[str] = Field(default_factory=list)
    important_methods: List[str] = Field(default_factory=list)
    datasets_and_benchmarks: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    research_opportunities: List[str] = Field(default_factory=list)
    recommended_projects: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)


class TrendAnalysis(BaseModel):
    dominant_themes: List[str] = Field(default_factory=list)
    emerging_topics: List[str] = Field(default_factory=list)
    saturated_areas: List[str] = Field(default_factory=list)
    underexplored_gaps: List[str] = Field(default_factory=list)
    fastest_growing: List[str] = Field(default_factory=list)
    method_trends: List[str] = Field(default_factory=list)
    benchmark_trends: List[str] = Field(default_factory=list)
    architecture_trends: List[str] = Field(default_factory=list)
    summary: str = ""
