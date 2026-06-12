"""RAG memory — a small, dependency-light vector store.

What this does: turn text into embeddings (vectors of numbers that capture
meaning), store them, and later find the chunks whose meaning is closest to a
query. That's retrieval-augmented generation (RAG): instead of dumping a whole
100-page PDF into the model, we store it once and pull back only the few
paragraphs that actually answer the question.

Why numpy and not Chroma/FAISS: those pull heavy ML wheels that don't build on
Python 3.10 here, and we don't need them. We bring our own embeddings (local
nomic-embed-text via Ollama), so a brute-force cosine search over a numpy matrix
is all it takes. This is fast for tens of thousands of chunks — plenty for a
personal agent. Swap in a real vector DB later if the corpus gets huge.

Persistence: vectors + metadata are saved to vector_store/ as .npy + .json so
memory survives restarts (and across sessions — the agent remembers).
"""

import json
from pathlib import Path

import numpy as np

from config import get_ollama_client, get_embed_model, get_embed_host

STORE_DIR = Path(__file__).resolve().parent.parent / "vector_store"
_VECS = STORE_DIR / "vectors.npy"
_META = STORE_DIR / "meta.json"

# Chunking: ~1000 chars per chunk with 150 char overlap so a sentence split
# across a boundary still shows up in one chunk.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# Structural chunking splits on the highest-level boundary that fits, falling
# back to finer ones. Paragraph first, then line, then sentence, then word,
# then hard char-split. This keeps whole ideas together instead of cutting
# mid-sentence the way blind fixed-size splitting does.
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _embed(texts: list[str]) -> np.ndarray:
    """Embed a list of texts via the LOCAL Ollama embedding model."""
    client = get_ollama_client(host=get_embed_host())
    resp = client.embed(model=get_embed_model(), input=texts)
    vecs = resp.get("embeddings") or resp.get("embedding")
    arr = np.array(vecs, dtype=np.float32)
    # L2-normalize so dot product == cosine similarity.
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def _recursive_split(text: str, size: int, separators: list[str]) -> list[str]:
    """Split text into pieces <= size, preferring high-level boundaries."""
    if len(text) <= size:
        return [text] if text.strip() else []

    sep = separators[0]
    rest = separators[1:] if len(separators) > 1 else [""]

    if sep == "":
        # No structure left — hard split by size.
        return [text[i : i + size] for i in range(0, len(text), size)]

    pieces: list[str] = []
    for part in text.split(sep):
        part = part + sep if sep not in ("",) else part
        if len(part) <= size:
            if part.strip():
                pieces.append(part)
        else:
            pieces.extend(_recursive_split(part, size, rest))
    return pieces


def _merge_with_overlap(pieces: list[str], size: int, overlap: int) -> list[str]:
    """Greedily pack small pieces into ~size chunks, carrying an overlap tail."""
    chunks: list[str] = []
    current = ""
    for p in pieces:
        candidate = (current + " " + p).strip() if current else p.strip()
        if len(candidate) <= size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if overlap and chunks:
                tail = chunks[-1][-overlap:]
                current = (tail + " " + p).strip()
                if len(current) > size:
                    current = p.strip()
            else:
                current = p.strip()
    if current.strip():
        chunks.append(current)
    return chunks


def chunk_text(text: str, source: str) -> list[dict]:
    """Split text into structure-aware, overlapping chunks tagged with source.

    Splits on paragraph/line/sentence boundaries before resorting to raw char
    splits, then packs the pieces into ~CHUNK_SIZE chunks with overlap.
    """
    pieces = _recursive_split(text, CHUNK_SIZE, SEPARATORS)
    merged = _merge_with_overlap(pieces, CHUNK_SIZE, CHUNK_OVERLAP)
    return [
        {"source": source, "text": c, "offset": i}
        for i, c in enumerate(merged)
    ]


def _load() -> tuple[np.ndarray | None, list[dict]]:
    if _VECS.exists() and _META.exists():
        vecs = np.load(_VECS)
        meta = json.loads(_META.read_text())
        return vecs, meta
    return None, []


def _save(vecs: np.ndarray, meta: list[dict]) -> None:
    STORE_DIR.mkdir(exist_ok=True)
    np.save(_VECS, vecs)
    _META.write_text(json.dumps(meta, indent=2))


def add_text(text: str, source: str) -> int:
    """Chunk, embed, and store text. Returns the number of chunks added."""
    new_chunks = chunk_text(text, source)
    if not new_chunks:
        return 0

    new_vecs = _embed([c["text"] for c in new_chunks])

    vecs, meta = _load()
    # Drop any prior chunks from the same source so re-indexing replaces.
    if meta:
        keep = [i for i, m in enumerate(meta) if m["source"] != source]
        vecs = vecs[keep] if keep else None
        meta = [meta[i] for i in keep]

    if vecs is not None and len(vecs):
        vecs = np.vstack([vecs, new_vecs])
    else:
        vecs = new_vecs
    meta = meta + new_chunks

    _save(vecs, meta)
    return len(new_chunks)


def search(query: str, k: int = 5) -> list[dict]:
    """Return the k chunks whose meaning is closest to the query."""
    vecs, meta = _load()
    if vecs is None or not len(meta):
        return []

    q = _embed([query])[0]
    scores = vecs @ q  # cosine sim (all normalized)
    top = np.argsort(-scores)[:k]
    return [
        {**meta[i], "score": float(scores[i])}
        for i in top
    ]


def stats() -> dict:
    """Summary of what's in memory."""
    vecs, meta = _load()
    sources = sorted({m["source"] for m in meta}) if meta else []
    return {"chunks": len(meta), "sources": sources}


def clear() -> None:
    """Wipe all memory."""
    for p in (_VECS, _META):
        if p.exists():
            p.unlink()
