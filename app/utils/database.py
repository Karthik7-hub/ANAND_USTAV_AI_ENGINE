# FILE: app/utils/database.py
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class DBMotor:
    client: AsyncIOMotorClient = None


db = DBMotor()


async def connect_to_mongo():
    logger.info("Connecting to MongoDB...")
    try:
        db.client = AsyncIOMotorClient(
            settings.MONGODB_URL, serverSelectionTimeoutMS=5000)
        await db.client.admin.command('ping')
        logger.info("Successfully connected to MongoDB.")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}. Fallback local data loader will be used.")
        db.client = None


async def close_mongo_connection():
    if db.client:
        db.client.close()
        logger.info("MongoDB connection closed.")


def get_database():
    return db.client[settings.DATABASE_NAME] if db.client else None
