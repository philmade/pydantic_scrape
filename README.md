# Pydantic Scrape

A modern web scraping framework that combines AI-powered content extraction with intelligent workflow orchestration. Built on pydantic-ai for reliable, type-safe scraping operations.

## Why Pydantic Scrape?

Web scraping is complex. You need to handle dynamic content, extract meaningful information, and orchestrate multi-step workflows. Most tools force you to choose between simple scrapers or complex frameworks with steep learning curves.

Pydantic Scrape bridges this gap by providing:

- **AI-powered extraction** - Let AI understand and extract what you need instead of writing brittle selectors
- **Type-safe workflows** - Structured data with validation built-in  
- **Academic research focus** - First-class support for papers, citations, and research workflows
- **Browser automation** - Handle JavaScript, authentication, and complex interactions seamlessly

## Installation

```bash
# Standard installation
pip install pydantic-scrape

# With development tools (if contributing)
pip install pydantic-scrape[dev]
```

## Quick Start

Get a comprehensive research answer in under 10 lines:

```python
import asyncio
from pydantic_scrape.graphs.search_answer import search_answer

async def research():
    result = await search_answer(
        query="latest advances in quantum computing",
        max_search_results=5
    )
    
    print(f"Found {len(result['answer']['sources'])} sources")
    print(result['answer']['answer'])

asyncio.run(research())
```

This searches academic sources, extracts content, and generates a structured answer with citations - all automatically.

## Core Features

### 🔍 Smart Content Extraction
```python
from pydantic_scrape.dependencies.fetch import fetch_url

# Automatically handles JavaScript, selects best extraction method
content = await fetch_url("https://example.com/article")
print(content.title, content.text, content.metadata)
```

### 🤖 AI-Powered Scraping
```python
from pydantic_scrape.agents.bs4_scrape_script_agent import get_bs4_scrape_script_agent

# AI writes the scraping code for you
agent = get_bs4_scrape_script_agent()
result = await agent.run_sync("Extract product prices from this e-commerce page", 
                              html_content=page_html)
```

### 📚 Academic Research
```python
from pydantic_scrape.dependencies.openalex import OpenAlexDependency

# Search papers by topic, author, or DOI
openalex = OpenAlexDependency()
papers = await openalex.search_papers("machine learning healthcare")
```

### 📄 Document Processing
```python
from pydantic_scrape.dependencies.document import DocumentDependency

# Extract text from PDFs, Word docs, EPUBs
doc = DocumentDependency()
content = await doc.extract_text("research_paper.pdf")
```

## Common Use Cases

- **Literature Reviews** - Automatically search, extract, and summarize academic papers
- **Market Research** - Monitor competitor content, pricing, and product updates  
- **News Monitoring** - Track mentions, trends, and breaking news across sources
- **Content Migration** - Extract structured data from legacy systems or websites
- **Research Workflows** - Build custom pipelines for domain-specific content extraction

## Architecture

Pydantic Scrape organizes code into three layers:

- **Dependencies** (`pydantic_scrape.dependencies.*`) - Reusable components for specific tasks
- **Agents** (`pydantic_scrape.agents.*`) - AI-powered workers that make decisions  
- **Graphs** (`pydantic_scrape.graphs.*`) - Orchestrate multi-step workflows

This makes it easy to compose complex workflows from simple, tested components.

## Configuration

Set your API keys in a `.env` file:

```bash
OPENAI_API_KEY=your_openai_key
GOOGLE_GENAI_API_KEY=your_google_key  
ANTHROPIC_API_KEY=your_anthropic_key
```

Most features work with any of these providers. The framework automatically selects the best model for each task.

## Documentation

- [Installation Guide](INSTALLATION.md) - Detailed setup instructions
- [Examples](examples/) - Working code samples for common tasks
- [API Reference](https://github.com/philmade/pydantic_scrape) - Full documentation

## Contributing

We welcome contributions! The framework is designed to be extensible - add new content sources, AI agents, or workflow patterns.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Ready to build intelligent scraping workflows?** Start with `pip install pydantic-scrape` and try the examples above.