"""
Flexible Task Generator
AI-driven task generation without rigid categories.
The system analyzes the query and autonomously decides:
- Task type and structure
- What tests are needed (unit, integration, performance, edge cases)
- Difficulty calibration
- Evaluation criteria
"""
from typing import Dict, List, Optional, Any
from openai import AsyncOpenAI
from pydantic import BaseModel
import httpx
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

CODE_RUNNER_URL = os.getenv("CODE_RUNNER_URL", "http://localhost:8003")
KNOWLEDGE_URL = os.getenv("KNOWLEDGE_SERVICE_URL", "http://localhost:8005")
LEARNING_URL = os.getenv("LEARNING_SERVICE_URL", "http://localhost:8006")

client = get_client()
http_client = httpx.AsyncClient(timeout=60.0)


# ============== Analysis Prompt ==============

ANALYSIS_PROMPT = """/no_think Ты эксперт по созданию задач для программистов.

Проанализируй запрос пользователя и определи оптимальную структуру задачи.

Запрос: "{query}"
Сложность: {difficulty}
Язык: {language}

Определи:
1. **Тип задачи** - что именно нужно создать (алгоритм, класс, API, функция, система и т.д.)
2. **Ключевые концепции** - какие знания проверяет задача
3. **Формат ввода/вывода** - как будут подаваться данные и что ожидается на выходе
4. **Какие тесты нужны**:
   - unit_tests: базовые тесты функциональности (всегда нужны)
   - edge_cases: граничные случаи (пустой ввод, максимальные значения)
   - performance_test: тест производительности (нужен для алгоритмов с ограничениями)
   - type_check: проверка типов и структуры (для ООП, API)
   - integration_test: интеграционный тест (для систем из нескольких компонентов)
5. **Критерии оценки** - по каким параметрам оценивать решение
6. **Ограничения** - временные/пространственные лимиты если применимо

Верни JSON:
{{
    "task_type": "algorithm|class|function|api|system|data_structure|other",
    "concepts": ["concept1", "concept2"],
    "complexity_factors": ["что делает задачу сложной"],
    
    "input_format": {{
        "type": "stdin|function_args|class_init|api_request",
        "description": "описание формата входных данных",
        "example": "пример входных данных"
    }},
    
    "output_format": {{
        "type": "stdout|return_value|class_state|api_response",
        "description": "описание формата выходных данных",
        "example": "пример выходных данных"
    }},
    
    "tests_needed": {{
        "unit_tests": true,
        "edge_cases": true,
        "performance_test": false,
        "type_check": false,
        "integration_test": false
    }},
    
    "constraints": {{
        "time_limit_ms": null,
        "memory_limit_mb": null,
        "input_size_max": null
    }},
    
    "evaluation_criteria": [
        {{"name": "correctness", "weight": 0.6, "description": "правильность результата"}},
        {{"name": "code_quality", "weight": 0.2, "description": "качество кода"}},
        {{"name": "efficiency", "weight": 0.2, "description": "эффективность решения"}}
    ],
    
    "hints_strategy": "progressive|on_demand|none",
    "estimated_time_minutes": 15
}}"""


# ============== Task Generation Prompt ==============

GENERATION_PROMPT = """/no_think Создай задачу по программированию.

**Запрос:** {query}
**Сложность:** {difficulty}
**Язык:** {language}

**Анализ задачи:**
{analysis}

Создай полную задачу с учётом анализа. Задача должна быть:
- Чётко сформулирована
- С конкретными примерами
- С тестами согласно анализу

Верни JSON:
{{
    "title": "Название задачи",
    "description": "Полное описание задачи с форматом ввода/вывода",
    
    "examples": [
        {{
            "input": "входные данные",
            "output": "ожидаемый результат",
            "explanation": "пояснение (опционально)"
        }}
    ],
    
    "test_cases": [
        {{
            "input": "...",
            "output": "...",
            "category": "basic|edge|performance",
            "description": "что проверяет тест"
        }}
    ],
    
    "hidden_tests": [
        {{
            "input": "...",
            "output": "...",
            "category": "basic|edge|performance",
            "points": 10
        }}
    ],
    
    "hints": [
        {{
            "level": 1,
            "text": "лёгкая подсказка",
            "penalty": 0.05
        }},
        {{
            "level": 2,
            "text": "более конкретная подсказка",
            "penalty": 0.15
        }}
    ],
    
    "constraints": {{
        "time_limit_ms": {time_limit},
        "memory_limit_mb": {memory_limit}
    }},
    
    "tags": ["tag1", "tag2"],
    "estimated_time_minutes": {estimated_time}
}}"""


# ============== Solution Generation Prompt ==============

SOLUTION_PROMPT = """/no_think Напиши решение задачи.

**Задача:**
{task_description}

**Примеры:**
{examples}

**Язык:** {language}

**Требования:**
- Код должен читать из stdin и писать в stdout (если это алгоритмическая задача)
- Или реализовать требуемый класс/функцию (если это ООП/API задача)
- Код должен быть эффективным и чистым

Верни ТОЛЬКО код без объяснений."""


# ============== Test Generation Prompt ==============

TEST_GENERATION_PROMPT = """/no_think Сгенерируй дополнительные тесты для задачи.

**Задача:**
{task_description}

**Существующие тесты:**
{existing_tests}

**Нужны тесты:**
{tests_needed}

Сгенерируй тесты каждой категории. Для performance тестов используй большие входные данные.

Верни JSON:
{{
    "tests": [
        {{
            "input": "...",
            "output": "...",
            "category": "basic|edge|performance",
            "description": "что проверяет"
        }}
    ]
}}"""


class FlexibleTaskGenerator:
    """
    Flexible task generator that adapts to any query.
    No rigid categories - AI decides everything.
    """
    
    def __init__(self):
        self.client = client
        self.http_client = http_client
    
    async def analyze_query(
        self,
        query: str,
        difficulty: str = "medium",
        language: str = "python"
    ) -> Dict:
        """
        Step 1: Analyze query to understand what kind of task to create.
        """
        prompt = ANALYSIS_PROMPT.format(
            query=query,
            difficulty=difficulty,
            language=language
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=Models.CHAT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            
            analysis = json.loads(response.choices[0].message.content)
            return {"success": True, "analysis": analysis}
            
        except Exception as e:
            print(f"Analysis error: {e}")
            # Fallback analysis
            return {
                "success": False,
                "analysis": {
                    "task_type": "algorithm",
                    "concepts": [query],
                    "input_format": {"type": "stdin", "description": "стандартный ввод"},
                    "output_format": {"type": "stdout", "description": "стандартный вывод"},
                    "tests_needed": {
                        "unit_tests": True,
                        "edge_cases": True,
                        "performance_test": False,
                        "type_check": False,
                        "integration_test": False
                    },
                    "constraints": {},
                    "evaluation_criteria": [
                        {"name": "correctness", "weight": 1.0}
                    ],
                    "estimated_time_minutes": 15
                }
            }
    
    async def generate_task(
        self,
        query: str,
        analysis: Dict,
        difficulty: str = "medium",
        language: str = "python"
    ) -> Dict:
        """
        Step 2: Generate task based on analysis.
        """
        # Determine constraints from analysis
        constraints = analysis.get("constraints", {})
        time_limit = constraints.get("time_limit_ms") or 2000
        memory_limit = constraints.get("memory_limit_mb") or 256
        estimated_time = analysis.get("estimated_time_minutes", 15)
        
        prompt = GENERATION_PROMPT.format(
            query=query,
            difficulty=difficulty,
            language=language,
            analysis=json.dumps(analysis, ensure_ascii=False, indent=2),
            time_limit=time_limit,
            memory_limit=memory_limit,
            estimated_time=estimated_time
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=Models.CHAT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=3000,
                response_format={"type": "json_object"}
            )
            
            task = json.loads(response.choices[0].message.content)
            
            # Add metadata from analysis
            task["_analysis"] = {
                "task_type": analysis.get("task_type"),
                "concepts": analysis.get("concepts", []),
                "tests_needed": analysis.get("tests_needed", {}),
                "evaluation_criteria": analysis.get("evaluation_criteria", [])
            }
            
            return {"success": True, "task": task}
            
        except Exception as e:
            print(f"Task generation error: {e}")
            return {"success": False, "error": str(e)}
    
    async def generate_solution(
        self,
        task: Dict,
        language: str = "python"
    ) -> Optional[str]:
        """
        Step 3: Generate reference solution.
        """
        examples_text = "\n".join([
            f"Вход: {ex.get('input', '')}\nВыход: {ex.get('output', '')}"
            for ex in task.get("examples", [])[:3]
        ])
        
        prompt = SOLUTION_PROMPT.format(
            task_description=task.get("description", ""),
            examples=examples_text,
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
    
    async def generate_additional_tests(
        self,
        task: Dict,
        analysis: Dict
    ) -> List[Dict]:
        """
        Step 4: Generate additional tests based on analysis.
        """
        tests_needed = analysis.get("tests_needed", {})
        
        # Check what tests are missing
        existing_categories = set()
        for test in task.get("test_cases", []) + task.get("hidden_tests", []):
            existing_categories.add(test.get("category", "basic"))
        
        needed = []
        if tests_needed.get("edge_cases") and "edge" not in existing_categories:
            needed.append("edge_cases")
        if tests_needed.get("performance_test") and "performance" not in existing_categories:
            needed.append("performance")
        
        if not needed:
            return []
        
        prompt = TEST_GENERATION_PROMPT.format(
            task_description=task.get("description", ""),
            existing_tests=json.dumps(task.get("test_cases", [])[:3], ensure_ascii=False),
            tests_needed=", ".join(needed)
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=Models.CHAT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result.get("tests", [])
            
        except Exception as e:
            print(f"Test generation error: {e}")
            return []
    
    async def validate_solution(
        self,
        code: str,
        test_cases: List[Dict],
        language: str = "python"
    ) -> Dict:
        """
        Step 5: Validate solution against test cases.
        """
        try:
            response = await self.http_client.post(
                f"{CODE_RUNNER_URL}/validate",
                json={
                    "code": code,
                    "language": language,
                    "test_cases": [
                        {"input": t.get("input", ""), "expected_output": t.get("output", "")}
                        for t in test_cases
                    ]
                }
            )
            return response.json()
        except Exception as e:
            print(f"Validation error: {e}")
            return {"error": str(e), "passed": 0, "failed": len(test_cases)}
    
    async def fix_solution(
        self,
        code: str,
        task: Dict,
        validation: Dict,
        language: str = "python"
    ) -> Optional[str]:
        """
        Step 6: Fix solution if tests failed.
        """
        failed_tests = validation.get("results", [])
        failed_tests = [t for t in failed_tests if not t.get("passed")]
        
        if not failed_tests:
            return code
        
        prompt = f"""/no_think Исправь код. Некоторые тесты не прошли.

Задача: {task.get('description', '')[:500]}

Код:
```{language}
{code}
```

Ошибки:
{json.dumps(failed_tests[:3], ensure_ascii=False, indent=2)}

Верни ТОЛЬКО исправленный код."""

        try:
            response = await self.client.chat.completions.create(
                model=Models.CODE,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2000
            )
            
            fixed = response.choices[0].message.content
            
            if "```" in fixed:
                import re
                match = re.search(r'```(?:\w+)?\n(.*?)```', fixed, re.DOTALL)
                if match:
                    fixed = match.group(1)
            
            return fixed.strip()
            
        except Exception as e:
            print(f"Fix error: {e}")
            return None
    
    async def generate(
        self,
        query: str,
        difficulty: str = "medium",
        language: str = "python",
        user_id: Optional[str] = None
    ) -> Dict:
        """
        Main entry point: Generate complete task with solution.
        """
        result = {
            "status": "pending",
            "query": query,
            "difficulty": difficulty,
            "language": language,
            "stages": []
        }
        
        # Stage 1: Analyze query
        result["stages"].append({"name": "Analysis", "status": "running"})
        analysis_result = await self.analyze_query(query, difficulty, language)
        analysis = analysis_result.get("analysis", {})
        result["analysis"] = analysis
        result["stages"][-1]["status"] = "done"
        
        # Get adaptive difficulty if user_id provided
        if user_id:
            try:
                concepts = analysis.get("concepts", [])
                resp = await self.http_client.get(
                    f"{LEARNING_URL}/adaptive-difficulty/{user_id}",
                    params={"concepts": ",".join(concepts)}
                )
                adaptive = resp.json().get("difficulty", 0.5)
                result["adaptive_difficulty"] = adaptive
                
                # Adjust difficulty based on user level
                if adaptive < 0.3:
                    difficulty = "easy"
                elif adaptive > 0.7:
                    difficulty = "hard"
            except:
                pass
        
        # Stage 2: Generate task
        result["stages"].append({"name": "Task Design", "status": "running"})
        task_result = await self.generate_task(query, analysis, difficulty, language)
        
        if not task_result.get("success"):
            result["status"] = "error"
            result["error"] = task_result.get("error", "Task generation failed")
            result["stages"][-1]["status"] = "error"
            return result
        
        task = task_result["task"]
        result["task"] = task
        result["stages"][-1]["status"] = "done"
        
        # Stage 3: Generate additional tests if needed
        tests_needed = analysis.get("tests_needed", {})
        if tests_needed.get("performance_test") or tests_needed.get("edge_cases"):
            result["stages"].append({"name": "Test Generation", "status": "running"})
            additional_tests = await self.generate_additional_tests(task, analysis)
            if additional_tests:
                task["hidden_tests"] = task.get("hidden_tests", []) + additional_tests
            result["stages"][-1]["status"] = "done"
        
        # Stage 4: Generate solution
        result["stages"].append({"name": "Solution", "status": "running"})
        solution = await self.generate_solution(task, language)
        result["solution"] = solution
        result["stages"][-1]["status"] = "done" if solution else "error"
        
        # Stage 5: Validate solution
        if solution and task.get("test_cases"):
            result["stages"].append({"name": "Validation", "status": "running"})
            all_tests = task.get("test_cases", []) + task.get("hidden_tests", [])[:5]
            validation = await self.validate_solution(solution, all_tests, language)
            result["validation"] = validation
            result["stages"][-1]["status"] = "done"
            
            # Stage 6: Fix if needed
            if not validation.get("all_passed") and validation.get("failed", 0) > 0:
                result["stages"].append({"name": "Fix", "status": "running"})
                fixed = await self.fix_solution(solution, task, validation, language)
                if fixed:
                    result["solution"] = fixed
                    # Re-validate
                    validation2 = await self.validate_solution(fixed, all_tests, language)
                    result["validation"] = validation2
                result["stages"][-1]["status"] = "done"
        
        result["status"] = "success"
        return result


# Singleton instance
generator = FlexibleTaskGenerator()


async def generate_flexible_task(
    query: str,
    difficulty: str = "medium",
    language: str = "python",
    user_id: Optional[str] = None
) -> Dict:
    """Convenience function for generating tasks."""
    return await generator.generate(query, difficulty, language, user_id)
