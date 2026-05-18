# FILE: app/utils/persistence.py
import json
import numpy as np
import os
import faiss
from typing import List, Dict, Any
from app.config import settings
import logging
from datetime import datetime
from bson import ObjectId

logger = logging.getLogger(__name__)


def _ensure_dir(file_path: str):
    """Ensures the directory for a file exists, handling permissions gracefully."""
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
        except PermissionError:
            logger.warning(
                f"Could not create directory '{directory}'. Assuming it exists as a mount point.")
        except Exception as e:
            logger.error(
                f"An unexpected error occurred creating directory '{directory}': {e}")
            raise


class CustomJSONEncoder(json.JSONEncoder):
    """A custom JSON encoder that handles both datetime and MongoDB ObjectId."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)


def save_items(items: List[Dict[str, Any]], path: str = settings.ITEMS_PATH):
    """Saves the list of items to a JSON file using the custom encoder."""
    try:
        _ensure_dir(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, cls=CustomJSONEncoder)
    except IOError as e:
        logger.error(f"Failed to save items to {path}: {e}")


def load_items(path: str = settings.ITEMS_PATH) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load items from {path}: {e}")
        return []


def save_faiss_index(index: faiss.Index, path: str = settings.FAISS_INDEX_PATH):
    try:
        _ensure_dir(path)
        faiss.write_index(index, path)
    except Exception as e:
        logger.error(f"Failed to save FAISS index to {path}: {e}")


def load_faiss_index(path: str = settings.FAISS_INDEX_PATH) -> faiss.Index | None:
    if not os.path.exists(path):
        return None
    try:
        return faiss.read_index(path)
    except Exception as e:
        logger.error(f"Error loading FAISS index from {path}: {e}")
        return None
