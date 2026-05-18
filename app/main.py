# FILE: app/main.py
from fastapi import FastAPI, HTTPException, Query
from contextlib import asynccontextmanager
import asyncio
import logging
import os
from cachetools import TTLCache
from typing import Optional

from app.config import settings
from app.models.pydantic_models import (
    SearchResponse, StatusResponse, HealthResponse, RefreshResponse, AutocompleteResponse,
    ContentRecommendationResponse, CollaborativeRecommendationResponse, RatingMatrixResponse, UpdateRatingRequest
)
from app.services.data_loader import fetch_and_extract_items, fetch_one_service
from app.services.encoder import create_blended_embeddings, get_model
from app.models.faiss_manager import FaissManager
from app.services.hybrid_search import HybridSearchEngine
from app.services.recommender import recommender
from app.utils.persistence import load_items, save_items
from app.utils.database import connect_to_mongo, close_mongo_connection, get_database
from app.utils.locks import data_lock
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Global State ---
faiss_manager: FaissManager | None = None
hybrid_engine: HybridSearchEngine | None = None
search_cache = TTLCache(maxsize=500, ttl=300)

# --- Real-Time Update Logic ---


async def _update_single_item(service_id: str):
    logger.info(f"Real-time update triggered for service ID: {service_id}")
    async with data_lock:
        item = await fetch_one_service(service_id)
        if item:
            embedding = create_blended_embeddings([item])
            faiss_manager.update_items([item], embedding)
            hybrid_engine.update_item_in_map(item)
            logger.info(
                f"Successfully updated item {service_id} in real-time.")
        else:
            faiss_manager.remove_items([service_id])
            hybrid_engine.remove_item_from_map(service_id)
            logger.info(f"Removed item {service_id} in real-time.")
        save_items(hybrid_engine.items)
        faiss_manager.save()


async def watch_mongodb_changes():
    db = get_database()
    if db is None:
        logger.error("Cannot start MongoDB watcher: No database connection.")
        return

    try:
        change_stream = db[settings.COLLECTION_NAME].watch()
        logger.info("MongoDB Change Stream watcher started...")
        async for change in change_stream:
            doc_id = str(change['documentKey']['_id'])
            if change['operationType'] in ['insert', 'update', 'replace', 'delete']:
                asyncio.create_task(_update_single_item(doc_id))
    except Exception as e:
        logger.error(
            f"MongoDB Change Stream watcher failed: {e}. Real-time updates are disabled.")

# --- Core Engine Management ---


async def _rebuild_search_engine_full():
    logger.info("Starting full engine rebuild...")
    global faiss_manager, hybrid_engine

    items = await fetch_and_extract_items()
    model_dim = get_model().get_sentence_embedding_dimension()

    # Fetch real user booking interactions
    from app.services.data_loader import fetch_collaborative_matrix
    real_matrix = await fetch_collaborative_matrix()

    async with data_lock:
        faiss_manager = FaissManager(dim=model_dim)
        if not items:
            faiss_manager.build_index([], None)
            hybrid_engine = HybridSearchEngine(faiss_manager, [])
        else:
            embeddings = create_blended_embeddings(items)
            faiss_manager.build_index(items, embeddings)
            hybrid_engine = HybridSearchEngine(faiss_manager, items)
            save_items(items)
            faiss_manager.save()
        
        # Initialize rating matrix in recommendation sandbox
        recommender.setup_collaborative_matrix(items if items else [], real_matrix=real_matrix)
        logger.info(f"Full engine rebuild complete with {len(items)} items.")

# --- FastAPI Lifespan ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup...")
    await connect_to_mongo()

    items = load_items()
    if items:
        logger.info("Loading persisted engine from disk...")
        model_dim = get_model().get_sentence_embedding_dimension()
        global faiss_manager, hybrid_engine
        faiss_manager = FaissManager(dim=model_dim)
        if faiss_manager.load():
            hybrid_engine = HybridSearchEngine(faiss_manager, items)
            # Initialize rating matrix in recommendation sandbox
            from app.services.data_loader import fetch_collaborative_matrix
            real_matrix = await fetch_collaborative_matrix()
            recommender.setup_collaborative_matrix(items, real_matrix=real_matrix)
            logger.info("Successfully loaded persisted search engine.")
        else:
            asyncio.create_task(_rebuild_search_engine_full())
    else:
        asyncio.create_task(_rebuild_search_engine_full())

    asyncio.create_task(watch_mongodb_changes())

    yield

    await close_mongo_connection()
    logger.info("Application shutdown.")

app = FastAPI(title="Smart Search API", version="2.0.0", lifespan=lifespan)

# --- API Endpoints ---
# --- CORS MIDDLEWARE CONFIGURATION ---
origins = [
    "https://anand-utsav.vercel.app",  # Your production front-end
    "http://localhost:5173",           # Your local development front-end (Vite default)
    "http://localhost:3000",           # Your local development front-end (Create React App default)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)


@app.get("/", tags=["API"])
def read_root():
    """Root Endpoint."""
    return {"message": "Anand Utsav ML Intelligence Backend is running successfully."}


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    if hybrid_engine is None or faiss_manager is None or faiss_manager.index is None:
        return HealthResponse(status="initializing")
    try:
        asyncio.run(hybrid_engine.search("test"))
        return HealthResponse(status="ok")
    except Exception as e:
        logger.error(f"Health check failed during test search: {e}")
        return HealthResponse(status="unhealthy")


@app.post("/refresh", response_model=RefreshResponse, tags=["Admin"])
async def trigger_refresh():
    await _rebuild_search_engine_full()
    return RefreshResponse(
        message="Full data refresh and index rebuild complete.",
        n_items=len(hybrid_engine.items) if hybrid_engine else 0
    )


@app.get("/db-status", tags=["Admin"])
async def db_status():
    from motor.motor_asyncio import AsyncIOMotorClient
    from app.config import settings
    try:
        client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=3000)
        await client.admin.command('ping')
        return {"status": "connected", "database": settings.DATABASE_NAME}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@app.get("/autocomplete", response_model=AutocompleteResponse, tags=["Search"])
def autocomplete(prefix: str):
    if hybrid_engine is None:
        raise HTTPException(
            status_code=503, detail="Search engine is not ready.")
    suggestions = hybrid_engine.get_autocomplete_suggestions(prefix)
    return AutocompleteResponse(suggestions=suggestions)


@app.get("/search", response_model=SearchResponse, tags=["Search"])
async def search(q: str, lat: Optional[float] = None, lng: Optional[float] = None, max_dist_km: float = 50.0):
    """Performs a simplified semantic search with optional location filtering."""
    if hybrid_engine is None:
        raise HTTPException(
            status_code=503, detail="Search engine is not ready.")

    cache_key = f"{q}_{lat}_{lng}_{max_dist_km}"
    if cache_key in search_cache:
        return search_cache[cache_key]

    results_dict = await hybrid_engine.search(q, lat=lat, lng=lng, max_dist_km=max_dist_km)
    response = SearchResponse(query=q, **results_dict)

    search_cache[cache_key] = response
    return response


# --- RECOMMENDATION SYSTEM ENDPOINTS ---

@app.get("/recommend/content-based", response_model=ContentRecommendationResponse, tags=["Recommender"])
async def recommend_content(service_id: str, top_n: int = Query(default=5, ge=1, le=20)):
    """Computes content-based recommendations using Sentence Transformer & FAISS."""
    if hybrid_engine is None or faiss_manager is None:
        raise HTTPException(status_code=503, detail="Search engine is not ready.")
    
    recs = await recommender.recommend_content_based(service_id, faiss_manager, hybrid_engine, top_n)
    return ContentRecommendationResponse(service_id=service_id, recommendations=recs)


@app.get("/recommend/collaborative/matrix", response_model=RatingMatrixResponse, tags=["Recommender"])
def get_cf_matrix():
    """Returns the current state of the sandbox ratings matrix."""
    return recommender.get_matrix_data()


@app.post("/recommend/collaborative/rate", tags=["Recommender"])
def cf_update_rating(req: UpdateRatingRequest):
    """Updates a single rating cell in the collaborative filtering matrix."""
    recommender.update_rating(req.user, req.item_id, req.rating)
    return {"message": "Rating updated successfully."}


@app.post("/recommend/collaborative/reset", tags=["Recommender"])
def cf_reset_matrix():
    """Resets the collaborative ratings matrix back to seeded defaults."""
    items = hybrid_engine.items if hybrid_engine else []
    recommender.reset_matrix(items)
    return {"message": "Rating matrix reset to seeded defaults."}


@app.get("/recommend/collaborative/user-based", response_model=CollaborativeRecommendationResponse, tags=["Recommender"])
def recommend_user_based(target_user: str, top_n: int = Query(default=5, ge=1, le=10)):
    """Predicts ratings and recommends items using User-Based Collaborative Filtering."""
    result = recommender.recommend_collaborative_user(target_user, top_n)
    return result


@app.get("/recommend/collaborative/item-based", response_model=CollaborativeRecommendationResponse, tags=["Recommender"])
def recommend_item_based(target_user: str, top_n: int = Query(default=5, ge=1, le=10)):
    """Predicts ratings and recommends items using Item-Based Collaborative Filtering."""
    result = recommender.recommend_collaborative_item(target_user, top_n)
    return result
