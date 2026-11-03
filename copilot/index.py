"""Persistent local Chroma index, with explicit embeddings and source metadata."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from .chunking import CHUNK_SCHEMA, chunk_parts
from .config import COLLECTION_NAME, DB_PATH, MIN_SIMILARITY
from .documents import DocumentPart, extract_document
from .pdf_layout import PDF_LAYOUT_SCHEMA
from .versions import VersionStore
from .comparison import compare_parts
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
        self.store = VersionStore(Path(path) / "history")
        self._migrate_legacy()
        # Originals and version IDs remain immutable. A PDF extraction upgrade
        # refreshes derived full text and search chunks together; a chunk-only
        # upgrade never changes comparison input.
        for digest in {v["sha256"] for v in self.list_versions() if v["original"]}:
            version = next(v for v in self.list_versions() if v["sha256"] == digest)
            upgrade_pdf = (Path(version["filename"]).suffix.lower() == ".pdf"
                           and self.store.extraction_schema(digest) != PDF_LAYOUT_SCHEMA)
            if self.store.chunk_schema(digest) != CHUNK_SCHEMA or upgrade_pdf:
                parts = extract_document(version["filename"], (self.store.blobs / digest).read_bytes())
                self._index_content(digest, parts)
                if upgrade_pdf:
                    self.store.update_extraction(digest, parts, PDF_LAYOUT_SCHEMA)

    def _migrate_legacy(self):
        # Preserve existing indexes. Original bytes cannot be recovered from old chunks.
        known = {v["sha256"] for v in self.store.versions()}
        records = self.collection.get(include=["documents", "metadatas"])
        grouped = {}
        for cid, text, meta in zip(records["ids"], records["documents"], records["metadatas"]):
            if meta["sha256"] not in known:
                grouped.setdefault(meta["sha256"], []).append((cid, text, meta))
        for digest, rows in grouped.items():
            rows.sort(key=lambda row: int(row[0].rsplit("_", 1)[-1]))
            parts = [DocumentPart(text, meta["filename"], meta["file_type"],
                     meta["section"], meta["location"], meta["page"]) for _, text, meta in rows]
            self.store.save_content(digest, parts, len(rows))
            self.store.add(rows[0][2]["filename"], digest)

    def list_versions(self, document_id=None):
        return [v for v in self.store.versions()
                if document_id is None or v["document_id"] == document_id]

    def compare_versions(self, before_id, after_id):
        versions = {v["version_id"]: v for v in self.list_versions()}
        if before_id not in versions or after_id not in versions:
            raise ValueError("Unknown document version")
        left, right = versions[before_id], versions[after_id]
        if left["sha256"] == right["sha256"]:
            return []
        if not left["original"] or not right["original"]:
            raise ValueError("Re-upload legacy versions before exact comparison; their original text was not retained.")
        return compare_parts(self.store.parts(before_id), self.store.parts(after_id))

    def original_file(self, version_id):
        version = next((v for v in self.list_versions() if v["version_id"] == version_id), None)
        if version is None or not version["original"]:
            raise ValueError("Original file is unavailable for this version.")
        return (self.store.blobs / version["sha256"]).read_bytes()

    def add_file(self, filename: str, payload: bytes, *, document_id=None,
                 version_label=None) -> tuple[int, bool]:
        filename = Path(filename.replace("\\", "/")).name
        if not filename or filename in {".", ".."}:
            raise ValueError("Invalid filename")
        parts = extract_document(filename, payload)
        digest = hashlib.sha256(payload).hexdigest()
        # Validate version labels before writing content.
        group = self.list_versions(document_id) if document_id else []
        if version_label and any(v["version_label"] == version_label for v in group):
            raise ValueError("That version label already exists for this document.")
        content = self.store.content(digest)
        if content is None:
            count = self._index_content(digest, parts)
            self.store.save_content(digest, parts, count, payload)
            self.store.update_extraction(digest, parts, PDF_LAYOUT_SCHEMA if filename.lower().endswith(".pdf") else "docx-native-v1")
            with self.store.connect() as db:
                db.execute("UPDATE contents SET chunk_schema=? WHERE sha256=?", (CHUNK_SCHEMA, digest))
        else:
            count = content[1]
            if not content[2]:
                # Recover exact extraction and original bytes for a legacy upload.
                import json
                from dataclasses import asdict
                (self.store.blobs / digest).write_bytes(payload)
                count = self._index_content(digest, parts)
                with self.store.connect() as db:
                    db.execute("UPDATE contents SET parts=?, original=1 WHERE sha256=?",
                               (json.dumps([asdict(p) for p in parts]), digest))
                self.store.update_extraction(digest, parts, PDF_LAYOUT_SCHEMA if filename.lower().endswith(".pdf") else "docx-native-v1")
        added = self.store.add(filename, digest, document_id, version_label)
        return (count, True) if added else (0, False)

    def _index_content(self, digest, parts):
        # Inject the actual embedding tokenizer; fake embedders used in offline
        # tests supply their own tokenizer and matching model budget.
        tokenizer = self.embedder.tokenizer
        from .config import CHUNK_TOKENS, CHUNK_OVERLAP
        budget = min(CHUNK_TOKENS, self.embedder.max_seq_length)
        chunks = chunk_parts(parts, size=budget, overlap=min(CHUNK_OVERLAP, budget // 4),
                             tokenizer=tokenizer)
        if not chunks:
            raise ValueError("The uploaded document did not produce any searchable chunks.")
        old_ids = self.collection.get(where={"sha256": digest}, include=[])["ids"]
        new_ids = []
        for offset in range(0, len(chunks), 24):
            batch = chunks[offset:offset + 24]
            ids = [f"{digest[:20]}_{CHUNK_SCHEMA}_{offset + i}" for i in range(len(batch))]
            self.collection.upsert(
                ids=ids, embeddings=self.embedder.embed([c.text for c in batch]),
                documents=[c.text for c in batch],
                metadatas=[{
                    "filename": c.filename, "file_type": c.file_type,
                    "section": c.section, "section_id": c.section_id,
                    "location": c.location, "page": c.page, "sha256": digest,
                    "chunk_index": c.chunk_index, "paragraph_start": c.paragraph_start,
                    "paragraph_end": c.paragraph_end, "paragraph_split": c.paragraph_split,
                    "token_count": c.token_count, "chunk_schema": CHUNK_SCHEMA,
                    "block_type": c.block_type, "source_regions": c.source_regions,
                } for c in batch])
            new_ids.extend(ids)
        stale = set(old_ids) - set(new_ids)
        if stale:
            self.collection.delete(ids=list(stale))
        with self.store.connect() as db:
            db.execute("UPDATE contents SET chunks=?, chunk_schema=? WHERE sha256=?",
                       (len(chunks), CHUNK_SCHEMA, digest))
        return len(chunks)

    def list_files(self) -> list[dict[str, Any]]:
        return [dict(v, filename=v["label"]) for v in self.list_versions()]

    def clear(self) -> None:
        self.store.clear()
        self.client.delete_collection(name=COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    def query(self, question: str, limit: int = 8,
              filename: str | None = None, threshold: float = MIN_SIMILARITY) -> list[Evidence]:
        versions = self.list_versions()
        selected = [v for v in versions if filename is None or v["label"] == filename]
        if not selected:
            return []
        count = self.collection.count()
        if not count:
            return []
        vector = self.embedder.embed([question])[0]
        kwargs = {"query_embeddings": [vector], "n_results": min(count, limit),
                  "include": ["documents", "metadatas", "distances"]}
        if filename:
            kwargs["where"] = {"sha256": selected[0]["sha256"]}
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
                for version in selected:
                    if version["sha256"] != meta["sha256"]:
                        continue
                    metadata = dict(meta, filename=version["label"],
                                    document_id=version["document_id"],
                                    version_id=version["version_id"],
                                    version_label=version["version_label"])
                    if meta.get("section_id"):
                        metadata["section_id"] = version["version_id"] + ":" + meta["section_id"]
                    matches.append(Evidence(text=txt, metadata=metadata,
                                            similarity=score,
                                            chunk_id=f'{version["version_id"]}:{cid}'))
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
