"""Lazy CPU embedding model; first run downloads the open model once."""
from functools import lru_cache

from .config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _model():
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(min(4, torch.get_num_threads()))
    return SentenceTransformer(EMBEDDING_MODEL, device="cpu")


class LocalEmbeddings:
    @property
    def tokenizer(self):
        return _model().tokenizer

    @property
    def max_seq_length(self):
        return _model().max_seq_length

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = _model().encode(texts, batch_size=12, show_progress_bar=False,
                                  normalize_embeddings=True)
        return vectors.tolist()
