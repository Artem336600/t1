"""
Agent implementations for Task Generation Workflow
Each agent is a standalone async function that operates on WorkflowContext

Models used:
- qwen3-32b-awq: Task design, quality check (general reasoning)
- qwen3-coder-30b-a3b-instruct-fp8: Code writing, fixing (code tasks)
"""
from typing import Dict, List, Optional, Any
from openai import OpenAI
import httpx
import json
import os
import sys

# Add shared to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from workflow import WorkflowContext, AgentStatus
from templates import get_template, detect_task_subtype, build_generation_prompt, TaskTemplate

try:
    from llm_config import Models, get_client, API_KEY, BASE_URL
except ImportError:
    # Fallback if shared not available
    API_KEY = os.getenv("LLM_API_KEY", "sk-SSWP5NVJpHecmOFI_yxp7Q")
    BASE_URL = os.getenv("LLM_BASE_URL", "https://llm.t1v.scibox.tech/v1")
    class Models:
        CHAT = "qwen3-32b-awq"
        CODE = "qwen3-coder-30b-a3b-instruct-fp8"
        EMBEDDING = "bge-m3"
    def get_client(api_key=None, base_url=None):
        return OpenAI(api_key=api_key or API_KEY, base_url=base_url or BASE_URL)

CODE_RUNNER_URL = os.getenv("CODE_RUNNER_URL", "http://localhost:8003")
KNOWLEDGE_URL = os.getenv("KNOWLEDGE_SERVICE_URL", "http://localhost:8005")
LEARNING_URL = os.getenv("LEARNING_SERVICE_URL", "http://localhost:8006")

llm_client = get_client()
http_client = httpx.AsyncClient(timeout=30.0)


# ============== Agent: Knowledge Analyzer ==============

async def knowledge_analyzer(ctx: WorkflowContext) -> Dict:
    """
    Analyze query to find/discover concepts.
    Updates ctx.concepts, ctx.learning_path, ctx.new_concept
    """
    try:
        resp = await http_client.post(
            f"{KNOWLEDGE_URL}/analyze",
            params={"query": ctx.query, "auto_learn": True}
        )
        data = resp.json()
        
        ctx.concepts = data.get("detected_concepts", [])
        ctx.learning_path = data.get("learning_path", [])
        
        if data.get("new_concepts"):
            ctx.new_concept = data["new_concepts"][0].get("name")
        
        return {
            "concepts": ctx.concepts,
            "learning_path": ctx.learning_path,
            "new_concept": ctx.new_concept
        }
    except Exception as e:
        print(f"Knowledge service error: {e}")
        ctx.concepts = []
        return {"concepts": [], "error": str(e)}


# ============== Agent: Difficulty Selector ==============

async def difficulty_selector(ctx: WorkflowContext) -> Dict:
    """
    Select appropriate difficulty based on user profile and concepts.
    Updates ctx.adaptive_difficulty, ctx.difficulty
    """
    if ctx.difficulty == "adaptive" and ctx.user_id:
        try:
            resp = await http_client.get(
                f"{LEARNING_URL}/adaptive-difficulty/{ctx.user_id}",
                params={"concepts": ",".join(ctx.concepts)}
            )
            data = resp.json()
            ctx.adaptive_difficulty = data.get("difficulty", 0.5)
            
            # Map to difficulty level
            if ctx.adaptive_difficulty < 0.35:
                ctx.difficulty = "easy"
            elif ctx.adaptive_difficulty > 0.65:
                ctx.difficulty = "hard"
            else:
                ctx.difficulty = "medium"
                
        except Exception as e:
            print(f"Learning service error: {e}")
            ctx.difficulty = "medium"
            ctx.adaptive_difficulty = 0.5
    else:
        # Use provided difficulty
        ctx.adaptive_difficulty = {"easy": 0.3, "medium": 0.5, "hard": 0.7}.get(ctx.difficulty, 0.5)
    
    # Detect and set template
    task_subtype = detect_task_subtype(ctx.query, ctx.section_type)
    ctx.template = get_template(ctx.section_type, task_subtype)
    
    return {
        "difficulty": ctx.difficulty,
        "adaptive_score": ctx.adaptive_difficulty,
        "template": ctx.template.type_id
    }


# ============== Agent: Task Designer ==============

async def task_designer(ctx: WorkflowContext) -> Dict:
    """
    Design task using LLM and template.
    Updates ctx.task
    """
    if not ctx.template:
        ctx.template = get_template(ctx.section_type)
    
    prompt = build_generation_prompt(ctx.template, ctx.query, ctx.difficulty, ctx.concepts)
    
    try:
        response = llm_client.chat.completions.create(
            model=Models.CHAT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2500,
            response_format={"type": "json_object"}
        )
        
        task = json.loads(response.choices[0].message.content)
        
        # Add metadata
        task["_template"] = ctx.template.type_id
        task["_concepts"] = ctx.concepts
        task["_difficulty"] = ctx.difficulty
        
        # Normalize test cases
        for tc in task.get("test_cases", []) + task.get("hidden_tests", []):
            if isinstance(tc.get("input"), (dict, list)):
                tc["input"] = json.dumps(tc["input"], ensure_ascii=False)
            else:
                tc["input"] = str(tc.get("input", ""))
            if isinstance(tc.get("output"), (dict, list)):
                tc["output"] = json.dumps(tc["output"], ensure_ascii=False)
            else:
                tc["output"] = str(tc.get("output", ""))
        
        ctx.task = task
        return task
        
    except Exception as e:
        raise RuntimeError(f"Task design failed: {e}")


# ============== Agent: Code Writer ==============

async def code_writer(ctx: WorkflowContext) -> Optional[str]:
    """
    Write solution code for the task.
    Updates ctx.solution
    """
    if not ctx.task:
        return None
    
    # Skip for non-coding tasks
    if not ctx.template or not ctx.template.requires_code:
        return None
    
    task = ctx.task
    example = task.get("test_cases", [{}])[0] if task.get("test_cases") else {}
    
    prompt = f"""/no_think Напиши решение на {ctx.language}.

Задача: {task.get('title', '')}
{task.get('description', '')}

Вход: {task.get('input_format', '')}
Выход: {task.get('output_format', '')}

Пример:
Вход: {example.get('input', '')}
Выход: {example.get('output', '')}

Код должен читать из stdin и писать в stdout.
Верни ТОЛЬКО код без объяснений."""

    try:
        response = llm_client.chat.completions.create(
            model=Models.CODE,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2000
        )
        
        code = response.choices[0].message.content
        
        # Extract code from markdown if present
        if "```" in code:
            import re
            match = re.search(r'```(?:python)?\n(.*?)```', code, re.DOTALL)
            if match:
                code = match.group(1)
        
        ctx.solution = code.strip()
        return ctx.solution
        
    except Exception as e:
        raise RuntimeError(f"Code writing failed: {e}")


# ============== Agent: Validator ==============

async def validator(ctx: WorkflowContext) -> Dict:
    """
    Validate solution against test cases.
    Updates ctx.validation
    """
    if not ctx.solution or not ctx.task:
        ctx.validation = {"all_passed": False, "skipped": True}
        return ctx.validation
    
    test_cases = ctx.task.get("test_cases", [])
    if not test_cases:
        ctx.validation = {"all_passed": True, "no_tests": True}
        return ctx.validation
    
    try:
        resp = await http_client.post(
            f"{CODE_RUNNER_URL}/validate",
            json={
                "code": ctx.solution,
                "test_cases": test_cases,
                "timeout": 10
            }
        )
        
        ctx.validation = resp.json()
        return ctx.validation
        
    except Exception as e:
        ctx.validation = {"all_passed": False, "error": str(e)}
        return ctx.validation


# ============== Agent: Fixer ==============

async def fixer(ctx: WorkflowContext) -> Optional[str]:
    """
    Fix solution if validation failed.
    Updates ctx.solution, ctx.validation
    """
    if not ctx.validation:
        return None
    
    # Skip if already passed or no failures
    if ctx.validation.get("all_passed") or ctx.validation.get("failed", 0) == 0:
        return ctx.solution
    
    # Get failed tests
    failed_tests = [t for t in ctx.validation.get("tests", []) if not t.get("passed")]
    if not failed_tests:
        return ctx.solution
    
    prompt = f"""/no_think Исправь код. Тесты не прошли:

Код:
```python
{ctx.solution}
```

Ошибки:
{json.dumps(failed_tests[:3], ensure_ascii=False, indent=2)}

Верни ТОЛЬКО исправленный код."""

    try:
        response = llm_client.chat.completions.create(
            model=Models.CODE,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2000
        )
        
        code = response.choices[0].message.content
        
        # Extract code
        if "```" in code:
            import re
            match = re.search(r'```(?:python)?\n(.*?)```', code, re.DOTALL)
            if match:
                code = match.group(1)
        
        fixed_code = code.strip()
        
        # Re-validate
        resp = await http_client.post(
            f"{CODE_RUNNER_URL}/validate",
            json={
                "code": fixed_code,
                "test_cases": ctx.task.get("test_cases", []),
                "timeout": 10
            }
        )
        
        new_validation = resp.json()
        
        # Update if better
        if new_validation.get("passed", 0) >= ctx.validation.get("passed", 0):
            ctx.solution = fixed_code
            ctx.validation = new_validation
        
        return ctx.solution
        
    except Exception as e:
        print(f"Fixer error: {e}")
        return ctx.solution


# ============== Agent: Quality Checker ==============

async def quality_checker(ctx: WorkflowContext) -> Dict:
    """
    Check task quality: novelty, difficulty estimation, clarity.
    Updates ctx.quality_score
    """
    if not ctx.task:
        return {"score": 0, "skipped": True}
    
    prompt = f"""/no_think Оцени качество задачи по шкале 0-10:

Задача: {ctx.task.get('title', '')}
{ctx.task.get('description', '')}

Критерии:
1. Понятность условия (0-10)
2. Корректность примеров (0-10)
3. Соответствие сложности "{ctx.difficulty}" (0-10)

JSON: {{"clarity": N, "examples": N, "difficulty_match": N, "overall": N, "suggestions": ["..."]}}"""

    try:
        response = llm_client.chat.completions.create(
            model=Models.CHAT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        
        quality = json.loads(response.choices[0].message.content)
        ctx.quality_score = quality.get("overall", 5) / 10
        
        return quality
        
    except Exception as e:
        ctx.quality_score = 0.5
        return {"score": 5, "error": str(e)}
