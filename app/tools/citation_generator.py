"""Multi-format citation generator supporting IEEE, APA, MLA, and Chicago styles.

Generates properly formatted citations from Source or SourceMetadata models,
assigns sequential indices, and produces Reference lists for reports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import structlog

from app.models.citation import Citation, CitationStyle, Reference
from app.models.source import Source, SourceMetadata

logger = structlog.get_logger(__name__)


class CitationGeneratorTool:
    """Generate formatted citations and reference lists from research sources.

    Features
    --------
    - Supports IEEE, APA, MLA, and Chicago citation styles.
    - Auto-increments citation indices across calls.
    - Deduplicates references by URL.
    - Provides both inline citation markers and full reference entries.
    - Generates complete reference sections in Markdown.

    Usage
    -----
    >>> gen = CitationGeneratorTool(style=CitationStyle.APA)
    >>> citation = gen.cite_source(source)
    >>> ref_section = gen.generate_reference_section()
    """

    def __init__(self, style: CitationStyle = CitationStyle.IEEE) -> None:
        self._style = style
        self._references: list[Reference] = []
        self._url_to_index: dict[str, int] = {}
        self._next_index: int = 1
        self._log = logger.bind(tool="CitationGeneratorTool")

    # ── Properties ──────────────────────────────────────────────

    @property
    def style(self) -> CitationStyle:
        """Current citation style."""
        return self._style

    @style.setter
    def style(self, value: CitationStyle) -> None:
        """Change the citation style.

        .. warning::
            Changing the style after citations have been generated will NOT
            retroactively reformat existing references.  Call ``reset()`` first
            if a full style change is needed.
        """
        self._style = value
        self._log.info("citation_style_changed", style=value.value)

    @property
    def references(self) -> list[Reference]:
        """All generated references in index order."""
        return sorted(self._references, key=lambda r: r.index)

    @property
    def count(self) -> int:
        """Number of unique references generated."""
        return len(self._references)

    # ── Public API ──────────────────────────────────────────────

    def cite_source(self, source: Source) -> Citation:
        """Create or retrieve a citation for the given Source.

        If the source URL has already been cited, returns the existing citation
        (deduplication). Otherwise, assigns a new index.

        Parameters
        ----------
        source:
            The Source model to cite.

        Returns
        -------
        Citation
            The citation object with a sequential index.
        """
        return self.cite_metadata(source.metadata)

    def cite_metadata(self, metadata: SourceMetadata) -> Citation:
        """Create or retrieve a citation from SourceMetadata.

        Parameters
        ----------
        metadata:
            The source metadata to cite.

        Returns
        -------
        Citation
            The citation object.
        """
        url = metadata.url

        # Deduplicate: return existing citation if URL was already cited
        if url in self._url_to_index:
            idx = self._url_to_index[url]
            existing = next((r for r in self._references if r.index == idx), None)
            if existing:
                self._log.debug("citation_deduplicated", url=url, index=idx)
                return existing.citation

        # Assign new index
        idx = self._next_index
        self._next_index += 1
        self._url_to_index[url] = idx

        accessed_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        citation = Citation(
            index=idx,
            url=url,
            title=metadata.title,
            author=metadata.author,
            published_date=metadata.published_date,
            domain=metadata.domain,
            accessed_date=accessed_date,
            style=self._style,
        )

        reference = Reference(
            index=idx,
            citation=citation,
            formatted=citation.format(),
        )
        self._references.append(reference)

        self._log.info(
            "citation_created",
            index=idx,
            url=url,
            style=self._style.value,
        )
        return citation

    def cite_sources(self, sources: list[Source]) -> list[Citation]:
        """Cite multiple sources at once.

        Parameters
        ----------
        sources:
            List of Source models to cite.

        Returns
        -------
        list[Citation]
            Citations in the same order as the input sources.
        """
        return [self.cite_source(s) for s in sources]

    def get_inline_marker(self, citation: Citation) -> str:
        """Get the inline citation marker for insertion into report text.

        Parameters
        ----------
        citation:
            The citation to create a marker for.

        Returns
        -------
        str
            The inline marker string (e.g. ``[1]`` for IEEE, ``(Author, 2024)`` for APA).
        """
        if self._style == CitationStyle.IEEE:
            return f"[{citation.index}]"
        elif self._style == CitationStyle.APA:
            author = citation.author.split(",")[0].strip() if citation.author else "Unknown"
            year = self._extract_year(citation.published_date) or "n.d."
            return f"({author}, {year})"
        elif self._style == CitationStyle.MLA:
            author_last = (
                citation.author.split(",")[0].strip().split()[-1]
                if citation.author
                else "Unknown"
            )
            return f"({author_last})"
        elif self._style == CitationStyle.CHICAGO:
            author = citation.author.split(",")[0].strip() if citation.author else "Unknown"
            year = self._extract_year(citation.published_date) or "n.d."
            return f"({author} {year})"
        else:
            return f"[{citation.index}]"

    def generate_reference_section(self) -> str:
        """Generate a complete Markdown reference section.

        Returns
        -------
        str
            Markdown-formatted reference list.
        """
        if not self._references:
            return ""

        sorted_refs = sorted(self._references, key=lambda r: r.index)

        lines: list[str] = ["## References", ""]

        for ref in sorted_refs:
            lines.append(f"{ref.formatted}")
            lines.append("")  # blank line between entries

        return "\n".join(lines)

    def format_citation_manually(
        self,
        *,
        url: str,
        title: str = "",
        author: str = "",
        published_date: str | None = None,
        domain: str = "",
        style: CitationStyle | None = None,
    ) -> str:
        """Format a citation string without adding it to the reference list.

        Useful for one-off formatting without tracking state.

        Parameters
        ----------
        url:
            Source URL.
        title:
            Source title.
        author:
            Author name(s).
        published_date:
            Publication date string.
        domain:
            Source domain.
        style:
            Citation style override; defaults to the tool's current style.

        Returns
        -------
        str
            The formatted citation string.
        """
        use_style = style or self._style
        accessed = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        citation = Citation(
            index=0,  # placeholder, not tracked
            url=url,
            title=title,
            author=author,
            published_date=published_date,
            domain=domain,
            accessed_date=accessed,
            style=use_style,
        )
        return citation.format()

    def reset(self) -> None:
        """Clear all generated references and reset the index counter."""
        self._references.clear()
        self._url_to_index.clear()
        self._next_index = 1
        self._log.info("citation_generator_reset")

    # ── Convenience: all four styles at once ────────────────────

    def format_all_styles(self, metadata: SourceMetadata) -> dict[str, str]:
        """Format a citation in all four styles for comparison.

        Parameters
        ----------
        metadata:
            The source metadata to format.

        Returns
        -------
        dict[str, str]
            Mapping of style name to formatted citation string.
        """
        accessed = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        results: dict[str, str] = {}

        for style in CitationStyle:
            citation = Citation(
                index=0,
                url=metadata.url,
                title=metadata.title,
                author=metadata.author,
                published_date=metadata.published_date,
                domain=metadata.domain,
                accessed_date=accessed,
                style=style,
            )
            results[style.value] = citation.format()

        return results

    # ── Internal helpers ────────────────────────────────────────

    @staticmethod
    def _extract_year(date_str: str | None) -> str | None:
        """Extract a 4-digit year from various date string formats."""
        if not date_str:
            return None
        # Try common patterns
        import re

        match = re.search(r"(\d{4})", date_str)
        return match.group(1) if match else None
