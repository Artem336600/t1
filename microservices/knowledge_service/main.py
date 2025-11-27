"""
Knowledge Graph Service
Self-learning knowledge base with vector embeddings and semantic search
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from openai import OpenAI
from datetime import datetime
import json
import os
import numpy as np

from vector_store import VectorStore, EmbeddingService, SearchResult

app = FastAPI(
    title="Knowledge Graph Service",
    description="Self-learning knowledge base with vector embeddings",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config - use centralized LLM config
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

try:
    from llm_config import Models, get_client, API_KEY, BASE_URL
except ImportError:
    API_KEY = os.getenv("LLM_API_KEY", "sk-SSWP5NVJpHecmOFI_yxp7Q")
    BASE_URL = os.getenv("LLM_BASE_URL", "https://llm.t1v.scibox.tech/v1")
    class Models:
        CHAT = "qwen3-32b-awq"
        CODE = "qwen3-coder-30b-a3b-instruct-fp8"
        EMBEDDING = "bge-m3"
    def get_client(api_key=None, base_url=None):
        return OpenAI(api_key=api_key or API_KEY, base_url=base_url or BASE_URL)

DATA_FILE = "data/knowledge_graph.json"
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.65"))

client = get_client()

# Initialize vector store and embedding service
vector_store = VectorStore(dimension=1024, index_path="data/concept_vectors.index")
embedding_service = EmbeddingService(client, model=Models.EMBEDDING)


# ============== Models ==============

class Concept(BaseModel):
    """A concept/topic in the knowledge graph"""
    id: str
    name: str
    description: str
    category: str  # algorithm, data_structure, pattern, language_feature, etc.
    difficulty: float = Field(ge=0, le=1)  # 0-1 scale
    prerequisites: List[str] = []  # concept IDs
    related: List[str] = []  # related concept IDs
    keywords: List[str] = []
    embedding: Optional[List[float]] = None
    examples: List[str] = []  # example problem titles
    created_at: str = ""
    usage_count: int = 0
    success_rate: float = 0.5  # how often users solve tasks with this concept


class ConceptCreate(BaseModel):
    name: str
    description: str = ""
    category: str = "general"


class TaskFeedback(BaseModel):
    concept_ids: List[str]
    solved: bool
    time_spent: int = 0  # seconds
    hints_used: int = 0


class QueryAnalysis(BaseModel):
    query: str
    detected_concepts: List[str] = []
    new_concepts: List[Dict] = []
    suggested_difficulty: float = 0.5
    learning_path: List[str] = []


# ============== Knowledge Graph ==============

class KnowledgeGraph:
    def __init__(self):
        self.concepts: Dict[str, Concept] = {}
        self.load()
    
    def load(self):
        os.makedirs("data", exist_ok=True)
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for cid, cdata in data.get("concepts", {}).items():
                        self.concepts[cid] = Concept(**cdata)
                print(f"Loaded {len(self.concepts)} concepts")
            except Exception as e:
                print(f"Failed to load knowledge graph: {e}")
                self._init_base_concepts()
        else:
            self._init_base_concepts()
    
    def save(self):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "concepts": {cid: c.model_dump() for cid, c in self.concepts.items()},
                "updated_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    
    def _init_base_concepts(self):
        """Initialize with seed concepts that will grow"""
        base = [
            # Fundamental
            {"id": "arrays", "name": "Массивы", "category": "data_structure", "difficulty": 0.1,
             "keywords": ["array", "массив", "список", "list", "индекс"], "prerequisites": []},
            {"id": "strings", "name": "Строки", "category": "data_structure", "difficulty": 0.1,
             "keywords": ["string", "строка", "символ", "char"], "prerequisites": []},
            {"id": "loops", "name": "Циклы", "category": "language_feature", "difficulty": 0.1,
             "keywords": ["loop", "цикл", "for", "while", "итерация"], "prerequisites": []},
            
            # Basic algorithms
            {"id": "two_pointers", "name": "Два указателя", "category": "pattern", "difficulty": 0.3,
             "keywords": ["two pointers", "два указателя", "left right"], "prerequisites": ["arrays"]},
            {"id": "sliding_window", "name": "Скользящее окно", "category": "pattern", "difficulty": 0.4,
             "keywords": ["sliding window", "окно", "подмассив", "subarray"], "prerequisites": ["arrays", "two_pointers"]},
            {"id": "binary_search", "name": "Бинарный поиск", "category": "algorithm", "difficulty": 0.3,
             "keywords": ["binary search", "бинарный поиск", "bisect", "отсортированный"], "prerequisites": ["arrays"]},
            {"id": "hash_table", "name": "Хеш-таблица", "category": "data_structure", "difficulty": 0.3,
             "keywords": ["hash", "хеш", "dict", "словарь", "map", "set"], "prerequisites": []},
            
            # Intermediate
            {"id": "recursion", "name": "Рекурсия", "category": "pattern", "difficulty": 0.4,
             "keywords": ["recursion", "рекурсия", "recursive", "base case"], "prerequisites": []},
            {"id": "sorting", "name": "Сортировка", "category": "algorithm", "difficulty": 0.3,
             "keywords": ["sort", "сортировка", "упорядочить", "quicksort", "mergesort"], "prerequisites": ["arrays"]},
            {"id": "linked_list", "name": "Связный список", "category": "data_structure", "difficulty": 0.4,
             "keywords": ["linked list", "связный список", "node", "next", "prev"], "prerequisites": []},
            {"id": "stack", "name": "Стек", "category": "data_structure", "difficulty": 0.3,
             "keywords": ["stack", "стек", "lifo", "push", "pop"], "prerequisites": []},
            {"id": "queue", "name": "Очередь", "category": "data_structure", "difficulty": 0.3,
             "keywords": ["queue", "очередь", "fifo", "deque"], "prerequisites": []},
            
            # Trees & Graphs
            {"id": "binary_tree", "name": "Бинарное дерево", "category": "data_structure", "difficulty": 0.5,
             "keywords": ["tree", "дерево", "binary tree", "root", "leaf", "node"], "prerequisites": ["recursion"]},
            {"id": "bst", "name": "BST", "category": "data_structure", "difficulty": 0.5,
             "keywords": ["bst", "binary search tree", "дерево поиска"], "prerequisites": ["binary_tree", "binary_search"]},
            {"id": "dfs", "name": "DFS", "category": "algorithm", "difficulty": 0.5,
             "keywords": ["dfs", "depth first", "обход в глубину", "preorder", "inorder", "postorder"], 
             "prerequisites": ["binary_tree", "recursion", "stack"]},
            {"id": "bfs", "name": "BFS", "category": "algorithm", "difficulty": 0.5,
             "keywords": ["bfs", "breadth first", "обход в ширину", "level order"], 
             "prerequisites": ["binary_tree", "queue"]},
            {"id": "graph", "name": "Графы", "category": "data_structure", "difficulty": 0.6,
             "keywords": ["graph", "граф", "vertex", "edge", "вершина", "ребро", "adjacency"], 
             "prerequisites": ["dfs", "bfs"]},
            
            # Advanced
            {"id": "dp", "name": "Динамическое программирование", "category": "pattern", "difficulty": 0.7,
             "keywords": ["dp", "dynamic programming", "динамическое", "memoization", "табуляция"], 
             "prerequisites": ["recursion", "arrays"]},
            {"id": "greedy", "name": "Жадные алгоритмы", "category": "pattern", "difficulty": 0.5,
             "keywords": ["greedy", "жадный", "оптимальный выбор"], "prerequisites": ["sorting"]},
            {"id": "backtracking", "name": "Перебор с возвратом", "category": "pattern", "difficulty": 0.6,
             "keywords": ["backtracking", "перебор", "комбинации", "permutations"], "prerequisites": ["recursion", "dfs"]},
            {"id": "heap", "name": "Куча", "category": "data_structure", "difficulty": 0.5,
             "keywords": ["heap", "куча", "priority queue", "heapq", "min heap", "max heap"], "prerequisites": ["binary_tree"]},
            {"id": "trie", "name": "Префиксное дерево", "category": "data_structure", "difficulty": 0.6,
             "keywords": ["trie", "prefix tree", "префиксное", "автодополнение"], "prerequisites": ["binary_tree", "strings"]},
        ]
        
        for c in base:
            concept = Concept(
                id=c["id"],
                name=c["name"],
                description=f"Концепция: {c['name']}",
                category=c["category"],
                difficulty=c["difficulty"],
                keywords=c["keywords"],
                prerequisites=c.get("prerequisites", []),
                created_at=datetime.now().isoformat()
            )
            self.concepts[c["id"]] = concept
        
        # Set related concepts
        self._compute_related()
        self.save()
        print(f"Initialized {len(self.concepts)} base concepts")
    
    def _compute_related(self):
        """Compute related concepts based on prerequisites and categories"""
        for cid, concept in self.concepts.items():
            related = set()
            # Concepts that have this as prerequisite
            for other_id, other in self.concepts.items():
                if cid in other.prerequisites:
                    related.add(other_id)
            # Same category
            for other_id, other in self.concepts.items():
                if other.category == concept.category and other_id != cid:
                    related.add(other_id)
            concept.related = list(related)[:5]
    
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for text using embedding service"""
        return embedding_service.get_embedding(text)
    
    def index_concept(self, concept: Concept):
        """Add concept to vector store"""
        # Create rich text for embedding
        text = f"{concept.name}. {concept.description}. Keywords: {', '.join(concept.keywords)}"
        embedding = self.get_embedding(text)
        
        if embedding and len(embedding) > 0:
            vector_store.add(
                concept_id=concept.id,
                embedding=embedding,
                name=concept.name,
                category=concept.category
            )
            concept.embedding = embedding
    
    def reindex_all(self):
        """Reindex all concepts in vector store"""
        print("Reindexing all concepts...")
        for concept in self.concepts.values():
            self.index_concept(concept)
        print(f"Indexed {vector_store.size} concepts")
    
    def find_concepts(self, query: str, top_k: int = 5) -> List[tuple]:
        """
        Find relevant concepts using hybrid search:
        1. Vector similarity (semantic)
        2. Keyword matching (exact)
        """
        query_lower = query.lower()
        scores: Dict[str, float] = {}
        
        # 1. Vector similarity search
        query_embedding = self.get_embedding(query)
        if query_embedding:
            vector_results = vector_store.search(
                query_embedding, 
                top_k=top_k * 2,
                threshold=SIMILARITY_THRESHOLD
            )
            for result in vector_results:
                scores[result.concept_id] = result.score * 0.6  # 60% weight for semantic
        
        # 2. Keyword matching (boost)
        for cid, concept in self.concepts.items():
            keyword_score = 0
            
            # Exact keyword match
            for kw in concept.keywords:
                if kw.lower() in query_lower:
                    keyword_score += 0.15
            
            # Name match
            if concept.name.lower() in query_lower or concept.id in query_lower:
                keyword_score += 0.25
            
            if keyword_score > 0:
                scores[cid] = scores.get(cid, 0) + keyword_score
        
        # Sort by combined score
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:top_k]
    
    def discover_new_concept(self, query: str, context: str = "") -> Optional[Dict]:
        """Use LLM to discover if query contains a new concept"""
        existing = ", ".join([c.name for c in self.concepts.values()])
        
        prompt = f"""/no_think Проанализируй запрос и определи, содержит ли он новую концепцию/тему, которой нет в списке.

Существующие концепции: {existing}

Запрос: {query}
Контекст: {context}

Если найдена НОВАЯ концепция, верни JSON:
{{"found": true, "concept": {{"name": "...", "category": "algorithm|data_structure|pattern|language_feature|problem_type", "description": "...", "keywords": ["..."], "prerequisites": ["id существующей концепции"], "difficulty": 0.0-1.0}}}}

Если концепция уже существует или это не концепция:
{{"found": false, "reason": "..."}}"""

        try:
            response = client.chat.completions.create(
                model=Models.CHAT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)
            
            if result.get("found") and result.get("concept"):
                return result["concept"]
        except Exception as e:
            print(f"Concept discovery error: {e}")
        
        return None
    
    def add_concept(self, concept_data: Dict) -> Concept:
        """Add new concept to the graph"""
        # Generate ID
        cid = concept_data["name"].lower().replace(" ", "_").replace("-", "_")
        cid = ''.join(c for c in cid if c.isalnum() or c == '_')
        
        # Ensure unique ID
        base_id = cid
        counter = 1
        while cid in self.concepts:
            cid = f"{base_id}_{counter}"
            counter += 1
        
        # Create concept
        concept = Concept(
            id=cid,
            name=concept_data["name"],
            description=concept_data.get("description", ""),
            category=concept_data.get("category", "general"),
            difficulty=concept_data.get("difficulty", 0.5),
            keywords=concept_data.get("keywords", []),
            prerequisites=concept_data.get("prerequisites", []),
            created_at=datetime.now().isoformat()
        )
        
        # Get embedding
        emb_text = f"{concept.name} {concept.description} {' '.join(concept.keywords)}"
        concept.embedding = self.get_embedding(emb_text)
        
        self.concepts[cid] = concept
        self._compute_related()
        self.save()
        
        return concept
    
    def update_from_feedback(self, feedback: TaskFeedback):
        """Update concept stats from user feedback"""
        for cid in feedback.concept_ids:
            if cid in self.concepts:
                c = self.concepts[cid]
                c.usage_count += 1
                # Update success rate with exponential moving average
                alpha = 0.1
                c.success_rate = alpha * (1.0 if feedback.solved else 0.0) + (1 - alpha) * c.success_rate
        self.save()
    
    def get_learning_path(self, target_concept_id: str, user_known: List[str] = []) -> List[str]:
        """Get optimal learning path to target concept"""
        if target_concept_id not in self.concepts:
            return []
        
        path = []
        visited = set(user_known)
        
        def collect_prerequisites(cid: str):
            if cid in visited:
                return
            concept = self.concepts.get(cid)
            if not concept:
                return
            
            for prereq in concept.prerequisites:
                collect_prerequisites(prereq)
            
            if cid not in visited:
                path.append(cid)
                visited.add(cid)
        
        collect_prerequisites(target_concept_id)
        return path


# Global instance
kg = KnowledgeGraph()


# ============== API Endpoints ==============

@app.get("/health")
async def health():
    return {
        "status": "ok", 
        "service": "knowledge", 
        "concepts_count": len(kg.concepts),
        "vector_index_size": vector_store.size,
        "models": {
            "embedding": Models.EMBEDDING,
            "chat": Models.CHAT
        }
    }


@app.post("/reindex")
async def reindex_concepts():
    """Rebuild vector index for all concepts"""
    kg.reindex_all()
    return {
        "success": True,
        "indexed": vector_store.size
    }


@app.post("/search")
async def semantic_search(query: str, top_k: int = 5, threshold: float = 0.5):
    """Pure semantic search using vector embeddings"""
    query_embedding = embedding_service.get_embedding(query)
    results = vector_store.search(query_embedding, top_k=top_k, threshold=threshold)
    
    return {
        "query": query,
        "results": [
            {
                "concept_id": r.concept_id,
                "name": r.name,
                "category": r.category,
                "score": round(r.score, 4)
            }
            for r in results
        ]
    }


@app.get("/concepts")
async def list_concepts(category: Optional[str] = None):
    """List all concepts"""
    concepts = list(kg.concepts.values())
    if category:
        concepts = [c for c in concepts if c.category == category]
    return [{"id": c.id, "name": c.name, "category": c.category, 
             "difficulty": c.difficulty, "usage_count": c.usage_count} for c in concepts]


@app.get("/concepts/{concept_id}")
async def get_concept(concept_id: str):
    """Get concept details"""
    if concept_id not in kg.concepts:
        raise HTTPException(status_code=404, detail="Concept not found")
    c = kg.concepts[concept_id]
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "category": c.category,
        "difficulty": c.difficulty,
        "keywords": c.keywords,
        "prerequisites": c.prerequisites,
        "related": c.related,
        "usage_count": c.usage_count,
        "success_rate": c.success_rate
    }


@app.post("/analyze")
async def analyze_query(query: str, auto_learn: bool = True):
    """Analyze query, find concepts, optionally discover new ones"""
    result = QueryAnalysis(query=query)
    
    # Find existing concepts
    found = kg.find_concepts(query)
    result.detected_concepts = [cid for cid, score in found]
    
    # Calculate suggested difficulty
    if result.detected_concepts:
        difficulties = [kg.concepts[cid].difficulty for cid in result.detected_concepts if cid in kg.concepts]
        result.suggested_difficulty = sum(difficulties) / len(difficulties) if difficulties else 0.5
    
    # Try to discover new concepts
    if auto_learn:
        new_concept = kg.discover_new_concept(query)
        if new_concept:
            result.new_concepts.append(new_concept)
            # Auto-add to graph
            added = kg.add_concept(new_concept)
            result.detected_concepts.append(added.id)
    
    # Build learning path for main concept
    if result.detected_concepts:
        result.learning_path = kg.get_learning_path(result.detected_concepts[0])
    
    return result


@app.post("/concepts")
async def create_concept(data: ConceptCreate):
    """Manually add a concept"""
    concept = kg.add_concept({
        "name": data.name,
        "description": data.description,
        "category": data.category
    })
    return {"id": concept.id, "name": concept.name}


@app.post("/feedback")
async def submit_feedback(feedback: TaskFeedback):
    """Submit task completion feedback to update concept stats"""
    kg.update_from_feedback(feedback)
    return {"success": True}


@app.get("/learning-path/{concept_id}")
async def get_learning_path(concept_id: str, known: str = ""):
    """Get learning path to concept"""
    known_list = [k.strip() for k in known.split(",") if k.strip()]
    path = kg.get_learning_path(concept_id, known_list)
    return {
        "target": concept_id,
        "path": path,
        "concepts": [{"id": cid, "name": kg.concepts[cid].name, 
                     "difficulty": kg.concepts[cid].difficulty} for cid in path if cid in kg.concepts]
    }


@app.get("/suggest")
async def suggest_next(known: str = "", target_difficulty: float = 0.5):
    """Suggest next concept to learn based on known concepts"""
    known_list = set(k.strip() for k in known.split(",") if k.strip())
    
    suggestions = []
    for cid, concept in kg.concepts.items():
        if cid in known_list:
            continue
        
        # Check if prerequisites are met
        prereqs_met = all(p in known_list for p in concept.prerequisites)
        if not prereqs_met:
            continue
        
        # Score based on difficulty match and success rate
        diff_match = 1 - abs(concept.difficulty - target_difficulty)
        score = diff_match * 0.5 + concept.success_rate * 0.3 + (concept.usage_count / 100) * 0.2
        
        suggestions.append({
            "id": cid,
            "name": concept.name,
            "difficulty": concept.difficulty,
            "score": score
        })
    
    suggestions.sort(key=lambda x: x["score"], reverse=True)
    return {"suggestions": suggestions[:5]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
