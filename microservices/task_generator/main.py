"""
Task Generator Service v3.0
Flexible AI-driven task generation without rigid categories.
The system analyzes queries and autonomously decides task structure.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from openai import AsyncOpenAI
import httpx
import json
import re
import os
import time

# Load environment variables from .env file
from pathlib import Path
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

# Import flexible generator (primary)
from flexible_generator import generate_flexible_task, FlexibleTaskGenerator

# Import hashtag-based generator
from hashtag_generator import (
    generate_with_hashtags, generate_multifile_task,
    HashtagTaskGenerator, Section, Level
)

# Import scenario engine for dynamic task generation
from scenario_engine import (
    generate_scenario, ScenarioEngine, ScenarioType, StepType
)

# Legacy imports for backward compatibility
from templates import (
    get_template, detect_task_subtype, build_generation_prompt,
    TEMPLATES, TaskTemplate
)

app = FastAPI(
    title="Task Generator Service",
    description="Flexible AI-driven task generation",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
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
        return AsyncOpenAI(api_key=api_key or API_KEY, base_url=base_url or BASE_URL)

CODE_RUNNER_URL = os.getenv("CODE_RUNNER_URL", "http://localhost:8003")
KNOWLEDGE_URL = os.getenv("KNOWLEDGE_SERVICE_URL", "http://localhost:8005")
LEARNING_URL = os.getenv("LEARNING_SERVICE_URL", "http://localhost:8006")

client = get_client()
http_client = httpx.AsyncClient(timeout=60.0)

# Initialize generators
flexible_generator = FlexibleTaskGenerator()
hashtag_generator = HashtagTaskGenerator()


class GenerateRequest(BaseModel):
    """Request for task generation - simplified without rigid categories"""
    query: str
    difficulty: str = "adaptive"  # easy, medium, hard, or "adaptive" for auto
    language: str = "python"
    user_id: Optional[str] = None  # For adaptive learning
    
    # Legacy fields (ignored in v3, kept for backward compatibility)
    section_type: Optional[str] = None
    task_subtype: Optional[str] = None


class HashtagGenerateRequest(BaseModel):
    """Request for hashtag-based task generation"""
    query: str
    section: str = "live_coding"  # live_coding, hard_skills, soft_skills, logic
    level: str = "middle"  # junior, middle, senior
    language: str = "python"
    user_id: Optional[str] = None


class MultiFileGenerateRequest(BaseModel):
    """Request for multi-file task generation"""
    query: str
    task_type: str = "fix_bug"  # fix_bug, complete, refactor, multi_file
    level: str = "middle"  # junior, middle, senior
    language: str = "python"
    user_id: Optional[str] = None


class ScenarioGenerateRequest(BaseModel):
    """Request for dynamic scenario generation"""
    query: str
    difficulty: str = "medium"  # easy, medium, hard
    language: str = "python"
    scenario_type: Optional[str] = None  # Let AI decide if None
    # Available types: fix_code, complete, debug_output, refactor, 
    # multi_step, code_review, explain, optimize, write_tests, implement
    user_id: Optional[str] = None


class TestCase(BaseModel):
    input: str
    output: str
    description: Optional[str] = None


@app.get("/health")
async def health():
    return {
        "status": "ok", 
        "service": "task-generator",
        "version": "3.0.0",
        "mode": "flexible"
    }


@app.get("/templates")
async def list_templates():
    """List all available task templates"""
    result = {}
    for section, subtypes in TEMPLATES.items():
        result[section] = [
            {
                "id": t.type_id,
                "name": t.name,
                "description": t.description,
                "requires_code": t.requires_code,
                "requires_tests": t.requires_tests
            }
            for t in subtypes.values()
        ]
    return result


@app.get("/templates/{section_type}")
async def get_section_templates(section_type: str):
    """Get templates for specific section"""
    if section_type not in TEMPLATES:
        return {"templates": [], "error": "Section not found"}
    
    return {
        "section": section_type,
        "templates": [
            {
                "id": t.type_id,
                "name": t.name,
                "description": t.description,
                "structure": t.task_structure,
                "difficulty_hints": t.difficulty_hints,
                "example": t.example
            }
            for t in TEMPLATES[section_type].values()
        ]
    }


async def analyze_concepts(query: str) -> Dict:
    """Call Knowledge Service to analyze query and find/discover concepts"""
    try:
        resp = await http_client.post(
            f"{KNOWLEDGE_URL}/analyze",
            params={"query": query, "auto_learn": True}
        )
        return resp.json()
    except Exception as e:
        print(f"Knowledge service error: {e}")
        return {"detected_concepts": [], "learning_path": []}


async def get_adaptive_difficulty(user_id: str, concepts: List[str]) -> float:
    """Get adaptive difficulty from Learning Service"""
    try:
        resp = await http_client.get(
            f"{LEARNING_URL}/adaptive-difficulty/{user_id}",
            params={"concepts": ",".join(concepts)}
        )
        return resp.json().get("difficulty", 0.5)
    except Exception as e:
        print(f"Learning service error: {e}")
        return 0.5


async def record_task_attempt(user_id: str, concepts: List[str], solved: bool, time_spent: int = 0):
    """Record attempt to Learning Service"""
    try:
        await http_client.post(f"{LEARNING_URL}/attempt", json={
            "user_id": user_id,
            "concept_ids": concepts,
            "solved": solved,
            "time_spent": time_spent
        })
    except Exception as e:
        print(f"Failed to record attempt: {e}")


@app.post("/generate")
async def generate_task(req: GenerateRequest):
    """
    Generate task using flexible AI-driven approach.
    
    The system automatically:
    1. Analyzes the query to understand task requirements
    2. Determines what type of task to create
    3. Decides what tests are needed (unit, edge cases, performance)
    4. Generates task with appropriate structure
    5. Creates and validates solution
    
    No rigid categories - AI decides everything based on the query.
    """
    start_time = time.time()
    
    # Use flexible generator
    result = await flexible_generator.generate(
        query=req.query,
        difficulty=req.difficulty,
        language=req.language,
        user_id=req.user_id
    )
    
    result["execution_time"] = round(time.time() - start_time, 2)
    
    # Extract concepts from analysis for learning service
    if result.get("analysis"):
        result["concepts"] = result["analysis"].get("concepts", [])
        result["task_type"] = result["analysis"].get("task_type")
        result["tests_config"] = result["analysis"].get("tests_needed", {})
    
    return result


@app.post("/generate/hashtag")
async def generate_task_with_hashtags(req: HashtagGenerateRequest):
    """
    Generate task using hashtag taxonomy and example tasks.
    
    Pipeline:
    1. RAG search for relevant hashtags
    2. Get example tasks with those hashtags
    3. Generate task with context from examples
    4. Check novelty (not too similar to existing)
    5. Generate and validate solution
    6. Create new hashtag if AI suggests one
    
    This approach ensures:
    - Consistency with existing task style
    - Proper difficulty calibration per hashtag
    - Auto-expansion of hashtag taxonomy
    """
    start_time = time.time()
    
    result = await hashtag_generator.generate(
        query=req.query,
        section=req.section,
        level=req.level,
        language=req.language
    )
    
    result["execution_time"] = round(time.time() - start_time, 2)
    
    return result


@app.post("/generate/multifile")
async def generate_multifile_task_endpoint(req: MultiFileGenerateRequest):
    """
    Generate multi-file task (fix bugs, complete functions, etc.)
    
    Task types:
    - fix_bug: Find and fix bugs in existing code
    - complete: Complete function implementations (TODO markers)
    - refactor: Improve/refactor existing code
    - multi_file: General multi-file coding task
    
    Returns a task with multiple files, objectives, and tests.
    """
    start_time = time.time()
    
    result = await hashtag_generator.generate_multifile(
        query=req.query,
        task_type=req.task_type,
        level=req.level,
        language=req.language
    )
    
    result["execution_time"] = round(time.time() - start_time, 2)
    
    return result


@app.post("/generate/scenario")
async def generate_scenario_endpoint(req: ScenarioGenerateRequest):
    """
    Generate dynamic scenario using AI tools.
    
    This is the most flexible generation method. The AI:
    1. Analyzes the query to decide the best way to test the candidate
    2. Uses tools to build the scenario step by step
    3. Creates multi-step, interactive tasks
    
    Scenario Types:
    - fix_code: Show broken code, ask to fix bugs
    - complete: Show partial code with TODOs, ask to implement
    - debug_output: Show code and wrong output, find the bug
    - refactor: Show working but ugly code, improve it
    - multi_step: Progressive task with multiple stages
    - code_review: Review code and find issues
    - explain: Explain what code does
    - optimize: Make code faster/better
    - write_tests: Write tests for given code
    - implement: Classic write-from-scratch task
    
    If scenario_type is not specified, AI will choose the best type.
    
    Returns:
        Scenario with steps, each step has:
        - step_type: show_code, show_text, ask_fix, ask_complete, run_tests, etc.
        - content: The content for this step
        - is_interactive: Whether user input is required
        - points: Points for completing this step
    """
    start_time = time.time()
    
    result = await generate_scenario(
        query=req.query,
        difficulty=req.difficulty,
        language=req.language,
        scenario_type=req.scenario_type
    )
    
    result["execution_time"] = round(time.time() - start_time, 2)
    
    return result


@app.get("/scenario-types")
async def list_scenario_types():
    """
    List all available scenario types with descriptions.
    """
    return {
        "scenario_types": [
            {
                "id": "fix_code",
                "name": "Исправление багов",
                "description": "Показывается код с багами, нужно найти и исправить",
                "difficulty_range": ["easy", "medium", "hard"],
                "interactive": True,
                "typical_time_minutes": 15
            },
            {
                "id": "complete",
                "name": "Дополнение кода",
                "description": "Показывается частичный код с TODO, нужно дописать реализацию",
                "difficulty_range": ["easy", "medium", "hard"],
                "interactive": True,
                "typical_time_minutes": 20
            },
            {
                "id": "debug_output",
                "name": "Отладка по выводу",
                "description": "Показывается код и неправильный вывод, нужно найти баг",
                "difficulty_range": ["medium", "hard"],
                "interactive": True,
                "typical_time_minutes": 15
            },
            {
                "id": "refactor",
                "name": "Рефакторинг",
                "description": "Показывается рабочий но плохой код, нужно улучшить",
                "difficulty_range": ["medium", "hard"],
                "interactive": True,
                "typical_time_minutes": 25
            },
            {
                "id": "multi_step",
                "name": "Многошаговая задача",
                "description": "Последовательные этапы: базовое решение → edge cases → оптимизация",
                "difficulty_range": ["medium", "hard"],
                "interactive": True,
                "typical_time_minutes": 35
            },
            {
                "id": "code_review",
                "name": "Код-ревью",
                "description": "Провести ревью кода, найти проблемы и предложить улучшения",
                "difficulty_range": ["easy", "medium", "hard"],
                "interactive": True,
                "typical_time_minutes": 15
            },
            {
                "id": "explain",
                "name": "Объяснение кода",
                "description": "Объяснить что делает данный код",
                "difficulty_range": ["easy", "medium"],
                "interactive": True,
                "typical_time_minutes": 10
            },
            {
                "id": "optimize",
                "name": "Оптимизация",
                "description": "Улучшить производительность кода",
                "difficulty_range": ["medium", "hard"],
                "interactive": True,
                "typical_time_minutes": 25
            },
            {
                "id": "write_tests",
                "name": "Написание тестов",
                "description": "Написать тесты для данного кода",
                "difficulty_range": ["easy", "medium", "hard"],
                "interactive": True,
                "typical_time_minutes": 20
            },
            {
                "id": "implement",
                "name": "Реализация с нуля",
                "description": "Классическая задача - написать код с нуля",
                "difficulty_range": ["easy", "medium", "hard"],
                "interactive": True,
                "typical_time_minutes": 25
            }
        ],
        "step_types": [
            {"id": "show_code", "description": "Показать код пользователю"},
            {"id": "show_text", "description": "Показать текст/инструкции"},
            {"id": "show_output", "description": "Показать ожидаемый/фактический вывод"},
            {"id": "ask_fix", "description": "Попросить исправить код"},
            {"id": "ask_complete", "description": "Попросить дописать код"},
            {"id": "ask_explain", "description": "Попросить объяснить"},
            {"id": "ask_write", "description": "Попросить написать код"},
            {"id": "ask_review", "description": "Попросить провести ревью"},
            {"id": "run_tests", "description": "Запустить тесты на коде пользователя"},
            {"id": "hint", "description": "Показать подсказку"},
            {"id": "solution", "description": "Показать решение"}
        ]
    }


@app.post("/generate/legacy")
async def generate_task_legacy(req: GenerateRequest):
    """Legacy endpoint - uses old sequential approach"""
    start_time = time.time()
    
    result = {
        "status": "pending",
        "agents": [],
        "task": None,
        "solution": None,
        "validation": None,
        "concepts": [],
        "learning_path": [],
        "template_used": None
    }
    
    # Detect task subtype from query
    task_subtype = req.task_subtype or detect_task_subtype(req.query, req.section_type)
    template = get_template(req.section_type, task_subtype)
    result["template_used"] = {"type": template.type_id, "name": template.name}
    
    # Agent 0: Knowledge Analyzer (find/discover concepts)
    result["agents"].append({"name": "Knowledge Analyzer", "status": "running"})
    concepts_data = await analyze_concepts(req.query)
    result["concepts"] = concepts_data.get("detected_concepts", [])
    result["learning_path"] = concepts_data.get("learning_path", [])
    if concepts_data.get("new_concepts"):
        result["new_concept_discovered"] = concepts_data["new_concepts"][0].get("name")
    result["agents"][-1]["status"] = "done"
    
    # Get adaptive difficulty if user_id provided
    difficulty = req.difficulty
    if req.user_id and req.difficulty == "adaptive":
        adaptive_diff = await get_adaptive_difficulty(req.user_id, result["concepts"])
        difficulty = "easy" if adaptive_diff < 0.35 else "hard" if adaptive_diff > 0.65 else "medium"
        result["adaptive_difficulty"] = adaptive_diff
    
    # Agent 1: Task Designer (using template)
    result["agents"].append({"name": "Task Designer", "status": "running", "model": "qwen3-32b-awq"})
    task = await design_task_with_template(template, req.query, difficulty, result["concepts"])
    result["agents"][-1]["status"] = "done" if task else "error"
    
    if not task:
        result["status"] = "error"
        result["error"] = "Failed to generate task"
        return result
    
    result["task"] = task
    
    # For non-coding tasks, skip code generation
    if not template.requires_code:
        result["status"] = "success"
        result["execution_time"] = round(time.time() - start_time, 2)
        return result
    
    # Agent 2: Code Writer
    result["agents"].append({"name": "Code Writer", "status": "running", "model": "qwen3-coder-30b-a3b-instruct-fp8"})
    solution = await write_solution(task, req.language)
    result["agents"][-1]["status"] = "done" if solution else "error"
    result["solution"] = solution
    
    # Agent 3: Validator
    if solution and task.get("test_cases"):
        result["agents"].append({"name": "Validator", "status": "running"})
        validation = await validate_solution(solution, task["test_cases"])
        result["validation"] = validation
        result["agents"][-1]["status"] = "done"
        
        # Agent 4: Fixer
        if not validation.get("all_passed") and validation.get("failed", 0) > 0:
            result["agents"].append({"name": "Fixer", "status": "running", "model": "qwen3-coder-30b-a3b-instruct-fp8"})
            fixed = await fix_solution(solution, task, validation)
            if fixed:
                result["solution"] = fixed
                validation2 = await validate_solution(fixed, task["test_cases"])
                result["validation"] = validation2
            result["agents"][-1]["status"] = "done"
    
    result["status"] = "success" if result.get("validation", {}).get("all_passed") else "partial"
    result["execution_time"] = round(time.time() - start_time, 2)
    
    return result


async def design_task_with_template(
    template: TaskTemplate, 
    query: str, 
    difficulty: str, 
    concepts: List[str] = []
) -> Optional[Dict]:
    """Agent 1: Design task using dynamic template"""
    
    # Build prompt from template
    prompt = build_generation_prompt(template, query, difficulty, concepts)
    
    try:
        response = await client.chat.completions.create(
            model=Models.CHAT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2500,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        
        # Add metadata
        data["_template"] = template.type_id
        data["_concepts"] = concepts
        
        # Normalize test cases if present
        for tc in data.get("test_cases", []) + data.get("hidden_tests", []):
            if isinstance(tc.get("input"), (dict, list)):
                tc["input"] = json.dumps(tc["input"], ensure_ascii=False)
            else:
                tc["input"] = str(tc.get("input", ""))
            if isinstance(tc.get("output"), (dict, list)):
                tc["output"] = json.dumps(tc["output"], ensure_ascii=False)
            else:
                tc["output"] = str(tc.get("output", ""))
        
        return data
    except Exception as e:
        print(f"Task Designer Error: {e}")
        return None


# Legacy function for backward compatibility
async def design_task(query: str, difficulty: str, section_type: str, concepts: List[str] = []) -> Optional[Dict]:
    """Agent 1: Design task (legacy, uses templates internally)"""
    template = get_template(section_type)
    return await design_task_with_template(template, query, difficulty, concepts)


async def design_task_old(query: str, difficulty: str, section_type: str, concepts: List[str] = []) -> Optional[Dict]:
    """Old implementation - kept for reference"""
    
    concepts_hint = f"\nКонцепции для использования: {', '.join(concepts)}" if concepts else ""
    
    if section_type == "live_coding":
        prompt = f"""/no_think Создай алгоритмическую задачу.
Тема: {query}
Сложность: {difficulty}{concepts_hint}

JSON:
{{"title": "...", "description": "условие с примерами", "input_format": "...", "output_format": "...", 
"constraints": "...", "test_cases": [{{"input": "stdin строка", "output": "stdout строка"}}], 
"hidden_tests": [{{"input": "...", "output": "...", "description": "граничный случай"}}],
"hints": ["..."], "time_limit": "1 секунда", "tags": ["..."], "concepts": {json.dumps(concepts)}}}"""
    
    elif section_type == "hard_skills":
        prompt = f"""/no_think Создай технический вопрос для интервью.
Тема: {query}
Сложность: {difficulty}

JSON:
{{"title": "...", "description": "вопрос", "key_points": ["ключевые моменты"], 
"example_answer": "пример ответа", "code_example": "пример кода если нужен", "tags": ["..."]}}"""
    
    elif section_type == "soft_skills":
        prompt = f"""/no_think Создай поведенческий вопрос для интервью.
Тема: {query}

JSON:
{{"title": "...", "description": "вопрос", "structure": "STAR структура ответа", 
"tips": ["советы"], "example_answer": "пример", "tags": ["..."]}}"""
    
    else:  # logic
        prompt = f"""/no_think Создай логическую задачу.
Тема: {query}
Сложность: {difficulty}

JSON:
{{"title": "...", "description": "условие", "correct_answer": "ответ", 
"explanation": "объяснение", "hints": ["..."], "tags": ["..."]}}"""
    
    try:
        response = await client.chat.completions.create(
            model=Models.CHAT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        
        # Normalize test cases
        for tc in data.get("test_cases", []) + data.get("hidden_tests", []):
            if isinstance(tc.get("input"), (dict, list)):
                tc["input"] = json.dumps(tc["input"], ensure_ascii=False)
            else:
                tc["input"] = str(tc.get("input", ""))
            if isinstance(tc.get("output"), (dict, list)):
                tc["output"] = json.dumps(tc["output"], ensure_ascii=False)
            else:
                tc["output"] = str(tc.get("output", ""))
        
        return data
    except Exception as e:
        print(f"Task Designer Error: {e}")
        return None


async def write_solution(task: Dict, language: str = "python") -> Optional[str]:
    """Agent 2: Write solution"""
    example = task.get("test_cases", [{}])[0]
    
    prompt = f"""Напиши решение на {language}.

Задача: {task.get('title', '')}
Условие: {task.get('description', '')}
Вход: {task.get('input_format', '')}
Выход: {task.get('output_format', '')}

Пример:
Вход: {example.get('input', '')}
Выход: {example.get('output', '')}

Читай из stdin, пиши в stdout. Верни ТОЛЬКО код."""
    
    try:
        response = await client.chat.completions.create(
            model=Models.CODE,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1500
        )
        code = response.choices[0].message.content
        code = re.sub(r'^```\w*\n?', '', code)
        code = re.sub(r'\n?```$', '', code)
        return code.strip()
    except Exception as e:
        print(f"Code Writer Error: {e}")
        return None


async def validate_solution(code: str, test_cases: List[Dict]) -> Dict:
    """Agent 3: Validate via Code Runner service"""
    try:
        resp = await http_client.post(f"{CODE_RUNNER_URL}/validate", json={
            "code": code,
            "test_cases": test_cases[:5]
        })
        return resp.json()
    except Exception as e:
        print(f"Validation Error: {e}")
        return {"all_passed": False, "passed": 0, "failed": len(test_cases), "error": str(e)}


async def fix_solution(code: str, task: Dict, validation: Dict) -> Optional[str]:
    """Agent 4: Fix failed solution"""
    failed = [t for t in validation.get("tests", []) if not t.get("passed")][:2]
    
    prompt = f"""Исправь код.

Задача: {task.get('title', '')}

Код:
{code}

Ошибки:
{json.dumps(failed, ensure_ascii=False)}

Верни ТОЛЬКО исправленный код."""
    
    try:
        response = await client.chat.completions.create(
            model=Models.CODE,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1500
        )
        code = response.choices[0].message.content
        code = re.sub(r'^```\w*\n?', '', code)
        code = re.sub(r'\n?```$', '', code)
        return code.strip()
    except Exception as e:
        print(f"Fixer Error: {e}")
        return None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
