"""Composable graphs for different use cases"""

from .dynamic_scrape import scrape_with_ai
from .science import science_graph, scrape_science_paper

__all__ = [
    "science_graph",
    "scrape_science_paper",
    "scrape_with_ai",
]
