"""
Hashtag-based Task Generator
Uses hashtag taxonomy and example tasks for context-aware generation.

Optimized for speed:
- Parallel LLM calls where possible
- Reduced prompt sizes
- Timeouts and retry with exponential backoff
- Caching for repeated queries
"""
from typing import Dict, List, Optional, Any, Tuple
from openai import AsyncOpenAI
from pydantic import BaseModel
import httpx
import json
import os
import sys
import time
import asyncio
import hashlib
from functools import lru_cache

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

HASHTAG_SERVICE_URL = os.getenv("HASHTAG_SERVICE_URL", "http://localhost:8010")
LIBRARY_SERVICE_URL = os.getenv("LIBRARY_SERVICE_URL", "http://localhost:8001")
CODE_RUNNER_URL = os.getenv("CODE_RUNNER_URL", "http://localhost:8003")

# Optimized timeouts
LLM_TIMEOUT = 45  # seconds - reduced from default
HTTP_TIMEOUT = 15  # seconds for internal services
MAX_RETRIES = 2   # reduced retries
RETRY_DELAY = 1   # initial delay

client = get_client()
http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT)

# Simple in-memory cache for prompts
_prompt_cache: Dict[str, Dict] = {}
_cache_ttl = 300  # 5 minutes

def _cache_key(query: str, level: str, section: str) -> str:
    """Generate cache key for task generation"""
    return hashlib.md5(f"{query}:{level}:{section}".encode()).hexdigest()

def _get_cached(key: str) -> Optional[Dict]:
    """Get cached result if not expired"""
    if key in _prompt_cache:
        cached = _prompt_cache[key]
        if time.time() - cached.get('_ts', 0) < _cache_ttl:
            return cached.get('data')
    return None

def _set_cache(key: str, data: Dict):
    """Cache result with timestamp"""
    _prompt_cache[key] = {'data': data, '_ts': time.time()}
    # Cleanup old entries
    if len(_prompt_cache) > 100:
        oldest = min(_prompt_cache.items(), key=lambda x: x[1].get('_ts', 0))
        del _prompt_cache[oldest[0]]

async def _llm_call_with_timeout(
    client: AsyncOpenAI,
    model: str,
    messages: List[Dict],
    temperature: float = 0.3,
    max_tokens: int = 2000,
    response_format: Optional[Dict] = None,
    timeout: float = LLM_TIMEOUT
) -> Optional[str]:
    """LLM call with timeout and retry.
    Returns response content or None on failure.
    """
    for attempt in range(MAX_RETRIES):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format

            # Use asyncio.wait_for for timeout
            response = await asyncio.wait_for(
                client.chat.completions.create(**kwargs),
                timeout=timeout
            )
            return response.choices[0].message.content

        except asyncio.TimeoutError:
            print(f"[LLM] Timeout after {timeout}s (attempt {attempt + 1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
        except Exception as e:
            print(f"[LLM] Error: {e} (attempt {attempt + 1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    return None


class Level:
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"


class Section:
    LIVE_CODING = "live_coding"
    HARD_SKILLS = "hard_skills"
    SOFT_SKILLS = "soft_skills"
    LOGIC = "logic"


# ============== Prompts ==============

TASK_GENERATION_PROMPT = """/no_think Ты эксперт по созданию задач для технических интервью.

Создай задачу по теме: {query}
Раздел: {section}
Уровень сложности: {level}
Язык программирования: {language}

{context_section}

Требования к задаче:
1. Придумай ОРИГИНАЛЬНУЮ задачу на тему "{query}"
2. Описание должно содержать формат ввода и вывода
3. Примеры должны быть с РЕАЛЬНЫМИ числами
4. Тесты должны покрывать базовые и граничные случаи

КРИТИЧЕСКИ ВАЖНО для тестов:
- Каждая строка ввода разделяется символом \\n (перенос строки)
- НЕ используй пробелы для разделения строк!
- Пример: "3\\n1 2 3\\n4 5 6\\n7 8 9" - это 4 строки ввода

ОТВЕТЬ ТОЛЬКО ВАЛИДНЫМ JSON (без комментариев):
{{
    "title": "Название задачи на русском",
    "description": "Полное описание задачи.\\n\\nФормат ввода:\\n...\\n\\nФормат вывода:\\n...",
    "hashtags": ["{query}"],
    "level": "{level}",
    "examples": [
        {{"input": "3\\n1 2 3", "output": "6", "explanation": "Сумма трёх чисел"}}
    ],
    "test_cases": [
        {{"input": "3\\n1 2 3", "output": "6", "category": "basic"}},
        {{"input": "1\\n0", "output": "0", "category": "edge"}}
    ],
    "hidden_tests": [
        {{"input": "5\\n1 2 3 4 5", "output": "15", "category": "basic", "points": 10}}
    ],
    "hints": [
        {{"level": 1, "text": "Подумай о структуре данных", "penalty": 0.05}},
        {{"level": 2, "text": "Используй подходящий алгоритм", "penalty": 0.15}}
    ],
    "constraints": {{"time_limit_ms": 2000, "memory_limit_mb": 256}},
    "new_hashtag": null,
    "estimated_time_minutes": 20
}}"""


TASK_GENERATION_PROMPT_SIMPLE = """/no_think Создай задачу для технического интервью.

Тема: {query}
Уровень: {level}
Язык: {language}

ВАЖНО: В тестах используй \\n для переноса строк! Пример: "3\\nстрока1\\nстрока2\\nстрока3"

Верни JSON:
{{
    "title": "Название на русском",
    "description": "Условие задачи.\\n\\nФормат ввода:\\n...\\n\\nФормат вывода:\\n...",
    "hashtags": ["{query}"],
    "level": "{level}",
    "examples": [{{"input": "3\\n1 2 3", "output": "6", "explanation": "1+2+3=6"}}],
    "test_cases": [{{"input": "2\\n5 5", "output": "10", "category": "basic"}}],
    "hidden_tests": [{{"input": "1\\n100", "output": "100", "category": "edge", "points": 10}}],
    "hints": [{{"level": 1, "text": "Подсказка", "penalty": 0.05}}],
    "constraints": {{"time_limit_ms": 1000, "memory_limit_mb": 256}},
    "estimated_time_minutes": 10
}}

Создай уникальную задачу на тему "{query}"!"""


SOLUTION_PROMPT = """/no_think Напиши решение задачи.

**Задача:**
{task_description}

**Примеры:**
{examples}

**Хэштеги (подсказка по технике):**
{hashtags}

**Язык:** {language}

Требования:
- Читай из stdin, пиши в stdout
- Используй технику из хэштегов
- Код должен быть эффективным

Верни ТОЛЬКО код."""


# ============== Multi-File Task Prompts ==============

MULTIFILE_TASK_PROMPT = """/no_think Ты эксперт по созданию задач для технических интервью.

Создай задачу типа "{task_type}" по теме: {query}
Уровень: {level}
Язык: {language}

Типы задач:
- fix_bug: найти и исправить баги в коде
- complete: дописать реализацию функций
- refactor: улучшить/рефакторить код
- multi_file: работа с несколькими файлами

Требования:
1. Создай реалистичный проект из нескольких файлов
2. Для fix_bug: вставь баги в код (но сохрани правильную версию в solution_files)
3. Для complete: оставь # TODO метки где нужно дописать код
4. Файлы должны импортировать друг друга
5. Добавь unit-тесты для проверки

Верни JSON:
{{
    "title": "Название задачи",
    "description": "Описание что нужно сделать",
    "task_type": "{task_type}",
    "hashtags": ["{query}"],
    "level": "{level}",
    "objectives": ["Цель 1", "Цель 2"],
    "files": [
        {{
            "filename": "main.py",
            "path": "",
            "content": "Код файла",
            "role": "main",
            "editable": true
        }},
        {{
            "filename": "utils.py",
            "path": "",
            "content": "Код модуля",
            "role": "module",
            "editable": true
        }}
    ],
    "entry_point": "main.py",
    "solution_files": [
        {{
            "filename": "main.py",
            "content": "Правильный код"
        }}
    ],
    "test_cases": [
        {{"input": "", "output": "Ожидаемый вывод", "category": "basic", "points": 10}}
    ],
    "unit_tests": [
        {{
            "test_name": "test_function",
            "test_code": "from main import func\\nassert func(1) == 2",
            "points": 15
        }}
    ],
    "hints": [
        {{"level": 1, "text": "Подсказка", "penalty": 0.1, "for_file": "main.py"}}
    ],
    "estimated_time_minutes": 25
}}"""


BUGFIX_TASK_PROMPT = """/no_think Создай задачу на поиск и исправление багов.

Тема: {query}
Уровень: {level}
Язык: {language}

Требования:
1. Создай проект из 2-3 файлов с багами
2. Баги должны быть реалистичными (ошибки в логике, off-by-one, неправильные условия)
3. Сохрани правильную версию в solution_files
4. Добавь тесты которые падают из-за багов

Примеры багов:
- Неправильный индекс (i < len вместо i <= len)
- Ошибка в формуле
- Необработанный граничный случай
- Неправильный тип данных

Верни JSON:
{{
    "title": "Название",
    "description": "Описание проблемы. Найдите и исправьте баги.",
    "task_type": "fix_bug",
    "hashtags": ["{query}", "debugging"],
    "level": "{level}",
    "num_bugs": 2,
    "objectives": ["Найти баг в функции X", "Исправить ошибку в модуле Y"],
    "files": [
        {{"filename": "main.py", "content": "Код с багом", "role": "main", "editable": true}},
        {{"filename": "calculator.py", "content": "Модуль с багом", "role": "module", "editable": true}}
    ],
    "entry_point": "main.py",
    "solution_files": [
        {{"filename": "main.py", "content": "Исправленный код"}},
        {{"filename": "calculator.py", "content": "Исправленный модуль"}}
    ],
    "bug_locations": [
        {{"file": "main.py", "line": 10, "hint": "Проверьте условие цикла"}}
    ],
    "test_cases": [
        {{"input": "5", "output": "25", "category": "basic", "points": 10}}
    ],
    "unit_tests": [
        {{"test_name": "test_edge_case", "test_code": "from calculator import square\\nassert square(0) == 0", "points": 15}}
    ],
    "hints": [
        {{"level": 1, "text": "Посмотри на граничные случаи", "penalty": 0.1}}
    ],
    "estimated_time_minutes": 20
}}"""


COMPLETE_FUNCTION_PROMPT = """/no_think Создай задачу на дописывание функций.

Тема: {query}
Уровень: {level}
Язык: {language}

Требования:
1. Создай проект где нужно дописать 1-3 функции
2. Оставь # TODO: метки где нужно написать код
3. Дай чёткие docstring для каждой функции
4. Сохрани полную реализацию в solution_files

Верни JSON:
{{
    "title": "Название",
    "description": "Допишите реализацию функций...",
    "task_type": "complete",
    "hashtags": ["{query}"],
    "level": "{level}",
    "objectives": ["Реализовать функцию X", "Реализовать метод Y"],
    "functions_to_complete": [
        {{"file": "utils.py", "function_name": "calculate", "signature": "def calculate(x: int) -> int", "docstring": "Вычисляет..."}}
    ],
    "files": [
        {{
            "filename": "main.py",
            "content": "from utils import calculate\\n\\nif __name__ == '__main__':\\n    print(calculate(int(input())))",
            "role": "main",
            "editable": false
        }},
        {{
            "filename": "utils.py",
            "content": "def calculate(x: int) -> int:\\n    \\\"\\\"\\\"\u0412ычисляет квадрат числа.\\\"\\\"\\\"\\n    # TODO: Реализуйте функцию\\n    pass",
            "role": "module",
            "editable": true,
            "todo_markers": ["# TODO: Реализуйте функцию"]
        }}
    ],
    "entry_point": "main.py",
    "solution_files": [
        {{"filename": "utils.py", "content": "def calculate(x: int) -> int:\\n    return x * x"}}
    ],
    "test_cases": [
        {{"input": "5", "output": "25", "category": "basic", "points": 10}}
    ],
    "unit_tests": [
        {{"test_name": "test_calculate", "test_code": "from utils import calculate\\nassert calculate(3) == 9", "points": 15}}
    ],
    "hints": [
        {{"level": 1, "text": "Используй оператор **", "penalty": 0.1, "for_file": "utils.py"}}
    ],
    "estimated_time_minutes": 15
}}"""


NOVELTY_CHECK_PROMPT = """/no_think Проверь уникальность задачи.

**Новая задача:**
{new_task}

**Существующие задачи с такими же хэштегами:**
{existing_tasks}

Оцени насколько новая задача УНИКАЛЬНА (не копия существующих).

Верни JSON:
{{
    "is_unique": true/false,
    "novelty_score": 0.0-1.0,
    "similar_to": "id похожей задачи или null",
    "reason": "почему уникальна/не уникальна"
}}"""


# ============== Solution-First Prompts (OPTIMIZED) ==============
# Баланс между скоростью и качеством

# Словарь примеров задач по темам для лучшего соответствия
TOPIC_EXAMPLES = {
    "ооп": "Реализуй класс банковского счёта с методами deposit, withdraw, get_balance. Поддержи проверку на отрицательный баланс.",
    "oop": "Реализуй класс банковского счёта с методами deposit, withdraw, get_balance. Поддержи проверку на отрицательный баланс.",
    "классы": "Создай класс Rectangle с методами area(), perimeter() и is_square().",
    "наследование": "Реализуй иерархию классов: Animal -> Dog, Cat с методом speak().",
    "полиморфизм": "Создай систему фигур (Circle, Rectangle, Triangle) с общим методом area().",
    "инкапсуляция": "Реализуй класс Password с приватным хранением и валидацией.",
    "массивы": "Найди два числа в массиве, сумма которых равна заданному числу.",
    "строки": "Подсчитай количество уникальных слов в тексте.",
    "сортировка": "Отсортируй массив объектов по нескольким полям.",
    "поиск": "Реализуй бинарный поиск в отсортированном массиве.",
    "стек": "Реализуй стек с операциями push, pop, peek и min за O(1).",
    "очередь": "Реализуй очередь с приоритетами.",
    "хэш": "Найди первый неповторяющийся символ в строке.",
    "рекурсия": "Вычисли N-е число Фибоначчи с мемоизацией.",
    "оптимизир": "Оптимизируй алгоритм поиска дубликатов с O(n²) до O(n) используя хэш-таблицу.",
    "оптимизац": "Оптимизируй алгоритм поиска дубликатов с O(n²) до O(n) используя хэш-таблицу.",
    "рефактор": "Улучши код: замени вложенные циклы на более эффективный алгоритм.",
    "улучш": "Улучши производительность кода сортировки большого массива.",
    "ускор": "Ускорь алгоритм подсчёта частоты элементов в массиве.",
    "существующ": "Оптимизируй существующий код поиска максимума в матрице.",
    "default": "Реши алгоритмическую задачу с использованием указанной техники."
}

# Описание сложности по уровням
LEVEL_DESCRIPTIONS = {
    "junior": {
        "complexity": "простая",
        "description": "базовые концепции, простая логика, 1-2 класса/функции",
        "time": 10,
        "test_count": 5,
        "examples": "простые числа, короткие строки, маленькие массивы (до 10 элементов)"
    },
    "middle": {
        "complexity": "средняя", 
        "description": "несколько классов, паттерны проектирования, обработка ошибок",
        "time": 20,
        "test_count": 7,
        "examples": "средние данные (10-1000 элементов), несколько сценариев"
    },
    "senior": {
        "complexity": "сложная",
        "description": "архитектура, оптимизация, edge cases, многопоточность",
        "time": 30,
        "test_count": 10,
        "examples": "большие данные (10000+ элементов), сложные граничные случаи, стресс-тесты"
    }
}

def _get_topic_example(query: str) -> str:
    """Get relevant example for the topic"""
    query_lower = query.lower()
    for key, example in TOPIC_EXAMPLES.items():
        if key in query_lower:
            return example
    return TOPIC_EXAMPLES["default"]

def _get_level_info(level: str) -> dict:
    """Get level description"""
    return LEVEL_DESCRIPTIONS.get(level.lower(), LEVEL_DESCRIPTIONS["middle"])

# Этап 1: Генерация задачи - КАЧЕСТВЕННЫЙ промпт с учётом уровня
SOLUTION_FIRST_TASK_PROMPT = """/no_think Создай задачу для технического интервью.

ТЕМА: {query}
УРОВЕНЬ СЛОЖНОСТИ: {level} ({level_complexity})

Требования к уровню {level}:
- {level_description}
- Время решения: ~{level_time} минут

ВАЖНО: Задача ОБЯЗАТЕЛЬНО должна быть связана с темой "{query}"!

Примеры задач по этой теме:
{topic_example}

Требования к задаче:
1. Задача ДОЛЖНА использовать концепции из темы "{query}"
2. Сложность ДОЛЖНА соответствовать уровню {level}
3. Название должно отражать суть задачи
4. Описание должно быть подробным с форматом ввода/вывода
5. Тесты должны включать: базовые случаи, граничные случаи, большие данные

JSON (создай минимум {test_count} тестов!):
{{
  "title": "Название задачи (связанное с {query})",
  "description": "Подробное условие задачи уровня {level}.\\n\\nФормат ввода:\\n...\\n\\nФормат вывода:\\n...",
  "hashtags": ["{query}"],
  "level": "{level}",
  "test_inputs": [
    {{"input": "простой тест", "description": "базовый случай", "is_hidden": false, "time_limit_ms": 500, "points": 5}},
    {{"input": "другой тест", "description": "второй базовый", "is_hidden": false, "time_limit_ms": 500, "points": 5}},
    {{"input": "граничный случай 1", "description": "пустой/минимальный вход", "is_hidden": true, "time_limit_ms": 1000, "points": 10}},
    {{"input": "граничный случай 2", "description": "максимальные значения", "is_hidden": true, "time_limit_ms": 2000, "points": 15}},
    {{"input": "большие данные (1000+ элементов)", "description": "стресс-тест на производительность", "is_hidden": true, "time_limit_ms": 3000, "points": 20}}
  ],
  "hints": [
    {{"level": 1, "text": "Подсказка по структуре решения", "penalty": 0.05}},
    {{"level": 2, "text": "Более детальная подсказка", "penalty": 0.15}}
  ],
  "constraints": {{"time_limit_ms": 2000, "memory_limit_mb": 256}},
  "estimated_time_minutes": {level_time}
}}

ВАЖНО для time_limit_ms:
- Простые тесты (маленькие данные): 500-1000 мс
- Средние тесты: 1000-2000 мс
- Стресс-тесты (большие данные): 2000-5000 мс
- Учитывай сложность алгоритма: O(n) быстрее чем O(n²)"""

# Этап 2: Генерация решения
SOLUTION_FIRST_CODE_PROMPT = """/no_think Напиши решение на Python.

Задача: {description}

Пример входа: {example_input}

Требования:
- Читай из stdin (input())
- Пиши в stdout (print())
- Код должен быть рабочим

Верни ТОЛЬКО код:"""

# Запасной промпт (если первый не сработал)
SOLUTION_FIRST_SIMPLE_PROMPT = """/no_think Создай КОНКРЕТНУЮ задачу по программированию.

Тема: {query}
Уровень: {level}

ВАЖНО: Придумай КОНКРЕТНУЮ задачу, НЕ абстрактную!

Примеры ХОРОШИХ названий:
- "Найди два числа с заданной суммой"
- "Оптимизируй поиск дубликатов"
- "Реализуй LRU кэш"

Примеры ПЛОХИХ названий (НЕ ИСПОЛЬЗУЙ!):
- "Оптимизация кода" (слишком абстрактно)
- "Задача на массивы" (не конкретно)

Верни JSON:
{{
  "title": "Конкретное название задачи",
  "description": "Дано: ...\\nТребуется: ...\\n\\nФормат ввода:\\nПервая строка содержит число N.\\nВторая строка содержит N чисел.\\n\\nФормат вывода:\\nВыведите результат.",
  "test_inputs": [
    {{"input": "5\\n1 2 3 4 5", "description": "базовый случай"}},
    {{"input": "1\\n0", "description": "граничный случай"}}
  ]
}}"""

# Конкретные задачи для абстрактных запросов
ABSTRACT_QUERY_MAPPING = {
    # Оптимизация
    "оптимизировать существующий код": "Оптимизируй алгоритм поиска дубликатов в массиве с O(n²) до O(n)",
    "оптимизация кода": "Оптимизируй алгоритм сортировки пузырьком до быстрой сортировки",
    "оптимизация": "Оптимизируй алгоритм поиска максимальной подпоследовательности",
    "оптимизировать": "Оптимизируй функцию проверки анаграмм с O(n log n) до O(n)",
    
    # Рефакторинг
    "рефакторинг": "Улучши код: замени вложенные циклы на использование словаря",
    "рефакторинг кода": "Рефакторинг: преобразуй процедурный код в объектно-ориентированный",
    
    # Улучшение
    "улучшить код": "Улучши производительность функции подсчёта частоты слов",
    "улучшение кода": "Улучши алгоритм: замени рекурсию на итерацию с мемоизацией",
    
    # Ускорение
    "ускорить код": "Ускорь алгоритм поиска подстроки в строке",
    "ускорение": "Ускорь функцию вычисления чисел Фибоначчи используя матричное возведение в степень",
    
    # Исправление
    "исправить баг": "Найди и исправь баг в алгоритме бинарного поиска",
    "исправить ошибку": "Найди и исправь ошибку в реализации связного списка",
    "дебаг": "Отладь функцию сортировки слиянием - она неправильно сливает массивы",
    "debug": "Найди баг в алгоритме обхода графа в глубину",
    
    # Общие
    "написать код": "Реализуй алгоритм поиска кратчайшего пути в графе",
    "реализовать": "Реализуй структуру данных MinHeap с операциями insert и extract_min",
    "создать": "Создай класс для работы с матрицами: сложение, умножение, транспонирование",
}

def _make_query_concrete(query: str) -> str:
    """Convert abstract queries to concrete task descriptions"""
    query_lower = query.lower().strip()
    
    # Check for exact matches first
    if query_lower in ABSTRACT_QUERY_MAPPING:
        return ABSTRACT_QUERY_MAPPING[query_lower]
    
    # Check for partial matches
    for abstract, concrete in ABSTRACT_QUERY_MAPPING.items():
        if abstract in query_lower or query_lower in abstract:
            return concrete
    
    # If query is too short or generic, make it more specific
    generic_words = ["код", "задача", "алгоритм", "программа", "функция"]
    if len(query_lower) < 15 or any(query_lower == word for word in generic_words):
        return f"Реализуй эффективный алгоритм для: {query}"
    
    return query


class HashtagTaskGenerator:
    """
    Task generator that uses hashtag taxonomy for context.
    """
    
    def __init__(self):
        self.client = client
        self.http_client = http_client
    
    def _fix_test_formatting(self, task: Dict) -> Dict:
        """
        Fix test case formatting - ensure proper newlines.
        LLM sometimes uses spaces instead of \\n for line breaks.
        """
        import re
        
        def fix_input(input_str: str) -> str:
            if not input_str:
                return input_str
            
            # Already has newlines - probably correct
            if '\n' in input_str:
                return input_str
            
            # Pattern 1: "N num1 num2 num3..." -> "N\nnum1 num2 num3..."
            # Common pattern: first number is count, rest is data
            match = re.match(r'^(\d+)\s+(.+)$', input_str)
            if match:
                n = int(match.group(1))
                rest = match.group(2)
                
                # Check if rest looks like numbers (array input)
                rest_parts = rest.split()
                if all(re.match(r'^-?\d+$', p) for p in rest_parts):
                    # It's "N num1 num2 ..." -> "N\nnum1 num2 ..."
                    return f"{n}\n{rest}"
                
                # Check for command patterns
                commands = ['add', 'remove', 'search', 'list', 'get', 'set', 'delete', 
                           'insert', 'update', 'find', 'push', 'pop', 'enqueue', 'dequeue']
                has_commands = any(cmd in input_str.lower() for cmd in commands)
                
                if has_commands and n > 0:
                    # Reconstruct with newlines for commands
                    result = [str(n)]
                    current_line = []
                    
                    for part in rest_parts:
                        if part.lower() in commands:
                            if current_line:
                                result.append(' '.join(current_line))
                            current_line = [part]
                        else:
                            current_line.append(part)
                    
                    if current_line:
                        result.append(' '.join(current_line))
                    
                    if len(result) > 1:
                        return '\n'.join(result)
                
                # Default: just split after first number
                return f"{n}\n{rest}"
            
            return input_str
        
        # Fix examples
        for ex in task.get('examples', []):
            if 'input' in ex:
                ex['input'] = fix_input(ex['input'])
        
        # Fix test_cases
        for tc in task.get('test_cases', []):
            if 'input' in tc:
                tc['input'] = fix_input(tc['input'])
        
        # Fix hidden_tests
        for ht in task.get('hidden_tests', []):
            if 'input' in ht:
                ht['input'] = fix_input(ht['input'])
        
        return task
    
    async def search_hashtags(self, query: str, section: str) -> List[Dict]:
        """Find relevant hashtags for query"""
        try:
            print(f"[HASHTAG SEARCH] Searching for '{query}' in section '{section}'...")
            resp = await self.http_client.post(
                f"{HASHTAG_SERVICE_URL}/hashtags/search",
                json={"query": query, "section": section, "limit": 5}
            )
            data = resp.json()
            results = data.get("results", [])
            print(f"[HASHTAG SEARCH] Found {len(results)} hashtags")
            return results
        except Exception as e:
            print(f"Hashtag search error: {e}")
            return []
    
    async def get_example_tasks(
        self, 
        hashtags: List[str], 
        level: str,
        section: str,
        limit_per_hashtag: int = 2
    ) -> Dict[str, List[Dict]]:
        """Get example tasks for hashtags"""
        try:
            resp = await self.http_client.post(
                f"{HASHTAG_SERVICE_URL}/tasks/search",
                json={
                    "hashtags": hashtags,
                    "level": level,
                    "section": section,
                    "limit_per_hashtag": limit_per_hashtag,
                    "min_rating": 3.0
                }
            )
            data = resp.json()
            return data.get("tasks_by_hashtag", {})
        except Exception as e:
            print(f"Task search error: {e}")
            return {}
    
    async def get_task_details(self, task_id: str) -> Optional[Dict]:
        """Get full task details from library"""
        try:
            resp = await self.http_client.get(f"{LIBRARY_SERVICE_URL}/tasks/{task_id}")
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        return None
    
    async def suggest_new_hashtag(self, query: str, section: str) -> Optional[Dict]:
        """Ask AI if new hashtag is needed"""
        try:
            resp = await self.http_client.post(
                f"{HASHTAG_SERVICE_URL}/hashtags/suggest",
                json={"query": query, "section": section}
            )
            data = resp.json()
            return data.get("suggestion")
        except Exception as e:
            print(f"Suggest hashtag error: {e}")
            return None
    
    async def create_hashtag(self, hashtag_data: Dict, section: str) -> bool:
        """Create new hashtag"""
        try:
            resp = await self.http_client.post(
                f"{HASHTAG_SERVICE_URL}/hashtags/create",
                json={
                    "id": hashtag_data["id"],
                    "description": hashtag_data["description"],
                    "section": section,
                    "created_by": "ai_generated"
                }
            )
            return resp.status_code == 200
        except Exception as e:
            print(f"Create hashtag error: {e}")
            return False
    
    async def check_novelty(self, task: Dict, existing_tasks: List[Dict]) -> Dict:
        """Check if task is unique enough"""
        if not existing_tasks:
            return {"is_unique": True, "novelty_score": 1.0}
        
        prompt = NOVELTY_CHECK_PROMPT.format(
            new_task=json.dumps(task, ensure_ascii=False)[:1000],
            existing_tasks=json.dumps(existing_tasks, ensure_ascii=False)[:2000]
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=Models.CHAT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=300,
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"Novelty check error: {e}")
            return {"is_unique": True, "novelty_score": 0.7}
    
    async def run_code_for_output(self, code: str, input_data: str, timeout: int = 5) -> Dict:
        """
        Run code with input and get output.
        Used in Solution-First approach to generate test outputs.
        """
        try:
            resp = await self.http_client.post(
                f"{CODE_RUNNER_URL}/run",
                json={
                    "code": code,
                    "input": input_data,
                    "language": "python",
                    "timeout": timeout
                }
            )
            result = resp.json()
            return {
                "success": result.get("success", False),
                "output": result.get("stdout", "").strip(),
                "error": result.get("stderr", "") or result.get("error", ""),
                "execution_time": result.get("execution_time", 0)
            }
        except Exception as e:
            print(f"Run code error: {e}")
            return {"success": False, "output": "", "error": str(e)}
    
    async def generate_tests_from_solution(
        self, 
        code: str, 
        test_inputs: List[Dict]
    ) -> tuple[List[Dict], List[Dict], List[Dict]]:
        """
        Run solution on test inputs to generate test cases with correct outputs.
        Returns: (examples, test_cases, hidden_tests)
        """
        import re
        
        # Fix test input formatting first (add newlines where needed)
        def fix_test_input(input_val) -> str:
            # Handle non-string inputs
            if input_val is None:
                return ""
            if isinstance(input_val, list):
                # Convert list to newline-separated string
                return "\n".join(str(x) for x in input_val)
            if isinstance(input_val, dict):
                # Convert dict to JSON string
                return json.dumps(input_val, ensure_ascii=False)
            
            input_str = str(input_val)
            
            if not input_str or '\n' in input_str:
                return input_str
            # Pattern: "N num1 num2..." -> "N\nnum1 num2..."
            match = re.match(r'^(\d+)\s+(.+)$', input_str)
            if match:
                return f"{match.group(1)}\n{match.group(2)}"
            return input_str
        
        # Fix all test inputs
        for ti in test_inputs:
            if "input" in ti:
                ti["input"] = fix_test_input(ti["input"])
        
        examples = []
        test_cases = []
        hidden_tests = []
        
        print(f"\n[SOLUTION-FIRST] Running {len(test_inputs)} tests in PARALLEL...")
        start_time = time.time()
        
        # Run all tests in parallel for speed
        tasks = [
            self.run_code_for_output(code, test_input.get("input", ""))
            for test_input in test_inputs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, (test_input, result) in enumerate(zip(test_inputs, results)):
            input_data = test_input.get("input", "")
            description = test_input.get("description", f"Test {i+1}")
            is_hidden = test_input.get("is_hidden", False)
            
            # Handle exceptions from gather
            if isinstance(result, Exception):
                print(f"  [TEST {i+1}] ERROR: {result}")
                continue
            
            if result.get("success"):
                output = result["output"]
                execution_time = result.get("execution_time", 0)
                execution_time_ms = int(execution_time * 1000) if execution_time else 0
                
                # Get time_limit_ms from LLM (or calculate based on actual execution)
                time_limit_ms = test_input.get("time_limit_ms")
                if not time_limit_ms:
                    # Fallback: set limit as 10x actual execution time, min 500ms, max 5000ms
                    time_limit_ms = max(500, min(5000, execution_time_ms * 10)) if execution_time_ms > 0 else 2000
                
                # Get points from LLM or default
                points = test_input.get("points", 10)
                
                # Determine category based on description
                desc_lower = description.lower()
                if "граничн" in desc_lower or "edge" in desc_lower or "максим" in desc_lower or "миним" in desc_lower or "пуст" in desc_lower:
                    category = "edge"
                elif "стресс" in desc_lower or "больш" in desc_lower or "нагрузк" in desc_lower or "производ" in desc_lower:
                    category = "stress"
                else:
                    category = "basic"
                
                test_case = {
                    "input": input_data,
                    "output": output,
                    "description": description,
                    "category": category,
                    "time_limit_ms": time_limit_ms,
                    "execution_time_ms": execution_time_ms,
                    "points": points
                }
                
                # Use is_hidden flag from LLM, or fallback to position-based logic
                if is_hidden:
                    # Hidden test - use LLM points or default based on category
                    if not test_input.get("points"):
                        test_case["points"] = 10 if category == "basic" else (15 if category == "edge" else 20)
                    hidden_tests.append(test_case)
                    print(f"  [TEST {i+1}] HIDDEN ({category}, {time_limit_ms}ms, {test_case['points']}pts): {input_data[:25]}...")
                else:
                    # First non-hidden test becomes example
                    if len(examples) == 0:
                        examples.append({
                            "input": input_data,
                            "output": output,
                            "explanation": description
                        })
                    test_cases.append(test_case)
                    print(f"  [TEST {i+1}] VISIBLE ({category}, {time_limit_ms}ms, {test_case['points']}pts): {input_data[:25]}...")
            else:
                print(f"  [TEST {i+1}] FAILED: {result.get('error', 'unknown')[:50]}")
        
        # Ensure we always have hidden tests - if none marked, make last ones hidden
        if len(hidden_tests) == 0 and len(test_cases) > 2:
            # Move last tests to hidden
            while len(test_cases) > 2 and len(hidden_tests) < 3:
                tc = test_cases.pop()
                tc["points"] = 10
                hidden_tests.insert(0, tc)
            print(f"  [AUTO] Moved {len(hidden_tests)} tests to hidden")
        
        print(f"[SOLUTION-FIRST] Tests done in {time.time()-start_time:.1f}s: {len(test_cases)} visible, {len(hidden_tests)} hidden")
        
        return examples, test_cases, hidden_tests
    
    async def generate_task_solution_first(
        self,
        query: str,
        section: str,
        level: str,
        language: str,
        context_section: str = ""
    ) -> Dict:
        """
        OPTIMIZED: Generate task using Solution-First approach.
        
        Optimizations:
        - Reduced prompt sizes (fewer tokens = faster response)
        - Timeouts on LLM calls (45s max)
        - Reduced max_tokens (1500 instead of 3000)
        - Single retry with simpler prompt
        - Parallel test execution
        """
        import re
        start_time = time.time()
        
        # Make abstract queries more concrete
        original_query = query
        query = _make_query_concrete(query)
        if query != original_query:
            print(f"[QUERY] Converted abstract query: '{original_query}' -> '{query}'")
        
        print(f"\n{'='*60}")
        print(f"[SOLUTION-FIRST] Starting FAST generation for: {query}")
        print(f"{'='*60}")
        
        # ========== STAGE 1: Generate task structure (OPTIMIZED) ==========
        print(f"[STAGE 1] Generating task structure for level: {level}...")
        
        # Get topic-specific example for better relevance
        topic_example = _get_topic_example(query)
        
        # Get level-specific parameters
        level_info = _get_level_info(level)
        
        prompt = SOLUTION_FIRST_TASK_PROMPT.format(
            query=query,
            level=level,
            topic_example=topic_example,
            level_complexity=level_info["complexity"],
            level_description=level_info["description"],
            level_time=level_info["time"],
            test_count=level_info["test_count"]
        )
        
        task_data = None
        last_error = None
        
        # Single attempt with timeout
        raw_content = await _llm_call_with_timeout(
            self.client,
            Models.CHAT,
            [{"role": "user", "content": prompt}],
            temperature=0.5,  # Slightly higher for creativity
            max_tokens=2000,  # Enough for detailed task
            response_format={"type": "json_object"},
            timeout=LLM_TIMEOUT
        )
        
        if raw_content:
            try:
                print(f"[STAGE 1] Response: {len(raw_content)} chars in {time.time()-start_time:.1f}s")
                
                # Fast JSON extraction
                json_content = raw_content.strip()
                if "```" in json_content:
                    match = re.search(r'```(?:json)?\s*(.*?)\s*```', json_content, re.DOTALL)
                    if match:
                        json_content = match.group(1)
                
                if not json_content.startswith("{"):
                    start = json_content.find("{")
                    if start != -1:
                        json_content = json_content[start:]
                
                task_data = json.loads(json_content)
                
                # Quality validation - reject template/placeholder responses
                title = task_data.get("title", "")
                desc = task_data.get("description", "")
                
                # Check for placeholder/template titles
                bad_titles = ["название", "title", "конкретное название", "...", "задача"]
                if not title or len(title) < 5 or title.lower().strip() in bad_titles:
                    raise ValueError(f"Bad title: '{title}' - too generic or placeholder")
                
                # Check for placeholder descriptions
                if not desc or len(desc) < 50 or "..." in desc[:100]:
                    raise ValueError(f"Bad description: too short or contains placeholders")
                
                # Check topic relevance - task should mention the topic or related concepts
                query_lower = query.lower()
                title_lower = title.lower()
                desc_lower = desc.lower()
                
                # Keywords that indicate topic relevance
                topic_keywords = {
                    "ооп": ["класс", "объект", "метод", "наследован", "инкапсуляц", "полиморф", "class", "self", "__init__"],
                    "oop": ["класс", "объект", "метод", "наследован", "инкапсуляц", "полиморф", "class", "self", "__init__"],
                    "массив": ["массив", "список", "элемент", "индекс", "array", "list"],
                    "строк": ["строк", "символ", "текст", "слов", "string", "char"],
                    "сортировк": ["сортир", "упорядоч", "sort", "порядок"],
                    "поиск": ["поиск", "найти", "найди", "search", "find"],
                    "стек": ["стек", "stack", "push", "pop", "lifo"],
                    "очередь": ["очередь", "queue", "fifo", "enqueue", "dequeue"],
                    "рекурси": ["рекурси", "рекурсив", "recursive", "recursion"],
                }
                
                # Find relevant keywords for the query
                relevant_keywords = []
                for key, keywords in topic_keywords.items():
                    if key in query_lower:
                        relevant_keywords.extend(keywords)
                
                # If we have topic keywords, check if task mentions any of them
                if relevant_keywords:
                    found_keyword = any(kw in title_lower or kw in desc_lower for kw in relevant_keywords)
                    if not found_keyword:
                        print(f"[STAGE 1] Warning: Task may not be relevant to '{query}' - no keywords found")
                        # Don't fail, just log warning - LLM might have used different terminology
                
                # Add default test_inputs if missing
                if not task_data.get("test_inputs"):
                    task_data["test_inputs"] = [
                        {"input": "3\n1 2 3", "description": "basic"},
                        {"input": "1\n0", "description": "edge"}
                    ]
                
                print(f"[STAGE 1] Task: {task_data.get('title')}")
                
            except Exception as e:
                print(f"[STAGE 1] Parse error: {e}")
                last_error = str(e)
        else:
            last_error = "LLM timeout or error"
        
        # Fallback: try simpler prompt
        if not task_data:
            print(f"[STAGE 1] Trying fallback prompt...")
            raw_content = await _llm_call_with_timeout(
                self.client,
                Models.CHAT,
                [{"role": "user", "content": SOLUTION_FIRST_SIMPLE_PROMPT.format(query=query, level=level)}],
                temperature=0.2,
                max_tokens=1000,
                response_format={"type": "json_object"},
                timeout=30  # Shorter timeout for fallback
            )
            
            if raw_content:
                try:
                    task_data = json.loads(raw_content)
                    if not task_data.get("test_inputs"):
                        task_data["test_inputs"] = [{"input": "1\n5", "description": "test"}]
                except:
                    pass
        
        if not task_data or not task_data.get("title"):
            print(f"[STAGE 1] FAILED after {time.time()-start_time:.1f}s")
            return {"success": False, "error": f"Stage 1 failed: {last_error or 'No valid task'}"}
        
        # ========== STAGE 2: Generate solution code (OPTIMIZED) ==========
        print(f"[STAGE 2] Generating solution code...")
        stage2_start = time.time()
        
        test_inputs = task_data.get("test_inputs", [])
        example_input = test_inputs[0].get("input", "") if test_inputs else ""
        
        code_prompt = SOLUTION_FIRST_CODE_PROMPT.format(
            description=task_data.get("description", "")[:500],  # Limit description
            example_input=example_input[:100]  # Limit example
        )
        
        # Single attempt with timeout
        solution = await _llm_call_with_timeout(
            self.client,
            Models.CODE,
            [{"role": "user", "content": code_prompt}],
            temperature=0.2,
            max_tokens=1500,  # Reduced
            timeout=LLM_TIMEOUT
        )
        
        if solution:
            # Fast code extraction
            if "```" in solution:
                match = re.search(r'```(?:python)?\s*(.*?)\s*```', solution, re.DOTALL)
                if match:
                    solution = match.group(1)
            solution = solution.strip()
            print(f"[STAGE 2] Solution: {len(solution)} chars in {time.time()-stage2_start:.1f}s")
        
        if not solution:
            return {"success": False, "error": f"Stage 2 failed: {last_error}"}
        
        # ========== STAGE 3: Generate tests by running solution ==========
        print(f"[STAGE 3] Running solution on test inputs...")
        
        # Add more edge cases if needed
        if len(test_inputs) < 5:
            test_inputs.extend([
                {"input": "1", "description": "минимальный ввод"},
                {"input": "0", "description": "нулевой случай"},
            ])
        
        examples, test_cases, hidden_tests = await self.generate_tests_from_solution(
            solution, test_inputs[:8]
        )
        
        # Check if we got valid tests
        if not test_cases:
            print(f"[STAGE 3] No valid tests generated, solution may be broken")
            return {"success": False, "error": "Solution failed on all test inputs"}
        
        # Build final task
        task = {
            "title": task_data.get("title", ""),
            "description": task_data.get("description", ""),
            "hashtags": task_data.get("hashtags", [query]),
            "level": level,
            "examples": examples,
            "test_cases": test_cases,
            "hidden_tests": hidden_tests,
            "hints": task_data.get("hints", [{"level": 1, "text": "Подумай о структуре данных", "penalty": 0.05}]),
            "constraints": task_data.get("constraints", {"time_limit_ms": 2000, "memory_limit_mb": 256}),
            "estimated_time_minutes": task_data.get("estimated_time_minutes", 20)
        }
        
        print(f"[SOLUTION-FIRST] Task generated successfully!")
        print(f"[SOLUTION-FIRST] Tests: {len(test_cases)} visible, {len(hidden_tests)} hidden")
        print(f"{'='*60}\n")
        
        return {
            "success": True,
            "task": task,
            "solution": solution,
            "validation": {
                "all_passed": True,
                "passed": len(test_cases) + len(hidden_tests),
                "failed": 0
            }
        }
    
    async def generate_solution(self, task: Dict, language: str = "python") -> Optional[str]:
        """Generate solution for task"""
        examples_text = "\n".join([
            f"Вход: {ex.get('input', '')}\nВыход: {ex.get('output', '')}"
            for ex in task.get("examples", [])[:3]
        ])
        
        hashtags_text = ", ".join([f"#{h}" for h in task.get("hashtags", [])])
        
        prompt = SOLUTION_PROMPT.format(
            task_description=task.get("description", ""),
            examples=examples_text,
            hashtags=hashtags_text,
            language=language
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=Models.CODE,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2000
            )
            
            code = response.choices[0].message.content
            
            # Clean markdown
            if "```" in code:
                import re
                match = re.search(r'```(?:\w+)?\n(.*?)```', code, re.DOTALL)
                if match:
                    code = match.group(1)
            
            return code.strip()
        except Exception as e:
            print(f"Solution generation error: {e}")
            return None
    
    async def validate_solution(self, code: str, test_cases: List[Dict]) -> Dict:
        """Validate solution against tests"""
        try:
            resp = await self.http_client.post(
                f"{CODE_RUNNER_URL}/validate",
                json={
                    "code": code,
                    "test_cases": [
                        {"input": t.get("input", ""), "output": t.get("output", "")}
                        for t in test_cases
                    ]
                }
            )
            return resp.json()
        except Exception as e:
            print(f"Validation error: {e}")
            return {"error": str(e), "all_passed": False, "passed": 0, "failed": len(test_cases)}
    
    async def fix_solution(self, code: str, task: Dict, validation: Dict, language: str = "python") -> Optional[str]:
        """Fix solution based on failed tests"""
        if not validation or not code:
            return None
        
        # Get failed tests - check both 'tests' and 'results' keys
        tests_list = validation.get("tests", []) or validation.get("results", [])
        failed_tests = [t for t in tests_list if not t.get("passed")]
        if not failed_tests:
            return code
        
        # Build prompt with failed test info
        failed_info = []
        for ft in failed_tests[:3]:  # Limit to 3 failed tests
            test_num = ft.get('test_number') or ft.get('num', '?')
            input_data = ft.get('input', 'N/A')
            expected = ft.get('expected', '')
            actual = ft.get('actual', '')
            error = ft.get('error', '')
            
            # Format input for display (show newlines)
            input_display = input_data.replace('\n', '\\n')[:150] if input_data else 'N/A'
            
            failed_info.append(f"""Тест {test_num}:
  Вход: {input_display}
  Ожидалось: "{expected[:100]}"
  Получено: "{actual[:100]}"
  Ошибка: {error[:150] if error else 'нет'}""")
        
        # Get example from task for reference
        examples = task.get('examples', [])
        example_text = ""
        if examples:
            ex = examples[0]
            ex_input = ex.get('input', '').replace('\n', '\\n')[:100]
            ex_output = ex.get('output', '')[:100]
            example_text = f"""
**Пример из условия:**
Вход: {ex_input}
Выход: {ex_output}
"""
        
        prompt = f"""/no_think Исправь код. Тесты не проходят.

**Задача:**
{task.get('description', '')[:800]}
{example_text}
**Текущий код (с ошибками):**
```{language}
{code}
```

**Проваленные тесты:**
{chr(10).join(failed_info)}

**Анализ проблемы:**
- Если "Получено" пусто - код не печатает результат или падает с ошибкой
- Проверь что код читает ВСЕ входные данные правильно
- Проверь что код выводит результат через print()

**Требования:**
- Исправь ошибки чтобы ВСЕ тесты проходили
- Читай из stdin через input(), пиши в stdout через print()
- Верни ТОЛЬКО исправленный полный код без объяснений"""

        print(f"[FIX] Sending fix request to LLM...")
        
        try:
            response = await self.client.chat.completions.create(
                model=Models.CODE,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=3000
            )
            
            fixed_code = response.choices[0].message.content
            
            # Clean markdown
            if "```" in fixed_code:
                import re
                match = re.search(r'```(?:\w+)?\n(.*?)```', fixed_code, re.DOTALL)
                if match:
                    fixed_code = match.group(1)
            
            fixed_code = fixed_code.strip()
            
            # Log if code changed
            if fixed_code != code:
                print(f"[FIX] Code was modified ({len(code)} -> {len(fixed_code)} chars)")
            else:
                print(f"[FIX] Code unchanged")
            
            return fixed_code
        except Exception as e:
            print(f"Fix solution error: {e}")
            return code  # Return original if fix fails
    
    async def generate(
        self,
        query: str,
        section: str = Section.LIVE_CODING,
        level: str = Level.MIDDLE,
        language: str = "python",
        use_solution_first: bool = True,  # Solution-First by default
        fast_mode: bool = True  # FAST: Skip hashtag/example search
    ) -> Dict:
        """
        OPTIMIZED: Main generation pipeline.
        
        Fast mode (default):
        - Skip hashtag search (saves ~2-5s)
        - Skip example tasks fetch (saves ~3-10s)
        - Skip novelty check (saves ~5-10s)
        - Direct Solution-First generation
        
        Full mode (fast_mode=False):
        - Search hashtags for context
        - Get example tasks
        - Check novelty
        """
        start_time = time.time()
        
        result = {
            "status": "pending",
            "query": query,
            "section": section,
            "level": level,
            "stages": [],
            "approach": "solution_first" if use_solution_first else "legacy",
            "fast_mode": fast_mode
        }
        
        print(f"\n{'='*60}")
        print(f"[TASK GENERATION] Query: {query}, Section: {section}, Level: {level}")
        print(f"[TASK GENERATION] Approach: {'Solution-First' if use_solution_first else 'Legacy'}")
        print(f"[TASK GENERATION] Fast mode: {fast_mode}")
        print(f"{'='*60}")
        
        # ============== FAST PATH: Direct generation ==============
        if use_solution_first and fast_mode:
            result["stages"].append({"name": "Solution-First Generation", "status": "running"})
            
            sf_result = await self.generate_task_solution_first(
                query=query,
                section=section,
                level=level,
                language=language,
                context_section=""  # No context in fast mode
            )
            
            if sf_result.get("success"):
                result["task"] = sf_result["task"]
                result["solution"] = sf_result["solution"]
                result["validation"] = sf_result["validation"]
                result["solution_verified"] = True
                result["stages"][-1]["status"] = "done"
                result["status"] = "success"
                result["execution_time"] = round(time.time() - start_time, 2)
                print(f"[FAST] Task generated in {result['execution_time']}s")
                return result
            else:
                print(f"[FAST] Failed: {sf_result.get('error')}, trying with context...")
                result["stages"][-1]["status"] = "warning"
                result["stages"][-1]["fallback_reason"] = sf_result.get("error")
        
        # ============== FULL PATH: With context ==============
        hashtag_results = []
        all_examples = []
        context_section = ""
        
        if not fast_mode:
            # Stage 1: Search hashtags (for context)
            result["stages"].append({"name": "Hashtag Search", "status": "running"})
            try:
                hashtag_results = await asyncio.wait_for(
                    self.search_hashtags(query, section),
                    timeout=HTTP_TIMEOUT
                )
            except asyncio.TimeoutError:
                print("[HASHTAG] Search timeout, skipping...")
                hashtag_results = []
            
            hashtags = [r["hashtag"]["id"] for r in hashtag_results[:3]]
            result["hashtags"] = hashtags
            result["stages"][-1]["status"] = "done"
            
            # Stage 2: Get example tasks (parallel with timeout)
            if hashtags:
                result["stages"].append({"name": "Example Tasks", "status": "running"})
                try:
                    example_tasks = await asyncio.wait_for(
                        self.get_example_tasks(hashtags, level, section),
                        timeout=HTTP_TIMEOUT
                    )
                    for tag, tasks in example_tasks.items():
                        for t in tasks[:1]:  # Limit to 1 per tag
                            all_examples.append({
                                "id": t["id"],
                                "title": t["title"],
                                "hashtag": tag
                            })
                except asyncio.TimeoutError:
                    print("[EXAMPLES] Fetch timeout, skipping...")
                result["example_count"] = len(all_examples)
                result["stages"][-1]["status"] = "done"
            
            # Build minimal context
            if hashtag_results:
                context_section = f"Хэштеги: {', '.join(hashtags)}"
        
        # ============== SOLUTION-FIRST APPROACH ==============
        if use_solution_first:
            result["stages"].append({"name": "Solution-First Generation", "status": "running"})
            
            sf_result = await self.generate_task_solution_first(
                query=query,
                section=section,
                level=level,
                language=language,
                context_section=context_section
            )
            
            if sf_result.get("success"):
                result["task"] = sf_result["task"]
                result["solution"] = sf_result["solution"]
                result["validation"] = sf_result["validation"]
                result["solution_verified"] = True
                result["stages"][-1]["status"] = "done"
                result["status"] = "success"
                result["execution_time"] = round(time.time() - start_time, 2)
                return result
            else:
                # Fallback to legacy approach
                print(f"[SOLUTION-FIRST] Failed: {sf_result.get('error')}, falling back to legacy...")
                result["stages"][-1]["status"] = "warning"
                result["stages"][-1]["fallback_reason"] = sf_result.get("error")
        
        # ============== LEGACY APPROACH (fallback) ==============
        result["stages"].append({"name": "Task Generation (Legacy)", "status": "running"})
        
        prompt = TASK_GENERATION_PROMPT.format(
            query=query,
            section=section,
            level=level,
            language=language,
            context_section=context_section
        )
        
        max_retries = 3
        last_error = None
        task = None
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    print(f"[INFO] Retrying generation (attempt {attempt+1}/{max_retries+1})...")
                    time.sleep(1)
                
                current_prompt = prompt
                current_temp = 0.4
                if attempt >= 2:
                    print(f"[INFO] Switching to simplified prompt...")
                    current_prompt = TASK_GENERATION_PROMPT_SIMPLE.format(
                        query=query,
                        level=level,
                        language=language
                    )
                    current_temp = 0.3
                
                response = await self.client.chat.completions.create(
                    model=Models.CHAT,
                    messages=[{"role": "user", "content": current_prompt}],
                    temperature=current_temp,
                    max_tokens=3000,
                    response_format={"type": "json_object"}
                )
                
                raw_content = response.choices[0].message.content
                
                if "error" in raw_content.lower() and len(raw_content) < 100:
                    raise Exception(f"API Error: {raw_content}")
                
                if not raw_content or raw_content.strip() in ["{}", ""]:
                    raise Exception("Empty response from LLM")
                
                print(f"\n[LLM RAW RESPONSE] Length: {len(raw_content)} chars")
                
                task = json.loads(raw_content)
                
                if not task.get('title') or not task.get('description'):
                    raise Exception(f"Missing title or description. Got keys: {list(task.keys())}")
                
                print(f"\n[PARSED TASK] Keys: {list(task.keys())}")
                print(f"[PARSED TASK] Title: {task.get('title', 'NO TITLE')}")
                print(f"{'='*60}\n")
                
                task = self._fix_test_formatting(task)
                result["task"] = task
                result["stages"][-1]["status"] = "done"
                break
                
            except json.JSONDecodeError as e:
                print(f"[ERROR] JSON parse error: {e}")
                last_error = f"JSON parse error: {e}"
            except Exception as e:
                print(f"[ERROR] Task generation error: {e}")
                last_error = str(e)
        
        if result["stages"][-1]["status"] != "done":
            result["stages"][-1]["status"] = "error"
            result["error"] = last_error
            result["status"] = "error"
            return result
        
        # Novelty check
        if all_examples:
            result["stages"].append({"name": "Novelty Check", "status": "running"})
            novelty = await self.check_novelty(task, all_examples)
            result["novelty"] = novelty
            result["stages"][-1]["status"] = "done"
        
        # Generate solution and validate with retries
        result["stages"].append({"name": "Solution", "status": "running"})
        
        all_tests = task.get("test_cases", []) + task.get("hidden_tests", [])[:3]
        solution = None
        validation = None
        max_fix_attempts = 3
        
        for attempt in range(max_fix_attempts):
            if attempt == 0:
                solution = await self.generate_solution(task, language)
            else:
                print(f"[FIX ATTEMPT {attempt}] Fixing solution based on failed tests...")
                solution = await self.fix_solution(solution, task, validation, language)
            
            if not solution:
                print(f"[ERROR] Failed to generate/fix solution")
                break
            
            if all_tests:
                print(f"[VALIDATION] Testing solution (attempt {attempt + 1}/{max_fix_attempts})...")
                validation = await self.validate_solution(solution, all_tests)
                
                passed = validation.get("passed", 0)
                total = validation.get("total", len(all_tests))
                all_passed = validation.get("all_passed", False)
                
                print(f"[VALIDATION] Result: {passed}/{total} tests passed")
                
                if all_passed:
                    print(f"[SUCCESS] All tests passed!")
                    break
                elif attempt < max_fix_attempts - 1:
                    tests_list = validation.get("tests", []) or validation.get("results", [])
                    failed_tests = [t for t in tests_list if not t.get("passed")]
                    for ft in failed_tests[:2]:
                        test_num = ft.get('test_number') or ft.get('num', '?')
                        expected = ft.get('expected', '')[:50]
                        actual = ft.get('actual', '')[:50]
                        print(f"  [FAILED] Test {test_num}: expected '{expected}', got '{actual}'")
            else:
                print(f"[WARNING] No tests to validate solution")
                break
        
        result["solution"] = solution
        result["stages"][-1]["status"] = "done" if solution else "error"
        
        if validation:
            result["stages"].append({"name": "Validation", "status": "running"})
            result["validation"] = validation
            
            if validation.get("all_passed"):
                result["stages"][-1]["status"] = "done"
                result["solution_verified"] = True
            else:
                result["stages"][-1]["status"] = "warning"
                result["solution_verified"] = False
                passed = validation.get("passed", 0)
                total = validation.get("total", 0)
                result["validation_warning"] = f"Solution passes {passed}/{total} tests"
        
        if task.get("new_hashtag"):
            result["stages"].append({"name": "New Hashtag", "status": "running"})
            created = await self.create_hashtag(task["new_hashtag"], section)
            result["new_hashtag_created"] = created
            result["stages"][-1]["status"] = "done" if created else "pending_approval"
        
        result["status"] = "success"
        return result


    async def generate_multifile(
        self,
        query: str,
        task_type: str = "fix_bug",  # fix_bug, complete, refactor, multi_file
        level: str = Level.MIDDLE,
        language: str = "python"
    ) -> Dict:
        """
        Generate multi-file task.
        
        Task types:
        - fix_bug: Find and fix bugs in code
        - complete: Complete function implementations
        - refactor: Refactor/improve code
        - multi_file: General multi-file task
        """
        result = {
            "status": "pending",
            "query": query,
            "task_type": task_type,
            "level": level,
            "stages": []
        }
        
        # Select appropriate prompt
        if task_type == "fix_bug":
            prompt = BUGFIX_TASK_PROMPT.format(
                query=query,
                level=level,
                language=language
            )
        elif task_type == "complete":
            prompt = COMPLETE_FUNCTION_PROMPT.format(
                query=query,
                level=level,
                language=language
            )
        else:
            prompt = MULTIFILE_TASK_PROMPT.format(
                query=query,
                task_type=task_type,
                level=level,
                language=language
            )
        
        result["stages"].append({"name": "Task Generation", "status": "running"})
        
        print(f"\n{'='*60}")
        print(f"[MULTIFILE TASK] Query: {query}, Type: {task_type}, Level: {level}")
        print(f"{'='*60}")
        
        # Retry logic
        max_retries = 3
        last_error = None
        task = None
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    print(f"[INFO] Retrying generation (attempt {attempt+1}/{max_retries+1})...")
                    time.sleep(1)
                
                response = self.client.chat.completions.create(
                    model=Models.CHAT,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                    max_tokens=4000,
                    response_format={"type": "json_object"}
                )
                
                raw_content = response.choices[0].message.content
                
                if not raw_content or raw_content.strip() in ["{}", ""]:
                    raise Exception("Empty response from LLM")
                
                print(f"[LLM RESPONSE] Length: {len(raw_content)} chars")
                
                task = json.loads(raw_content)
                
                # Validate essential fields
                if not task.get('title') or not task.get('description'):
                    raise Exception(f"Missing title or description. Got keys: {list(task.keys())}")
                
                if not task.get('files'):
                    raise Exception("Missing files array")
                
                print(f"[PARSED TASK] Title: {task.get('title')}")
                print(f"[PARSED TASK] Files: {[f.get('filename') for f in task.get('files', [])]}")
                print(f"[PARSED TASK] Objectives: {len(task.get('objectives', []))}")
                
                result["task"] = task
                result["stages"][-1]["status"] = "done"
                break
                
            except json.JSONDecodeError as e:
                print(f"[ERROR] JSON parse error: {e}")
                last_error = f"JSON parse error: {e}"
            except Exception as e:
                print(f"[ERROR] Task generation error: {e}")
                last_error = str(e)
        
        if result["stages"][-1]["status"] != "done":
            result["stages"][-1]["status"] = "error"
            result["error"] = last_error
            result["status"] = "error"
            return result
        
        # Stage 2: Validate solution files work
        if task.get("solution_files") and task.get("test_cases"):
            result["stages"].append({"name": "Solution Validation", "status": "running"})
            
            # Build solution files list
            solution_files = []
            for sf in task.get("solution_files", []):
                solution_files.append({
                    "filename": sf.get("filename"),
                    "path": sf.get("path", ""),
                    "content": sf.get("content")
                })
            
            # Add non-editable files from original
            for f in task.get("files", []):
                if not f.get("editable", True):
                    # Check if not already in solution_files
                    if not any(sf["filename"] == f["filename"] for sf in solution_files):
                        solution_files.append({
                            "filename": f.get("filename"),
                            "path": f.get("path", ""),
                            "content": f.get("content")
                        })
            
            try:
                validation = await self.validate_multifile_solution(
                    files=solution_files,
                    entry_point=task.get("entry_point", "main.py"),
                    test_cases=task.get("test_cases", []),
                    unit_tests=task.get("unit_tests", [])
                )
                result["solution_validation"] = validation
                result["stages"][-1]["status"] = "done" if validation.get("all_passed") else "warning"
            except Exception as e:
                print(f"[ERROR] Solution validation error: {e}")
                result["stages"][-1]["status"] = "error"
                result["solution_validation"] = {"error": str(e)}
        
        result["status"] = "success"
        return result
    
    async def validate_multifile_solution(
        self,
        files: List[Dict],
        entry_point: str,
        test_cases: List[Dict],
        unit_tests: List[Dict] = None
    ) -> Dict:
        """Validate multi-file solution against tests"""
        try:
            resp = await self.http_client.post(
                f"{CODE_RUNNER_URL}/validate/multifile",
                json={
                    "files": files,
                    "entry_point": entry_point,
                    "test_cases": [
                        {"input": t.get("input", ""), "output": t.get("output", "")}
                        for t in test_cases
                    ],
                    "unit_tests": unit_tests or [],
                    "language": "python"
                }
            )
            return resp.json()
        except Exception as e:
            print(f"Multifile validation error: {e}")
            return {"error": str(e)}


# Singleton
generator = HashtagTaskGenerator()


async def generate_with_hashtags(
    query: str,
    section: str = Section.LIVE_CODING,
    level: str = Level.MIDDLE,
    language: str = "python"
) -> Dict:
    """Convenience function for single-file tasks"""
    return await generator.generate(query, section, level, language)


async def generate_multifile_task(
    query: str,
    task_type: str = "fix_bug",
    level: str = Level.MIDDLE,
    language: str = "python"
) -> Dict:
    """Convenience function for multi-file tasks"""
    return await generator.generate_multifile(query, task_type, level, language)
