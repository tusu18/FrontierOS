# ◎ FrontierOS
### Research Terminal

> Know when the frontier moves near your work.

FrontierOS is an agentic research intelligence terminal that learns your research context, monitors new research, builds a research-memory graph, and surfaces papers, citations, trends, gaps, risks, and project ideas that are close to your work.

Most research tools help you search or summarize papers. FrontierOS starts from your work. It compares your research context against the global research frontier and tells you what changed, what matters, what to cite, what may compete with you, and what to build next.

---

## What FrontierOS Does

FrontierOS helps researchers, labs, and technical teams answer:

- What new papers are close to my work?
- What should I cite?
- What methods or datasets should I try?
- What topics are emerging near my research direction?
- What gaps are becoming important?
- What papers may compete with or strengthen my idea?
- What can I reproduce, implement, or turn into a project?

The system combines public research ingestion, LLM-based analysis, evidence extraction, a knowledge graph, personal research directives, and agentic workflows to produce actionable research intelligence.

---

## Core Product Loop

```text
Research context
      ↓
New paper ingestion
      ↓
Evidence-backed analysis
      ↓
Knowledge graph update
      ↓
Near My Work matching
      ↓
Citation, alert, gap, and project recommendations
```

The user defines what they are working on. FrontierOS continuously monitors new research, compares it against that context, and surfaces the most relevant papers and next actions.

---

## Key Features

### Research Paper Ingestion

FrontierOS fetches new research papers from public sources such as arXiv and processes them into structured records. It supports deduplication, queue-based processing, and scalable ingestion for growing paper collections.

### Evidence-Backed Summaries

Each paper is analyzed with LLM agents to extract:

- problem statement
- method
- main contribution
- datasets and benchmarks
- claims
- limitations
- future work
- reproducibility signals
- code/project potential

Important claims are linked to evidence spans, source quotes, confidence scores, and uncertainty labels.

### Research-Memory Knowledge Graph

FrontierOS builds a graph of research entities and relationships, including:

- papers
- authors
- topics
- methods
- datasets
- benchmarks
- metrics
- claims
- limitations
- future work
- research gaps
- code repositories

This allows the system to reason over research as a connected memory instead of isolated papers.

### Near My Work Engine

The Near My Work engine compares new papers against the user's research context, directives, saved topics, and private memory.

It identifies whether a paper is:

- directly relevant
- a citation candidate
- a useful baseline
- a useful dataset
- a useful method
- a competitor
- related but low priority
- irrelevant

Each match includes a score, explanation, evidence, and suggested action.

### Citation Advisor

The Citation Advisor helps users decide whether a paper should be cited.

It can suggest:

- whether to cite the paper
- where to cite it
- citation role
- related work sentence
- difference from the user's work
- evidence supporting the recommendation

Citation roles include related work, baseline, method comparison, dataset reference, limitation support, future work, and competing work.

### Research Directives

Users can create persistent research directives such as:

- track papers near my thesis
- alert me when a new benchmark appears
- find reproducible papers I can build from
- monitor work similar to my lab's project
- detect new methods relevant to my dataset

Directives guide recommendations, alerts, reports, and agent behavior.

### Private Research Context

Users can add their own research context, including:

- papers
- drafts
- notes
- proposals
- project ideas
- dataset descriptions
- experiment logs
- README files

FrontierOS extracts private memory entities such as topics, methods, datasets, claims, open questions, goals, and target venues.

### Alerts and Trend Tracking

FrontierOS detects important changes near the user's research direction.

Alert types include:

- new paper near my work
- citation candidate
- topic spike
- new research gap
- possible competitor paper
- new dataset or benchmark
- method worth trying

The system can also track topic velocity, saturation, and emerging gaps over time.

### Paper-to-Project Intelligence

FrontierOS can turn relevant papers into buildable next steps, including:

- reproduction plans
- code skeletons
- dataset plans
- baseline checklists
- experiment ideas
- project roadmaps
- GitHub-ready README outlines

### Research Reports and Digests

The system can generate daily or weekly research digests showing:

- what changed near your work
- top papers to read
- citation candidates
- trend changes
- emerging research gaps
- papers to reproduce
- suggested next actions

---

## Agentic Workflow

FrontierOS uses multiple specialized agents:

| Agent | Function |
|-------|----------|
| PaperCollectorAgent | Fetches new papers from public research sources. |
| FetchQueueAgent | Tracks queued, processed, failed, and duplicate papers. |
| PaperSummarizerAgent | Generates structured summaries using OpenRouter GPT-4o-mini. |
| EvidenceExtractorAgent | Extracts source quotes, confidence, and uncertainty labels. |
| KnowledgeGraphBuilderAgent | Builds graph entities and relationships from papers. |
| ResearchMemoryEngine | Maintains the global research-memory graph. |
| TrendAnalystAgent | Tracks topic velocity, saturation, and research direction shifts. |
| ResearchGapAgent | Detects repeated limitations and open research gaps. |
| NearMyWorkAgent | Compares new papers against the user's research context. |
| CitationAdvisorAgent | Suggests whether and where a paper should be cited. |
| RecommendationAgent | Ranks papers based on global signals and user context. |
| AlertAgent | Generates alerts for relevant papers, trends, and gaps. |
| DigestAgent | Produces research updates and briefs. |
| CodeGeneratorAgent | Converts papers into project/code scaffolds. |
| ReportWriterAgent | Generates research reports and summaries. |

---

## Memory Architecture

FrontierOS uses three memory layers.

### Global Research Memory

Stores public research knowledge, including papers, summaries, entities, relationships, trends, gaps, and evidence.

### Private Research Memory

Stores the user's own research context, such as drafts, notes, datasets, and project ideas. This allows FrontierOS to understand what the user is working on.

### Personal Interaction Memory

Tracks user behavior such as saved papers, ignored papers, reading history, liked topics, directives, notes, and collections. This improves recommendations over time.

---

## What Makes FrontierOS Different

FrontierOS is not just a paper search tool or paper summarizer.

**Traditional workflow:** Search query → papers → summaries

**FrontierOS workflow:** Your work → global research frontier → nearby changes → next actions

Elicit-style tools help users search and review literature. FrontierOS watches the literature for the user's work.

It focuses on:

- continuous research monitoring
- private research context
- knowledge graph memory
- evidence-backed recommendations
- citation advice
- novelty and competitor awareness
- project/code generation
- personalized research directives

---

## Product Direction

FrontierOS is designed to expand into a research operating system for individuals, labs, and technical teams.

Planned and evolving extensions include:

### Private Lab Knowledge Base

Labs can connect private papers, unpublished drafts, datasets, experiment logs, model cards, benchmark results, and internal notes.

FrontierOS will build a private lab graph and compare it against the global research graph.

### Private Dataset Linking

Labs can register private datasets and receive recommendations for:

- relevant public methods
- matching benchmarks
- useful metrics
- experiment ideas
- papers that can be tested on the dataset

### Novelty Risk Tracking

FrontierOS can monitor whether new papers overlap with a user's or lab's unpublished work and suggest how to reposition the contribution.

### Living Related Work Agent

The system can continuously update related work sections, citation buckets, comparison tables, and BibTeX suggestions as new papers appear.

### Threat or Opportunity Agent

New papers can be classified as:

- competing work
- complementary work
- useful baseline
- useful dataset
- useful method
- must cite
- potential collaborator

### Lab Intelligence Briefs

Labs can receive weekly briefs summarizing:

- papers near each project
- citation candidates
- competitor papers
- new methods to try
- research gaps
- suggested experiments

### Federated Learning for Private Lab Data

Future lab nodes can train local relevance and recommendation models on private data without sending raw private papers, datasets, notes, or experiment logs to the platform.

The first target is a federated Near My Work ranker that improves recommendations while preserving lab privacy.

### Production Scaling

FrontierOS is designed to scale from a local MVP toward hosted and lab/team deployments with:

- PostgreSQL
- background workers
- vector search
- private file storage
- cloud or local memory sync
- lab workspaces
- role-based permissions
- audit logs
- federated learning nodes

---

## Short Pitch

FrontierOS watches the research frontier for your work.

It learns your context, tracks new papers, builds a memory graph, and tells you what to read, cite, watch, or build next.

---

## Team

**Tushar Singh** — Creator  
[LinkedIn](https://www.linkedin.com/in/tushar-singh-4326b7188) · [GitHub](https://github.com/tusu18/FrontierOS)

**Landing:** [tusu18.github.io/FrontierOS](https://tusu18.github.io/FrontierOS/)  
**Deploy API:** see [DEPLOY.md](DEPLOY.md)
