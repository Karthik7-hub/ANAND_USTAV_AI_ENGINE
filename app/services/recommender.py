# FILE: app/services/recommender.py
import numpy as np
import logging
from typing import List, Dict, Any, Tuple
from app.services.encoder import create_blended_embeddings
from app.utils.locks import data_lock

logger = logging.getLogger(__name__)

class RecommenderEngine:
    def __init__(self):
        self.users: List[str] = []
        self.item_pool: List[Dict[str, Any]] = []
        self.ratings_matrix: Dict[str, Dict[str, float]] = {}
        
    def setup_collaborative_matrix(self, active_services: List[Dict[str, Any]], real_matrix: Dict[str, Dict[str, float]] = None):
        """Initializes the collaborative user-item rating matrix using real services and bookings."""
        valid_services = [s for s in active_services if not s.get("isCategory") and s.get("_id")]
        self.item_pool = valid_services
        self.ratings_matrix = real_matrix if real_matrix is not None else {}
        self.users = list(self.ratings_matrix.keys())
        logger.info(f"Loaded collaborative matrix with {len(self.users)} users and {len(self.item_pool)} items.")

    def get_matrix_data(self) -> Dict[str, Any]:
        """Formats the rating matrix for display in the frontend."""
        return {
            "users": self.users,
            "items": [{"_id": item["_id"], "name": item["name"]} for item in self.item_pool],
            "ratings": self.ratings_matrix
        }

    def update_rating(self, user: str, item_id: str, rating: float):
        """Updates a single rating in the matrix."""
        if user not in self.ratings_matrix:
            self.ratings_matrix[user] = {}
            if user not in self.users:
                self.users.append(user)
        self.ratings_matrix[user][item_id] = max(0.0, min(5.0, rating))
        logger.info(f"Updated rating: User={user}, Item={item_id}, Rating={rating}")

    def reset_matrix(self, active_services: List[Dict[str, Any]]):
        """Resets the rating matrix using real services."""
        self.setup_collaborative_matrix(active_services)

    # --- CONTENT-BASED FILTERING ---
    async def recommend_content_based(self, service_id: str, faiss_manager, hybrid_engine, top_n: int = 5) -> List[Dict[str, Any]]:
        """
        Recommends items similar to the given service_id using item features (Sentence Transformer Embeddings + FAISS).
        """
        if not hybrid_engine or not faiss_manager:
            return []
            
        # 1. Find the target service in the system
        target_item = hybrid_engine.item_map.get(service_id)
        if not target_item:
            logger.warning(f"Content-Based: Service ID {service_id} not found in engine. Falling back to category-based matching.")
            results = []
            for item in hybrid_engine.items:
                if item.get("isCategory") or item.get("_id") == service_id:
                    continue
                avg_rating = float(item.get("avgRating", 0.0))
                popularity = float(item.get("popularityScore", 0.0))
                score = (avg_rating * 0.7) + (popularity * 0.3)
                results.append({
                    "item": item,
                    "score": float(round(score, 2)),
                    "matchPercentage": float(round(avg_rating * 20.0, 1))
                })
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_n]
            
        # 2. Re-compute blended embedding of the single target item to represent its features
        target_embedding = create_blended_embeddings([target_item])
        
        # 3. Query FAISS index for top_n + 1 items (since the item itself will match)
        distances, indices = faiss_manager.search(target_embedding, k=min(len(hybrid_engine.items), top_n + 10))
        
        results = []
        seen_ids = {service_id} # Exclude the query item itself
        
        for dist, idx in zip(distances[0].tolist(), indices[0].tolist()):
            if idx == -1:
                continue
                
            item = hybrid_engine.int_id_map.get(idx)
            if not item:
                continue
            # Exclude categories and the item itself
            if item.get("isCategory") or item.get("_id") in seen_ids:
                continue
                
            seen_ids.add(item["_id"])
            
            # Map score to a beautiful percentage 0-100%
            # Cosine similarity for normalized vectors is in range [-1, 1], typically [0, 1] for positive matches
            match_percentage = round(float(dist) * 100, 1)
            results.append({
                "item": item,
                "score": float(dist),
                "matchPercentage": max(0.0, min(100.0, match_percentage))
            })
            
            if len(results) >= top_n:
                break
                
        return results

    # --- COLLABORATIVE FILTERING ---
    
    def _get_user_average(self, user: str) -> float:
        ratings = self.ratings_matrix.get(user, {})
        rated = [r for r in ratings.values() if r > 0.0]
        return np.mean(rated) if rated else 0.0

    def _compute_user_similarities(self, target_user: str) -> List[Dict[str, Any]]:
        """Computes Pearson correlation/mean-centered Cosine similarity between target_user and all other users."""
        similarities = []
        
        target_ratings = self.ratings_matrix.get(target_user, {})
        target_avg = self._get_user_average(target_user)
        
        # Vector of target's mean-centered ratings
        target_centered = {}
        for item_id, rating in target_ratings.items():
            if rating > 0.0:
                target_centered[item_id] = rating - target_avg
                
        for other_user in self.users:
            if other_user == target_user:
                continue
                
            other_ratings = self.ratings_matrix.get(other_user, {})
            other_avg = self._get_user_average(other_user)
            
            other_centered = {}
            for item_id, rating in other_ratings.items():
                if rating > 0.0:
                    other_centered[item_id] = rating - other_avg
            
            # Find common rated items
            common_items = set(target_centered.keys()).intersection(set(other_centered.keys()))
            
            if not common_items:
                similarity = 0.0
            else:
                # Compute Cosine similarity on mean-centered ratings (Pearson)
                numerator = sum(target_centered[i] * other_centered[i] for i in common_items)
                target_denom = sum(target_centered[i] ** 2 for i in target_centered.keys())
                other_denom = sum(other_centered[i] ** 2 for i in other_centered.keys())
                
                denom = np.sqrt(target_denom) * np.sqrt(other_denom)
                similarity = numerator / denom if denom != 0.0 else 0.0
                
            similarities.append({
                "user": other_user,
                "similarity": float(round(similarity, 3))
            })
            
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        return similarities

    def recommend_collaborative_user(self, target_user: str, top_n: int = 5) -> Dict[str, Any]:
        """
        Calculates User-Based Collaborative Filtering recommendations.
        Formula: predicted_rating = avg(target) + sum(sim(target, v) * (R_v_i - avg(v))) / sum(|sim|)
        """
        if target_user not in self.ratings_matrix:
            # Cold-Start Fallback: Recommend highly rated services dynamically
            recommendations = []
            for item in self.item_pool:
                avg_rating = float(item.get("avgRating", 0.0))
                popularity = float(item.get("popularityScore", 0.0))
                score = (avg_rating * 0.7) + (popularity * 0.3)
                recommendations.append({
                    "item": item,
                    "score": float(round(score, 2)),
                    "predictedRating": float(round(avg_rating, 1))
                })
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return {
                "user": target_user,
                "method": "user-based (cold-start fallback)",
                "recommendations": recommendations[:top_n],
                "similarUsers": []
            }
            
        # 1. Compute similarity to all other users
        similarities_list = self._compute_user_similarities(target_user)
        sim_map = {x["user"]: x["similarity"] for x in similarities_list}
        
        target_ratings = self.ratings_matrix.get(target_user, {})
        target_avg = self._get_user_average(target_user)
        
        # 2. Find items the target user hasn't rated yet
        unrated_items = [item for item in self.item_pool if target_ratings.get(item["_id"], 0.0) == 0.0]
        
        recommendations = []
        
        for item in unrated_items:
            item_id = item["_id"]
            
            # Weighted average rating prediction
            weighted_sum = 0.0
            sim_sum = 0.0
            
            for other_user in self.users:
                if other_user == target_user:
                    continue
                    
                other_rating = self.ratings_matrix[other_user].get(item_id, 0.0)
                # Only consider users who actually rated the item
                if other_rating > 0.0:
                    sim = sim_map[other_user]
                    # We only consider similar users (similarity > 0) to avoid negative bias complications in small sets
                    if sim > 0:
                        other_avg = self._get_user_average(other_user)
                        weighted_sum += sim * (other_rating - other_avg)
                        sim_sum += abs(sim)
            
            if sim_sum > 0:
                predicted_rating = target_avg + (weighted_sum / sim_sum)
            else:
                # If no user similarity matches, blend target user's avg rating with item's own high-fidelity avg rating
                item_avg = float(item.get("avgRating", 3.0))
                predicted_rating = (target_avg * 0.3) + (item_avg * 0.7) if target_avg > 0.0 else item_avg
                
            predicted_rating = max(1.0, min(5.0, predicted_rating))
            
            recommendations.append({
                "item": item,
                "score": float(round(predicted_rating, 2)),
                "predictedRating": float(round(predicted_rating, 1))
            })
            
        recommendations.sort(key=lambda x: x["predictedRating"], reverse=True)
        
        return {
            "user": target_user,
            "method": "user-based",
            "recommendations": recommendations[:top_n],
            "similarUsers": similarities_list
        }

    def _compute_item_similarities(self) -> Dict[str, Dict[str, float]]:
        """Computes Item-to-Item cosine similarity matrix based on user ratings."""
        item_ids = [item["_id"] for item in self.item_pool]
        similarities = {id1: {id2: 0.0 for id2 in item_ids} for id1 in item_ids}
        
        # Calculate mean-centered rating vector for each item
        item_centered = {}
        for item_id in item_ids:
            ratings = []
            for user in self.users:
                r = self.ratings_matrix[user].get(item_id, 0.0)
                if r > 0.0:
                    ratings.append(r)
            avg = np.mean(ratings) if ratings else 0.0
            
            centered = {}
            for user in self.users:
                r = self.ratings_matrix[user].get(item_id, 0.0)
                if r > 0.0:
                    centered[user] = r - avg
            item_centered[item_id] = centered

        for id1 in item_ids:
            for id2 in item_ids:
                if id1 == id2:
                    similarities[id1][id2] = 1.0
                    continue
                    
                v1 = item_centered[id1]
                v2 = item_centered[id2]
                
                common_users = set(v1.keys()).intersection(set(v2.keys()))
                
                if not common_users:
                    sim = 0.0
                else:
                    numerator = sum(v1[u] * v2[u] for u in common_users)
                    denom_v1 = sum(val**2 for val in v1.values())
                    denom_v2 = sum(val**2 for val in v2.values())
                    
                    denom = np.sqrt(denom_v1) * np.sqrt(denom_v2)
                    sim = numerator / denom if denom != 0.0 else 0.0
                    
                similarities[id1][id2] = float(round(sim, 3))
                
        return similarities

    def recommend_collaborative_item(self, target_user: str, top_n: int = 5) -> Dict[str, Any]:
        """
        Calculates Item-Based Collaborative Filtering recommendations.
        Formula: predicted_rating = sum(sim(i, j) * R_u_j) / sum(|sim(i, j)|)
        """
        if target_user not in self.ratings_matrix:
            # Cold-Start Fallback: Recommend highly rated services dynamically
            recommendations = []
            for item in self.item_pool:
                avg_rating = float(item.get("avgRating", 0.0))
                popularity = float(item.get("popularityScore", 0.0))
                score = (avg_rating * 0.7) + (popularity * 0.3)
                recommendations.append({
                    "item": item,
                    "score": float(round(score, 2)),
                    "predictedRating": float(round(avg_rating, 1))
                })
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return {
                "user": target_user,
                "method": "item-based (cold-start fallback)",
                "recommendations": recommendations[:top_n],
                "itemSimilarities": {}
            }
            
        # 1. Compute all item similarities
        item_similarities = self._compute_item_similarities()
        
        target_ratings = self.ratings_matrix.get(target_user, {})
        rated_items = {k: v for k, v in target_ratings.items() if v > 0.0}
        target_avg = self._get_user_average(target_user)
        
        # 2. Find items target user hasn't rated yet
        unrated_items = [item for item in self.item_pool if target_ratings.get(item["_id"], 0.0) == 0.0]
        
        recommendations = []
        
        for item in unrated_items:
            item_id = item["_id"]
            
            weighted_sum = 0.0
            sim_sum = 0.0
            
            for rated_id, rating in rated_items.items():
                sim = item_similarities[item_id].get(rated_id, 0.0)
                # Only use positive similarities to predict
                if sim > 0:
                    weighted_sum += sim * rating
                    sim_sum += abs(sim)
                    
            if sim_sum > 0:
                predicted_rating = weighted_sum / sim_sum
            else:
                # If no item similarity matches, blend target user's avg rating with item's own high-fidelity avg rating
                item_avg = float(item.get("avgRating", 3.0))
                predicted_rating = (target_avg * 0.3) + (item_avg * 0.7) if target_avg > 0.0 else item_avg
                    
            predicted_rating = max(1.0, min(5.0, predicted_rating))
            recommendations.append({
                "item": item,
                "score": float(round(predicted_rating, 2)),
                "predictedRating": float(round(predicted_rating, 1))
            })
            
        recommendations.sort(key=lambda x: x["predictedRating"], reverse=True)
        
        return {
            "user": target_user,
            "method": "item-based",
            "recommendations": recommendations[:top_n],
            "itemSimilarities": item_similarities
        }

# Global singleton recommender instance
recommender = RecommenderEngine()
