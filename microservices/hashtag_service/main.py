"""
Hashtag Service
Manages hashtag taxonomy with RAG search, hierarchy, and auto-expansion.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from openai import AsyncOpenAI
from datetime import datetime
from enum import Enum
import numpy as np
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

try:
    from llm_config import Models, get_client
except ImportError:
    class Models:
        CHAT = "qwen3-32b-awq"
        CODE = "qwen3-coder-30b-a3b-instruct-fp8"
        EMBEDDING = "bge-m3"
    def get_client():
        return AsyncOpenAI(
            api_key=os.getenv("LLM_API_KEY", "sk-SSWP5NVJpHecmOFI_yxp7Q"),
            base_url=os.getenv("LLM_BASE_URL", "https://llm.t1v.scibox.tech/v1")
        )

app = FastAPI(
    title="Hashtag Service",
    description="Hashtag taxonomy with RAG search and auto-expansion",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = get_client()
DATA_FILE = "data/hashtags.json"
TASKS_FILE = "data/tasks_index.json"

# Similarity thresholds
DUPLICATE_THRESHOLD = 0.85  # Above this = duplicate hashtag
RELEVANT_THRESHOLD = 0.6    # Above this = relevant for search


# ============== Models ==============

class Section(str, Enum):
    LIVE_CODING = "live_coding"
    HARD_SKILLS = "hard_skills"
    SOFT_SKILLS = "soft_skills"
    LOGIC = "logic"


class Level(str, Enum):
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"


class Hashtag(BaseModel):
    id: str                          # "sliding_window"
    name: str                        # "#sliding_window"
    description: str                 # "Скользящее окно для подмассивов"
    section: Section
    parent_id: Optional[str] = None  # For hierarchy
    related_ids: List[str] = []      # Often used together
    embedding: Optional[List[float]] = None
    task_count: int = 0
    avg_difficulty: float = 0.5
    success_rate: float = 0.0
    created_by: str = "system"       # "system" | "ai_generated" | "user"
    created_at: str = ""
    approved: bool = True            # AI-generated need approval


class TaskIndex(BaseModel):
    """Lightweight task reference for hashtag search"""
    id: str
    title: str
    hashtags: List[str]
    level: Level
    section: Section
    rating: float = 0.0              # Quality rating
    solve_count: int = 0
    success_rate: float = 0.0


class HashtagSearchRequest(BaseModel):
    query: str
    section: Optional[Section] = None
    limit: int = 10


class HashtagSearchResult(BaseModel):
    hashtag: Hashtag
    score: float
    task_count: int


class TaskSearchRequest(BaseModel):
    hashtags: List[str]
    level: Optional[Level] = None
    section: Optional[Section] = None
    limit_per_hashtag: int = 3
    min_rating: float = 0.0


class CreateHashtagRequest(BaseModel):
    id: str
    description: str
    section: Section
    parent_id: Optional[str] = None
    created_by: str = "user"


class SuggestHashtagRequest(BaseModel):
    query: str
    section: Section
    existing_hashtags: List[str] = []


# ============== Storage ==============

class HashtagStore:
    def __init__(self):
        self.hashtags: Dict[str, Hashtag] = {}
        self.tasks: Dict[str, TaskIndex] = {}
        self._load()
        if not self.hashtags:
            self._init_default_hashtags()
    
    def _load(self):
        os.makedirs("data", exist_ok=True)
        
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for h in data.get("hashtags", []):
                        self.hashtags[h["id"]] = Hashtag(**h)
            except Exception as e:
                print(f"Error loading hashtags: {e}")
        
        if os.path.exists(TASKS_FILE):
            try:
                with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for t in data.get("tasks", []):
                        self.tasks[t["id"]] = TaskIndex(**t)
            except Exception as e:
                print(f"Error loading tasks: {e}")
    
    def _save(self):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "hashtags": [h.model_dump() for h in self.hashtags.values()]
            }, f, ensure_ascii=False, indent=2)
        
        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "tasks": [t.model_dump() for t in self.tasks.values()]
            }, f, ensure_ascii=False, indent=2)
    
    def _init_default_hashtags(self):
        """Initialize with default hashtag taxonomy"""
        defaults = [
            # Live Coding - Array Techniques
            ("two_pointers", "Техника двух указателей для массивов и строк", Section.LIVE_CODING, None, ["sliding_window", "binary_search"]),
            ("sliding_window", "Скользящее окно для поиска подмассивов/подстрок", Section.LIVE_CODING, None, ["two_pointers"]),
            ("prefix_sum", "Префиксные суммы для быстрых range-запросов", Section.LIVE_CODING, None, ["array"]),
            ("binary_search", "Бинарный поиск и его вариации", Section.LIVE_CODING, None, ["sorting"]),
            
            # Live Coding - Graph/Tree
            ("dfs", "Обход в глубину для графов и деревьев", Section.LIVE_CODING, None, ["recursion", "backtracking"]),
            ("bfs", "Обход в ширину, кратчайший путь в невзвешенном графе", Section.LIVE_CODING, None, ["graph", "queue"]),
            ("tree_traversal", "Обходы деревьев: inorder, preorder, postorder", Section.LIVE_CODING, None, ["dfs", "recursion"]),
            ("graph", "Работа с графами: представление, обходы, алгоритмы", Section.LIVE_CODING, None, ["dfs", "bfs"]),
            
            # Live Coding - DP & Greedy
            ("dynamic_programming", "Динамическое программирование: мемоизация и табуляция", Section.LIVE_CODING, None, ["recursion"]),
            ("greedy", "Жадные алгоритмы: локально оптимальный выбор", Section.LIVE_CODING, None, []),
            ("backtracking", "Перебор с возвратом для комбинаторных задач", Section.LIVE_CODING, None, ["dfs", "recursion"]),
            
            # Live Coding - Data Structures
            ("hash_map", "Решения через хэш-таблицы за O(1)", Section.LIVE_CODING, None, []),
            ("stack", "Задачи на стек: скобки, монотонный стек", Section.LIVE_CODING, None, []),
            ("heap", "Куча/приоритетная очередь для top-k задач", Section.LIVE_CODING, None, ["sorting"]),
            ("linked_list", "Операции со связными списками", Section.LIVE_CODING, None, ["two_pointers"]),
            
            # Live Coding - Other
            ("string_manipulation", "Манипуляции со строками: парсинг, преобразования", Section.LIVE_CODING, None, []),
            ("math", "Математические задачи: числа, комбинаторика", Section.LIVE_CODING, None, []),
            ("bit_manipulation", "Битовые операции: XOR, маски, сдвиги", Section.LIVE_CODING, None, []),
            ("sorting", "Сортировки и их применение", Section.LIVE_CODING, None, ["binary_search"]),
            ("recursion", "Рекурсивные решения и их анализ", Section.LIVE_CODING, None, ["dfs", "dynamic_programming"]),
            
            # Hard Skills - OOP
            ("oop_inheritance", "Наследование, полиморфизм, инкапсуляция", Section.HARD_SKILLS, None, ["oop_patterns"]),
            ("oop_patterns", "Паттерны проектирования: Singleton, Factory, Observer...", Section.HARD_SKILLS, None, ["oop_inheritance", "solid"]),
            ("solid", "Принципы SOLID в проектировании", Section.HARD_SKILLS, None, ["oop_patterns"]),
            
            # Hard Skills - System
            ("api_design", "Проектирование REST/GraphQL API", Section.HARD_SKILLS, None, ["system_design"]),
            ("database_design", "Проектирование БД: нормализация, индексы, SQL", Section.HARD_SKILLS, None, ["system_design"]),
            ("system_design", "Проектирование распределённых систем", Section.HARD_SKILLS, None, ["api_design", "database_design"]),
            ("concurrency", "Многопоточность, асинхронность, race conditions", Section.HARD_SKILLS, None, []),
            
            # Hard Skills - Quality
            ("testing", "Unit/Integration тестирование, TDD", Section.HARD_SKILLS, None, []),
            ("refactoring", "Рефакторинг: улучшение кода без изменения поведения", Section.HARD_SKILLS, None, ["code_review"]),
            ("code_review", "Код-ревью: найти проблемы в чужом коде", Section.HARD_SKILLS, None, ["refactoring"]),
            
            # Soft Skills
            ("conflict_resolution", "Разрешение конфликтов в команде", Section.SOFT_SKILLS, None, ["communication"]),
            ("estimation", "Оценка задач и сроков", Section.SOFT_SKILLS, None, ["prioritization"]),
            ("communication", "Коммуникация с командой и заказчиком", Section.SOFT_SKILLS, None, ["feedback"]),
            ("prioritization", "Приоритизация задач и управление бэклогом", Section.SOFT_SKILLS, None, ["estimation"]),
            ("feedback", "Дача и получение обратной связи", Section.SOFT_SKILLS, None, ["communication"]),
            ("leadership", "Лидерство, менторство, делегирование", Section.SOFT_SKILLS, None, []),
            ("decision_making", "Принятие решений в условиях неопределённости", Section.SOFT_SKILLS, None, []),
            
            # Logic
            ("puzzle", "Логические головоломки и загадки", Section.LOGIC, None, ["lateral_thinking"]),
            ("probability", "Задачи на вероятность и статистику", Section.LOGIC, None, ["math"]),
            ("fermi_estimation", "Ферми-оценки: сколько мячиков в автобусе", Section.LOGIC, None, []),
            ("sequence", "Числовые последовательности и паттерны", Section.LOGIC, None, []),
            ("lateral_thinking", "Нестандартное мышление, задачи с подвохом", Section.LOGIC, None, ["puzzle"]),
            ("deduction", "Дедуктивные задачи: логические выводы", Section.LOGIC, None, []),
        ]
        
        for id_, desc, section, parent, related in defaults:
            self.hashtags[id_] = Hashtag(
                id=id_,
                name=f"#{id_}",
                description=desc,
                section=section,
                parent_id=parent,
                related_ids=related,
                created_at=datetime.now().isoformat(),
                approved=True
            )
        
        self._save()
        print(f"Initialized {len(self.hashtags)} default hashtags")
    
    async def get_embedding(self, text: str) -> List[float]:
        """Get embedding for text"""
        try:
            response = await client.embeddings.create(
                model=Models.EMBEDDING,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Embedding error: {e}")
            return [0.0] * 1024
    
    async def ensure_embeddings(self):
        """Generate embeddings for hashtags that don't have them"""
        updated = False
        for h in self.hashtags.values():
            if not h.embedding:
                text = f"{h.name}: {h.description}"
                h.embedding = await self.get_embedding(text)
                updated = True
        if updated:
            self._save()
    
    async def search_hashtags(
        self, 
        query: str, 
        section: Optional[Section] = None,
        limit: int = 10
    ) -> List[tuple]:
        """Search hashtags by semantic similarity"""
        await self.ensure_embeddings()
        
        query_emb = np.array(await self.get_embedding(query))
        
        results = []
        for h in self.hashtags.values():
            if section and h.section != section:
                continue
            if not h.approved:
                continue
            if not h.embedding:
                continue
            
            h_emb = np.array(h.embedding)
            # Cosine similarity
            score = float(np.dot(query_emb, h_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(h_emb) + 1e-9))
            
            if score >= RELEVANT_THRESHOLD:
                results.append((h, score))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
    
    async def check_duplicate(self, description: str, section: Section) -> Optional[Hashtag]:
        """Check if similar hashtag already exists"""
        await self.ensure_embeddings()
        
        query_emb = np.array(await self.get_embedding(description))
        
        for h in self.hashtags.values():
            if h.section != section:
                continue
            if not h.embedding:
                continue
            
            h_emb = np.array(h.embedding)
            score = float(np.dot(query_emb, h_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(h_emb) + 1e-9))
            
            if score >= DUPLICATE_THRESHOLD:
                return h
        
        return None
    
    async def add_hashtag(self, hashtag: Hashtag) -> tuple:
        """Add new hashtag with duplicate check"""
        # Normalize ID
        hashtag.id = hashtag.id.lower().replace(" ", "_").replace("-", "_")
        hashtag.name = f"#{hashtag.id}"
        
        # Check if ID exists
        if hashtag.id in self.hashtags:
            return False, f"Hashtag #{hashtag.id} already exists"
        
        # Check semantic duplicate
        duplicate = await self.check_duplicate(hashtag.description, hashtag.section)
        if duplicate:
            return False, f"Similar hashtag exists: #{duplicate.id} - {duplicate.description}"
        
        # Generate embedding
        text = f"{hashtag.name}: {hashtag.description}"
        hashtag.embedding = await self.get_embedding(text)
        hashtag.created_at = datetime.now().isoformat()
        
        self.hashtags[hashtag.id] = hashtag
        self._save()
        
        return True, f"Created #{hashtag.id}"
    
    def get_tasks_by_hashtags(
        self,
        hashtags: List[str],
        level: Optional[Level] = None,
        section: Optional[Section] = None,
        limit_per_hashtag: int = 3,
        min_rating: float = 0.0
    ) -> Dict[str, List[TaskIndex]]:
        """Get tasks grouped by hashtag"""
        result = {}
        
        for tag in hashtags:
            matching = []
            for task in self.tasks.values():
                if tag not in task.hashtags:
                    continue
                if level and task.level != level:
                    continue
                if section and task.section != section:
                    continue
                if task.rating < min_rating:
                    continue
                matching.append(task)
            
            # Sort by rating, take top N
            matching.sort(key=lambda t: t.rating, reverse=True)
            result[tag] = matching[:limit_per_hashtag]
        
        return result
    
    def add_task(self, task: TaskIndex):
        """Add or update task in index"""
        self.tasks[task.id] = task
        
        # Update hashtag stats
        for tag_id in task.hashtags:
            if tag_id in self.hashtags:
                self.hashtags[tag_id].task_count += 1
        
        self._save()
    
    def get_hashtag(self, id: str) -> Optional[Hashtag]:
        return self.hashtags.get(id)
    
    def get_all_hashtags(self, section: Optional[Section] = None) -> List[Hashtag]:
        result = list(self.hashtags.values())
        if section:
            result = [h for h in result if h.section == section]
        return result
    
    def get_related(self, hashtag_id: str) -> List[Hashtag]:
        """Get related hashtags"""
        h = self.hashtags.get(hashtag_id)
        if not h:
            return []
        return [self.hashtags[rid] for rid in h.related_ids if rid in self.hashtags]


store = HashtagStore()


# ============== API Endpoints ==============

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "hashtag",
        "hashtag_count": len(store.hashtags),
        "task_count": len(store.tasks)
    }


@app.get("/hashtags")
async def list_hashtags(section: Optional[Section] = None):
    """List all hashtags, optionally filtered by section"""
    hashtags = store.get_all_hashtags(section)
    return {
        "hashtags": [
            {
                "id": h.id,
                "name": h.name,
                "description": h.description,
                "section": h.section,
                "task_count": h.task_count,
                "related": h.related_ids
            }
            for h in hashtags if h.approved
        ]
    }


@app.get("/hashtags/{hashtag_id}")
async def get_hashtag(hashtag_id: str):
    """Get single hashtag with details"""
    h = store.get_hashtag(hashtag_id)
    if not h:
        raise HTTPException(status_code=404, detail="Hashtag not found")
    
    related = store.get_related(hashtag_id)
    
    return {
        "hashtag": {
            "id": h.id,
            "name": h.name,
            "description": h.description,
            "section": h.section,
            "parent_id": h.parent_id,
            "task_count": h.task_count,
            "avg_difficulty": h.avg_difficulty,
            "success_rate": h.success_rate,
            "created_by": h.created_by,
            "approved": h.approved
        },
        "related": [
            {"id": r.id, "name": r.name, "description": r.description}
            for r in related
        ]
    }


@app.post("/hashtags/search")
async def search_hashtags(req: HashtagSearchRequest):
    """Search hashtags by semantic similarity"""
    results = await store.search_hashtags(req.query, req.section, req.limit)
    
    return {
        "query": req.query,
        "results": [
            {
                "hashtag": {
                    "id": h.id,
                    "name": h.name,
                    "description": h.description,
                    "section": h.section,
                    "task_count": h.task_count
                },
                "score": round(score, 3)
            }
            for h, score in results
        ]
    }


@app.post("/hashtags/create")
async def create_hashtag(req: CreateHashtagRequest):
    """Create new hashtag with duplicate check"""
    hashtag = Hashtag(
        id=req.id,
        name=f"#{req.id}",
        description=req.description,
        section=req.section,
        parent_id=req.parent_id,
        created_by=req.created_by,
        approved=(req.created_by != "ai_generated")  # AI-generated need review
    )
    
    success, message = await store.add_hashtag(hashtag)
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {"success": True, "message": message, "hashtag_id": hashtag.id}


@app.post("/hashtags/suggest")
async def suggest_hashtag(req: SuggestHashtagRequest):
    """AI suggests a new hashtag if needed"""
    # First check if existing hashtags cover the query
    existing = await store.search_hashtags(req.query, req.section, limit=5)
    
    if existing and existing[0][1] > 0.8:
        return {
            "suggestion": None,
            "reason": "Existing hashtags cover this topic",
            "existing": [
                {"id": h.id, "name": h.name, "score": round(s, 3)}
                for h, s in existing[:3]
            ]
        }
    
    # Ask AI to suggest a hashtag
    existing_list = "\n".join([
        f"#{h.id}: {h.description}" 
        for h in store.get_all_hashtags(req.section)
    ])
    
    prompt = f"""/no_think Ты эксперт по категоризации задач для программистов.

Запрос: "{req.query}"
Раздел: {req.section.value}

Существующие хэштеги в этом разделе:
{existing_list}

Нужен ли НОВЫЙ хэштег для этого запроса, или существующие покрывают тему?

Если нужен новый, верни JSON:
{{
    "need_new": true,
    "id": "snake_case_id",
    "description": "Краткое описание что покрывает этот хэштег",
    "related_to": ["id существующих связанных хэштегов"]
}}

Если существующие подходят:
{{
    "need_new": false,
    "use_existing": ["id1", "id2"],
    "reason": "почему существующие подходят"
}}"""

    try:
        response = await client.chat.completions.create(
            model=Models.CHAT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        if result.get("need_new"):
            # Check for duplicate before suggesting
            duplicate = await store.check_duplicate(result["description"], req.section)
            if duplicate:
                return {
                    "suggestion": None,
                    "reason": f"Similar hashtag exists: #{duplicate.id}",
                    "existing": [{"id": duplicate.id, "name": duplicate.name}]
                }
            
            return {
                "suggestion": {
                    "id": result["id"],
                    "description": result["description"],
                    "related_to": result.get("related_to", [])
                },
                "reason": "New hashtag suggested by AI"
            }
        else:
            return {
                "suggestion": None,
                "reason": result.get("reason", "Existing hashtags cover this"),
                "use_existing": result.get("use_existing", [])
            }
            
    except Exception as e:
        print(f"Suggest error: {e}")
        return {
            "suggestion": None,
            "reason": f"Error: {e}",
            "existing": [{"id": h.id, "name": h.name} for h, _ in existing[:3]]
        }


@app.post("/tasks/search")
async def search_tasks(req: TaskSearchRequest):
    """Get example tasks for given hashtags"""
    results = store.get_tasks_by_hashtags(
        hashtags=req.hashtags,
        level=req.level,
        section=req.section,
        limit_per_hashtag=req.limit_per_hashtag,
        min_rating=req.min_rating
    )
    
    return {
        "hashtags": req.hashtags,
        "level": req.level,
        "tasks_by_hashtag": {
            tag: [
                {
                    "id": t.id,
                    "title": t.title,
                    "level": t.level,
                    "rating": t.rating
                }
                for t in tasks
            ]
            for tag, tasks in results.items()
        },
        "total_tasks": sum(len(tasks) for tasks in results.values())
    }


@app.post("/tasks/index")
async def index_task(task: TaskIndex):
    """Add task to index for hashtag search"""
    # Validate hashtags exist
    for tag in task.hashtags:
        if tag not in store.hashtags:
            raise HTTPException(status_code=400, detail=f"Unknown hashtag: #{tag}")
    
    store.add_task(task)
    
    return {"success": True, "task_id": task.id}


@app.get("/stats")
async def get_stats():
    """Get hashtag statistics"""
    by_section = {}
    for h in store.hashtags.values():
        section = h.section.value
        if section not in by_section:
            by_section[section] = {"count": 0, "total_tasks": 0}
        by_section[section]["count"] += 1
        by_section[section]["total_tasks"] += h.task_count
    
    # Find hashtags needing more tasks
    low_coverage = [
        {"id": h.id, "name": h.name, "task_count": h.task_count}
        for h in store.hashtags.values()
        if h.task_count < 3 and h.approved
    ]
    
    # Pending approval
    pending = [
        {"id": h.id, "name": h.name, "description": h.description}
        for h in store.hashtags.values()
        if not h.approved
    ]
    
    return {
        "total_hashtags": len(store.hashtags),
        "total_tasks": len(store.tasks),
        "by_section": by_section,
        "low_coverage": low_coverage[:10],
        "pending_approval": pending
    }


@app.post("/hashtags/{hashtag_id}/approve")
async def approve_hashtag(hashtag_id: str):
    """Approve AI-generated hashtag"""
    h = store.get_hashtag(hashtag_id)
    if not h:
        raise HTTPException(status_code=404, detail="Hashtag not found")
    
    h.approved = True
    store._save()
    
    return {"success": True, "hashtag_id": hashtag_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
