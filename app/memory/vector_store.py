"""ChromaDB-backed vector store for semantic search over research documents.

Provides text chunking, embedding via sentence-transformers, and
similarity search scoped to individual research sessions.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import chromadb
import structlog
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from app.config import get_settings

logger = structlog.get_logger(__name__)


def _chunk_text(
    text: str,
    chunk_size: int = 1500,
    overlap: int = 200,
) -> list[str]:
    """Split *text* into overlapping chunks.

    Parameters
    ----------
    text:
        The full text to split.
    chunk_size:
        Maximum character length of each chunk.
    overlap:
        Number of overlapping characters between consecutive chunks.

    Returns
    -------
    list[str]
        Ordered list of text chunks.
    """
    if not text or not text.strip():
        return []

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size

        # Try to break at a paragraph or sentence boundary
        if end < text_len:
            # Look for paragraph break first
            para_break = text.rfind("\n\n", start, end)
            if para_break > start + chunk_size // 2:
                end = para_break + 2
            else:
                # Fall back to sentence boundary
                for sep in (". ", "! ", "? ", "\n"):
                    sent_break = text.rfind(sep, start, end)
                    if sent_break > start + chunk_size // 2:
                        end = sent_break + len(sep)
                        break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap if end < text_len else text_len

    return chunks


class VectorStore:
    """Per-session ChromaDB vector store with sentence-transformer embeddings.

    Usage::

        store = VectorStore(session_id="abc-123")
        await store.add_documents(
            texts=["..."],
            metadatas=[{"source_url": "..."}],
            ids=["doc-1"],
        )
        results = await store.search_similar("query text", n_results=5)
    """

    def __init__(
        self,
        session_id: str,
        persist_dir: str | None = None,
        collection_prefix: str | None = None,
        embedding_model: str = "all-MiniLM-L6-v2",
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
    ) -> None:
        settings = get_settings()
        self._persist_dir = persist_dir or str(settings.chroma_path)
        self._prefix = collection_prefix or settings.chroma_collection_prefix
        self._session_id = session_id
        self._collection_name = f"{self._prefix}{session_id}"
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

        # Embedding function
        self._embedding_fn = SentenceTransformerEmbeddingFunction(
            model_name=embedding_model,
        )

        # Persistent ChromaDB client
        self._client = chromadb.PersistentClient(path=self._persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            "vector_store_initialized",
            session_id=session_id,
            collection=self._collection_name,
            persist_dir=self._persist_dir,
        )

    # ── Public async API ────────────────────────────────────────

    async def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> int:
        """Chunk and add documents to the collection.

        Parameters
        ----------
        texts:
            Raw document texts to chunk and index.
        metadatas:
            Optional per-document metadata dicts.  Metadata is propagated
            to every chunk derived from the document.
        ids:
            Optional per-document base IDs.  If omitted, UUIDs are generated.
            Each chunk receives ``{base_id}_chunk_{i}``.

        Returns
        -------
        int
            Number of chunks actually added.
        """
        if not texts:
            return 0

        all_chunks: list[str] = []
        all_metas: list[dict[str, Any]] = []
        all_ids: list[str] = []

        for doc_idx, text in enumerate(texts):
            base_id = (ids[doc_idx] if ids and doc_idx < len(ids)
                       else str(uuid.uuid4()))
            doc_meta = (metadatas[doc_idx] if metadatas and doc_idx < len(metadatas)
                        else {})

            chunks = _chunk_text(text, self._chunk_size, self._chunk_overlap)

            for chunk_idx, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_ids.append(f"{base_id}_chunk_{chunk_idx}")
                all_metas.append({
                    **doc_meta,
                    "doc_id": base_id,
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                })

        if not all_chunks:
            return 0

        # Offload blocking ChromaDB call to a thread
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._collection.add(
                documents=all_chunks,
                metadatas=all_metas,
                ids=all_ids,
            ),
        )

        logger.info(
            "documents_added",
            documents=len(texts),
            chunks=len(all_chunks),
            collection=self._collection_name,
        )
        return len(all_chunks)

    async def search_similar(
        self,
        query: str,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for chunks semantically similar to *query*.

        Parameters
        ----------
        query:
            Natural-language search query.
        n_results:
            Maximum number of results to return.
        where:
            Optional ChromaDB ``where`` filter dict.

        Returns
        -------
        list[dict]
            Each dict has keys: ``id``, ``document``, ``metadata``,
            ``distance``.
        """
        loop = asyncio.get_running_loop()

        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n_results, self._collection.count() or n_results),
        }
        if where:
            kwargs["where"] = where

        if self._collection.count() == 0:
            logger.warning("search_on_empty_collection", collection=self._collection_name)
            return []

        raw = await loop.run_in_executor(
            None,
            lambda: self._collection.query(**kwargs),
        )

        results: list[dict[str, Any]] = []
        if raw and raw.get("ids"):
            for i, doc_id in enumerate(raw["ids"][0]):
                results.append({
                    "id": doc_id,
                    "document": raw["documents"][0][i] if raw.get("documents") else "",
                    "metadata": raw["metadatas"][0][i] if raw.get("metadatas") else {},
                    "distance": raw["distances"][0][i] if raw.get("distances") else 0.0,
                })

        logger.info(
            "search_completed",
            query_preview=query[:80],
            results_count=len(results),
            collection=self._collection_name,
        )
        return results

    async def get_collection_stats(self) -> dict[str, Any]:
        """Return basic statistics about the current collection.

        Returns
        -------
        dict
            Keys: ``collection_name``, ``document_count``, ``persist_dir``.
        """
        loop = asyncio.get_running_loop()
        count = await loop.run_in_executor(None, self._collection.count)

        return {
            "collection_name": self._collection_name,
            "document_count": count,
            "persist_dir": self._persist_dir,
        }

    async def delete_collection(self) -> None:
        """Delete the entire collection for this session."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.delete_collection(self._collection_name),
        )
        logger.info("collection_deleted", collection=self._collection_name)
