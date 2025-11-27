"""
Dynamic Task Templates
Flexible instruction system for different task types
"""
from typing import Dict, List, Optional
from pydantic import BaseModel


class TaskTemplate(BaseModel):
    """Template for generating specific task types"""
    type_id: str
    name: str
    description: str
    
    # Generation instructions
    system_prompt: str
    task_structure: Dict[str, str]  # Field -> Description
    
    # Validation rules
    requires_code: bool = False
    requires_tests: bool = False
    test_format: Optional[str] = None  # stdin/stdout, function_call, class_test
    
    # Difficulty modifiers
    difficulty_hints: Dict[str, str] = {}  # easy/medium/hard -> specific instructions
    
    # Example for few-shot
    example: Optional[Dict] = None


# ============== Live Coding Templates ==============

LIVE_CODING_ALGORITHMIC = TaskTemplate(
    type_id="live_coding_algo",
    name="Алгоритмическая задача",
    description="Классическая задача на алгоритмы с stdin/stdout",
    requires_code=True,
    requires_tests=True,
    test_format="stdin_stdout",
    
    system_prompt="""Ты — эксперт по алгоритмическим задачам для технических интервью.
Создавай задачи в стиле LeetCode/Codeforces с чёткими условиями.

ВАЖНО:
- Условие должно быть понятным и однозначным
- Тесты должны покрывать граничные случаи
- Формат ввода/вывода должен быть простым (stdin/stdout)
- Сложность должна соответствовать уровню""",

    task_structure={
        "title": "Краткое название задачи",
        "description": "Полное условие с объяснением что нужно сделать",
        "input_format": "Формат входных данных (что читать из stdin)",
        "output_format": "Формат выходных данных (что выводить в stdout)",
        "constraints": "Ограничения на входные данные (размеры, диапазоны)",
        "test_cases": "Открытые тесты с примерами",
        "hidden_tests": "Скрытые тесты для проверки",
        "hints": "Подсказки для решения",
        "time_limit": "Ограничение по времени",
        "complexity": "Ожидаемая сложность O(...)"
    },
    
    difficulty_hints={
        "easy": "Простая задача на 1 концепцию, решается за 5-10 минут. Линейная сложность.",
        "medium": "Задача на 1-2 концепции, требует продумывания. O(n log n) или O(n).",
        "hard": "Сложная задача, комбинация техник, оптимизация. Может требовать DP или сложных структур."
    },
    
    example={
        "title": "Два числа с заданной суммой",
        "description": "Дан массив целых чисел nums и целое число target. Найдите два числа, сумма которых равна target, и верните их индексы.",
        "input_format": "Первая строка: n - размер массива. Вторая строка: n чисел через пробел. Третья строка: target.",
        "output_format": "Два индекса через пробел (0-indexed).",
        "constraints": "2 ≤ n ≤ 10^4, -10^9 ≤ nums[i] ≤ 10^9",
        "test_cases": [
            {"input": "4\n2 7 11 15\n9", "output": "0 1"},
            {"input": "3\n3 2 4\n6", "output": "1 2"}
        ]
    }
)


LIVE_CODING_OOP = TaskTemplate(
    type_id="live_coding_oop",
    name="ООП задача",
    description="Задача на проектирование классов и ООП",
    requires_code=True,
    requires_tests=True,
    test_format="class_test",
    
    system_prompt="""Ты — эксперт по объектно-ориентированному программированию.
Создавай задачи на проектирование классов, наследование, полиморфизм.

ВАЖНО:
- Чёткое описание требуемых классов и методов
- Указать какие методы должны быть реализованы
- Тесты проверяют создание объектов и вызов методов
- Код должен демонстрировать принципы ООП""",

    task_structure={
        "title": "Название задачи",
        "description": "Что нужно реализовать (классы, методы, наследование)",
        "classes_required": "Список классов с описанием",
        "methods_required": "Список методов с сигнатурами",
        "test_cases": "Примеры использования классов",
        "hints": "Подсказки по реализации"
    },
    
    difficulty_hints={
        "easy": "1-2 простых класса, базовое наследование",
        "medium": "Иерархия классов, полиморфизм, абстрактные методы",
        "hard": "Сложные паттерны проектирования, множественное наследование, миксины"
    },
    
    example={
        "title": "Иерархия геометрических фигур",
        "description": "Создайте базовый класс Shape с методом area(). Реализуйте подклассы Rectangle(length, width) и Circle(radius).",
        "classes_required": ["Shape (базовый)", "Rectangle(Shape)", "Circle(Shape)"],
        "methods_required": ["area() -> float"],
        "test_code": """
shapes = [Rectangle(3, 4), Circle(5), Rectangle(2, 2)]
assert Rectangle(3, 4).area() == 12
assert abs(Circle(1).area() - 3.14159) < 0.01
"""
    }
)


LIVE_CODING_SYSTEM_DESIGN = TaskTemplate(
    type_id="live_coding_system",
    name="Системный дизайн (код)",
    description="Реализация компонента системы",
    requires_code=True,
    requires_tests=True,
    test_format="function_call",
    
    system_prompt="""Ты — эксперт по системному дизайну.
Создавай задачи на реализацию компонентов систем: кэши, очереди, rate limiters и т.д.

ВАЖНО:
- Чёткий API с методами
- Учитывать производительность
- Тесты проверяют корректность и edge cases""",

    task_structure={
        "title": "Название компонента",
        "description": "Что нужно реализовать и зачем",
        "api": "Публичный API (методы с сигнатурами)",
        "requirements": "Требования к производительности",
        "test_cases": "Сценарии использования",
        "hints": "Подсказки по структурам данных"
    },
    
    difficulty_hints={
        "easy": "Простой компонент: стек, очередь, простой кэш",
        "medium": "LRU Cache, Rate Limiter, простой планировщик",
        "hard": "Распределённые системы, консенсус, сложные оптимизации"
    }
)


# ============== Hard Skills Templates ==============

HARD_SKILLS_CONCEPT = TaskTemplate(
    type_id="hard_skills_concept",
    name="Теоретический вопрос",
    description="Вопрос на понимание концепции",
    requires_code=False,
    requires_tests=False,
    
    system_prompt="""Ты — технический интервьюер.
Создавай глубокие вопросы на понимание технологий и концепций.

ВАЖНО:
- Вопрос должен проверять понимание, а не заучивание
- Включай follow-up вопросы
- Давай критерии хорошего ответа""",

    task_structure={
        "title": "Краткая формулировка вопроса",
        "question": "Полный вопрос",
        "key_points": "Ключевые моменты хорошего ответа",
        "follow_ups": "Дополнительные вопросы",
        "example_answer": "Пример хорошего ответа",
        "red_flags": "Признаки плохого ответа",
        "resources": "Полезные ресурсы для изучения"
    },
    
    difficulty_hints={
        "easy": "Базовые концепции, определения",
        "medium": "Сравнение подходов, trade-offs, когда что использовать",
        "hard": "Глубокое понимание внутренностей, оптимизации, edge cases"
    }
)


HARD_SKILLS_CODE_REVIEW = TaskTemplate(
    type_id="hard_skills_review",
    name="Code Review",
    description="Найти проблемы в коде",
    requires_code=True,
    requires_tests=False,
    
    system_prompt="""Ты — senior разработчик проводящий code review.
Создавай задачи на поиск багов, антипаттернов, проблем производительности.

ВАЖНО:
- Код должен содержать реальные проблемы
- Проблемы должны быть не очевидными
- Указать что именно нужно найти""",

    task_structure={
        "title": "Название задачи",
        "context": "Контекст кода (что он делает)",
        "code": "Код для ревью",
        "task": "Что нужно найти/исправить",
        "issues": "Список проблем (скрытый)",
        "hints": "Подсказки"
    }
)


# ============== Soft Skills Templates ==============

SOFT_SKILLS_BEHAVIORAL = TaskTemplate(
    type_id="soft_skills_behavioral",
    name="Поведенческий вопрос",
    description="Вопрос на soft skills (STAR)",
    requires_code=False,
    requires_tests=False,
    
    system_prompt="""Ты — HR-специалист проводящий behavioral интервью.
Создавай вопросы на оценку soft skills с использованием STAR метода.

ВАЖНО:
- Вопрос должен требовать конкретного примера из опыта
- Давай структуру ответа (STAR)
- Указывай что оценивается""",

    task_structure={
        "title": "Краткая тема",
        "question": "Полный вопрос",
        "what_evaluates": "Какие качества оценивает",
        "star_structure": "Как структурировать ответ",
        "good_answer_signs": "Признаки хорошего ответа",
        "bad_answer_signs": "Признаки плохого ответа",
        "example_answer": "Пример ответа"
    }
)


# ============== Logic Templates ==============

LOGIC_PUZZLE = TaskTemplate(
    type_id="logic_puzzle",
    name="Логическая задача",
    description="Задача на логику и рассуждения",
    requires_code=False,
    requires_tests=False,
    
    system_prompt="""Ты — составитель логических задач.
Создавай интересные задачи на логику, которые часто дают на интервью.

ВАЖНО:
- Задача должна решаться рассуждениями
- Не требует специальных знаний
- Есть чёткий правильный ответ""",

    task_structure={
        "title": "Название задачи",
        "puzzle": "Условие задачи",
        "hints": "Подсказки (по уровням)",
        "solution": "Решение с объяснением",
        "answer": "Краткий ответ"
    }
)


LOGIC_ESTIMATION = TaskTemplate(
    type_id="logic_estimation",
    name="Estimation задача",
    description="Задача на оценку (Fermi)",
    requires_code=False,
    requires_tests=False,
    
    system_prompt="""Ты — составитель Fermi-задач.
Создавай задачи на оценку порядка величины.

ВАЖНО:
- Нет точного ответа, важен ход рассуждений
- Требует разбиения на подзадачи
- Оценивается структура мышления""",

    task_structure={
        "title": "Вопрос",
        "question": "Полная формулировка",
        "approach": "Как подходить к решению",
        "breakdown": "Разбиение на компоненты",
        "estimation": "Примерная оценка с объяснением"
    }
)


# ============== Template Registry ==============

TEMPLATES: Dict[str, Dict[str, TaskTemplate]] = {
    "live_coding": {
        "algorithmic": LIVE_CODING_ALGORITHMIC,
        "oop": LIVE_CODING_OOP,
        "system": LIVE_CODING_SYSTEM_DESIGN,
    },
    "hard_skills": {
        "concept": HARD_SKILLS_CONCEPT,
        "code_review": HARD_SKILLS_CODE_REVIEW,
    },
    "soft_skills": {
        "behavioral": SOFT_SKILLS_BEHAVIORAL,
    },
    "logic": {
        "puzzle": LOGIC_PUZZLE,
        "estimation": LOGIC_ESTIMATION,
    }
}


def get_template(section_type: str, task_subtype: str = None) -> TaskTemplate:
    """Get appropriate template for task generation"""
    section_templates = TEMPLATES.get(section_type, {})
    
    if task_subtype and task_subtype in section_templates:
        return section_templates[task_subtype]
    
    # Return first/default template for section
    if section_templates:
        return list(section_templates.values())[0]
    
    # Fallback to algorithmic
    return LIVE_CODING_ALGORITHMIC


def detect_task_subtype(query: str, section_type: str) -> str:
    """Detect task subtype from query"""
    query_lower = query.lower()
    
    if section_type == "live_coding":
        if any(kw in query_lower for kw in ["класс", "class", "ооп", "oop", "наследование", "inheritance"]):
            return "oop"
        if any(kw in query_lower for kw in ["cache", "кэш", "rate limit", "queue", "очередь", "система"]):
            return "system"
        return "algorithmic"
    
    elif section_type == "hard_skills":
        if any(kw in query_lower for kw in ["review", "ревью", "найти ошибк", "баг", "bug"]):
            return "code_review"
        return "concept"
    
    elif section_type == "logic":
        if any(kw in query_lower for kw in ["сколько", "оцени", "estimation", "fermi"]):
            return "estimation"
        return "puzzle"
    
    return "default"


def build_generation_prompt(
    template: TaskTemplate,
    query: str,
    difficulty: str,
    concepts: List[str] = []
) -> str:
    """Build complete prompt for task generation"""
    
    # Structure description
    structure_desc = "\n".join([f"- {k}: {v}" for k, v in template.task_structure.items()])
    
    # Difficulty hint
    diff_hint = template.difficulty_hints.get(difficulty, "")
    
    # Concepts hint
    concepts_hint = f"\nИспользуй концепции: {', '.join(concepts)}" if concepts else ""
    
    # Example
    example_hint = ""
    if template.example:
        example_hint = f"\n\nПример задачи:\n{template.example}"
    
    prompt = f"""/no_think {template.system_prompt}

Тема: {query}
Сложность: {difficulty}
{diff_hint}{concepts_hint}

Создай задачу со следующей структурой (JSON):
{structure_desc}
{example_hint}

Верни ТОЛЬКО валидный JSON."""

    return prompt
