"""
embedder.py — Singleton de embeddings local para RAG de memórias.
Usa sentence-transformers (all-MiniLM-L6-v2, ~22MB, CPU, zero custo).
"""
from __future__ import annotations
import json
import math
import threading
from typing import List

_lock = threading.Lock()
_model = None

def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer
                _model = SentenceTransformer(
                    "all-MiniLM-L6-v2",
                    cache_folder="/app/data/models",
                )
    return _model


def embed(text: str) -> List[float]:
    """Retorna vetor de embedding para um texto."""
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def cosine_sim(a: List[float], b: List[float]) -> float:
    """Similaridade coseno entre dois vetores já normalizados (produto escalar)."""
    return sum(x * y for x, y in zip(a, b))


def embed_to_json(text: str) -> str:
    return json.dumps(embed(text))


def json_to_vec(s: str) -> List[float]:
    return json.loads(s)
