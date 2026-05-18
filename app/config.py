# FILE: app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # --- Database Settings ---
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "anandutsav"
    COLLECTION_NAME: str = "services"

    # --- ✅ New, Faster Machine Learning Model ---
    MODEL_NAME: str = "all-MiniLM-L6-v2"

    # --- File Paths (for persistent disk) ---
    ITEMS_PATH: str = "/data/items.json"
    FAISS_INDEX_PATH: str = "/data/faiss.index"

    # --- Search Algorithm Tuning ---
    CATEGORY_BOOST: float = 0.1
    SERVICE_NAME_WEIGHT: float = 0.6
    CATEGORY_NAME_WEIGHT: float = 0.3
    SERVICE_DESCRIPTION_WEIGHT: float = 0.1

    # --- Predefined Data ---
    PREDEFINED_CATEGORIES: List[str] = [
        "Catering", "Decorations", "Photography", "Videography",
        "Beauty & Makeup", "Fashion & Attire", "Invitations", "Venues",
        "Entertainment", "Music Bands", "DJs", "Travel", "Transport",
        "Event Planning", "Florists", "Production (Sound & Lights)",
        "Fireworks", "Mehndi Artists", "Gifting", "Jewellery"
    ]


settings = Settings()
