from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class SearchResultItem(BaseModel):
    item: Dict[str, Any]
    score: float


class SearchResponse(BaseModel):
    query: str
    categories: List[SearchResultItem]
    services: List[SearchResultItem]


class AutocompleteResponse(BaseModel):
    suggestions: List[str]


class RefreshResponse(BaseModel):
    message: str
    n_items: int


class StatusResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str


class RecommendationItem(BaseModel):
    item: Dict[str, Any]
    score: float
    matchPercentage: Optional[float] = None
    predictedRating: Optional[float] = None


class ContentRecommendationResponse(BaseModel):
    service_id: str
    recommendations: List[RecommendationItem]


class UserSimilarity(BaseModel):
    user: str
    similarity: float


class CollaborativeRecommendationResponse(BaseModel):
    user: str
    method: str
    recommendations: List[RecommendationItem]
    similarUsers: Optional[List[UserSimilarity]] = None


class RatingMatrixResponse(BaseModel):
    users: List[str]
    items: List[Dict[str, Any]]
    ratings: Dict[str, Dict[str, float]]


class UpdateRatingRequest(BaseModel):
    user: str
    item_id: str
    rating: float

