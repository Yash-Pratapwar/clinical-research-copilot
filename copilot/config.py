"""Central settings: no secrets or paid API keys are needed."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("COPILOT_DB_PATH", str(ROOT / ".chroma")))
MODEL_NAME = os.getenv("COPILOT_MODEL", "qwen2.5:1.5b")
EMBEDDING_MODEL = os.getenv("COPILOT_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
COLLECTION_NAME = "clinical_research_copilot_v1"
MAX_FILE_BYTES = 15 * 1024 * 1024
CHUNK_WORDS = 145  # MiniLM accepts only ~256 wordpieces; avoid truncating 600-token chunks
CHUNK_OVERLAP = 30
MAX_CONTEXT_CHUNKS = 9
MIN_SIMILARITY = 0.23  # heuristic only; evaluate on your actual documents
