# FILE: app/services/data_loader.py
from app.config import settings
from app.utils.database import get_database
import logging
from bson import ObjectId
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def serialize_mongo_doc(doc):
    if isinstance(doc, dict):
        return {k: serialize_mongo_doc(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [serialize_mongo_doc(v) for v in doc]
    elif isinstance(doc, ObjectId):
        return str(doc)
    return doc


async def fetch_services_from_db() -> list:
    database = get_database()
    if database is None:
        return []

    services_collection = database[settings.COLLECTION_NAME]
    pipeline = [
        {"$lookup": {
            "from": "categories", "localField": "categories",
            "foreignField": "_id", "as": "category_info"
        }},
        {"$unwind": {"path": "$category_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "serviceproviders", "localField": "providers",
            "foreignField": "_id", "as": "provider_info"
        }},
        {"$unwind": {"path": "$provider_info", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 1, "name": 1, "description": 1, "priceInfo": 1, "avgRating": 1,
            "images": 1, "category": "$category_info", "updatedAt": 1,
            "location": "$provider_info.exactLocation",
            "popularityScore": "$provider_info.popularityScore"
        }}
    ]
    cursor = services_collection.aggregate(pipeline)
    return [serialize_mongo_doc(doc) async for doc in cursor]


async def fetch_and_extract_items() -> list:
    try:
        services = await fetch_services_from_db()
        valid_services = [s for s in services if s.get("name")]
        category_objects = [
            {
                "name": cat,
                "isCategory": True,
                "_id": cat.lower().replace(" ", "-").replace("&", "and")
            } for cat in settings.PREDEFINED_CATEGORIES
        ]
        combined_items = valid_services + category_objects
        logger.info(
            f"Fetched {len(valid_services)} services from DB, combined with {len(category_objects)} categories.")
        return combined_items
    except Exception:
        logger.exception("Failed to fetch and process services from MongoDB.")
        return []


async def fetch_one_service(service_id: str) -> Dict[str, Any] | None:
    db = get_database()
    if db is None:
        return None
    pipeline = [
        {"$match": {"_id": ObjectId(service_id)}},
        {"$lookup": {"from": "categories", "localField": "categories",
                     "foreignField": "_id", "as": "category_info"}},
        {"$unwind": {"path": "$category_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {"from": "serviceproviders", "localField": "providers",
                     "foreignField": "_id", "as": "provider_info"}},
        {"$unwind": {"path": "$provider_info", "preserveNullAndEmptyArrays": True}},
        {"$project": {"_id": 1, "name": 1, "description": 1, "priceInfo": 1,
                      "avgRating": 1, "images": 1, "category": "$category_info", "updatedAt": 1,
                      "location": "$provider_info.exactLocation",
                      "popularityScore": "$provider_info.popularityScore"}}
    ]
    result = await db[settings.COLLECTION_NAME].aggregate(pipeline).to_list(1)
    return serialize_mongo_doc(result[0]) if result else None


async def fetch_collaborative_matrix() -> Dict[str, Dict[str, float]]:
    """Builds a user-service rating matrix based on real Bookings."""
    db = get_database()
    if db is None:
        return {}
    
    pipeline = [
        {"$match": {"status": {"$in": ["pending", "accepted", "completed"]}}},
        {"$project": {"user": 1, "service": 1, "status": 1}}
    ]
    bookings = await db["bookings"].aggregate(pipeline).to_list(None)
    
    matrix = {}
    for b in bookings:
        user_id = str(b.get("user", ""))
        service_id = str(b.get("service", ""))
        status = b.get("status")
        
        if not user_id or not service_id:
            continue
            
        rating = 5.0 if status == "completed" else (4.5 if status == "accepted" else 4.0)
        
        if user_id not in matrix:
            matrix[user_id] = {}
            
        # Keep highest rating if multiple bookings exist
        existing_rating = matrix[user_id].get(service_id, 0.0)
        matrix[user_id][service_id] = max(existing_rating, rating)
        
    return matrix
