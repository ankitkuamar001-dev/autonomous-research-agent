"""Citation and reference data models."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CitationStyle(str, Enum):
    IEEE = "ieee"
    APA = "apa"
    MLA = "mla"
    CHICAGO = "chicago"


class Citation(BaseModel):
    """A formatted citation for inline use in the report."""

    index: int = Field(..., ge=1, description="Citation number [1], [2], etc.")
    url: str = Field(..., description="Source URL.")
    title: str = Field(default="", description="Source title.")
    author: str = Field(default="", description="Author name(s).")
    published_date: Optional[str] = Field(default=None, description="Publication date.")
    domain: str = Field(default="", description="Source domain.")
    accessed_date: str = Field(default="", description="Date accessed by the agent.")
    style: CitationStyle = Field(default=CitationStyle.IEEE)

    def format(self) -> str:
        """Format citation according to the selected style."""
        formatters = {
            CitationStyle.IEEE: self._format_ieee,
            CitationStyle.APA: self._format_apa,
            CitationStyle.MLA: self._format_mla,
            CitationStyle.CHICAGO: self._format_chicago,
        }
        return formatters[self.style]()

    def _format_ieee(self) -> str:
        author = self.author or "Unknown Author"
        title = f'"{self.title}"' if self.title else '"Untitled"'
        date = self.published_date or "n.d."
        return f"[{self.index}] {author}, {title}, {date}. [Online]. Available: {self.url}"

    def _format_apa(self) -> str:
        author = self.author or "Unknown Author"
        date = f"({self.published_date})" if self.published_date else "(n.d.)"
        title = f"*{self.title}*" if self.title else "*Untitled*"
        return f"{author} {date}. {title}. Retrieved from {self.url}"

    def _format_mla(self) -> str:
        author = self.author or "Unknown Author"
        title = f'"{self.title}"' if self.title else '"Untitled"'
        domain = self.domain or "Web"
        accessed = self.accessed_date or "n.d."
        return f'{author}. {title}. *{domain}*, {self.published_date or "n.d."}. Web. {accessed}.'

    def _format_chicago(self) -> str:
        author = self.author or "Unknown Author"
        title = f'"{self.title}"' if self.title else '"Untitled"'
        accessed = self.accessed_date or "n.d."
        return f"{author}. {title}. Accessed {accessed}. {self.url}."


class Reference(BaseModel):
    """A numbered reference entry for the report's reference section."""

    index: int = Field(..., ge=1, description="Reference number.")
    citation: Citation
    formatted: str = Field(default="", description="Pre-formatted citation string.")

    def model_post_init(self, __context: object) -> None:
        if not self.formatted:
            self.formatted = self.citation.format()
