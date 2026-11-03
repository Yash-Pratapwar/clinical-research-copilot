"""Immutable version registry with content-addressed original files."""
import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


class VersionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.blobs = self.path / 'sources'
        self.blobs.mkdir(exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS contents (sha256 TEXT PRIMARY KEY, parts TEXT NOT NULL, chunks INTEGER NOT NULL, original INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS versions (version_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, label TEXT NOT NULL UNIQUE, filename TEXT NOT NULL, version_label TEXT NOT NULL, sha256 TEXT NOT NULL, uploaded_at TEXT NOT NULL)')

            columns = {row[1] for row in db.execute("PRAGMA table_info(contents)")}
            if "chunk_schema" not in columns:
                db.execute("ALTER TABLE contents ADD COLUMN chunk_schema TEXT NOT NULL DEFAULT 'legacy-words'")

            if "extraction_schema" not in columns:
                db.execute("ALTER TABLE contents ADD COLUMN extraction_schema TEXT NOT NULL DEFAULT 'legacy-blocks'")

    def extraction_schema(self, digest):
        with self.connect() as db:
            return db.execute("SELECT extraction_schema FROM contents WHERE sha256=?", (digest,)).fetchone()[0]

    def update_extraction(self, digest, parts, schema):
        with self.connect() as db:
            db.execute("UPDATE contents SET parts=?, extraction_schema=? WHERE sha256=?",
                       (json.dumps([asdict(p) for p in parts]), schema, digest))

    def chunk_schema(self, digest):
        with self.connect() as db:
            return db.execute("SELECT chunk_schema FROM contents WHERE sha256=?", (digest,)).fetchone()[0]

    def connect(self):
        return sqlite3.connect(self.path / 'versions.sqlite3', timeout=30)

    def content(self, digest):
        with self.connect() as db:
            return db.execute('SELECT parts, chunks, original FROM contents WHERE sha256=?', (digest,)).fetchone()

    def save_content(self, digest, parts, chunks, payload=None):
        if payload is not None:
            (self.blobs / digest).write_bytes(payload)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO contents (sha256, parts, chunks, original) VALUES (?, ?, ?, ?)',
                       (digest, json.dumps([asdict(p) for p in parts]), chunks, int(payload is not None)))

    def versions(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute('SELECT v.*, c.chunks, c.original FROM versions v JOIN contents c USING (sha256) ORDER BY v.rowid')]

    def add(self, filename, digest, document_id=None, version_label=None):
        versions = self.versions()
        family = re.sub(r'(?i)(?<![a-z0-9])(?:version|ver|v)[ _.-]*\d+(?:\.\d+)*', '{version}', Path(filename).stem).lower()
        document_id = document_id or hashlib.sha256(family.encode()).hexdigest()[:20]
        group = [v for v in versions if v['document_id'] == document_id]
        if group and group[-1]['filename'] == filename and group[-1]['sha256'] == digest and not version_label:
            return False
        version_label = version_label or f'v{len(group) + 1}'
        if any(v['version_label'] == version_label for v in group):
            raise ValueError('That version label already exists for this document.')
        label = filename
        occupied = {v['label'] for v in versions}
        if label in occupied:
            label = f'{Path(filename).stem} [{version_label}]{Path(filename).suffix}'
        if label in occupied:
            label = f'{Path(filename).stem} [{version_label}-{uuid.uuid4().hex[:8]}]{Path(filename).suffix}'
        with self.connect() as db:
            db.execute('INSERT INTO versions VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (uuid.uuid4().hex, document_id, label, filename, version_label, digest, datetime.now(timezone.utc).isoformat()))
        return True

    def parts(self, version_id):
        version = next((v for v in self.versions() if v['version_id'] == version_id), None)
        if version is None:
            raise ValueError('Unknown document version')
        return json.loads(self.content(version['sha256'])[0])

    def clear(self):
        with self.connect() as db:
            db.execute('DELETE FROM versions')
            db.execute('DELETE FROM contents')
        for blob in self.blobs.iterdir():
            if blob.is_file():
                blob.unlink()
