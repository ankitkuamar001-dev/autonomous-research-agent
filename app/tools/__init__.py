"""Tools package for the Autonomous Research Agent.

Re-exports all tool classes for convenient import::

    from app.tools import TavilySearchTool, WebScraperTool, PDFReaderTool
    from app.tools import CitationGeneratorTool, ReportWriterTool
"""

from app.tools.search import TavilySearchTool, SearchError, SearchRateLimitError
from app.tools.scraper import WebScraperTool, ScraperError
from app.tools.pdf_reader import PDFReaderTool, PDFReadError, PDFContent
from app.tools.citation_generator import CitationGeneratorTool
from app.tools.report_writer import ReportWriterTool

__all__ = [
    # Search
    "TavilySearchTool",
    "SearchError",
    "SearchRateLimitError",
    # Scraper
    "WebScraperTool",
    "ScraperError",
    # PDF Reader
    "PDFReaderTool",
    "PDFReadError",
    "PDFContent",
    # Citation Generator
    "CitationGeneratorTool",
    # Report Writer
    "ReportWriterTool",
]
