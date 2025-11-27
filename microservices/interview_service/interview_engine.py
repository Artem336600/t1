"""
Interview Engine - Core logic for conducting interviews
Handles conversation flow, question generation, and live coding integration
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from openai import AsyncOpenAI
import os
import json
import httpx

from schema_parser import InterviewStep


# LLM Configuration
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-SSWP5NVJpHecmOFI_yxp7Q")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://llm.t1v.scibox.tech/v1")
CHAT_MODEL = os.getenv("LLM_CHAT_MODEL", "qwen3-32b-awq")
CODE_MODEL = os.getenv("LLM_CODE_MODEL", "qwen3-coder-30b-a3b-instruct-fp8")

# Service URLs
TASK_GENERATOR_URL = os.getenv("TASK_GENERATOR_URL", "http://localhost:8002")
CODE_RUNNER_URL = os.getenv("CODE_RUNNER_URL", "http://localhost:8003")


@dataclass
class InterviewSession:
    """Active interview session"""
    session_id: str
    candidate_name: str
    steps: List[InterviewStep]
    current_step_index: int
    scores: Dict[str, Dict]  # step_id -> {earned, max, feedback}
    history: List[Dict]  # Chat history
    started_at: datetime
    current_level: str = "junior"  # junior, middle, senior
    current_live_coding_task: Optional[Dict] = None
    metadata: Dict = field(default_factory=dict)


class InterviewEngine:
    """
    Core engine for conducting interviews.
    
    Responsibilities:
    - Generate appropriate questions based on step
    - Process candidate answers
    - Manage conversation flow
    - Integrate with task generator for live coding
    """
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL
        )
        self.http_client = httpx.AsyncClient(timeout=120.0)
    
    async def generate_greeting(self, session: InterviewSession, first_step: InterviewStep) -> str:
        """Generate initial greeting for the interview"""
        
        prompt = f"""Ты HR-бот Алекс, проводящий техническое собеседование.

Кандидат: {session.candidate_name}
Первый этап: {first_step.label}
Описание: {first_step.description or 'Начало собеседования'}

Сгенерируй дружелюбное приветствие для начала собеседования.
Представься как Алекс, объясни формат собеседования и задай первый вопрос по теме "{first_step.label}".

Будь профессиональным, но дружелюбным. Не используй эмодзи.
Ответ должен быть на русском языке, 3-5 предложений.
ОТВЕЧАЙ СРАЗУ, без рассуждений и тегов <think>."""

        response = await self.client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300
        )
        
        # Filter out <think> tags
        content = response.choices[0].message.content.strip()
        import re
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        return content
    
    async def generate_greeting_stream(self, session: InterviewSession, first_step: InterviewStep):
        """Generate initial greeting with streaming"""
        
        prompt = f"""Ты HR-бот Алекс, проводящий техническое собеседование.

Кандидат: {session.candidate_name}
Первый этап: {first_step.label}
Описание: {first_step.description or 'Начало собеседования'}

Сгенерируй дружелюбное приветствие для начала собеседования.
Представься как Алекс, объясни формат собеседования и задай первый вопрос по теме "{first_step.label}".

Будь профессиональным, но дружелюбным. Не используй эмодзи.
Ответ должен быть на русском языке, 3-5 предложений.
ОТВЕЧАЙ СРАЗУ, без рассуждений и тегов <think>."""

        stream = await self.client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
            stream=True
        )
        
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                # Filter out <think> tags
                if '<think>' not in content and '</think>' not in content:
                    yield content
    
    async def generate_question(self, session: InterviewSession, step: InterviewStep) -> str:
        """Generate a question for the current step"""
        
        # Build context from previous answers
        recent_history = session.history[-6:] if len(session.history) > 6 else session.history
        history_context = "\n".join([
            f"{'Кандидат' if h['role'] == 'user' else 'HR'}: {h['content'][:200]}"
            for h in recent_history
        ])
        
        prompt = f"""/no_think Ты HR-бот, проводящий техническое собеседование.

Текущий этап: {step.label}
Описание: {step.description or 'Нет описания'}
Важность: {step.importance or 'medium'}
Баллы: {step.points or 0}

Предыдущий контекст:
{history_context}

Задай вопрос кандидату по теме "{step.label}".
Вопрос должен:
1. Быть конкретным и проверять реальные знания
2. Соответствовать важности ({step.importance or 'medium'})
3. Быть понятным и однозначным

Для high importance - задай глубокий технический вопрос.
Для medium - стандартный вопрос на понимание.
Для low - базовый вопрос на знакомство с темой.

Ответ на русском языке, только вопрос без лишних слов."""

        response = await self.client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=200
        )
        
        return response.choices[0].message.content.strip()
    
    async def process_answer(
        self, 
        session: InterviewSession, 
        step: InterviewStep, 
        answer: str
    ) -> Dict[str, Any]:
        """
        Process candidate's answer and generate follow-up.
        
        Returns dict with:
        - message: Response to candidate
        - follow_up: Whether to ask follow-up question
        - step_complete: Whether this step is done
        """
        
        # Build context
        recent_history = session.history[-4:] if len(session.history) > 4 else session.history
        
        prompt = f"""/no_think Ты HR-бот, проводящий техническое собеседование.

Текущий вопрос: {step.label}
Описание темы: {step.description or 'Нет описания'}

Ответ кандидата: {answer}

Проанализируй ответ и реши:
1. Ответ полный и можно переходить дальше
2. Нужно задать уточняющий вопрос
3. Ответ неполный, нужно попросить раскрыть тему

Верни JSON:
{{
    "assessment": "краткая оценка ответа",
    "response": "твой ответ кандидату (подтверждение или уточняющий вопрос)",
    "step_complete": true/false,
    "needs_followup": true/false
}}

Будь профессиональным. Не критикуй резко. На русском языке."""

        response = await self.client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=300
        )
        
        try:
            content = response.choices[0].message.content.strip()
            # Extract JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content)
            return {
                "message": result.get("response", "Спасибо за ответ. Давайте продолжим."),
                "step_complete": result.get("step_complete", True),
                "needs_followup": result.get("needs_followup", False)
            }
        except:
            return {
                "message": "Спасибо за ответ. Давайте перейдём к следующему вопросу.",
                "step_complete": True,
                "needs_followup": False
            }
    
    async def process_answer_stream(
        self, 
        session: InterviewSession, 
        step: InterviewStep, 
        answer: str,
        next_step: InterviewStep = None
    ):
        """
        Process candidate's answer with streaming response.
        Yields text chunks as they are generated.
        """
        
        # Build next question context
        next_question_info = ""
        if next_step and next_step.node_type not in ["end", "skill-group"]:
            next_question_info = f"\n\nСледующая тема для вопроса: {next_step.label}"
            if next_step.description:
                next_question_info += f" ({next_step.description})"
        
        prompt = f"""Ты HR-бот Алекс, проводящий техническое собеседование.

Текущий вопрос: {step.label}
Описание темы: {step.description or 'Нет описания'}

Ответ кандидата: {answer}
{next_question_info}

Дай ОДИН краткий ответ (2-3 предложения):
1. Кратко подтверди ответ
2. Если есть следующая тема - плавно перейди к ней и задай вопрос

НЕ генерируй несколько ответов. Только один связный текст.
Будь дружелюбным, но профессиональным. На русском языке.
ОТВЕЧАЙ СРАЗУ, без рассуждений и тегов <think>."""

        stream = await self.client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=200,
            stream=True
        )
        
        buffer = ""
        in_think_tag = False
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                buffer += content
                
                # Filter out <think>...</think> blocks
                while '<think>' in buffer:
                    before = buffer.split('<think>')[0]
                    if before:
                        yield before
                    buffer = buffer.split('<think>', 1)[1] if '<think>' in buffer else ''
                    in_think_tag = True
                
                if in_think_tag:
                    if '</think>' in buffer:
                        buffer = buffer.split('</think>', 1)[1] if '</think>' in buffer else ''
                        in_think_tag = False
                else:
                    if buffer and '</think>' not in buffer:
                        yield buffer
                        buffer = ""
    
    async def generate_transition(self, session: InterviewSession, next_step: InterviewStep) -> str:
        """Generate transition message to next step"""
        
        prompt = f"""/no_think Ты HR-бот, проводящий собеседование.

Следующий этап: {next_step.label}
Тип: {next_step.node_type}
Описание: {next_step.description or 'Нет описания'}
Группа: {next_step.group_name or 'Общие вопросы'}

Сгенерируй плавный переход к следующему этапу.
Если это новая группа вопросов - объяви её.
Если это skill-check - задай соответствующий вопрос.

Ответ на русском, 1-3 предложения."""

        response = await self.client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=200
        )
        
        return response.choices[0].message.content.strip()
    
    async def generate_transition_stream(self, session: InterviewSession, next_step: InterviewStep):
        """Generate transition message with streaming"""
        
        prompt = f"""Ты HR-бот Алекс, проводящий собеседование.

Следующий этап: {next_step.label}
Тип: {next_step.node_type}
Описание: {next_step.description or 'Нет описания'}
Группа: {next_step.group_name or 'Общие вопросы'}

Сгенерируй плавный переход к следующему этапу и задай вопрос.
Ответ на русском, 2-3 предложения.
ОТВЕЧАЙ СРАЗУ, без рассуждений и тегов <think>."""

        stream = await self.client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=200,
            stream=True
        )
        
        buffer = ""
        in_think_tag = False
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                buffer += content
                
                # Filter out <think>...</think> blocks
                while '<think>' in buffer:
                    before = buffer.split('<think>')[0]
                    if before:
                        yield before
                    buffer = buffer.split('<think>', 1)[1] if '<think>' in buffer else ''
                    in_think_tag = True
                
                if in_think_tag:
                    if '</think>' in buffer:
                        buffer = buffer.split('</think>', 1)[1] if '</think>' in buffer else ''
                        in_think_tag = False
                else:
                    if buffer and '</think>' not in buffer:
                        yield buffer
                        buffer = ""
    
    async def generate_live_coding_task(
        self, 
        session: InterviewSession, 
        step: InterviewStep,
        level: str
    ) -> Dict[str, Any]:
        """
        Generate a live coding task based on step description and level.
        
        Levels:
        - junior: Basic implementation, clear requirements
        - middle: More complex logic, edge cases
        - senior: Optimization, system design aspects
        """
        
        # Map level to difficulty
        difficulty_map = {
            "junior": "easy",
            "middle": "medium",
            "senior": "hard"
        }
        difficulty = difficulty_map.get(level, "medium")
        
        # Build task request from step
        task_query = f"{step.label}: {step.description or ''}"
        
        try:
            # Call task generator service
            response = await self.http_client.post(
                f"{TASK_GENERATOR_URL}/generate",
                json={
                    "query": f"Create a Python coding task for interview: {task_query}. Focus on {level} level skills.",
                    "difficulty": difficulty,
                    "language": "python"
                }
            )
            
            if response.status_code == 200:
                task_data = response.json()
                
                # Store task in session
                session.current_live_coding_task = task_data
                
                return {
                    "task_id": task_data.get("id"),
                    "title": task_data.get("title", step.label),
                    "description": task_data.get("description", step.description),
                    "examples": task_data.get("examples", []),
                    "hints": task_data.get("hints", []),
                    "difficulty": difficulty,
                    "level": level,
                    "steps": task_data.get("steps", []),
                    "test_cases": task_data.get("test_cases", []),
                    "time_limit_minutes": 15 if level == "junior" else 20 if level == "middle" else 30,
                    "points": step.points or 10
                }
        except Exception as e:
            print(f"Error calling task generator: {e}")
        
        # Fallback: generate task directly
        return await self._generate_task_directly(session, step, level, difficulty)
    
    async def _generate_task_directly(
        self,
        session: InterviewSession,
        step: InterviewStep,
        level: str,
        difficulty: str
    ) -> Dict[str, Any]:
        """Generate live coding task directly using LLM"""
        
        prompt = f"""Ты технический интервьюер. Создай задачу для live coding на Python.

Тема: {step.label}
Описание: {step.description or 'Нет описания'}
Уровень: {level} ({difficulty})

Требования по уровню:
- junior: Простая задача, 10-20 строк кода, базовая логика
- middle: Средняя сложность, 20-40 строк, работа со структурами данных
- senior: Сложная задача, оптимизация, 40+ строк

Верни ТОЛЬКО валидный JSON без markdown форматирования:
{{
    "id": "generated_task_{int(time.time())}",
    "title": "название задачи",
    "description": "подробное условие с форматом ввода/вывода",
    "examples": [
        {{"input": "пример входа", "output": "пример выхода"}}
    ],
    "test_cases": [
        {{"input": "скрытый тест", "output": "ожидаемый результат", "points": 10}}
    ],
    "hints": ["подсказка 1", "подсказка 2"],
    "time_limit_minutes": число
}}

НЕ используй теги <think>."""

        response = await self.client.chat.completions.create(
            model=CODE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1000
        )
        
        try:
            content = response.choices[0].message.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            task = json.loads(content)
            task["level"] = level
            task["difficulty"] = difficulty
            task["points"] = step.points or 10
            
            session.current_live_coding_task = task
            return task
            
        except Exception as e:
            print(f"Error parsing task: {e}")
            # Return minimal task
            task = {
                "title": step.label,
                "description": step.description or f"Реализуйте решение для: {step.label}",
                "examples": [],
                "test_cases": [],
                "hints": [],
                "level": level,
                "difficulty": difficulty,
                "points": step.points or 10,
                "time_limit_minutes": 15
            }
            session.current_live_coding_task = task
            return task
    
    async def evaluate_code(
        self,
        session: InterviewSession,
        step: InterviewStep,
        code: str,
        task: Dict[str, Any],
        language: str = "python"
    ) -> Dict[str, Any]:
        """
        Evaluate submitted code for live coding task.
        
        1. Run code against test cases
        2. Evaluate code quality with AI
        3. Calculate score
        """
        
        test_cases = task.get("test_cases", [])
        max_points = step.points or 10
        
        # Run tests via code runner
        test_results = None
        tests_passed = 0
        tests_total = len(test_cases)
        
        if test_cases:
            try:
                response = await self.http_client.post(
                    f"{CODE_RUNNER_URL}/validate",
                    json={
                        "code": code,
                        "test_cases": [
                            {
                                "input": tc.get("input", ""),
                                "output": tc.get("output", tc.get("expected", "")),
                                "points": tc.get("points", 10),
                                "time_limit_ms": tc.get("time_limit_ms", 5000)
                            }
                            for tc in test_cases
                        ]
                    }
                )
                
                if response.status_code == 200:
                    test_results = response.json()
                    tests_passed = test_results.get("passed", 0)
                    tests_total = test_results.get("passed", 0) + test_results.get("failed", 0)
            except Exception as e:
                print(f"Error running tests: {e}")
        
        # Calculate base score from tests
        if tests_total > 0:
            test_score = (tests_passed / tests_total) * max_points * 0.7  # 70% for correctness
        else:
            test_score = 0
        
        # Evaluate code quality with AI
        quality_evaluation = await self._evaluate_code_quality(code, task, language)
        quality_score = quality_evaluation.get("score", 0) * max_points * 0.3  # 30% for quality
        
        total_score = round(test_score + quality_score)
        all_passed = tests_passed == tests_total and tests_total > 0
        
        # Generate feedback
        feedback = await self._generate_code_feedback(
            code=code,
            task=task,
            test_results=test_results,
            quality_evaluation=quality_evaluation,
            all_passed=all_passed
        )
        
        return {
            "points": total_score,
            "max_points": max_points,
            "all_passed": all_passed,
            "tests_passed": tests_passed,
            "tests_total": tests_total,
            "test_results": test_results,
            "quality_score": quality_evaluation.get("score", 0),
            "quality_feedback": quality_evaluation.get("feedback", ""),
            "feedback": feedback
        }
    
    async def _evaluate_code_quality(
        self, 
        code: str, 
        task: Dict[str, Any],
        language: str
    ) -> Dict[str, Any]:
        """Evaluate code quality using AI"""
        
        prompt = f"""/no_think Оцени качество кода.

Задача: {task.get('title', '')}
{task.get('description', '')}

Код:
```{language}
{code}
```

Оцени по критериям:
1. Читаемость (понятные имена, структура)
2. Эффективность (алгоритмическая сложность)
3. Обработка ошибок
4. Стиль кода

Верни JSON:
{{
    "score": число от 0 до 1,
    "feedback": "краткий отзыв",
    "strengths": ["сильные стороны"],
    "improvements": ["что улучшить"]
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=CODE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=400
            )
            
            content = response.choices[0].message.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            return json.loads(content)
        except:
            return {"score": 0.5, "feedback": "Код получен", "strengths": [], "improvements": []}
    
    async def _generate_code_feedback(
        self,
        code: str,
        task: Dict[str, Any],
        test_results: Optional[Dict],
        quality_evaluation: Dict,
        all_passed: bool
    ) -> str:
        """Generate human-readable feedback for code submission"""
        
        if all_passed:
            base = "Отлично! Все тесты пройдены. "
        elif test_results:
            passed = test_results.get("passed", 0)
            total = passed + test_results.get("failed", 0)
            base = f"Пройдено {passed} из {total} тестов. "
        else:
            base = "Код получен. "
        
        quality_feedback = quality_evaluation.get("feedback", "")
        improvements = quality_evaluation.get("improvements", [])
        
        feedback = base + quality_feedback
        
        if improvements and not all_passed:
            feedback += " Рекомендации: " + "; ".join(improvements[:2])
        
        return feedback
