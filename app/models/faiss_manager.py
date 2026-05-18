# FILE: app/models/faiss_manager.py
import faiss
import numpy as np
import hashlib
from app.config import settings
from app.utils.persistence import save_faiss_index, load_faiss_index
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def id_to_int(doc_id: str) -> int:
    return int(hashlib.md5(doc_id.encode()).hexdigest(), 16) & (2**63 - 1)


class FaissManager:
    def __init__(self, dim: int):
        self.dim = dim
        self.index: faiss.Index | None = None

    def build_index(self, items: List[Dict[str, Any]], embeddings: np.ndarray):
        if not items:
            self.index = faiss.IndexIDMap(faiss.IndexFlatIP(self.dim))
            return

        if len(items) < 1000:
            logger.info(
                f"Building simple index (IndexFlatIP) for {len(items)} items.")
            base_index = faiss.IndexFlatIP(self.dim)
            self.index = faiss.IndexIDMap(base_index)
            self.add_items(items, embeddings)
        else:
            logger.info(
                f"Building quantized index (IVFPQ) for {len(items)} items.")
            quantizer = faiss.IndexFlatIP(self.dim)
            nlist = min(100, max(4, int(np.sqrt(len(items)))))
            M = 64
            if self.dim % M != 0:
                M = [m for m in [32, 16, 8, 4, 2, 1] if self.dim % m == 0][0]

            base_ivfpq_index = faiss.IndexIVFPQ(
                quantizer, self.dim, nlist, M, 8)
            base_ivfpq_index.metric_type = faiss.METRIC_INNER_PRODUCT

            logger.info("Training quantized index...")
            base_ivfpq_index.train(embeddings)

            self.index = faiss.IndexIDMap(base_ivfpq_index)
            self.add_items(items, embeddings)

    def add_items(self, items: List[Dict[str, Any]], embeddings: np.ndarray):
        if not items:
            return
        int_ids = np.array([id_to_int(item['_id']) for item in items])
        self.index.add_with_ids(embeddings, int_ids)

    def remove_items(self, item_ids: List[str]):
        if not item_ids or self.index.ntotal == 0:
            return
        int_ids_to_remove = np.array(
            [id_to_int(doc_id) for doc_id in item_ids])
        self.index.remove_ids(int_ids_to_remove)

    def update_items(self, items: List[Dict[str, Any]], embeddings: np.ndarray):
        if not items:
            return
        ids_to_update = [item['_id'] for item in items]
        self.remove_items(ids_to_update)
        self.add_items(items, embeddings)

    def search(self, query_embeddings: np.ndarray, k: int = 10) -> tuple:
        if self.index is None or self.index.ntotal == 0:
            return np.array([[]]), np.array([[]])

        if hasattr(self.index, 'nprobe'):
            self.index.nprobe = 10
        return self.index.search(query_embeddings, k)

    def save(self, path: str = settings.FAISS_INDEX_PATH):
        save_faiss_index(self.index, path)

    def load(self, path: str = settings.FAISS_INDEX_PATH) -> bool:
        index = load_faiss_index(path)
        if index and index.d == self.dim:
            self.index = index
            return True
        return False
