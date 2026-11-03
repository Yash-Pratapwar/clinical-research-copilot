"""Persistent local Chroma index, with explicit embeddings and source metadata."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from .chunking import chunk_parts
from .config import COLLECTION_NAME, DB_PATH, MIN_SIMILARITY
from .documents import extract_document
from .embeddings import LocalEmbeddings


@dataclass
class Evidence:
    text: str
    metadata: dict[str, Any]
    similarity: float
    chunk_id: str


class DocumentIndex:
    def __init__(self, path: Path = DB_PATH, embedder=None):
        self.client = chromadb.PersistentClient(
            path=str(path), settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
        self.embedder = embedder if embedder is not None else LocalEmbeddings()

    def add_file(self, filename: str, payload: bytes) -> tuple[int, bool]:
        filename = Path(filename.replace("\\", "/")).name
        if not filename or filename in {".", ".."}:
            raise ValueError("Invalid filename")
        parts = extract_document(filename, payload)
        digest = hashlib.sha256(payload).hexdigest()
        existing = self.collection.get(where={"sha256": digest}, limit=1)
        if existing.get("ids"):
            return 0, False
        # If the same name is re-uploaded with different content, replace old chunks.
        old = self.collection.get(where={"filename": filename}, include=[])
        chunks = chunk_parts(parts)
        if not chunks:
            raise ValueError("The uploaded document did not produce any searchable chunks.")
        # Batch to limit 8 GB memory usage.
        for offset in range(0, len(chunks), 24):
            batch = chunks[offset:offset + 24]
            embeddings = self.embedder.embed([c.text for c in batch])
            self.collection.add(
                ids=[f"{digest[:20]}_{offset + i}" for i in range(len(batch))],
                embeddings=embeddings,
                documents=[c.text for c in batch],
                metadatas=[{
                    "filename": c.filename, "file_type": c.file_type,
                    "section": c.section, "location": c.location,
                    "page": c.page, "sha256": digest,
                } for c in batch],
            )
        if old["ids"]:
            self.collection.delete(ids=old["ids"])
        return len(chunks), True

    def list_files(self) -> list[dict[str, Any]]:
        result = self.collection.get(include=["metadatas"])
        by_name: dict[str, dict[str, Any]] = {}
        for meta in result.get("metadatas") or []:
            if not meta:
                continue
            key = str(meta["filename"])
            if key not in by_name:
                by_name[key] = {"filename": key, "sha256": meta["sha256"], "chunks": 0}
            by_name[key]["chunks"] += 1
        return sorted(by_name.values(), key=lambda d: d["filename"].lower())

    def clear(self) -> None:
        self.client.delete_collection(name=COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    def query(self, question: str, limit: int = 8,
              filename: str | None = None, threshold: float = MIN_SIMILARITY) -> list[Evidence]:
        count = self.collection.count()
        if not count:
            return []
        vector = self.embedder.embed([question])[0]
        kwargs = {"query_embeddings": [vector], "n_results": min(count, limit),
                  "include": ["documents", "metadatas", "distances"]}
        if filename:
            kwargs["where"] = {"filename": filename}
        try:
            result = self.collection.query(**kwargs)
        except Exception:
            # Chroma may reject where filter if the document was removed; no evidence.
            if filename:
                return []
            raise
        matches = []
        for cid, txt, meta, distance in zip(
            result["ids"][0], result["documents"][0],
            result["metadatas"][0], result["distances"][0],
        ):
            score = max(-1.0, min(1.0, 1.0 - float(distance)))
            if score >= threshold:
                matches.append(Evidence(text=txt, metadata=meta,
                                        similarity=score, chunk_id=cid))
        return matches

    def retrieve(self, question: str, *, mode: str = "lookup", limit: int = 9,
                 filenames: list[str] | None = None) -> list[Evidence]:
        """Broad queries + per-document top hits when cross-document evidence matters."""
        files = [f["filename"] for f in self.list_files()]
        if not files:
            return []
        if filenames:
            if any(name not in files for name in filenames):
                raise ValueError('Selected documents are no longer available.')
            if len(filenames) > limit:
                raise ValueError(f'Please select at most {limit} documents for one question.')
            groups = [self.query(question, filename=name, limit=limit) for name in filenames]
            # Round-robin preserves representation for every selected source.
            return [group[i] for i in range(max(map(len, groups), default=0))
                    for group in groups if i < len(group)][:limit]
        variants = [question]
        if mode == "safety":
            variants += ["protocol required safety assessments reporting requirements",
                         "monitoring site observations missed assessments protocol deviations patient safety"]
        elif mode == "summary":
            variants += ["study objectives eligibility criteria trial design visit schedule safety reporting"]
        elif mode == "compare":
            variants += ["protocol amendments version changes eligibility visit schedule safety"]

        best: dict[str, Evidence] = {}
        for variant in variants:
            for item in self.query(variant, limit=limit):
                if item.chunk_id not in best or item.similarity > best[item.chunk_id].similarity:
                    best[item.chunk_id] = item

        # Make sure multi-document analysis can see a relevant chunk per document.
        if mode in {"safety", "compare"} and len(files) > 1:
            selected = files
            if mode == "compare":
                protocol_files = [f for f in files if "protocol" in f.lower()]
                if len(protocol_files) >= 2:
                    selected = protocol_files
            for filename in selected[:6]:
                for item in self.query(question, filename=filename, limit=2):
                    best.setdefault(item.chunk_id, item)

        ranked = sorted(best.values(), key=lambda ev: ev.similarity, reverse=True)
        if mode in {"safety", "compare"}:
            # Document diversity: reserve one reasonably relevant hit per selected document.
            per_file: dict[str, Evidence] = {}
            for e in ranked:
                per_file.setdefault(e.metadata["filename"], e)
            selected = list(per_file.values())[:min(5, limit)]
            selected_ids = {e.chunk_id for e in selected}
            selected.extend(e for e in ranked if e.chunk_id not in selected_ids)
            ranked = selected
        return ranked[:limit]
