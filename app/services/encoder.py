# FILE: app/services/encoder.py
from sentence_transformers import SentenceTransformer
import numpy as np
from functools import lru_cache
import logging
from app.config import settings
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_model(name: str = None) -> SentenceTransformer:
    model_name = name or settings.MODEL_NAME
    logger.info(f"Loading SentenceTransformer model: {model_name}")
    return SentenceTransformer(model_name)


def normalize_embeddings(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return np.divide(vectors, norms, out=np.zeros_like(vectors), where=norms != 0)


def encode_query(text: str) -> np.ndarray:
    model = get_model()
    embedding = model.encode([text], convert_to_numpy=True)
    return normalize_embeddings(embedding).astype("float32")


def create_blended_embeddings(items: List[Dict[str, Any]]) -> np.ndarray:
    model = get_model()

    names = [item.get("name", "") for item in items]
    descriptions = [item.get("description", "") for item in items]
    category_names = [item.get("category", {}).get(
        "name", "") if not item.get("isCategory") else "" for item in items]

    all_texts = names + descriptions + category_names
    all_embeddings = model.encode(all_texts, show_progress_bar=False)

    name_embs = all_embeddings[:len(names)]
    desc_embs = all_embeddings[len(names):len(names) * 2]
    cat_embs = all_embeddings[len(names) * 2:]

    blended_embeddings = (
        settings.SERVICE_NAME_WEIGHT * name_embs +
        settings.SERVICE_DESCRIPTION_WEIGHT * desc_embs +
        settings.CATEGORY_NAME_WEIGHT * cat_embs
    )

    return normalize_embeddings(blended_embeddings).astype("float32")
