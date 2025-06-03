# Pydantic Scrape

A modular AI-powered web scraping framework built on [pydantic-ai](https://github.com/pydantic/pydantic-ai) and [pydantic-graph](https://github.com/pydantic/pydantic-graph) for intelligent content extraction and research workflows.

## What is Pydantic Scrape?

Pydantic Scrape is a framework for building intelligent web scraping workflows that combine:

- **AI-powered content extraction** using pydantic-ai agents
- **Graph-based workflow orchestration** with pydantic-graph  
- **Type-safe dependency injection** for modular, reusable components
- **Specialized content handlers** for academic papers, articles, videos, and more

## ⚡ Quick Start: Search → Answer Workflow

Get comprehensive research answers in seconds with our streamlined search-to-answer pipeline:

```python
from pydantic_scrape.graphs.search_answer import search_answer

# One line to research any topic
result = await search_answer(
    query="Ivermectin working as a treatment for Cancer",
    max_search_results=5
)

# Rich structured output with sources
print(f"✅ Found {result['processing_stats']['search_results']} sources")
print(f"📝 Answer: {result['answer']['answer']}")
print(f"💡 Key insights: {len(result['answer']['key_insights'])}")
print(f"📚 Sources: {len(result['answer']['sources'])}")
```

**What it does:**
1. 🔍 **Intelligent search** - Finds relevant academic papers and articles
2. 📄 **Content synthesis** - Combines multiple sources into comprehensive summaries  
3. 🎯 **Answer generation** - Creates structured answers with key insights and sources
4. ⚡ **Fast execution** - Complete research workflow in ~10 seconds

## Core Architecture: Agents + Dependencies + Graphs

Pydantic Scrape follows a clean three-layer architecture:

### 🤖 **Agents** - AI-powered workers
```python
# Intelligent search agent
from pydantic_scrape.agents.search import search_agent

# AI summarization agent  
from pydantic_scrape.agents.summarization import summarize_content

# Dynamic scraping agent
from pydantic_scrape.agents.bs4_scrape_script_agent import get_bs4_scrape_script_agent
```

### 🔧 **Dependencies** - Reusable components
```python
# Content fetching with browser automation
from pydantic_scrape.dependencies.fetch import FetchDependency

# Academic API integrations
from pydantic_scrape.dependencies.openalex import OpenAlexDependency
from pydantic_scrape.dependencies.crossref import CrossrefDependency

# Content analysis and extraction
from pydantic_scrape.dependencies.content_analysis import ContentAnalysisDependency
```

### 📊 **Graphs** - Workflow orchestration
```python
# Fast search → answer workflow
from pydantic_scrape.graphs.search_answer import search_answer_graph

# Complete science paper extraction
from pydantic_scrape.graphs.science import science_graph

# Dynamic scraping workflows
from pydantic_scrape.graphs.dynamic_scrape import dynamic_scrape_graph
```

## 🔬 Example: AI Content Summarization

Create structured summaries from any content:

```python
from pydantic_scrape.agents.summarization import summarize_content

# Single document
summary = await summarize_content(
    "Machine learning advances in 2024 have focused on efficiency and safety...",
    max_length=1000
)

print(f"Title: {summary.title}")
print(f"Summary: {summary.summary}")
print(f"Key findings: {summary.key_findings}")
print(f"Confidence: {summary.confidence_score}")

# Multiple documents (returns comprehensive summary)
combined_summary = await summarize_content([
    doc1, doc2, doc3  # List of content objects
])
```

## 🧩 Example: Custom Dependency

Build reusable components for specific content types:

```python
from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel

class TwitterContent(BaseModel):
    tweet_text: str
    author: str
    likes: int
    retweets: int

@dataclass  
class TwitterDependency:
    """Extract structured data from Twitter/X"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    async def extract_tweet_data(self, url: str) -> TwitterContent:
        # Custom extraction logic here
        pass
```

## 📈 Example: Custom Graph Workflow

Compose agents and dependencies into intelligent workflows:

```python
from dataclasses import dataclass
from typing import Union
from pydantic_graph import BaseNode, Graph, GraphRunContext, End

@dataclass
class ResearchState:
    query: str
    sources_found: list = None
    summaries: list = None
    final_report: str = None

@dataclass
class ResearchDeps:
    search: SearchDependency
    summarizer: SummarizationDependency
    
@dataclass
class SearchNode(BaseNode[ResearchState, ResearchDeps, Union["SummarizeNode", End]]):
    async def run(self, ctx: GraphRunContext[ResearchState, ResearchDeps]):
        sources = await ctx.deps.search.find_sources(ctx.state.query)
        if not sources:
            return End({"error": "No sources found"})
        
        ctx.state.sources_found = sources
        return SummarizeNode()

# Assemble the graph
research_graph = Graph(nodes=[SearchNode, SummarizeNode, ReportNode])
```

## 🛠️ Installation

### Development Installation
```bash
# Clone the repository
git clone https://github.com/yourusername/pydantic-scrape.git
cd pydantic-scrape

# Install with development dependencies (using uv for speed)
uv pip install -e ".[dev]"
# or with pip
pip install -e ".[dev]"

# Set up environment variables
cp .env.example .env
# Add your API keys (OPENAI_API_KEY, etc.)
```

## 🧪 Comprehensive Testing & Validation

**✅ ALL 4 CORE GRAPHS TESTED AND OPERATIONAL!**

Run the complete test suite:

```bash
# Test all 4 graphs with real examples
python test_all_graphs.py

# Results: 4/4 graphs passing in ~90 seconds
# ✅ Search → Answer: Research workflow (32.9s)
# ✅ Dynamic AI Scraping: Extract from any site (12.4s)  
# ✅ Complete Science Scraping: Full academic processing (20.0s)
# ✅ Search → Scrape → Answer: Advanced research pipeline (29.0s)
```

**🎯 Framework Capabilities Demonstrated:**
- 🔍 **Fast Research** - Search academic sources and generate comprehensive answers
- 🤖 **AI Extraction** - Dynamically extract structured data from any website using AI agents
- 📄 **Science Processing** - Complete academic paper processing with metadata enrichment
- 🔬 **Deep Research** - Advanced pipeline that searches, scrapes full content, and synthesizes answers

### Quick Individual Tests

```bash
# Test search-answer workflow
python -c "
import asyncio
from pydantic_scrape.graphs.search_answer import search_answer

async def test():
    result = await search_answer('latest advances in quantum computing')
    print(f'Found {len(result[\"answer\"][\"sources\"])} sources')
    print(result['answer']['answer'][:200] + '...')

asyncio.run(test())
"

# Test summarization agent
python -c "
import asyncio
from pydantic_scrape.agents.summarization import summarize_content

async def test():
    summary = await summarize_content(
        'Artificial intelligence is transforming scientific research...'
    )
    print(f'Summary: {summary.summary}')

asyncio.run(test())
"
```

## 🤝 Contributing - We Need Your Help!

We're building the future of intelligent web scraping and **we want you to be part of it!** 

### 🎯 What We're Looking For

#### 🤖 **Agent Builders**
Create specialized AI agents for:
- **Domain-specific extraction** (legal docs, medical papers, financial reports)
- **Multi-modal content** (image + text analysis, video transcription)
- **Real-time processing** (news monitoring, social media tracking)
- **Quality assurance** (fact-checking, source verification)

#### 🔧 **Dependency Developers**  
Build reusable components for:
- **API integrations** (Google Scholar, PubMed, arXiv, GitHub, social platforms)
- **Content processors** (PDF extraction, video analysis, image recognition)
- **Data enrichment** (NLP analysis, metadata extraction, classification)
- **Storage & caching** (vector databases, knowledge graphs, search indices)

#### 📊 **Graph Architects**
Design intelligent workflows for:
- **Research pipelines** (literature review, systematic analysis, meta-analysis)
- **Content monitoring** (news tracking, social listening, trend analysis)
- **Knowledge extraction** (entity recognition, relationship mapping, fact extraction)
- **Quality control** (validation, verification, bias detection)

### 🚀 Getting Started as a Contributor

```bash
# 1. Fork and clone
git clone https://github.com/yourusername/pydantic-scrape.git
cd pydantic-scrape

# 2. Install development dependencies  
uv pip install -e ".[dev]"

# 3. Test current functionality
python test_search_answer.py  # Should work out of the box

# 4. Check the current structure
ls pydantic_scrape/agents/      # See existing agents
ls pydantic_scrape/dependencies/ # See existing dependencies  
ls pydantic_scrape/graphs/       # See existing graphs

# 5. Start building!
```

### 💡 Contribution Ideas

**Easy wins for new contributors:**
- Add a new academic API (NASA ADS, bioRxiv, SSRN)
- Create a social media dependency (Reddit, LinkedIn, Mastodon)
- Build a specialized graph for a domain (legal research, patent analysis)
- Add content format support (EPUB, Markdown, slides)

**Advanced challenges:**
- Multi-agent coordination for complex research tasks
- Real-time streaming workflows with live updates
- Advanced caching and optimization strategies  
- Cross-language content extraction and translation

### 🌟 Community & Support

- 🐛 **Found a bug?** [Open an issue](https://github.com/yourusername/pydantic-scrape/issues) with reproduction steps
- 💡 **Have an idea?** [Start a discussion](https://github.com/yourusername/pydantic-scrape/discussions) about new features
- 🔧 **Ready to contribute?** Check out our [contribution guidelines](CONTRIBUTING.md)
- 📧 **Questions?** Reach out to the maintainers

## 📋 Core Dependencies

- **AI Framework**: [pydantic-ai](https://github.com/pydantic/pydantic-ai) - Type-safe AI agents with structured outputs
- **Workflow Engine**: [pydantic-graph](https://github.com/pydantic/pydantic-graph) - Graph-based workflow orchestration  
- **Browser Automation**: [Camoufox](https://github.com/daijro/camoufox) - Undetectable browser automation
- **Content Processing**: BeautifulSoup4, newspaper3k, pypdf
- **Academic APIs**: Integration with OpenAlex, Crossref, arXiv

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🎉 Join Us!

Pydantic Scrape is more than a framework - it's a community building the next generation of intelligent web scraping tools. Whether you're a researcher, developer, data scientist, or domain expert, there's a place for you here.

**Let's build something amazing together!** 🚀

[![Stars](https://img.shields.io/github/stars/philmade/pydantic_scrape?style=social)](https://github.com/philmade/pydantic_scrape)
[![Forks](https://img.shields.io/github/forks/philmade/pydantic_scrape?style=social)](https://github.com/philmade/pydantic_scrape)
[![Issues](https://img.shields.io/github/issues/philmade/pydantic_scrape)](https://github.com/philmade/pydantic_scrape/issues)
[![Contributors](https://img.shields.io/github/contributors/philmade/pydantic_scrape)](https://github.com/philmade/pydantic_scrape/graphs/contributors)