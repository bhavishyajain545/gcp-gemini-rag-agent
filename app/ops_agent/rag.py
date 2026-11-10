"""Minimal RAG over Markdown runbooks.

Pipeline: load runbooks (GCS bucket, or local folder for dev) -> chunk with
overlap -> embed with a Vertex AI text embedding model -> keep vectors in memory
-> cosine similarity search. Small on purpose: a few dozen chunks do not need a
vector database. See README "Interview talking points" for when to move to
Vertex AI RAG Engine or BigQuery vector search.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from google import genai
from google.genai import types

log = logging.getLogger(__name__)

# gemini-embedding-001 embeds a batch of texts per request. (gemini-embedding-2 was
# tried first: on Vertex it returned ONE vector for a batched request, which
# silently collapsed the index to a single chunk; the assertion in _embed guards that.)
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
RUNBOOKS_BUCKET = os.environ.get("RUNBOOKS_BUCKET")  # unset => local folder
LOCAL_RUNBOOKS_DIR = Path(os.environ.get("LOCAL_RUNBOOKS_DIR", Path(__file__).resolve().parents[2] / "runbooks"))
CHUNK_CHARS = 1000
CHUNK_OVERLAP = 200
TOP_K = 4
EMBED_BATCH = 20


@dataclass
class Chunk:
    source: str
    text: str


def _load_documents() -> dict[str, str]:
    """Return {file_name: markdown_text} from GCS when configured, else local disk."""
    if RUNBOOKS_BUCKET:
        from google.cloud import storage

        client = storage.Client()
        docs = {}
        for blob in client.list_blobs(RUNBOOKS_BUCKET, prefix="runbooks/"):
            if blob.name.endswith(".md"):
                docs[Path(blob.name).name] = blob.download_as_text()
        log.info("loaded %d runbooks from gs://%s/runbooks", len(docs), RUNBOOKS_BUCKET)
        return docs

    docs = {p.name: p.read_text(encoding="utf-8") for p in sorted(LOCAL_RUNBOOKS_DIR.glob("*.md"))}
    log.info("loaded %d runbooks from %s", len(docs), LOCAL_RUNBOOKS_DIR)
    return docs


def _chunk(source: str, text: str) -> list[Chunk]:
    """Fixed-size character windows with overlap, snapped to the previous newline when possible."""
    chunks, start, n = [], 0, len(text)
    while start < n:
        end = min(start + CHUNK_CHARS, n)
        if end < n:
            nl = text.rfind("\n", start + CHUNK_CHARS // 2, end)
            if nl != -1:
                end = nl
        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(source, piece))
        if end >= n:
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


class RunbookIndex:
    """Lazily built in-memory vector index, shared by all requests in the process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._docs: dict[str, str] = {}
        self._chunks: list[Chunk] = []
        self._matrix: np.ndarray | None = None
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client()  # Vertex AI via GOOGLE_GENAI_USE_VERTEXAI env
        return self._client

    def _embed(self, texts: list[str], task_type: str) -> np.ndarray:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            resp = self.client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=texts[i : i + EMBED_BATCH],
                config=types.EmbedContentConfig(task_type=task_type),
            )
            vectors.extend(e.values for e in resp.embeddings)
        if len(vectors) != len(texts):
            raise RuntimeError(f"{EMBEDDING_MODEL} returned {len(vectors)} vectors for {len(texts)} texts")
        m = np.asarray(vectors, dtype=np.float32)
        return m / np.linalg.norm(m, axis=1, keepdims=True)

    def ensure_built(self) -> None:
        if self._matrix is not None:
            return
        with self._lock:
            if self._matrix is not None:
                return
            docs = _load_documents()
            chunks = [c for name, text in docs.items() for c in _chunk(name, text)]
            if not chunks:
                raise RuntimeError("no runbooks found; check RUNBOOKS_BUCKET or LOCAL_RUNBOOKS_DIR")
            self._matrix = self._embed([c.text for c in chunks], "RETRIEVAL_DOCUMENT")
            self._chunks = chunks
            self._docs = docs
            log.info("indexed %d chunks from %d runbooks", len(chunks), len(docs))

    def document(self, name: str) -> str | None:
        self.ensure_built()
        return self._docs.get(name)

    def names(self) -> list[str]:
        self.ensure_built()
        return sorted(self._docs)

    def search(self, query: str, top_k: int = TOP_K) -> list[dict]:
        self.ensure_built()
        assert self._matrix is not None
        q = self._embed([query], "RETRIEVAL_QUERY")[0]
        scores = self._matrix @ q
        best = np.argsort(-scores)[:top_k]
        return [
            {"source": self._chunks[i].source, "score": round(float(scores[i]), 3), "text": self._chunks[i].text}
            for i in best
        ]


_index = RunbookIndex()


def search_runbooks(query: str) -> dict:
    """Find which runbooks are relevant to a question or incident (semantic search).

    Call this ONCE with the user's question. It returns the best-matching
    excerpts and their `source` file names. Then call `read_runbook` on the top
    source to get the complete procedure before answering.

    Args:
        query: The user's question or incident description, in plain English.

    Returns:
        dict with `results`: list of {source, score, text} ordered by relevance.
    """
    return {"results": _index.search(query)}


def read_runbook(file_name: str) -> dict:
    """Return the full text of one runbook so you can give complete, ordered steps.

    Args:
        file_name: Exact `source` value returned by search_runbooks, e.g. "couchdb-recovery.md".

    Returns:
        dict with `source` and `text`, or `error` plus the list of available runbooks.
    """
    text = _index.document(file_name.strip())
    if text is None:
        return {"error": f"no runbook named '{file_name}'", "available": _index.names()}
    return {"source": file_name.strip(), "text": text}
