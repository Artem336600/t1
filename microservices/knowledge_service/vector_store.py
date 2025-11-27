"""
Vector Store for Knowledge Service
FAISS-based semantic search for concepts
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import json
import os

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("⚠️ FAISS not available, using numpy fallback")


@dataclass
class SearchResult:
    """Result of vector similarity search"""
    concept_id: str
    score: float
    name: str
    category: str


class VectorStore:
    """
    Vector store for concept embeddings.
    Uses FAISS for efficient similarity search.
    Falls back to numpy if FAISS not available.
    """
    
    def __init__(self, dimension: int = 1024, index_path: str = "data/concept_vectors.index"):
        self.dimension = dimension
        self.index_path = index_path
        self.id_map_path = index_path + ".ids.json"
        
        # Mapping from FAISS index position to concept ID
        self.id_to_idx: Dict[str, int] = {}
        self.idx_to_id: Dict[int, str] = {}
        self.concept_metadata: Dict[str, Dict] = {}  # concept_id -> {name, category}
        
        # Initialize index
        if FAISS_AVAILABLE:
            self.index = faiss.IndexFlatIP(dimension)  # Inner product (cosine after normalization)
        else:
            self.vectors = np.zeros((0, dimension), dtype=np.float32)
        
        self._load()
    
    def _load(self):
        """Load index and ID mappings from disk"""
        try:
            if os.path.exists(self.id_map_path):
                with open(self.id_map_path, 'r') as f:
                    data = json.load(f)
                    self.id_to_idx = data.get("id_to_idx", {})
                    self.idx_to_id = {int(k): v for k, v in data.get("idx_to_id", {}).items()}
                    self.concept_metadata = data.get("metadata", {})
            
            if FAISS_AVAILABLE and os.path.exists(self.index_path):
                self.index = faiss.read_index(self.index_path)
                print(f"Loaded FAISS index with {self.index.ntotal} vectors")
            elif not FAISS_AVAILABLE and os.path.exists(self.index_path + ".npy"):
                self.vectors = np.load(self.index_path + ".npy")
                print(f"Loaded numpy vectors: {self.vectors.shape}")
        except Exception as e:
            print(f"Failed to load vector store: {e}")
    
    def _save(self):
        """Save index and ID mappings to disk"""
        os.makedirs(os.path.dirname(self.index_path) or ".", exist_ok=True)
        
        # Save ID mappings
        with open(self.id_map_path, 'w') as f:
            json.dump({
                "id_to_idx": self.id_to_idx,
                "idx_to_id": {str(k): v for k, v in self.idx_to_id.items()},
                "metadata": self.concept_metadata
            }, f)
        
        # Save index
        if FAISS_AVAILABLE:
            faiss.write_index(self.index, self.index_path)
        else:
            np.save(self.index_path + ".npy", self.vectors)
    
    def _normalize(self, vector: np.ndarray) -> np.ndarray:
        """L2 normalize vector for cosine similarity"""
        norm = np.linalg.norm(vector)
        if norm > 0:
            return vector / norm
        return vector
    
    def add(
        self, 
        concept_id: str, 
        embedding: List[float],
        name: str = "",
        category: str = ""
    ):
        """Add or update concept embedding"""
        vector = np.array(embedding, dtype=np.float32).reshape(1, -1)
        vector = self._normalize(vector)
        
        if concept_id in self.id_to_idx:
            # Update existing - need to rebuild index (FAISS limitation)
            idx = self.id_to_idx[concept_id]
            if FAISS_AVAILABLE:
                # FAISS doesn't support updates, so we just add and track latest
                pass
            else:
                self.vectors[idx] = vector
        else:
            # Add new
            if FAISS_AVAILABLE:
                idx = self.index.ntotal
                self.index.add(vector)
            else:
                idx = len(self.vectors)
                self.vectors = np.vstack([self.vectors, vector]) if len(self.vectors) > 0 else vector
            
            self.id_to_idx[concept_id] = idx
            self.idx_to_id[idx] = concept_id
        
        # Store metadata
        self.concept_metadata[concept_id] = {"name": name, "category": category}
        self._save()
    
    def search(
        self, 
        query_embedding: List[float], 
        top_k: int = 5,
        threshold: float = 0.5
    ) -> List[SearchResult]:
        """
        Search for similar concepts.
        
        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            threshold: Minimum similarity score (0-1)
        
        Returns:
            List of SearchResult sorted by score descending
        """
        if len(self.id_to_idx) == 0:
            return []
        
        query = np.array(query_embedding, dtype=np.float32).reshape(1, -1)
        query = self._normalize(query)
        
        if FAISS_AVAILABLE:
            scores, indices = self.index.search(query, min(top_k * 2, self.index.ntotal))
            scores = scores[0]
            indices = indices[0]
        else:
            # Numpy fallback - cosine similarity
            if len(self.vectors) == 0:
                return []
            scores = np.dot(self.vectors, query.T).flatten()
            indices = np.argsort(scores)[::-1][:top_k * 2]
            scores = scores[indices]
        
        results = []
        for score, idx in zip(scores, indices):
            if idx < 0 or score < threshold:
                continue
            
            concept_id = self.idx_to_id.get(int(idx))
            if not concept_id:
                continue
            
            metadata = self.concept_metadata.get(concept_id, {})
            results.append(SearchResult(
                concept_id=concept_id,
                score=float(score),
                name=metadata.get("name", concept_id),
                category=metadata.get("category", "")
            ))
            
            if len(results) >= top_k:
                break
        
        return results
    
    def get_embedding(self, concept_id: str) -> Optional[List[float]]:
        """Get embedding for a concept"""
        if concept_id not in self.id_to_idx:
            return None
        
        idx = self.id_to_idx[concept_id]
        
        if FAISS_AVAILABLE:
            vector = self.index.reconstruct(idx)
        else:
            vector = self.vectors[idx]
        
        return vector.tolist()
    
    def remove(self, concept_id: str):
        """Remove concept from index (marks as deleted)"""
        if concept_id in self.id_to_idx:
            # Note: FAISS doesn't support deletion, so we just remove from mappings
            idx = self.id_to_idx.pop(concept_id)
            self.idx_to_id.pop(idx, None)
            self.concept_metadata.pop(concept_id, None)
            self._save()
    
    def rebuild(self, concepts: Dict[str, Tuple[List[float], str, str]]):
        """
        Rebuild entire index from scratch.
        
        Args:
            concepts: Dict of concept_id -> (embedding, name, category)
        """
        # Reset
        self.id_to_idx = {}
        self.idx_to_id = {}
        self.concept_metadata = {}
        
        if FAISS_AVAILABLE:
            self.index = faiss.IndexFlatIP(self.dimension)
        else:
            self.vectors = np.zeros((0, self.dimension), dtype=np.float32)
        
        # Add all concepts
        for concept_id, (embedding, name, category) in concepts.items():
            self.add(concept_id, embedding, name, category)
        
        print(f"Rebuilt index with {len(self.id_to_idx)} concepts")
    
    @property
    def size(self) -> int:
        """Number of vectors in index"""
        if FAISS_AVAILABLE:
            return self.index.ntotal
        return len(self.vectors)


class EmbeddingService:
    """Service for generating embeddings using LLM API"""
    
    def __init__(self, client, model: str = "bge-m3"):
        self.client = client
        self.model = model
        self._cache: Dict[str, List[float]] = {}
    
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for text"""
        # Check cache
        if text in self._cache:
            return self._cache[text]
        
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text
            )
            embedding = response.data[0].embedding
            
            # Cache result
            self._cache[text] = embedding
            
            return embedding
        except Exception as e:
            print(f"Embedding error: {e}")
            # Return zero vector as fallback
            return [0.0] * 1024
    
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts"""
        # Check which need to be computed
        to_compute = [t for t in texts if t not in self._cache]
        
        if to_compute:
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=to_compute
                )
                for text, data in zip(to_compute, response.data):
                    self._cache[text] = data.embedding
            except Exception as e:
                print(f"Batch embedding error: {e}")
        
        return [self._cache.get(t, [0.0] * 1024) for t in texts]
