# Pydantic Scrape

A modular web scraping framework using [pydantic-ai](https://github.com/pydantic/pydantic-ai) and [pydantic-graph](https://github.com/pydantic/pydantic-graph) with intelligent dependency injection.

## What is Pydantic Scrape?

Pydantic Scrape is a framework for scraping data from websites with a focus on modularity, type safety, and dependency injection. It leverages pydantic-ai for AI-driven data extraction and pydantic-graph for workflow orchestration.

## Core Architecture: Dependencies + Nodes

The framework follows a **dependency-heavy, graph-heavy architecture** where:

- **Dependencies do the heavy lifting**: All scraping, parsing, and AI logic
- **Nodes are logic gates**: Simple routing and orchestration  
- **Graphs become complex**: Multi-path routing with decision points and caching
- **Strong typing throughout**: Full pydantic-graph type safety
- **Dependency injection**: Clean `deps=` pattern with typed annotations

## The Composability Challenge

### The Problem

Nodes in pydantic-graph are **not composable** across different graphs because:

1. **Return type binding**: Node `run()` functions use return type annotations
2. **Graph-specific types**: Return types tie nodes to specific graph contexts
3. **Static routing**: Next nodes determined by return types at definition time

### Our Solution: Dependency-Heavy Architecture

We solve this by pushing **most logic into dependencies**:

```python
# ✅ Heavy lifting in dependency (reusable)
class FetchDependency:
    async def fetch_content(self, url: str) -> FetchResult:
        # Complex fetching logic with Camoufox
        pass

# ✅ Simple logic gate node (graph-specific but lightweight)  
class FetchNode(BaseNode[State, Deps, Union[ContentNode, End]]):
    async def run(self, ctx: GraphRunContext[State, Deps]) -> Union[ContentNode, End]:
        result = await ctx.deps.fetch.fetch_content(self.url)
        return ContentNode() if not result.error else End(error=result.error)
```

## Complete Science Graph Architecture

The framework includes a complete, production-ready science paper scraping graph that demonstrates the full power of the dependency-heavy, graph-heavy architecture:

![Complete Science Graph](scrape-complete.jpg)

This graph handles:
- **Multi-format content**: Science papers, YouTube videos, articles, documents
- **Intelligent routing**: Content type detection with confidence scoring
- **Rich metadata extraction**: OpenAlex, Crossref, YouTube, article analysis
- **PDF processing**: Download and full-text extraction
- **AI-powered fallback**: When standard APIs fail, AI scraping finds PDFs
- **Optimized flow**: Smart routing back to ScienceNode when AI finds PDFs

### Quick Start with Complete Graph

```python
from pydantic_scrape.graphs.complete_science_graph import scrape_science_complete

# One line to scrape any scientific content
result = await scrape_science_complete("https://arxiv.org/abs/2301.00001")

print(f"Title: {result['metadata']['title']}")
print(f"Authors: {result['openalex_data']['authors']}")
print(f"Full text extracted: {result['full_text_extracted']}")
print(f"PDF links: {result['pdf_links']}")
```

## Core Framework Patterns

### 1. Define State and Dependencies

```python
from dataclasses import dataclass
from typing import Optional, List
from pydantic_scrape.dependencies import FetchDependency, AiScraperDependency, FetchResult

@dataclass
class YourState:
    """State tracks progress and accumulates data across nodes"""
    url: str
    iterations: int = 0
    errors: List[str] = None
    retry_count: int = 0
    extracted_data: Optional[dict] = None
    fetch_result: Optional[FetchResult] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []

@dataclass  
class ScrapeDeps:
    """Dependencies do the heavy lifting"""
    fetch: FetchDependency
    ai_scraper: AiScraperDependency
```

### 2. Create Lightweight Nodes (Logic Gates)

```python
from pydantic_graph import BaseNode, GraphRunContext, End
from typing import Union

@dataclass
class FetchNode(BaseNode[YourState, ScrapeDeps, Union["ProcessNode", End[dict]]]):
    
    async def run(self, ctx: GraphRunContext[YourState, ScrapeDeps]) -> Union["ProcessNode", End[dict]]:
        # Update state
        ctx.state.iterations += 1
        
        # Dependency does the work
        result = await ctx.deps.fetch.fetch_content(
            ctx.state.url, 
            browser_config={"headless": True, "humanize": True}
        )
        
        # Node is just a logic gate
        if result.error:
            ctx.state.errors.append(f"Fetch failed: {result.error}")
            return End({"error": result.error, "state": ctx.state})
        
        # Store result for next node
        ctx.state.fetch_result = result
        return ProcessNode()

@dataclass  
class ProcessNode(BaseNode[YourState, ScrapeDeps, End[dict]]):
    
    async def run(self, ctx: GraphRunContext[YourState, ScrapeDeps]) -> End[dict]:
        # Dependency does the AI extraction
        try:
            from pydantic import BaseModel, Field
            
            class ExtractedData(BaseModel):
                title: str = Field(description="Page title")
                content: str = Field(description="Main content")
            
            # Use the fetch result from state
            if not ctx.state.fetch_result:
                raise ValueError("No fetch result in state")
                
            data = await ctx.deps.ai_scraper.extract_data(
                fetch_result=ctx.state.fetch_result,
                output_type=ExtractedData, 
                extraction_prompt="Extract title and main content"
            )
            
            ctx.state.extracted_data = data.model_dump()
            return End({"success": True, "data": ctx.state.extracted_data, "state": ctx.state})
            
        except Exception as e:
            ctx.state.errors.append(f"Processing failed: {str(e)}")
            return End({"error": str(e), "state": ctx.state})
```

### 3. Assemble Graph with Dependency Injection

```python
from pydantic_graph import Graph

# Create the graph
scrape_graph = Graph(nodes=[FetchNode, ProcessNode])

# Create dependencies (heavy lifting objects)
deps = ScrapeDeps(
    fetch=FetchDependency(timeout_ms=30000),
    ai_scraper=AiScraperDependency()
)

# Create initial state
initial_state = YourState(url="https://example.com")

# Run with dependency injection
result = await scrape_graph.run(
    FetchNode(),  # Starting node
    state=initial_state,  # State tracks progress across nodes
    deps=deps  # Dependencies injected with strong typing
)

print(f"Iterations: {result.state.iterations}")
print(f"Errors: {result.state.errors}")
print(f"Success: {result.output}")
```

### 4. Real Example: Science Paper Graph

```python
from dataclasses import dataclass
from typing import Optional, List, Union
from pydantic_graph import BaseNode, Graph, GraphRunContext, End
from pydantic_scrape.dependencies import (
    FetchDependency, 
    ContentAnalysisDependency, 
    OpenAlexDependency, 
    CrossrefDependency,
    FetchResult
)

@dataclass
class ScienceState:
    """State tracks science paper extraction progress"""
    url: str
    fetch_attempts: int = 0
    analysis_errors: List[str] = None
    fetch_result: Optional[FetchResult] = None
    final_metadata: Optional[dict] = None
    
    def __post_init__(self):
        if self.analysis_errors is None:
            self.analysis_errors = []

@dataclass
class ScienceDeps:
    """Science scraping dependencies - all the heavy lifting"""
    fetch: FetchDependency
    content_analysis: ContentAnalysisDependency  
    openalex: OpenAlexDependency
    crossref: CrossrefDependency

@dataclass
class ScienceFetchNode(BaseNode[ScienceState, ScienceDeps, Union["ContentAnalysisNode", End]]):
    
    async def run(self, ctx: GraphRunContext[ScienceState, ScienceDeps]):
        ctx.state.fetch_attempts += 1
        
        # Dependency does the fetching
        result = await ctx.deps.fetch.fetch_content(
            ctx.state.url,
            browser_config={"headless": True, "humanize": True}
        )
        
        if result.error:
            ctx.state.analysis_errors.append(f"Fetch failed: {result.error}")
            return End({"error": result.error, "state": ctx.state})
        
        # Store in state for next nodes
        ctx.state.fetch_result = result
        return ContentAnalysisNode()

@dataclass  
class ContentAnalysisNode(BaseNode[ScienceState, ScienceDeps, Union["OpenAlexNode", End]]):
    
    async def run(self, ctx: GraphRunContext[ScienceState, ScienceDeps]):
        # Dependency analyzes content
        try:
            analysis = await ctx.deps.content_analysis.analyze_content(ctx.state.fetch_result)
            
            if analysis.content_type != "science":
                return End({"type": "not_science", "confidence": analysis.confidence})
            
            return OpenAlexNode()
            
        except Exception as e:
            ctx.state.analysis_errors.append(f"Analysis failed: {str(e)}")
            return End({"error": str(e), "state": ctx.state})

@dataclass
class OpenAlexNode(BaseNode[ScienceState, ScienceDeps, End]):
    
    async def run(self, ctx: GraphRunContext[ScienceState, ScienceDeps]) -> End:
        # Dependencies do the API calls
        openalex_result = await ctx.deps.openalex.lookup(
            title=ctx.state.fetch_result.title or ""
        )
        crossref_result = await ctx.deps.crossref.lookup(
            title=ctx.state.fetch_result.title or ""
        )
        
        # Compose final metadata
        ctx.state.final_metadata = {
            "url": ctx.state.url,
            "title": ctx.state.fetch_result.title,
            "openalex_data": openalex_result.model_dump() if openalex_result else None,
            "crossref_data": crossref_result.model_dump() if crossref_result else None,
            "fetch_attempts": ctx.state.fetch_attempts,
            "errors": ctx.state.analysis_errors
        }
        
        return End(ctx.state.final_metadata)

# Create and run the science graph
science_graph = Graph(nodes=[ScienceFetchNode, ContentAnalysisNode, OpenAlexNode])

deps = ScienceDeps(
    fetch=FetchDependency(timeout_ms=30000),
    content_analysis=ContentAnalysisDependency(),
    openalex=OpenAlexDependency(fuzzy_match_threshold=85.0),
    crossref=CrossrefDependency()
)

initial_state = ScienceState(url="https://arxiv.org/abs/2301.00001")

result = await science_graph.run(
    ScienceFetchNode(),
    state=initial_state,
    deps=deps
)

print(f"Paper metadata: {result.output}")
print(f"Fetch attempts: {result.state.fetch_attempts}")
print(f"Errors encountered: {result.state.analysis_errors}")
```

## Simple Direct Usage (No Graph Needed)

For simple cases, use dependencies directly:

```python
from pydantic import BaseModel, Field
from pydantic_scrape.dependencies import FetchDependency, AiScraperDependency

class NewsData(BaseModel):
    headlines: list[str] = Field(description="News headlines")

# Direct dependency usage
fetch_dep = FetchDependency(timeout_ms=30000)
ai_dep = AiScraperDependency()

# Fetch content  
result = await fetch_dep.fetch_content("https://news.ycombinator.com")

# Extract with AI
data = await ai_dep.extract_data(
    fetch_result=result,
    output_type=NewsData, 
    extraction_prompt="Extract the top headlines"
)

print(data.headlines)
```

## Working Examples

Test the complete science graph with real examples:

```bash
# Test the enhanced science workflow (requires OPENAI_API_KEY environment variable)
python test_enhanced_science_final.py

# Try the quick start example
python -c "
import asyncio
from pydantic_scrape.graphs.complete_science_graph import scrape_science_complete

async def test():
    result = await scrape_science_complete('https://arxiv.org/abs/2301.00001')
    print(f'Success: {result[\"success\"]}')
    print(f'Content type: {result[\"content_type\"]}')
    print(f'Full text: {len(result.get(\"full_text_content\", \"\"))} chars')

asyncio.run(test())
"
```

## Installation

### From Git (Recommended for now)

```bash
# Using uv (fastest)
uv pip install git+https://github.com/yourusername/pydantic-scrape.git

# Using pip
pip install git+https://github.com/yourusername/pydantic-scrape.git

# For development (clone and install in editable mode)
git clone https://github.com/yourusername/pydantic-scrape.git
cd pydantic-scrape
uv pip install -e .
```

### From PyPI (Coming Soon!)

```bash
# Will be available when we publish
pip install pydantic-scrape
# or
uv pip install pydantic-scrape
```

### Development Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/pydantic-scrape.git
cd pydantic-scrape

# Install with development dependencies
uv pip install -e ".[dev]"

# Or with pip
pip install -e ".[dev]"
```

## Core Dependencies

- **Browser automation**: [Camoufox](https://github.com/daijro/camoufox) - Undetectable browser automation
- **AI extraction**: [pydantic-ai](https://github.com/pydantic/pydantic-ai) - Type-safe AI framework  
- **Workflow orchestration**: [pydantic-graph](https://github.com/pydantic/pydantic-graph) - Graph-based workflows
- **Content parsing**: BeautifulSoup4, newspaper3k

## License

MIT License - see [LICENSE](LICENSE) file for details.

## 🚀 We're Publishing Soon!

Pydantic Scrape is nearly ready for its first public release! We're putting the finishing touches on the framework and preparing for publication to PyPI.

## 🤝 Contributors Welcome!

We're actively looking for contributors to help us make Pydantic Scrape even better! Whether you're interested in:

- **Core framework development** - Improving the dependency injection patterns and graph orchestration
- **New dependencies** - Adding support for more content types, APIs, or extraction methods
- **Documentation** - Helping with examples, tutorials, and API documentation
- **Testing** - Writing tests for edge cases and real-world scenarios
- **Performance** - Optimizing the scraping pipeline and browser automation

We'd love to have you join us! Here's how to get started:

### Quick Contribution Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/pydantic-scrape.git
cd pydantic-scrape

# Install development dependencies (using uv for speed)
uv pip install -e ".[dev]"
# or with pip
pip install -e ".[dev]"

# Run the test suite
python test_enhanced_science_final.py

# Start building!
```

### What We're Looking For

- **Dependency creators**: Build new `*Dependency` classes for different content types
- **Graph designers**: Create specialized graphs for different use cases
- **API integrators**: Add support for more academic APIs, social media, etc.
- **Performance optimizers**: Help make the framework faster and more efficient
- **Documentation writers**: Improve examples and tutorials

### Join the Community

- 🐛 **Found a bug?** Open an issue with reproduction steps
- 💡 **Have an idea?** Start a discussion about new features
- 🔧 **Want to contribute?** Check out our contributor guidelines
- 📧 **Questions?** Reach out to the maintainers

Let's build the future of intelligent web scraping together! 🌟