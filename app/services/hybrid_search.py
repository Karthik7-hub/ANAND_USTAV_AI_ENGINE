# FILE: app/services/hybrid_search.py
from app.config import settings
from app.models.faiss_manager import FaissManager
from app.services.encoder import encode_query
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class HybridSearchEngine:
    def __init__(self, faiss_manager: FaissManager, items: List[Dict[str, Any]]):
        self.fm = faiss_manager
        self.items = items
        self.item_map = {item['_id']: item for item in items}
<<<<<<< HEAD
        
        # Map MD5 hashed 64-bit int IDs from FAISS back to item objects
        from app.models.faiss_manager import id_to_int
        self.int_id_map = {id_to_int(item['_id']): item for item in items}
=======
>>>>>>> eaee55d441f248a9c8b8c1753f9a0c6e40ce403f

    def update_item_in_map(self, item: Dict[str, Any]):
        self.item_map[item['_id']] = item
        self.items = list(self.item_map.values())
<<<<<<< HEAD
        
        from app.models.faiss_manager import id_to_int
        self.int_id_map[id_to_int(item['_id'])] = item
=======
>>>>>>> eaee55d441f248a9c8b8c1753f9a0c6e40ce403f

    def remove_item_from_map(self, item_id: str):
        if item_id in self.item_map:
            del self.item_map[item_id]
            self.items = list(self.item_map.values())
<<<<<<< HEAD
            
            from app.models.faiss_manager import id_to_int
            hashed_id = id_to_int(item_id)
            if hashed_id in self.int_id_map:
                del self.int_id_map[hashed_id]
=======
>>>>>>> eaee55d441f248a9c8b8c1753f9a0c6e40ce403f

    def get_autocomplete_suggestions(self, prefix: str, limit: int = 10) -> List[str]:
        prefix_lower = prefix.lower()
        suggestions = {item.get("name") for item in self.items if item.get(
            "name", "").lower().startswith(prefix_lower)}
        return sorted(list(suggestions))[:limit]

<<<<<<< HEAD
    async def search(self, query: str, lat: float = None, lng: float = None, max_dist_km: float = 50.0) -> Dict[str, Any]:
=======
    async def search(self, query: str) -> Dict[str, Any]:
>>>>>>> eaee55d441f248a9c8b8c1753f9a0c6e40ce403f
        if not self.items:
            return {"categories": [], "services": []}

        query_embedding = encode_query(query)

        num_candidates = min(len(self.items), 200)
        distances, indices = self.fm.search(query_embedding, k=num_candidates)

        ranked_results = self._compute_scores(
            indices[0].tolist(), distances[0].tolist())
<<<<<<< HEAD
            
        # Optional Location Filtering
        if lat is not None and lng is not None:
            import math
            def haversine_distance(lat1, lon1, lat2, lon2):
                R = 6371.0
                dLat = math.radians(lat2 - lat1)
                dLon = math.radians(lon2 - lon1)
                a = math.sin(dLat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon / 2)**2
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                return R * c

            filtered_results = []
            for res in ranked_results:
                item = res['item']
                if item.get("isCategory"):
                    filtered_results.append(res)
                    continue
                    
                loc = item.get("location")
                if loc and loc.get("type") == "Point" and len(loc.get("coordinates", [])) == 2:
                    item_lng, item_lat = loc["coordinates"]
                    dist = haversine_distance(lat, lng, item_lat, item_lng)
                    if dist <= max_dist_km:
                        res['distance_km'] = round(dist, 2)
                        filtered_results.append(res)
                else:
                    # Keep items without location to not break everything, but rank them lower or just keep them
                    filtered_results.append(res)
            ranked_results = filtered_results

=======
>>>>>>> eaee55d441f248a9c8b8c1753f9a0c6e40ce403f
        top_categories, top_services = self._separate_results(ranked_results)

        return {"categories": top_categories, "services": top_services}

    def _separate_results(self, final_ranked_list):
        top_categories, top_services, seen_ids = [], [], set()
        for result in final_ranked_list:
            if len(top_categories) >= 5 and len(top_services) >= 50:
                break
            item = result['item']
            item_id = item.get('_id')
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            if item.get('isCategory') and len(top_categories) < 5:
                top_categories.append(result)
            elif not item.get('isCategory') and len(top_services) < 50:
                top_services.append(result)
        return top_categories, top_services

    def _compute_scores(self, indices: List[int], distances: List[float]) -> List[Dict[str, Any]]:
        results = []
        for score, idx in zip(distances, indices):
<<<<<<< HEAD
            if idx == -1:
                continue

            item_object = self.int_id_map.get(idx)
            if not item_object:
                continue

=======
            if idx == -1 or idx >= len(self.items):
                continue

            item_object = self.items[idx]
>>>>>>> eaee55d441f248a9c8b8c1753f9a0c6e40ce403f
            final_score = float(score)

            if item_object.get("isCategory"):
                final_score += settings.CATEGORY_BOOST

            results.append({"item": item_object, "score": final_score})

        results.sort(key=lambda x: x['score'], reverse=True)
        return results
