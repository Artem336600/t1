"""
Task Architect Service
Analyzes user queries to determine the best task structure (single-file vs multi-file).
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from openai import AsyncOpenAI
import os
import json
import sys

# Path to shared config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

try:
    from llm_config import Models, get_client, API_KEY, BASE_URL
except ImportError:
    API_KEY = os.getenv("LLM_API_KEY", "sk-SSWP5NVJpHecmOFI_yxp7Q")
    BASE_URL = os.getenv("LLM_BASE_URL", "https://llm.t1v.scibox.tech/v1")
    class Models:
        CHAT = "qwen3-32b-awq"
    def get_client(api_key=None, base_url=None):
        return AsyncOpenAI(api_key=api_key or API_KEY, base_url=base_url or BASE_URL)

app = FastAPI(
    title="Task Architect Service",
    description="Analyzes queries to determine task structure",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = get_client()


class AnalyzeRequest(BaseModel):
    query: str
    difficulty: str = "medium"
    language: str = "python"


class AnalyzeResponse(BaseModel):
    task_type: str  # "single_file" or "multi_file"
    strategy: str   # "flexible", "hashtag", "multifile"
    complexity: str
    reasoning: str
    suggested_components: List[str] = []


ARCHITECT_PROMPT = """/no_think Ты системный архитектор задач для программистов.
Твоя цель - определить, какую структуру задачи лучше создать для запроса пользователя.

Запрос: "{query}"
Сложность: {difficulty}

Проанализируй:
1. Насколько сложная тема?
2. Требует ли она взаимодействия нескольких модулей/классов?
3. Подходит ли она для одной функции/файла или нужен проект?

Типы задач:
- single_file: Алгоритмы, простые функции, базовые классы, задачи на логику.
- multi_file: Проектирование систем, API, сложные паттерны, debug существующих проектов, рефакторинг.

Верни JSON:
{{
    "task_type": "single_file|multi_file",
    "strategy": "flexible|multifile", 
    "complexity": "low|medium|high",
    "reasoning": "Почему выбран этот тип",
    "suggested_components": ["main.py", "utils.py", "test_*.py"] (если multi_file)
}}

Правила выбора:
- Если запрос про "исправь баг", "найди ошибку", "рефакторинг" -> multi_file (strategy: multifile)
- Если запрос про "создай api", "напиши игру", "система" -> multi_file (strategy: multifile)
- Если запрос про "сортировка", "поиск", "функция", "класс" -> single_file (strategy: flexible)
"""

@app.get("/health")
async def health():
    return {"status": "ok", "service": "task-architect"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_task(req: AnalyzeRequest):
    """Analyze query and decide task structure"""
    prompt = ARCHITECT_PROMPT.format(
        query=req.query,
        difficulty=req.difficulty
    )

    try:
        response = await client.chat.completions.create(
            model=Models.CHAT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
            response_format={"type": "json_object"}
        )

        data = json.loads(response.choices[0].message.content)
        
        # Fallback for strategy if missing
        if "strategy" not in data:
            if data.get("task_type") == "multi_file":
                data["strategy"] = "multifile"
            else:
                data["strategy"] = "flexible"
        
        return AnalyzeResponse(
            task_type=data.get("task_type", "single_file"),
            strategy=data.get("strategy", "flexible"),
            complexity=data.get("complexity", "medium"),
            reasoning=data.get("reasoning", "Default analysis"),
            suggested_components=data.get("suggested_components", [])
        )

    except Exception as e:
        print(f"Architect error: {e}")
        # Default safe fallback
        return AnalyzeResponse(
            task_type="single_file",
            strategy="flexible",
            complexity="medium",
            reasoning=f"Error during analysis: {str(e)}",
            suggested_components=[]
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
