"""
Scenario Engine - Dynamic Task Generation with AI Tools

This module provides a flexible system for AI to create complex interview scenarios
by "calling tools" to build tasks step by step.

The AI can:
1. Analyze the request and decide the best scenario type
2. Use tools to generate code, create bugs, add hints, etc.
3. Build multi-step tasks with context and progression

Scenario Types:
- fix_code: Show broken code, ask to fix it
- complete_function: Show partial code with TODOs
- debug_output: Show code and wrong output, find the bug
- refactor: Show working but ugly code, improve it
- multi_step: Sequential steps building on each other
- code_review: Review code and find issues
- explain_code: Explain what code does
- optimize: Make code faster/better
"""

from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from openai import AsyncOpenAI
import json
import os
import sys
import asyncio
import re
import random

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


class ScenarioType(str, Enum):
    """Types of scenarios the AI can create"""
    FIX_CODE = "fix_code"              # Fix bugs in existing code
    COMPLETE_FUNCTION = "complete"      # Complete TODO implementations
    DEBUG_OUTPUT = "debug_output"       # Find bug based on wrong output
    REFACTOR = "refactor"               # Improve code quality
    MULTI_STEP = "multi_step"           # Multi-step progressive task
    CODE_REVIEW = "code_review"         # Review and critique code
    EXPLAIN_CODE = "explain"            # Explain what code does
    OPTIMIZE = "optimize"               # Optimize for performance
    WRITE_TESTS = "write_tests"         # Write tests for given code
    IMPLEMENT = "implement"             # Implement from scratch (classic)


class StepType(str, Enum):
    """Types of steps in a scenario"""
    SHOW_CODE = "show_code"             # Display code to user
    SHOW_TEXT = "show_text"             # Display text/instructions
    SHOW_OUTPUT = "show_output"         # Show expected/actual output
    ASK_FIX = "ask_fix"                 # Ask user to fix something
    ASK_COMPLETE = "ask_complete"       # Ask user to complete code
    ASK_EXPLAIN = "ask_explain"         # Ask user to explain
    ASK_WRITE = "ask_write"             # Ask user to write code
    ASK_REVIEW = "ask_review"           # Ask user to review
    RUN_TESTS = "run_tests"             # Run tests on user's code
    HINT = "hint"                       # Provide a hint
    SOLUTION = "solution"               # Show solution (after attempts)


@dataclass
class ScenarioStep:
    """A single step in a scenario"""
    step_type: StepType
    content: Any  # Can be code, text, test cases, etc.
    metadata: Dict = field(default_factory=dict)
    is_interactive: bool = False  # Requires user input
    points: int = 0  # Points for this step
    time_limit_seconds: Optional[int] = None


@dataclass
class Scenario:
    """Complete scenario with all steps"""
    id: str
    type: ScenarioType
    title: str
    description: str
    difficulty: str
    language: str
    steps: List[ScenarioStep] = field(default_factory=list)
    total_points: int = 100
    time_limit_minutes: int = 30
    hashtags: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "description": self.description,
            "difficulty": self.difficulty,
            "language": self.language,
            "steps": [
                {
                    "step_type": s.step_type.value,
                    "content": s.content,
                    "metadata": s.metadata,
                    "is_interactive": s.is_interactive,
                    "points": s.points,
                    "time_limit_seconds": s.time_limit_seconds
                }
                for s in self.steps
            ],
            "total_points": self.total_points,
            "time_limit_minutes": self.time_limit_minutes,
            "hashtags": self.hashtags,
            "metadata": self.metadata
        }


# ============== AI Tools for Scenario Building ==============

SCENARIO_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_working_code",
            "description": "Generate working code that solves a problem. Use this to create the 'correct' version.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {"type": "string", "description": "What the code should do"},
                    "language": {"type": "string", "description": "Programming language"},
                    "complexity": {"type": "string", "enum": ["simple", "medium", "complex"]},
                    "style": {"type": "string", "enum": ["clean", "verbose", "minimal"]}
                },
                "required": ["task_description", "language"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "inject_bugs",
            "description": "Take working code and inject realistic bugs into it. Returns buggy code and bug descriptions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Working code to inject bugs into"},
                    "num_bugs": {"type": "integer", "description": "Number of bugs to inject (1-5)"},
                    "bug_types": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["logic", "off_by_one", "type_error", "edge_case", "performance", "syntax"]},
                        "description": "Types of bugs to inject"
                    },
                    "difficulty": {"type": "string", "enum": ["obvious", "subtle", "tricky"]}
                },
                "required": ["code", "num_bugs"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_partial_code",
            "description": "Create partial code with TODO markers where user needs to implement.",
            "parameters": {
                "type": "object",
                "properties": {
                    "full_code": {"type": "string", "description": "Complete working code"},
                    "parts_to_remove": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Which parts to replace with TODO (e.g., 'main_logic', 'edge_cases', 'optimization')"
                    },
                    "hint_level": {"type": "string", "enum": ["none", "signature", "comments", "pseudocode"]}
                },
                "required": ["full_code", "parts_to_remove"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_test_cases",
            "description": "Generate test cases for code validation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Code to generate tests for"},
                    "num_basic": {"type": "integer", "description": "Number of basic test cases"},
                    "num_edge": {"type": "integer", "description": "Number of edge case tests"},
                    "num_stress": {"type": "integer", "description": "Number of stress/performance tests"},
                    "include_hidden": {"type": "boolean", "description": "Include hidden tests"}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_code_with_bad_style",
            "description": "Create code that works but has style/quality issues for refactoring tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {"type": "string"},
                    "issues": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["naming", "complexity", "duplication", "magic_numbers", "no_comments", "deep_nesting", "long_functions"]},
                        "description": "Style issues to include"
                    }
                },
                "required": ["task_description", "issues"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_step",
            "description": "Add a step to the scenario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "step_type": {
                        "type": "string",
                        "enum": ["show_code", "show_text", "show_output", "ask_fix", "ask_complete", "ask_explain", "ask_write", "ask_review", "run_tests", "hint", "solution"]
                    },
                    "content": {"type": "string", "description": "Content for this step"},
                    "is_interactive": {"type": "boolean", "description": "Does this step require user input?"},
                    "points": {"type": "integer", "description": "Points for completing this step"},
                    "time_limit_seconds": {"type": "integer", "description": "Time limit for this step"}
                },
                "required": ["step_type", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_hint",
            "description": "Add a hint that can be revealed with a penalty.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hint_text": {"type": "string"},
                    "penalty_percent": {"type": "integer", "description": "Percentage penalty for using hint (5-30)"},
                    "reveal_after_attempts": {"type": "integer", "description": "Auto-reveal after N failed attempts"}
                },
                "required": ["hint_text", "penalty_percent"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_scenario",
            "description": "Finalize the scenario with metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "estimated_time_minutes": {"type": "integer"},
                    "total_points": {"type": "integer"}
                },
                "required": ["title", "description"]
            }
        }
    }
]


# ============== Scenario Planner Prompt ==============

SCENARIO_PLANNER_PROMPT = """/no_think Ты эксперт по созданию сценариев для технических интервью.

Запрос пользователя: {query}
Сложность: {difficulty}
Язык программирования: {language}

Твоя задача - спланировать ЛУЧШИЙ сценарий для проверки навыков кандидата.

Доступные типы сценариев:
1. fix_code - Показать код с багами, попросить исправить
2. complete - Показать частичный код с TODO, попросить дописать
3. debug_output - Показать код и неправильный вывод, найти баг
4. refactor - Показать рабочий но плохой код, улучшить
5. multi_step - Многошаговая задача с прогрессией
6. code_review - Ревью кода, найти проблемы
7. explain - Объяснить что делает код
8. optimize - Оптимизировать код
9. write_tests - Написать тесты для кода
10. implement - Написать код с нуля (классика)

Выбери тип сценария и спланируй шаги.

Верни JSON:
{{
    "scenario_type": "тип сценария",
    "reasoning": "почему выбран этот тип",
    "complexity_factors": ["что делает задачу сложной"],
    "steps_plan": [
        {{"action": "что сделать", "tool": "какой инструмент использовать"}}
    ],
    "estimated_time_minutes": число,
    "skills_tested": ["навыки которые проверяются"]
}}"""


# ============== Tool Execution Prompts ==============

GENERATE_CODE_PROMPT = """/no_think Напиши код на {language}.

Задача: {task_description}
Сложность: {complexity}
Стиль: {style}

Требования:
- Код должен быть рабочим
- Читай из stdin, пиши в stdout
- Следуй указанному стилю

Верни ТОЛЬКО код без объяснений."""


INJECT_BUGS_PROMPT = """/no_think Возьми этот рабочий код и внеси в него {num_bugs} баг(ов).

Код:
```
{code}
```

Типы багов для внесения: {bug_types}
Сложность обнаружения: {difficulty}

Требования:
1. Баги должны быть реалистичными (такие делают реальные программисты)
2. Код должен компилироваться/запускаться
3. Баги должны приводить к неправильным результатам

Верни JSON:
{{
    "buggy_code": "код с багами",
    "bugs": [
        {{
            "line": номер_строки,
            "original": "исходный код",
            "buggy": "код с багом",
            "bug_type": "тип бага",
            "description": "описание бага",
            "hint": "подсказка для поиска"
        }}
    ]
}}"""


CREATE_PARTIAL_PROMPT = """/no_think Создай частичный код с TODO метками.

Полный код:
```
{full_code}
```

Части для удаления: {parts_to_remove}
Уровень подсказок: {hint_level}

Замени указанные части на TODO комментарии.
Если hint_level = "signature" - оставь сигнатуры функций
Если hint_level = "comments" - добавь комментарии что нужно сделать
Если hint_level = "pseudocode" - добавь псевдокод

Верни JSON:
{{
    "partial_code": "код с TODO",
    "todos": [
        {{
            "location": "где TODO",
            "description": "что нужно реализовать",
            "difficulty": "easy/medium/hard"
        }}
    ]
}}"""


GENERATE_TESTS_PROMPT = """/no_think Сгенерируй тесты для кода. ВАЖНО: Вычисли правильные ответы!

Код:
```
{code}
```

Количество тестов:
- Базовых: {num_basic}
- Граничных: {num_edge}
- Стресс: {num_stress}

ВАЖНО:
1. Для каждого теста ВЫЧИСЛИ правильный output, выполнив код мысленно
2. Проверь вычисления дважды
3. Для стресс-тестов используй данные размером 1000-10000 элементов

Пример правильного теста для суммы массива:
- input: "3\\n1 2 3" (3 числа: 1, 2, 3)
- output: "6" (1+2+3=6)

Верни JSON:
{{
    "test_cases": [
        {{"input": "вход\\nс переносами", "output": "точный_ответ", "category": "basic/edge/stress", "hidden": true/false, "points": число, "description": "описание"}}
    ]
}}"""


GENERATE_SLOW_CODE_PROMPT = """/no_think Напиши НЕОПТИМАЛЬНЫЙ но РАБОЧИЙ код на {language}.

Задача: {task_description}

Требования:
1. Код ДОЛЖЕН давать ПРАВИЛЬНЫЕ ответы
2. Код должен быть МЕДЛЕННЫМ (O(n²) или хуже)
3. Используй неэффективные алгоритмы:
   - Вложенные циклы вместо хеш-таблиц
   - Сортировка пузырьком вместо встроенной
   - Линейный поиск вместо бинарного
   - Пересоздание списков вместо изменения на месте
4. Читай из stdin, пиши в stdout

Пример неоптимального кода для поиска дубликатов:
```python
# O(n²) - медленно для больших данных
n = int(input())
arr = list(map(int, input().split()))
has_dup = False
for i in range(n):
    for j in range(i+1, n):
        if arr[i] == arr[j]:
            has_dup = True
            break
print("YES" if has_dup else "NO")
```

Верни ТОЛЬКО код без объяснений."""


GENERATE_OPTIMAL_CODE_PROMPT = """/no_think Напиши ОПТИМАЛЬНЫЙ код на {language}.

Задача: {task_description}
Неоптимальный код для сравнения:
```
{slow_code}
```

Требования:
1. Код должен давать ТЕ ЖЕ ответы что и неоптимальный
2. Используй эффективные алгоритмы (O(n) или O(n log n))
3. Читай из stdin, пиши в stdout

Верни ТОЛЬКО код без объяснений."""


BAD_STYLE_PROMPT = """/no_think Напиши код который работает, но имеет проблемы со стилем.

Задача: {task_description}
Проблемы для внесения: {issues}

Код должен:
1. Правильно решать задачу
2. Иметь указанные проблемы со стилем
3. Быть реалистичным (как пишут джуниоры)

Верни JSON:
{{
    "code": "код с проблемами",
    "issues_present": [
        {{
            "type": "тип проблемы",
            "location": "где в коде",
            "description": "описание проблемы",
            "how_to_fix": "как исправить"
        }}
    ],
    "clean_version": "чистая версия кода"
}}"""


# ============== СПЕЦИАЛИЗИРОВАННЫЕ ПРОМПТЫ ДЛЯ РАЗНЫХ ТИПОВ ЗАДАЧ ==============

# Промпт для задач на ОПТИМИЗАЦИЮ
OPTIMIZATION_TASK_PROMPT = """/no_think Создай задачу на ОПТИМИЗАЦИЮ алгоритма на {language}.

Тема: {topic}
Сложность: {difficulty}

ТРЕБОВАНИЯ К ЗАДАЧЕ:
1. Задача должна иметь ОЧЕВИДНОЕ неоптимальное решение (O(n²), O(n³) или хуже)
2. Существует ОПТИМАЛЬНОЕ решение (O(n), O(n log n))
3. На малых данных (N < 100) оба решения работают быстро
4. На больших данных (N > 10000) неоптимальное решение НЕ УКЛАДЫВАЕТСЯ в лимит

ПРИМЕРЫ ХОРОШИХ ЗАДАЧ НА ОПТИМИЗАЦИЮ:
- Поиск двух чисел с заданной суммой (O(n²) → O(n) с хеш-таблицей)
- Поиск дубликатов (O(n²) → O(n) с set)
- Подсчёт пар с разницей K (O(n²) → O(n) с dict)
- Максимальная подпоследовательность (O(n³) → O(n) Кадане)
- Поиск медианы (O(n log n) сортировка → O(n) quickselect)

СГЕНЕРИРУЙ:
1. Условие задачи (чёткое, с примерами ввода/вывода)
2. Неоптимальный код (РАБОЧИЙ, но медленный)
3. Оптимальный код (РАБОЧИЙ и быстрый)
4. Объяснение оптимизации

Верни JSON:
{{
    "title": "название задачи",
    "description": "условие задачи с примерами",
    "slow_code": "неоптимальный рабочий код",
    "optimal_code": "оптимальный код",
    "slow_complexity": "O(n²)",
    "optimal_complexity": "O(n)",
    "optimization_hint": "подсказка какую структуру данных использовать",
    "key_insight": "ключевая идея оптимизации"
}}"""

# Промпт для задач на ИСПРАВЛЕНИЕ БАГОВ
FIX_BUGS_TASK_PROMPT = """/no_think Создай задачу на ПОИСК И ИСПРАВЛЕНИЕ БАГОВ на {language}.

Тема: {topic}
Сложность: {difficulty}
Количество багов: {num_bugs}

ТРЕБОВАНИЯ:
1. Код должен КОМПИЛИРОВАТЬСЯ/ЗАПУСКАТЬСЯ
2. Баги должны быть РЕАЛИСТИЧНЫМИ (такие делают реальные разработчики)
3. Баги должны приводить к НЕПРАВИЛЬНЫМ результатам на некоторых тестах
4. Сложность багов должна соответствовать уровню: {difficulty}

ТИПЫ БАГОВ ПО СЛОЖНОСТИ:

EASY (очевидные):
- Опечатки в именах переменных
- Неправильный оператор (< вместо <=)
- Забытый return
- Неправильная инициализация

MEDIUM (требуют анализа):
- Off-by-one ошибки в циклах
- Неправильная обработка граничных случаев
- Проблемы с типами данных
- Неправильный порядок операций

HARD (хитрые):
- Проблемы с переполнением
- Race conditions в логике
- Неочевидные граничные случаи
- Проблемы с точностью float
- Неправильная работа с отрицательными числами

Верни JSON:
{{
    "title": "название задачи",
    "description": "что должен делать код",
    "correct_code": "правильный код",
    "buggy_code": "код с багами",
    "bugs": [
        {{
            "line": номер_строки,
            "type": "тип бага",
            "description": "описание бага",
            "original": "правильный код",
            "buggy": "код с багом",
            "hint": "подсказка для поиска",
            "test_that_fails": "тест который не проходит из-за этого бага"
        }}
    ]
}}"""

# Промпт для задач на ДОПОЛНЕНИЕ КОДА (с защитой от сдачи базового кода)
COMPLETE_CODE_TASK_PROMPT = """/no_think Создай задачу на ДОПОЛНЕНИЕ КОДА на {language}.

Тема: {topic}
Сложность: {difficulty}

ВАЖНО: Базовый код с TODO НЕ ДОЛЖЕН проходить ни один тест!

ТРЕБОВАНИЯ:
1. Создай ПОЛНЫЙ рабочий код
2. Замени ключевые части на TODO с комментариями
3. TODO должны быть в КРИТИЧЕСКИХ местах - без них код НЕ РАБОТАЕТ
4. Если пользователь отправит код с TODO как есть - 0 баллов

СТРУКТУРА TODO ПО СЛОЖНОСТИ:

EASY:
- 1-2 TODO в основной логике
- Чёткие комментарии что нужно сделать
- Сигнатуры функций даны

MEDIUM:
- 2-3 TODO включая обработку граничных случаев
- Комментарии менее подробные
- Нужно понять логику из контекста

HARD:
- 3-4 TODO включая оптимизацию
- Минимум подсказок
- Нужно самому понять что реализовать

Верни JSON:
{{
    "title": "название задачи",
    "description": "условие задачи",
    "full_code": "полный рабочий код",
    "partial_code": "код с TODO (НЕ РАБОТАЕТ без реализации)",
    "todos": [
        {{
            "location": "где TODO",
            "what_to_implement": "что нужно реализовать",
            "difficulty": "easy/medium/hard",
            "lines_of_code": примерное_количество_строк
        }}
    ],
    "validation_test": {{
        "input": "тест для проверки что TODO не реализованы",
        "expected_error": "ожидаемая ошибка или неправильный результат"
    }}
}}"""

# Промпт для задач на РЕФАКТОРИНГ
REFACTOR_TASK_PROMPT = """/no_think Создай задачу на РЕФАКТОРИНГ кода на {language}.

Тема: {topic}
Сложность: {difficulty}

ТРЕБОВАНИЯ:
1. Код должен РАБОТАТЬ ПРАВИЛЬНО
2. Код должен иметь ЯВНЫЕ проблемы со стилем/качеством
3. После рефакторинга код должен работать ТАК ЖЕ

ПРОБЛЕМЫ ДЛЯ ВНЕСЕНИЯ ПО СЛОЖНОСТИ:

EASY:
- Плохие имена переменных (a, b, x, temp1, temp2)
- Magic numbers без констант
- Отсутствие комментариев

MEDIUM:
- Дублирование кода
- Слишком длинные функции (50+ строк)
- Глубокая вложенность (3+ уровней)
- Смешение ответственностей

HARD:
- Всё вышеперечисленное
- Неэффективные паттерны
- Нарушение SOLID принципов
- Сложная логика без разбиения

Верни JSON:
{{
    "title": "название задачи",
    "description": "что делает код и что нужно улучшить",
    "bad_code": "код с проблемами",
    "clean_code": "отрефакторенный код",
    "issues": [
        {{
            "type": "тип проблемы",
            "location": "где в коде",
            "description": "описание",
            "how_to_fix": "как исправить",
            "priority": "high/medium/low"
        }}
    ],
    "refactoring_checklist": ["что проверить после рефакторинга"]
}}"""

# Промпт для задач на НАПИСАНИЕ С НУЛЯ (классика)
IMPLEMENT_TASK_PROMPT = """/no_think Создай задачу на НАПИСАНИЕ КОДА С НУЛЯ на {language}.

Тема: {topic}
Сложность: {difficulty}

ТРЕБОВАНИЯ К ЗАДАЧЕ ПО СЛОЖНОСТИ:

EASY (15-20 минут):
- Простая логика, 10-20 строк кода
- Один основной алгоритм
- Минимум граничных случаев
- Примеры: сумма массива, поиск максимума, проверка палиндрома

MEDIUM (25-35 минут):
- Средняя сложность, 20-40 строк кода
- Требуется знание структур данных
- Несколько граничных случаев
- Примеры: бинарный поиск, сортировка, работа со строками

HARD (40-60 минут):
- Сложная логика, 40-80 строк кода
- Требуется оптимальный алгоритм
- Много граничных случаев
- Примеры: динамическое программирование, графы, сложные структуры

ФОРМАТ ВВОДА/ВЫВОДА:
- Чтение из stdin
- Вывод в stdout
- Чёткий формат с примерами

Верни JSON:
{{
    "title": "название задачи",
    "description": "подробное условие с форматом ввода/вывода",
    "examples": [
        {{"input": "пример входа", "output": "пример выхода", "explanation": "объяснение"}}
    ],
    "solution_code": "эталонное решение",
    "hints": ["подсказки по уровням"],
    "common_mistakes": ["типичные ошибки"],
    "time_complexity": "ожидаемая сложность",
    "space_complexity": "ожидаемая память"
}}"""

# Промпт для задач на ОТЛАДКУ ПО ВЫВОДУ
DEBUG_OUTPUT_TASK_PROMPT = """/no_think Создай задачу на ОТЛАДКУ ПО НЕПРАВИЛЬНОМУ ВЫВОДУ на {language}.

Тема: {topic}
Сложность: {difficulty}

СУТЬ ЗАДАЧИ:
- Дан код который ПОЧТИ работает
- Показан ОЖИДАЕМЫЙ и ФАКТИЧЕСКИЙ вывод
- Нужно найти и исправить баг

ТРЕБОВАНИЯ:
1. Баг должен быть ОДНИМ, но НЕОЧЕВИДНЫМ
2. Код должен компилироваться
3. Разница в выводе должна помогать найти баг

ТИПЫ БАГОВ ПО СЛОЖНОСТИ:

EASY:
- Баг виден из сравнения вывода
- Например: вывод "5" вместо "6" → ошибка в формуле

MEDIUM:
- Нужно проанализировать логику
- Например: работает для положительных, ломается для отрицательных

HARD:
- Баг проявляется только в определённых условиях
- Например: работает для N<100, ломается для N>=100 (переполнение)

Верни JSON:
{{
    "title": "название задачи",
    "description": "что должен делать код",
    "buggy_code": "код с багом",
    "correct_code": "исправленный код",
    "test_case": {{
        "input": "вход",
        "expected_output": "правильный вывод",
        "actual_output": "фактический вывод с багом"
    }},
    "bug": {{
        "line": номер_строки,
        "description": "описание бага",
        "fix": "как исправить"
    }},
    "debugging_hints": ["подсказки для отладки"]
}}"""

# Промпт для задач на НАПИСАНИЕ ТЕСТОВ
WRITE_TESTS_TASK_PROMPT = """/no_think Создай задачу на НАПИСАНИЕ ТЕСТОВ на {language}.

Тема: {topic}
Сложность: {difficulty}

ТРЕБОВАНИЯ:
1. Дан РАБОЧИЙ код
2. Нужно написать ТЕСТЫ для проверки кода
3. Тесты должны покрывать разные случаи

ТРЕБОВАНИЯ К ТЕСТАМ ПО СЛОЖНОСТИ:

EASY (минимум 3 теста):
- 1 базовый случай
- 1 граничный случай
- 1 тест на ошибку

MEDIUM (минимум 5 тестов):
- 2 базовых случая
- 2 граничных случая
- 1 тест на производительность

HARD (минимум 7 тестов):
- Полное покрытие всех веток
- Граничные случаи
- Тесты на ошибки
- Тесты на производительность
- Тесты на безопасность (если применимо)

Верни JSON:
{{
    "title": "название задачи",
    "description": "описание кода для тестирования",
    "code_to_test": "код который нужно протестировать",
    "expected_tests": [
        {{
            "name": "имя теста",
            "category": "basic/edge/error/performance",
            "description": "что проверяет тест",
            "input": "входные данные",
            "expected": "ожидаемый результат"
        }}
    ],
    "test_framework": "pytest/unittest",
    "coverage_requirements": "минимальное покрытие в %"
}}"""

# Промпт для задач на ОБЪЯСНЕНИЕ КОДА
EXPLAIN_CODE_TASK_PROMPT = """/no_think Создай задачу на ОБЪЯСНЕНИЕ КОДА на {language}.

Тема: {topic}
Сложность: {difficulty}

ТРЕБОВАНИЯ:
1. Код должен быть БЕЗ комментариев (или с минимумом)
2. Код должен реализовывать НЕТРИВИАЛЬНЫЙ алгоритм
3. Нужно объяснить ЧТО делает код и КАК

ВОПРОСЫ ПО СЛОЖНОСТИ:

EASY:
- Что делает этот код?
- Какой результат для входа X?

MEDIUM:
- Что делает этот код?
- Какова временная сложность?
- Какие граничные случаи обрабатывает?

HARD:
- Что делает этот код?
- Временная и пространственная сложность?
- Граничные случаи?
- Потенциальные проблемы?
- Как улучшить?

Верни JSON:
{{
    "title": "название задачи",
    "code": "код для объяснения (без комментариев)",
    "questions": ["вопросы для ответа"],
    "expected_answers": [
        {{
            "question": "вопрос",
            "key_points": ["ключевые моменты ответа"],
            "full_answer": "полный ответ"
        }}
    ],
    "algorithm_name": "название алгоритма если известно",
    "complexity": {{
        "time": "временная сложность",
        "space": "пространственная сложность"
    }}
}}"""

# Промпт для задач на КОД-РЕВЬЮ
CODE_REVIEW_TASK_PROMPT = """/no_think Создай задачу на КОД-РЕВЬЮ на {language}.

Тема: {topic}
Сложность: {difficulty}

ТРЕБОВАНИЯ:
1. Код должен содержать СМЕСЬ проблем:
   - Баги (логические ошибки)
   - Проблемы со стилем
   - Проблемы с производительностью
   - Проблемы с безопасностью (опционально)
2. Нужно найти ВСЕ проблемы и предложить исправления

КОЛИЧЕСТВО ПРОБЛЕМ ПО СЛОЖНОСТИ:

EASY: 3-4 проблемы
- 1 баг
- 2-3 проблемы со стилем

MEDIUM: 5-6 проблем
- 2 бага
- 2-3 проблемы со стилем
- 1 проблема с производительностью

HARD: 7-8 проблем
- 2-3 бага (включая хитрые)
- 2-3 проблемы со стилем
- 1-2 проблемы с производительностью
- 1 проблема с безопасностью

Верни JSON:
{{
    "title": "название задачи",
    "description": "контекст код-ревью",
    "code_for_review": "код для ревью",
    "issues": [
        {{
            "type": "bug/style/performance/security",
            "severity": "critical/major/minor",
            "line": номер_строки,
            "description": "описание проблемы",
            "suggestion": "как исправить"
        }}
    ],
    "review_checklist": ["что проверить"],
    "good_practices": ["что в коде хорошо"]
}}"""

# Промпт для МНОГОШАГОВЫХ задач
MULTI_STEP_TASK_PROMPT = """/no_think Создай МНОГОШАГОВУЮ задачу на {language}.

Тема: {topic}
Сложность: {difficulty}

СТРУКТУРА МНОГОШАГОВОЙ ЗАДАЧИ:
1. Шаг 1: Базовое решение (простое, работает на малых данных)
2. Шаг 2: Обработка граничных случаев
3. Шаг 3: Оптимизация для больших данных

ТРЕБОВАНИЯ:
1. Каждый шаг СТРОИТСЯ на предыдущем
2. Тесты для каждого шага ОТДЕЛЬНЫЕ
3. Можно получить частичные баллы за каждый шаг

РАСПРЕДЕЛЕНИЕ БАЛЛОВ:
- Шаг 1: 30 баллов
- Шаг 2: 30 баллов  
- Шаг 3: 40 баллов

Верни JSON:
{{
    "title": "название задачи",
    "description": "общее описание",
    "steps": [
        {{
            "step_number": 1,
            "title": "название шага",
            "description": "что нужно сделать",
            "requirements": ["требования"],
            "tests": [
                {{"input": "вход", "output": "выход", "points": баллы}}
            ],
            "solution": "решение для этого шага",
            "points": баллы_за_шаг
        }}
    ],
    "final_solution": "полное оптимальное решение",
    "total_points": 100
}}"""

# Промпт для генерации ТЕСТОВ С ОГРАНИЧЕНИЯМИ ПО ВРЕМЕНИ
GENERATE_TESTS_WITH_LIMITS_PROMPT = """/no_think Сгенерируй тесты для кода С ОГРАНИЧЕНИЯМИ ПО ВРЕМЕНИ.

Код:
```
{code}
```

Тип задачи: {task_type}
Сложность: {difficulty}

Количество тестов:
- Базовых: {num_basic}
- Граничных: {num_edge}
- Стресс: {num_stress}

ВАЖНО:
1. Код читает данные из STDIN. Поле "input" в тесте ДОЛЖНО содержать данные для stdin.
2. Если код использует `input()`, поле "input" НЕ МОЖЕТ быть пустым!
3. Для каждого теста ВЫЧИСЛИ правильный output.
4. Укажи ОГРАНИЧЕНИЕ ПО ВРЕМЕНИ для каждого теста.

ОГРАНИЧЕНИЯ ПО ВРЕМЕНИ:
- Базовые тесты: 2-5 секунд (любой код пройдёт)
- Граничные тесты: 2-3 секунды
- Стресс-тесты: 1-2 секунды (только оптимальный код пройдёт)

ДЛЯ ЗАДАЧ НА ОПТИМИЗАЦИЮ:
- Стресс-тесты должны иметь N >= 10000
- Время для стресс-тестов: 1 секунда
- Неоптимальный O(n²) код НЕ ДОЛЖЕН проходить стресс-тесты

Верни JSON:
{{
    "test_cases": [
        {{
            "input": "данные для stdin\\nс переносами строк",
            "output": "точный_ответ",
            "category": "basic/edge/stress",
            "time_limit_ms": время_в_миллисекундах,
            "memory_limit_mb": память_в_мегабайтах,
            "points": баллы,
            "description": "описание теста",
            "hidden": true/false
        }}
    ]
}}"""


class ScenarioEngine:
    """
    Engine for creating dynamic interview scenarios.
    Uses AI with tools to build complex, multi-step tasks.
    """
    
    def __init__(self):
        self.client = get_client()
        self.tools = SCENARIO_TOOLS
        
    async def _call_llm(
        self,
        prompt: str,
        model: str = None,
        temperature: float = 0.3,
        max_tokens: int = 3000,
        response_format: Optional[Dict] = None
    ) -> Optional[str]:
        """Call LLM with timeout and retry"""
        model = model or Models.CHAT
        
        try:
            # Use /no_think to disable reasoning mode for faster responses
            system_content = "/no_think You are a helpful assistant that generates programming tasks."
            
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            if response_format:
                kwargs["response_format"] = response_format
                
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**kwargs),
                timeout=120  # Увеличил таймаут до 120 секунд
            )
            return response.choices[0].message.content
            
        except asyncio.TimeoutError:
            print(f"[ScenarioEngine] LLM timeout after 120s")
            return None
        except Exception as e:
            import traceback
            print(f"[ScenarioEngine] LLM error: {type(e).__name__}: {str(e)}")
            traceback.print_exc()
            return None
    
    async def plan_scenario(
        self,
        query: str,
        difficulty: str = "medium",
        language: str = "python"
    ) -> Dict:
        """
        Step 1: Plan the best scenario type for the query.
        AI analyzes the request and decides how to test the candidate.
        """
        prompt = SCENARIO_PLANNER_PROMPT.format(
            query=query,
            difficulty=difficulty,
            language=language
        )
        
        response = await self._call_llm(
            prompt,
            response_format={"type": "json_object"}
        )
        
        if not response:
            # Fallback to classic implementation
            return {
                "scenario_type": "implement",
                "reasoning": "Fallback to classic task",
                "steps_plan": [{"action": "generate task", "tool": "generate_working_code"}],
                "estimated_time_minutes": 20,
                "skills_tested": [query]
            }
        
        try:
            return json.loads(response)
        except:
            return {
                "scenario_type": "implement",
                "reasoning": "Parse error fallback",
                "steps_plan": [],
                "estimated_time_minutes": 20,
                "skills_tested": [query]
            }
    
    async def execute_tool(
        self,
        tool_name: str,
        params: Dict,
        context: Dict
    ) -> Dict:
        """Execute a scenario building tool"""
        
        if tool_name == "generate_working_code":
            return await self._generate_working_code(params, context)
        
        elif tool_name == "inject_bugs":
            return await self._inject_bugs(params, context)
        
        elif tool_name == "create_partial_code":
            return await self._create_partial_code(params, context)
        
        elif tool_name == "generate_test_cases":
            return await self._generate_test_cases(params, context)
        
        elif tool_name == "create_code_with_bad_style":
            return await self._create_bad_style_code(params, context)
        
        elif tool_name == "generate_slow_code":
            return await self._generate_slow_code(params, context)
        
        elif tool_name == "generate_optimal_code":
            return await self._generate_optimal_code(params, context)
        
        elif tool_name == "create_step":
            return self._create_step(params, context)
        
        elif tool_name == "add_hint":
            return self._add_hint(params, context)
        
        elif tool_name == "finalize_scenario":
            return self._finalize_scenario(params, context)
        
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    
    async def _generate_working_code(self, params: Dict, context: Dict) -> Dict:
        """Generate working code for a task"""
        prompt = GENERATE_CODE_PROMPT.format(
            language=params.get("language", context.get("language", "python")),
            task_description=params.get("task_description", context.get("query", "")),
            complexity=params.get("complexity", "medium"),
            style=params.get("style", "clean")
        )
        
        code = await self._call_llm(prompt, model=Models.CODE, max_tokens=2000)
        
        if code:
            # Clean markdown
            code = self._clean_code(code)
            context["working_code"] = code
            return {"success": True, "code": code}
        
        return {"success": False, "error": "Failed to generate code"}
    
    async def _generate_slow_code(self, params: Dict, context: Dict) -> Dict:
        """Generate working but slow/unoptimized code"""
        prompt = GENERATE_SLOW_CODE_PROMPT.format(
            language=params.get("language", context.get("language", "python")),
            task_description=params.get("task_description", context.get("query", ""))
        )
        
        code = await self._call_llm(prompt, model=Models.CODE, max_tokens=2000)
        
        if code:
            code = self._clean_code(code)
            context["slow_code"] = code
            context["working_code"] = code  # Slow code is still working code
            return {"success": True, "code": code}
        
        return {"success": False, "error": "Failed to generate slow code"}
    
    async def _generate_optimal_code(self, params: Dict, context: Dict) -> Dict:
        """Generate optimized version of slow code"""
        slow_code = params.get("slow_code") or context.get("slow_code")
        if not slow_code:
            return {"success": False, "error": "No slow code to optimize"}
        
        prompt = GENERATE_OPTIMAL_CODE_PROMPT.format(
            language=params.get("language", context.get("language", "python")),
            task_description=params.get("task_description", context.get("query", "")),
            slow_code=slow_code
        )
        
        code = await self._call_llm(prompt, model=Models.CODE, max_tokens=2000)
        
        if code:
            code = self._clean_code(code)
            context["optimal_code"] = code
            return {"success": True, "code": code}
        
        return {"success": False, "error": "Failed to generate optimal code"}
    
    def _clean_code(self, code: str) -> str:
        """Clean code from markdown formatting"""
        if "```" in code:
            match = re.search(r'```(?:\w+)?\n(.*?)```', code, re.DOTALL)
            if match:
                code = match.group(1)
        return code.strip()
    
    async def _run_code_for_test(self, code: str, input_data: str, timeout: float = 5.0) -> tuple:
        """Run code with input and return (output, error)"""
        import subprocess
        import tempfile
        
        try:
            # Если input_data None, заменяем на пустую строку
            if input_data is None:
                input_data = ""
                
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(code)
                temp_file = f.name
            
            # Log input for debugging
            # print(f"[DEBUG] Running code with input: {repr(input_data)}")
            
            result = subprocess.run(
                ['python', temp_file],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            import os
            os.unlink(temp_file)
            
            # Если код упал с ошибкой, возвращаем stderr
            if result.returncode != 0:
                # Игнорируем EOFError если ожидался ввод но его не дали
                if "EOFError" in result.stderr and not input_data:
                    return None, "EOFError: Code expects input but none provided"
                return None, result.stderr
                
            return result.stdout.strip(), None
        except subprocess.TimeoutExpired:
            return None, "Timeout"
        except Exception as e:
            return None, str(e)
    
    async def _inject_bugs(self, params: Dict, context: Dict) -> Dict:
        """Inject bugs into working code"""
        code = params.get("code") or context.get("working_code")
        if not code:
            return {"success": False, "error": "No code to inject bugs into"}
        
        prompt = INJECT_BUGS_PROMPT.format(
            code=code,
            num_bugs=params.get("num_bugs", 2),
            bug_types=json.dumps(params.get("bug_types", ["logic", "edge_case"])),
            difficulty=params.get("difficulty", "subtle")
        )
        
        response = await self._call_llm(
            prompt,
            response_format={"type": "json_object"}
        )
        
        if response:
            try:
                result = json.loads(response)
                context["buggy_code"] = result.get("buggy_code")
                context["bugs"] = result.get("bugs", [])
                return {"success": True, **result}
            except:
                pass
        
        return {"success": False, "error": "Failed to inject bugs"}
    
    async def _create_partial_code(self, params: Dict, context: Dict) -> Dict:
        """Create partial code with TODOs"""
        code = params.get("full_code") or context.get("working_code")
        if not code:
            return {"success": False, "error": "No code to make partial"}
        
        prompt = CREATE_PARTIAL_PROMPT.format(
            full_code=code,
            parts_to_remove=json.dumps(params.get("parts_to_remove", ["main_logic"])),
            hint_level=params.get("hint_level", "comments")
        )
        
        response = await self._call_llm(
            prompt,
            response_format={"type": "json_object"}
        )
        
        if response:
            try:
                result = json.loads(response)
                context["partial_code"] = result.get("partial_code")
                context["todos"] = result.get("todos", [])
                return {"success": True, **result}
            except:
                pass
        
        return {"success": False, "error": "Failed to create partial code"}
    
    async def _generate_test_cases(self, params: Dict, context: Dict) -> Dict:
        """Generate test cases and validate them by running the code"""
        code = params.get("code") or context.get("working_code")
        if not code:
            return {"success": False, "error": "No code to generate tests for"}
        
        task_type = params.get("task_type", context.get("scenario_type", "implement"))
        difficulty = params.get("difficulty", context.get("difficulty", "medium"))
        
        # Используем новый промпт с ограничениями по времени
        prompt = GENERATE_TESTS_WITH_LIMITS_PROMPT.format(
            code=code,
            task_type=task_type,
            difficulty=difficulty,
            num_basic=params.get("num_basic", 3),
            num_edge=params.get("num_edge", 2),
            num_stress=params.get("num_stress", 1)
        )
        
        response = await self._call_llm(
            prompt,
            response_format={"type": "json_object"}
        )
        
        if response:
            try:
                result = json.loads(response)
                test_cases = result.get("test_cases", [])
                
                # Validate tests by running the code
                validated_tests = []
                for tc in test_cases:
                    input_data = tc.get("input", "")
                    expected = tc.get("output", "")
                    category = tc.get("category", "basic")
                    
                    # Run code to get actual output
                    actual, error = await self._run_code_for_test(code, input_data)
                    
                    if error:
                        # Skip tests that cause errors
                        print(f"[TEST] Skipping test due to error: {error}")
                        continue
                    
                    if actual is not None:
                        # Use actual output from running the code (correct answer)
                        tc["output"] = actual
                        
                        # Добавляем ограничения по времени если их нет
                        if "time_limit_ms" not in tc:
                            tc["time_limit_ms"] = self._get_default_time_limit(category, difficulty)
                        
                        # Добавляем ограничения по памяти если их нет
                        if "memory_limit_mb" not in tc:
                            tc["memory_limit_mb"] = 256
                        
                        # Добавляем баллы если их нет
                        if "points" not in tc:
                            tc["points"] = self._get_default_points(category, len(test_cases))
                        
                        validated_tests.append(tc)
                        
                        if actual != expected.strip():
                            print(f"[TEST] Fixed output: '{expected}' -> '{actual}'")
                
                # If validation failed for all, use original tests with default limits
                if not validated_tests:
                    for tc in test_cases:
                        category = tc.get("category", "basic")
                        if "time_limit_ms" not in tc:
                            tc["time_limit_ms"] = self._get_default_time_limit(category, difficulty)
                        if "memory_limit_mb" not in tc:
                            tc["memory_limit_mb"] = 256
                        if "points" not in tc:
                            tc["points"] = self._get_default_points(category, len(test_cases))
                    validated_tests = test_cases
                
                context["test_cases"] = validated_tests
                return {"success": True, "test_cases": validated_tests}
            except Exception as e:
                print(f"[TEST] Error generating tests: {e}")
                pass
        
        return {"success": False, "error": "Failed to generate tests"}
    
    def _get_default_time_limit(self, category: str, difficulty: str) -> int:
        """Получить ограничение по времени по умолчанию в миллисекундах"""
        limits = {
            "basic": {"easy": 5000, "medium": 3000, "hard": 2000},
            "edge": {"easy": 3000, "medium": 2000, "hard": 1500},
            "stress": {"easy": 2000, "medium": 1500, "hard": 1000}
        }
        return limits.get(category, limits["basic"]).get(difficulty, 3000)
    
    def _get_default_points(self, category: str, total_tests: int) -> int:
        """Получить баллы по умолчанию для теста"""
        if total_tests == 0:
            return 10
        
        # Распределяем 100 баллов между тестами
        # Стресс-тесты дают больше баллов
        weights = {"basic": 1, "edge": 1.5, "stress": 2}
        weight = weights.get(category, 1)
        
        # Примерно 100 / total_tests * weight
        base_points = 100 // total_tests
        return int(base_points * weight)
    
    async def _create_bad_style_code(self, params: Dict, context: Dict) -> Dict:
        """Create code with style issues"""
        prompt = BAD_STYLE_PROMPT.format(
            task_description=params.get("task_description", context.get("query", "")),
            issues=json.dumps(params.get("issues", ["naming", "complexity"]))
        )
        
        response = await self._call_llm(
            prompt,
            response_format={"type": "json_object"}
        )
        
        if response:
            try:
                result = json.loads(response)
                context["bad_style_code"] = result.get("code")
                context["style_issues"] = result.get("issues_present", [])
                context["clean_code"] = result.get("clean_version")
                return {"success": True, **result}
            except:
                pass
        
        return {"success": False, "error": "Failed to create bad style code"}
    
    def _create_step(self, params: Dict, context: Dict) -> Dict:
        """Create a scenario step"""
        step = ScenarioStep(
            step_type=StepType(params.get("step_type", "show_text")),
            content=params.get("content", ""),
            is_interactive=params.get("is_interactive", False),
            points=params.get("points", 0),
            time_limit_seconds=params.get("time_limit_seconds")
        )
        
        if "steps" not in context:
            context["steps"] = []
        context["steps"].append(step)
        
        return {"success": True, "step_index": len(context["steps"]) - 1}
    
    def _add_hint(self, params: Dict, context: Dict) -> Dict:
        """Add a hint"""
        hint = {
            "text": params.get("hint_text", ""),
            "penalty_percent": params.get("penalty_percent", 10),
            "reveal_after_attempts": params.get("reveal_after_attempts", 3)
        }
        
        if "hints" not in context:
            context["hints"] = []
        context["hints"].append(hint)
        
        return {"success": True, "hint_index": len(context["hints"]) - 1}
    
    def _finalize_scenario(self, params: Dict, context: Dict) -> Dict:
        """Finalize scenario metadata"""
        context["title"] = params.get("title", "Задача")
        context["description"] = params.get("description", "")
        context["hashtags"] = params.get("hashtags", [])
        context["estimated_time_minutes"] = params.get("estimated_time_minutes", 20)
        context["total_points"] = params.get("total_points", 100)
        
        return {"success": True, "finalized": True}
    
    async def build_scenario(
        self,
        query: str,
        difficulty: str = "medium",
        language: str = "python",
        scenario_type: Optional[str] = None
    ) -> Scenario:
        """
        Main entry point: Build a complete scenario.
        
        1. Plan the scenario (or use provided type)
        2. Execute tools to build content
        3. Assemble into Scenario object
        """
        import uuid
        
        context = {
            "query": query,
            "difficulty": difficulty,
            "language": language,
            "steps": [],
            "hints": []
        }
        
        # Step 1: Plan scenario
        if not scenario_type:
            plan = await self.plan_scenario(query, difficulty, language)
            scenario_type = plan.get("scenario_type", "implement")
        else:
            plan = {"scenario_type": scenario_type, "skills_tested": [query]}
        
        # Step 2: Build scenario based on type
        if scenario_type == "fix_code":
            await self._build_fix_code_scenario(context)
        
        elif scenario_type == "complete":
            await self._build_complete_scenario(context)
        
        elif scenario_type == "debug_output":
            await self._build_debug_output_scenario(context)
        
        elif scenario_type == "refactor":
            await self._build_refactor_scenario(context)
        
        elif scenario_type == "code_review":
            await self._build_code_review_scenario(context)
        
        elif scenario_type == "optimize":
            await self._build_optimize_scenario(context)
        
        elif scenario_type == "multi_step":
            await self._build_multi_step_scenario(context)
        
        elif scenario_type == "write_tests":
            await self._build_write_tests_scenario(context)
        
        elif scenario_type == "explain":
            await self._build_explain_scenario(context)
        
        else:  # implement (classic)
            await self._build_implement_scenario(context)
        
        # Step 3: Assemble scenario
        metadata = {
            "plan": plan,
            "working_code": context.get("working_code"),
            "test_cases": context.get("test_cases", []),
            "hints": context.get("hints", []),
            "task_type": scenario_type
        }
        
        # For optimization tasks, include original slow code for validation
        if scenario_type == "optimize":
            metadata["original_code"] = context.get("slow_code")
            metadata["optimal_code"] = context.get("optimal_code")
        
        scenario = Scenario(
            id=str(uuid.uuid4()),
            type=ScenarioType(scenario_type),
            title=context.get("title", f"Задача: {query}"),
            description=context.get("description", ""),
            difficulty=difficulty,
            language=language,
            steps=context.get("steps", []),
            total_points=context.get("total_points", 100),
            time_limit_minutes=context.get("estimated_time_minutes", 20),
            hashtags=context.get("hashtags", [query]),
            metadata=metadata
        )
        
        return scenario
    
    # ============== Scenario Builders ==============
    
    async def _build_fix_code_scenario(self, context: Dict):
        """Build a 'fix the bugs' scenario"""
        query = context["query"]
        difficulty = context["difficulty"]
        
        # Generate working code
        await self.execute_tool("generate_working_code", {
            "task_description": query,
            "complexity": difficulty
        }, context)
        
        # Inject bugs based on difficulty
        bug_config = {
            "easy": {
                "num_bugs": 1,
                "bug_types": ["logic", "syntax"],
                "difficulty": "obvious"
            },
            "medium": {
                "num_bugs": 2,
                "bug_types": ["logic", "edge_case", "off_by_one"],
                "difficulty": "subtle"
            },
            "hard": {
                "num_bugs": 3,
                "bug_types": ["logic", "edge_case", "off_by_one", "performance"],
                "difficulty": "tricky"
            }
        }
        config = bug_config.get(difficulty, bug_config["medium"])
        
        await self.execute_tool("inject_bugs", {
            "num_bugs": config["num_bugs"],
            "bug_types": config["bug_types"],
            "difficulty": config["difficulty"]
        }, context)
        
        # Generate tests with time limits
        await self.execute_tool("generate_test_cases", {
            "num_basic": 2,
            "num_edge": 2,
            "num_stress": 1,
            "task_type": "fix_code"
        }, context)
        
        # Build steps
        bugs = context.get("bugs", [])
        test_cases = context.get("test_cases", [])
        buggy_code = context.get("buggy_code", "")
        
        # Step 1: Show context with difficulty info
        difficulty_desc = {
            "easy": "очевидный",
            "medium": "требующий анализа",
            "hard": "хитрый и неочевидный"
        }
        
        self._create_step({
            "step_type": "show_text",
            "content": f"""## Исправление багов: {query}

В следующем коде есть **{len(bugs)} баг(ов)** ({difficulty_desc.get(difficulty, 'средней сложности')}).

Найдите и исправьте их так, чтобы код проходил все тесты.

### Информация о тестах:""",
            "is_interactive": False
        }, context)
        
        # Show test info with time limits
        test_info_lines = []
        for i, tc in enumerate(test_cases):
            category = tc.get("category", "basic")
            time_limit = tc.get("time_limit_ms", 3000)
            points = tc.get("points", 10)
            test_info_lines.append(f"- **Тест {i+1}** [{category}]: {time_limit}ms, {points} pts")
        
        self._create_step({
            "step_type": "show_text",
            "content": "\n".join(test_info_lines),
            "is_interactive": False
        }, context)
        
        # Step 2: Show buggy code
        self._create_step({
            "step_type": "show_code",
            "content": buggy_code,
            "metadata": {
                "language": context["language"], 
                "editable": True,
                "num_bugs": len(bugs),
                "bug_difficulty": config["difficulty"]
            }
        }, context)
        
        # Step 3: Ask to fix
        time_limits = {"easy": 600, "medium": 900, "hard": 1200}
        self._create_step({
            "step_type": "ask_fix",
            "content": "Исправьте код и отправьте решение",
            "is_interactive": True,
            "points": 70,
            "time_limit_seconds": time_limits.get(difficulty, 900)
        }, context)
        
        # Step 4: Run tests
        self._create_step({
            "step_type": "run_tests",
            "content": test_cases,
            "points": 30,
            "metadata": {"show_time_limits": True}
        }, context)
        
        # Add hints based on bugs and difficulty
        hint_penalties = {"easy": [5, 10, 15], "medium": [10, 15, 20], "hard": [15, 20, 25]}
        penalties = hint_penalties.get(difficulty, [10, 15, 20])
        
        for i, bug in enumerate(bugs[:3]):
            self._add_hint({
                "hint_text": bug.get("hint", f"Проверьте строку {bug.get('line', '?')}: {bug.get('description', '')}"),
                "penalty_percent": penalties[min(i, len(penalties)-1)]
            }, context)
        
        # Finalize
        self._finalize_scenario({
            "title": f"Исправление багов: {query}",
            "description": f"Найдите и исправьте {len(bugs)} баг(ов) в коде. Сложность: {difficulty}",
            "hashtags": [query, "debugging", "bug_fixing", difficulty],
            "estimated_time_minutes": {"easy": 15, "medium": 25, "hard": 35}.get(difficulty, 25),
            "total_points": 100
        }, context)
    
    async def _build_complete_scenario(self, context: Dict):
        """Build a 'complete the code' scenario"""
        query = context["query"]
        difficulty = context["difficulty"]
        
        # Generate working code
        await self.execute_tool("generate_working_code", {
            "task_description": query,
            "complexity": difficulty
        }, context)
        
        # Create partial code
        parts = ["main_logic"]
        if difficulty in ["medium", "hard"]:
            parts.append("edge_cases")
        if difficulty == "hard":
            parts.append("optimization")
        
        await self.execute_tool("create_partial_code", {
            "parts_to_remove": parts,
            "hint_level": "comments" if difficulty != "hard" else "signature"
        }, context)
        
        # Generate tests
        await self.execute_tool("generate_test_cases", {
            "num_basic": 3,
            "num_edge": 2,
            "num_stress": 1,
            "task_type": "complete"
        }, context)
        
        # Build steps
        todos = context.get("todos", [])
        partial_code = context.get("partial_code", "")
        
        # Step 1: Show task with WARNING about base code
        self._create_step({
            "step_type": "show_text",
            "content": f"""Допишите реализацию функций. Места для реализации отмечены TODO комментариями.

⚠️ **ВАЖНО**: Базовый код с TODO **НЕ ПРОЙДЁТ** ни один тест!
Если вы отправите код без реализации TODO - вы получите **0 баллов**.""",
            "is_interactive": False
        }, context)
        
        # Step 2: Show partial code
        self._create_step({
            "step_type": "show_code",
            "content": partial_code,
            "metadata": {
                "language": context["language"], 
                "editable": True, 
                "todos": todos,
                "base_code_hash": hash(partial_code),  # Для проверки что код изменён
                "reject_base_code": True  # Флаг для отклонения базового кода
            }
        }, context)
        
        # Step 3: Ask to complete
        self._create_step({
            "step_type": "ask_complete",
            "content": "Реализуйте все TODO и отправьте решение",
            "is_interactive": True,
            "points": 60,
            "time_limit_seconds": 900,
            "metadata": {
                "reject_unchanged_code": True,
                "base_code": partial_code
            }
        }, context)
        
        # Step 4: Run tests with validation
        test_cases = context.get("test_cases", [])
        # Добавляем валидационный тест который проверяет что TODO реализованы
        validation_test = {
            "input": test_cases[0]["input"] if test_cases else "",
            "output": test_cases[0]["output"] if test_cases else "",
            "category": "validation",
            "description": "Проверка что TODO реализованы",
            "time_limit_ms": 5000,
            "points": 0,  # Не даёт баллов, только проверяет
            "hidden": True,
            "fail_message": "Код с нереализованными TODO не принимается. Реализуйте все TODO."
        }
        
        self._create_step({
            "step_type": "run_tests",
            "content": [validation_test] + test_cases,
            "points": 40,
            "metadata": {
                "check_todo_implemented": True,
                "base_code": partial_code
            }
        }, context)
        
        # Add hints based on TODOs
        for i, todo in enumerate(todos[:3]):
            self._add_hint({
                "hint_text": todo.get("description", "Подсказка"),
                "penalty_percent": 10 + i * 5
            }, context)
        
        # Finalize with metadata about base code rejection
        self._finalize_scenario({
            "title": f"Дополните код: {query}",
            "description": f"Реализуйте {len(todos)} функци(й/ю). Базовый код без реализации TODO даёт 0 баллов.",
            "hashtags": [query, "implementation"],
            "estimated_time_minutes": 20 + len(todos) * 5,
            "total_points": 100
        }, context)
        
        # Store base code for validation
        context["base_code_for_validation"] = partial_code
    
    async def _build_debug_output_scenario(self, context: Dict):
        """Build a 'debug based on output' scenario"""
        query = context["query"]
        difficulty = context["difficulty"]
        
        # Generate working code
        await self.execute_tool("generate_working_code", {
            "task_description": query,
            "complexity": difficulty
        }, context)
        
        # Inject ONE subtle bug
        await self.execute_tool("inject_bugs", {
            "num_bugs": 1,
            "bug_types": ["logic"],
            "difficulty": "tricky"
        }, context)
        
        # Generate tests
        await self.execute_tool("generate_test_cases", {
            "num_basic": 2,
            "num_edge": 1,
            "num_stress": 0
        }, context)
        
        # Build steps
        test_cases = context.get("test_cases", [])
        
        # Step 1: Show problem description
        self._create_step({
            "step_type": "show_text",
            "content": f"Код должен решать задачу: {query}\n\nНо он выдаёт неправильный результат. Найдите и исправьте ошибку.",
            "is_interactive": False
        }, context)
        
        # Step 2: Show code
        self._create_step({
            "step_type": "show_code",
            "content": context.get("buggy_code", ""),
            "metadata": {"language": context["language"], "editable": True}
        }, context)
        
        # Step 3: Show expected vs actual output
        if test_cases:
            tc = test_cases[0]
            self._create_step({
                "step_type": "show_output",
                "content": {
                    "input": tc.get("input", ""),
                    "expected": tc.get("output", ""),
                    "actual": "??? (запустите код чтобы увидеть)"
                },
                "metadata": {"show_diff": True}
            }, context)
        
        # Step 4: Ask to fix
        self._create_step({
            "step_type": "ask_fix",
            "content": "Найдите баг и исправьте код",
            "is_interactive": True,
            "points": 80,
            "time_limit_seconds": 600
        }, context)
        
        # Step 5: Run tests
        self._create_step({
            "step_type": "run_tests",
            "content": test_cases,
            "points": 20
        }, context)
        
        # Add hint
        bugs = context.get("bugs", [])
        if bugs:
            self._add_hint({
                "hint_text": bugs[0].get("hint", "Проверьте логику"),
                "penalty_percent": 20
            }, context)
        
        # Finalize
        self._finalize_scenario({
            "title": f"Отладка: {query}",
            "description": "Найдите баг по неправильному выводу",
            "hashtags": [query, "debugging", "output_analysis"],
            "estimated_time_minutes": 15,
            "total_points": 100
        }, context)
    
    async def _build_refactor_scenario(self, context: Dict):
        """Build a 'refactor the code' scenario"""
        query = context["query"]
        difficulty = context["difficulty"]
        
        # Create code with bad style
        issues = ["naming", "magic_numbers"]
        if difficulty in ["medium", "hard"]:
            issues.extend(["complexity", "duplication"])
        if difficulty == "hard":
            issues.extend(["deep_nesting", "long_functions"])
        
        await self.execute_tool("create_code_with_bad_style", {
            "task_description": query,
            "issues": issues
        }, context)
        
        # Generate tests (to verify refactored code still works)
        await self.execute_tool("generate_test_cases", {
            "num_basic": 3,
            "num_edge": 2,
            "num_stress": 0
        }, context)
        
        # Build steps
        style_issues = context.get("style_issues", [])
        
        # Step 1: Show task
        self._create_step({
            "step_type": "show_text",
            "content": f"Следующий код работает, но имеет проблемы с качеством. Проведите рефакторинг, сохранив функциональность.",
            "is_interactive": False
        }, context)
        
        # Step 2: Show bad code
        self._create_step({
            "step_type": "show_code",
            "content": context.get("bad_style_code", ""),
            "metadata": {"language": context["language"], "editable": True}
        }, context)
        
        # Step 3: List issues to fix
        issues_text = "\n".join([f"- {issue.get('type', 'issue')}: {issue.get('description', '')}" 
                                  for issue in style_issues[:5]])
        self._create_step({
            "step_type": "show_text",
            "content": f"Проблемы для исправления:\n{issues_text}",
            "is_interactive": False
        }, context)
        
        # Step 4: Ask to refactor
        self._create_step({
            "step_type": "ask_write",
            "content": "Отрефакторите код и отправьте решение",
            "is_interactive": True,
            "points": 60,
            "time_limit_seconds": 900
        }, context)
        
        # Step 5: Run tests
        self._create_step({
            "step_type": "run_tests",
            "content": context.get("test_cases", []),
            "points": 40
        }, context)
        
        # Add hints
        for i, issue in enumerate(style_issues[:3]):
            self._add_hint({
                "hint_text": issue.get("how_to_fix", "Подсказка"),
                "penalty_percent": 5 + i * 5
            }, context)
        
        # Finalize
        self._finalize_scenario({
            "title": f"Рефакторинг: {query}",
            "description": f"Улучшите качество кода ({len(style_issues)} проблем)",
            "hashtags": [query, "refactoring", "code_quality"],
            "estimated_time_minutes": 20 + len(style_issues) * 3,
            "total_points": 100
        }, context)
    
    async def _build_code_review_scenario(self, context: Dict):
        """Build a 'code review' scenario"""
        query = context["query"]
        difficulty = context["difficulty"]
        
        # Create code with issues (mix of bugs and style)
        await self.execute_tool("generate_working_code", {
            "task_description": query,
            "complexity": difficulty
        }, context)
        
        # Inject some bugs
        await self.execute_tool("inject_bugs", {
            "num_bugs": 1,
            "bug_types": ["edge_case"],
            "difficulty": "subtle"
        }, context)
        
        # Also create style issues version
        await self.execute_tool("create_code_with_bad_style", {
            "task_description": query,
            "issues": ["naming", "no_comments"]
        }, context)
        
        # Build steps
        bugs = context.get("bugs", [])
        style_issues = context.get("style_issues", [])
        
        # Step 1: Show task
        self._create_step({
            "step_type": "show_text",
            "content": "Проведите код-ревью. Найдите баги, проблемы со стилем и предложите улучшения.",
            "is_interactive": False
        }, context)
        
        # Step 2: Show code for review
        self._create_step({
            "step_type": "show_code",
            "content": context.get("buggy_code", context.get("bad_style_code", "")),
            "metadata": {"language": context["language"], "editable": False, "review_mode": True}
        }, context)
        
        # Step 3: Ask for review
        self._create_step({
            "step_type": "ask_review",
            "content": {
                "questions": [
                    "Какие баги вы нашли?",
                    "Какие проблемы со стилем?",
                    "Какие улучшения предлагаете?"
                ],
                "expected_findings": len(bugs) + len(style_issues)
            },
            "is_interactive": True,
            "points": 100,
            "time_limit_seconds": 600
        }, context)
        
        # Finalize
        self._finalize_scenario({
            "title": f"Код-ревью: {query}",
            "description": "Проведите ревью кода и найдите проблемы",
            "hashtags": [query, "code_review", "best_practices"],
            "estimated_time_minutes": 15,
            "total_points": 100
        }, context)
    
    async def _build_optimize_scenario(self, context: Dict):
        """Build an 'optimize the code' scenario"""
        query = context["query"]
        difficulty = context.get("difficulty", "medium")
        
        # Generate SLOW but working code (O(n²) or worse)
        await self._generate_slow_code({
            "task_description": query,
            "language": context.get("language", "python")
        }, context)
        
        slow_code = context.get("slow_code", "")
        
        # Generate optimal solution for reference
        await self._generate_optimal_code({
            "task_description": query,
            "slow_code": slow_code,
            "language": context.get("language", "python")
        }, context)
        
        optimal_code = context.get("optimal_code", "")
        
        # Generate tests with STRICT time limits for optimization tasks
        # Use optimal code for generating correct outputs
        context["working_code"] = optimal_code  # Use optimal for correct answers
        await self.execute_tool("generate_test_cases", {
            "num_basic": 3,
            "num_edge": 2,
            "num_stress": 4,  # Больше стресс-тестов для оптимизации
            "task_type": "optimize"
        }, context)
        
        # Override time limits for optimization scenario
        # ВАЖНО: Лимиты должны быть достаточно строгими, чтобы O(n²) не проходил на больших данных
        test_cases = context.get("test_cases", [])
        for tc in test_cases:
            category = tc.get("category", "basic")
            if category == "stress":
                # ОЧЕНЬ строгий лимит - только оптимальный O(n) или O(n log n) код пройдёт
                # O(n²) на N=10000 занимает ~1-10 секунд, поэтому ставим 500ms
                tc["time_limit_ms"] = 500  # 0.5 секунды - O(n²) НЕ пройдёт
                tc["points"] = tc.get("points", 20)  # Больше баллов за стресс
            elif category == "edge":
                tc["time_limit_ms"] = 1500  # 1.5 секунды
                tc["points"] = tc.get("points", 10)
            else:
                tc["time_limit_ms"] = 3000  # 3 секунды - любой код пройдёт
                tc["points"] = tc.get("points", 5)
        
        # Build steps
        self._create_step({
            "step_type": "show_text",
            "content": f"""## Задача на оптимизацию: {query}

Дан код, который работает **ПРАВИЛЬНО**, но **СЛИШКОМ МЕДЛЕННО** для больших данных.

### Ваша задача:
Оптимизировать алгоритм так, чтобы он проходил **ВСЕ** тесты, включая стресс-тесты.

### Текущая сложность: O(n²) или хуже
### Требуемая сложность: O(n) или O(n log n)

⚠️ **ВАЖНО**: Базовый неоптимизированный код **НЕ ПРОЙДЁТ** стресс-тесты!""",
            "is_interactive": False
        }, context)
        
        self._create_step({
            "step_type": "show_code",
            "content": slow_code,
            "metadata": {
                "language": context["language"], 
                "editable": True, 
                "is_slow": True,
                "slow_complexity": "O(n²)",
                "required_complexity": "O(n) или O(n log n)"
            }
        }, context)
        
        # Show performance requirements with test info
        test_info = []
        for i, tc in enumerate(test_cases):
            category = tc.get("category", "basic")
            time_limit = tc.get("time_limit_ms", 5000)
            points = tc.get("points", 10)
            desc = tc.get("description", f"Тест {i+1}")
            
            if category == "stress":
                status = "❌ (медленный код не пройдёт)"
            else:
                status = "✓ (любой код пройдёт)"
            
            test_info.append(f"- **Тест {i+1}** [{category}]: {time_limit}ms, {points} pts {status}")
        
        self._create_step({
            "step_type": "show_text",
            "content": f"""### Ограничения по времени для тестов:

{chr(10).join(test_info)}

### Подсказки для оптимизации:
- Используйте **хеш-таблицы** (dict, set) вместо вложенных циклов
- Попробуйте **сортировку + два указателя**
- Рассмотрите **префиксные суммы**
- Примените **бинарный поиск** где возможно""",
            "is_interactive": False
        }, context)
        
        self._create_step({
            "step_type": "ask_write",
            "content": "Оптимизируйте код",
            "is_interactive": True,
            "points": 60,
            "time_limit_seconds": 900
        }, context)
        
        self._create_step({
            "step_type": "run_tests",
            "content": context.get("test_cases", []),
            "points": 40,
            "metadata": {"check_performance": True, "time_limits": True}
        }, context)
        
        # Add hints about optimization
        self._add_hint({
            "hint_text": "Попробуйте использовать словарь (dict) для O(1) поиска вместо вложенных циклов",
            "penalty_percent": 10
        }, context)
        
        self._add_hint({
            "hint_text": "Можно отсортировать данные и использовать бинарный поиск или два указателя",
            "penalty_percent": 15
        }, context)
        
        # Finalize with optimal code as reference
        self._finalize_scenario({
            "title": f"Оптимизация: {query}",
            "description": f"Дан рабочий но медленный код (O(n²)). Оптимизируйте его до O(n) или O(n log n).",
            "hashtags": [query, "optimization", "performance", "algorithms"],
            "estimated_time_minutes": 25,
            "total_points": 100
        }, context)
        
        # Store optimal code for showing after completion
        context["optimal_solution"] = context.get("optimal_code", "")
    
    async def _build_multi_step_scenario(self, context: Dict):
        """Build a multi-step progressive scenario"""
        query = context["query"]
        difficulty = context["difficulty"]
        
        # Generate base code
        await self.execute_tool("generate_working_code", {
            "task_description": f"Базовая версия: {query}",
            "complexity": "simple"
        }, context)
        
        base_code = context.get("working_code", "")
        
        # Generate tests
        await self.execute_tool("generate_test_cases", {
            "num_basic": 3,
            "num_edge": 2,
            "num_stress": 1
        }, context)
        
        # Build progressive steps
        
        # Step 1: Understand the problem
        self._create_step({
            "step_type": "show_text",
            "content": f"Задача: {query}\n\nЭто многошаговая задача. Вы будете постепенно улучшать решение.",
            "is_interactive": False
        }, context)
        
        # Step 2: Write basic solution
        self._create_step({
            "step_type": "ask_write",
            "content": "Шаг 1: Напишите базовое решение (не оптимизированное)",
            "is_interactive": True,
            "points": 30,
            "time_limit_seconds": 600
        }, context)
        
        # Step 3: Run basic tests
        basic_tests = [t for t in context.get("test_cases", []) if t.get("category") == "basic"]
        self._create_step({
            "step_type": "run_tests",
            "content": basic_tests or context.get("test_cases", [])[:2],
            "points": 10
        }, context)
        
        # Step 4: Handle edge cases
        self._create_step({
            "step_type": "show_text",
            "content": "Шаг 2: Теперь обработайте граничные случаи",
            "is_interactive": False
        }, context)
        
        self._create_step({
            "step_type": "ask_write",
            "content": "Добавьте обработку граничных случаев",
            "is_interactive": True,
            "points": 30,
            "time_limit_seconds": 600
        }, context)
        
        # Step 5: Run edge case tests
        edge_tests = [t for t in context.get("test_cases", []) if t.get("category") == "edge"]
        self._create_step({
            "step_type": "run_tests",
            "content": edge_tests or context.get("test_cases", [])[2:4],
            "points": 10
        }, context)
        
        # Step 6: Optimize
        self._create_step({
            "step_type": "show_text",
            "content": "Шаг 3: Оптимизируйте решение для больших данных",
            "is_interactive": False
        }, context)
        
        self._create_step({
            "step_type": "ask_write",
            "content": "Оптимизируйте код",
            "is_interactive": True,
            "points": 20,
            "time_limit_seconds": 600
        }, context)
        
        # Step 7: Run all tests
        self._create_step({
            "step_type": "run_tests",
            "content": context.get("test_cases", []),
            "points": 0,
            "metadata": {"final_validation": True}
        }, context)
        
        # Finalize
        self._finalize_scenario({
            "title": f"Многошаговая задача: {query}",
            "description": "Постепенно улучшайте решение",
            "hashtags": [query, "progressive", "multi_step"],
            "estimated_time_minutes": 35,
            "total_points": 100
        }, context)
    
    async def _build_implement_scenario(self, context: Dict):
        """Build a classic 'implement from scratch' scenario"""
        query = context["query"]
        difficulty = context["difficulty"]
        
        # Configuration based on difficulty
        config = {
            "easy": {
                "num_basic": 3, "num_edge": 1, "num_stress": 0,
                "time_limit": 900, "code_lines": "10-20",
                "description": "Простая задача на базовые навыки программирования"
            },
            "medium": {
                "num_basic": 3, "num_edge": 2, "num_stress": 1,
                "time_limit": 1500, "code_lines": "20-40",
                "description": "Задача средней сложности, требующая знания структур данных"
            },
            "hard": {
                "num_basic": 2, "num_edge": 3, "num_stress": 2,
                "time_limit": 2400, "code_lines": "40-80",
                "description": "Сложная задача, требующая оптимального алгоритма"
            }
        }
        cfg = config.get(difficulty, config["medium"])
        
        # Generate solution
        await self.execute_tool("generate_working_code", {
            "task_description": query,
            "complexity": difficulty
        }, context)
        
        # Generate tests with time limits
        await self.execute_tool("generate_test_cases", {
            "num_basic": cfg["num_basic"],
            "num_edge": cfg["num_edge"],
            "num_stress": cfg["num_stress"],
            "task_type": "implement"
        }, context)
        
        test_cases = context.get("test_cases", [])
        
        # Build test info for display
        test_info_lines = []
        for i, tc in enumerate(test_cases):
            category = tc.get("category", "basic")
            time_limit = tc.get("time_limit_ms", 3000)
            points = tc.get("points", 10)
            hidden = "🔒" if tc.get("hidden", False) else ""
            test_info_lines.append(f"- **Тест {i+1}** [{category}]: {time_limit}ms, {points} pts {hidden}")
        
        # Build steps
        self._create_step({
            "step_type": "show_text",
            "content": f"""## {query}

{cfg["description"]}

### Сложность: {difficulty.upper()}
### Ожидаемый размер решения: {cfg["code_lines"]} строк кода
### Время на решение: {cfg["time_limit"] // 60} минут

### Тесты:
{chr(10).join(test_info_lines)}

Напишите решение с нуля. Читайте данные из stdin, выводите в stdout.""",
            "is_interactive": False
        }, context)
        
        self._create_step({
            "step_type": "ask_write",
            "content": "Напишите код решения",
            "is_interactive": True,
            "points": 70,
            "time_limit_seconds": cfg["time_limit"]
        }, context)
        
        self._create_step({
            "step_type": "run_tests",
            "content": test_cases,
            "points": 30,
            "metadata": {"show_time_limits": True}
        }, context)
        
        # Add hints based on difficulty
        hints = {
            "easy": ["Начните с простого решения, не думайте об оптимизации"],
            "medium": ["Подумайте какую структуру данных использовать", "Обработайте граничные случаи"],
            "hard": ["Оцените сложность вашего алгоритма", "Подумайте об оптимизации", "Проверьте граничные случаи"]
        }
        for i, hint in enumerate(hints.get(difficulty, [])):
            self._add_hint({
                "hint_text": hint,
                "penalty_percent": 5 + i * 5
            }, context)
        
        # Finalize
        self._finalize_scenario({
            "title": query,
            "description": f"{cfg['description']}. Сложность: {difficulty}",
            "hashtags": [query, difficulty, "implementation"],
            "estimated_time_minutes": cfg["time_limit"] // 60,
            "total_points": 100
        }, context)
    
    async def _build_write_tests_scenario(self, context: Dict):
        """Build a 'write tests for code' scenario"""
        query = context["query"]
        difficulty = context["difficulty"]
        
        # Generate working code
        await self.execute_tool("generate_working_code", {
            "task_description": query,
            "complexity": difficulty
        }, context)
        
        # Build steps
        self._create_step({
            "step_type": "show_text",
            "content": f"Напишите тесты для следующего кода. Покройте базовые случаи, граничные условия и возможные ошибки.",
            "is_interactive": False
        }, context)
        
        self._create_step({
            "step_type": "show_code",
            "content": context.get("working_code", ""),
            "metadata": {"language": context["language"], "editable": False}
        }, context)
        
        # Requirements based on difficulty
        test_requirements = {
            "easy": "Напишите минимум 3 теста: 1 базовый, 1 граничный, 1 на ошибку",
            "medium": "Напишите минимум 5 тестов: 2 базовых, 2 граничных, 1 на производительность",
            "hard": "Напишите минимум 7 тестов с полным покрытием: базовые, граничные, ошибки, производительность"
        }
        
        self._create_step({
            "step_type": "show_text",
            "content": test_requirements.get(difficulty, test_requirements["medium"]),
            "is_interactive": False
        }, context)
        
        self._create_step({
            "step_type": "ask_write",
            "content": "Напишите тесты (используйте pytest или unittest)",
            "is_interactive": True,
            "points": 80,
            "time_limit_seconds": 900,
            "metadata": {"test_mode": True, "expected_test_count": {"easy": 3, "medium": 5, "hard": 7}.get(difficulty, 5)}
        }, context)
        
        # Validation step - check if tests pass on correct code and fail on buggy
        self._create_step({
            "step_type": "run_tests",
            "content": {"validate_tests": True, "code_to_test": context.get("working_code", "")},
            "points": 20,
            "metadata": {"check_test_quality": True}
        }, context)
        
        # Finalize
        self._finalize_scenario({
            "title": f"Написание тестов: {query}",
            "description": "Напишите unit-тесты для данного кода",
            "hashtags": [query, "testing", "unit_tests"],
            "estimated_time_minutes": {"easy": 15, "medium": 20, "hard": 30}.get(difficulty, 20),
            "total_points": 100
        }, context)
    
    async def _build_explain_scenario(self, context: Dict):
        """Build an 'explain the code' scenario"""
        query = context["query"]
        difficulty = context["difficulty"]
        
        # Generate code to explain
        await self.execute_tool("generate_working_code", {
            "task_description": query,
            "complexity": difficulty,
            "style": "minimal"  # Less comments to make it harder to understand
        }, context)
        
        # Build steps
        self._create_step({
            "step_type": "show_text",
            "content": "Изучите следующий код и объясните:",
            "is_interactive": False
        }, context)
        
        self._create_step({
            "step_type": "show_code",
            "content": context.get("working_code", ""),
            "metadata": {"language": context["language"], "editable": False}
        }, context)
        
        # Questions based on difficulty
        questions = {
            "easy": [
                "Что делает этот код?",
                "Какой результат вернёт функция для входа X?"
            ],
            "medium": [
                "Что делает этот код?",
                "Какова временная сложность алгоритма?",
                "Какие граничные случаи обрабатывает код?"
            ],
            "hard": [
                "Что делает этот код?",
                "Какова временная и пространственная сложность?",
                "Какие граничные случаи обрабатывает код?",
                "Какие потенциальные проблемы вы видите?",
                "Как бы вы улучшили этот код?"
            ]
        }
        
        self._create_step({
            "step_type": "ask_explain",
            "content": {
                "questions": questions.get(difficulty, questions["medium"]),
                "code_context": context.get("working_code", "")
            },
            "is_interactive": True,
            "points": 100,
            "time_limit_seconds": 600
        }, context)
        
        # Finalize
        self._finalize_scenario({
            "title": f"Объяснение кода: {query}",
            "description": "Объясните что делает данный код",
            "hashtags": [query, "code_reading", "explanation"],
            "estimated_time_minutes": {"easy": 5, "medium": 10, "hard": 15}.get(difficulty, 10),
            "total_points": 100
        }, context)


# ============== Singleton ==============

engine = ScenarioEngine()


async def generate_scenario(
    query: str,
    difficulty: str = "medium",
    language: str = "python",
    scenario_type: Optional[str] = None
) -> Dict:
    """
    Generate a complete scenario for the given query.
    
    Args:
        query: What to test (e.g., "binary search", "ООП")
        difficulty: easy/medium/hard
        language: Programming language
        scenario_type: Optional specific type, or let AI decide
    
    Returns:
        Scenario as dictionary
    """
    scenario = await engine.build_scenario(query, difficulty, language, scenario_type)
    return scenario.to_dict()
