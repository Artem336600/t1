"""
AI Judge - Evaluates candidate answers and provides scores
Uses LLM to assess quality of responses
"""
from typing import Dict, List, Optional, Any
from openai import AsyncOpenAI
import os
import json


# LLM Configuration
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-SSWP5NVJpHecmOFI_yxp7Q")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://llm.t1v.scibox.tech/v1")
CHAT_MODEL = os.getenv("LLM_CHAT_MODEL", "qwen3-32b-awq")


class AIJudge:
    """
    AI-powered judge for evaluating interview answers.
    
    Responsibilities:
    - Evaluate text answers for technical questions
    - Score answers based on criteria
    - Provide constructive feedback
    - Analyze overall interview performance
    """
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL
        )
    
    async def evaluate_answer(
        self,
        question: str,
        description: Optional[str],
        answer: str,
        max_points: int,
        importance: Optional[str] = "medium"
    ) -> Dict[str, Any]:
        """
        Evaluate a candidate's answer to a question.
        
        Args:
            question: The question that was asked
            description: Additional context about what to evaluate
            answer: Candidate's answer
            max_points: Maximum points for this question
            importance: high/medium/low - affects scoring strictness
        
        Returns:
            Dict with points, feedback, and step_complete flag
        """
        
        # Adjust expectations based on importance
        strictness = {
            "high": "Будь строгим. Ожидай глубокое понимание и конкретные примеры.",
            "medium": "Оценивай справедливо. Достаточно хорошего понимания темы.",
            "low": "Будь снисходительным. Достаточно базового знакомства с темой."
        }.get(importance, "Оценивай справедливо.")
        
        prompt = f"""/no_think Ты эксперт-оценщик на техническом собеседовании.

Вопрос: {question}
Контекст: {description or 'Нет дополнительного контекста'}
Максимум баллов: {max_points}

Ответ кандидата:
"{answer}"

{strictness}

Оцени ответ по критериям:
1. Правильность (соответствует ли ответ вопросу)
2. Полнота (раскрыта ли тема)
3. Глубина (есть ли понимание нюансов)
4. Примеры (приведены ли практические примеры)

Верни JSON:
{{
    "points": число от 0 до {max_points},
    "feedback": "краткий отзыв для кандидата",
    "internal_notes": "заметки для HR (не показывать кандидату)",
    "strengths": ["что хорошо в ответе"],
    "weaknesses": ["что можно улучшить"],
    "step_complete": true если ответ достаточен для перехода дальше
}}

Будь объективным и конструктивным."""

        try:
            response = await self.client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500
            )
            
            content = response.choices[0].message.content.strip()
            
            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content)
            
            # Ensure points are within bounds
            points = min(max(0, result.get("points", 0)), max_points)
            
            return {
                "points": points,
                "max_points": max_points,
                "feedback": result.get("feedback", "Ответ получен."),
                "internal_notes": result.get("internal_notes", ""),
                "strengths": result.get("strengths", []),
                "weaknesses": result.get("weaknesses", []),
                "step_complete": result.get("step_complete", True),
                "score_percent": round(points / max_points * 100, 1) if max_points > 0 else 0
            }
            
        except Exception as e:
            print(f"Error evaluating answer: {e}")
            # Return neutral evaluation on error
            return {
                "points": max_points // 2,
                "max_points": max_points,
                "feedback": "Ответ получен.",
                "internal_notes": f"Ошибка оценки: {str(e)}",
                "strengths": [],
                "weaknesses": [],
                "step_complete": True,
                "score_percent": 50.0
            }
    
    async def evaluate_code_answer(
        self,
        task_description: str,
        code: str,
        test_results: Optional[Dict],
        max_points: int
    ) -> Dict[str, Any]:
        """
        Evaluate a code submission for live coding.
        
        Combines test results with code quality assessment.
        """
        
        # Calculate test score (60% weight)
        test_score = 0
        if test_results:
            passed = test_results.get("passed", 0)
            total = passed + test_results.get("failed", 0)
            if total > 0:
                test_score = (passed / total) * max_points * 0.6
        
        # Evaluate code quality (40% weight)
        quality_prompt = f"""/no_think Оцени качество кода для задачи.

Задача: {task_description}

Код:
```python
{code[:2000]}
```

Результаты тестов: {json.dumps(test_results, ensure_ascii=False) if test_results else 'Нет данных'}

Оцени по критериям:
1. Читаемость и стиль
2. Эффективность алгоритма
3. Обработка граничных случаев
4. Общее качество решения

Верни JSON:
{{
    "quality_score": число от 0 до 1,
    "feedback": "отзыв о коде",
    "code_issues": ["проблемы в коде"],
    "suggestions": ["рекомендации"]
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[{"role": "user", "content": quality_prompt}],
                temperature=0.3,
                max_tokens=400
            )
            
            content = response.choices[0].message.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            quality = json.loads(content)
            quality_score = quality.get("quality_score", 0.5) * max_points * 0.4
            
            total_points = round(test_score + quality_score)
            
            return {
                "points": total_points,
                "max_points": max_points,
                "test_score": round(test_score),
                "quality_score": round(quality_score),
                "feedback": quality.get("feedback", "Код получен."),
                "code_issues": quality.get("code_issues", []),
                "suggestions": quality.get("suggestions", []),
                "score_percent": round(total_points / max_points * 100, 1) if max_points > 0 else 0
            }
            
        except Exception as e:
            print(f"Error evaluating code: {e}")
            return {
                "points": round(test_score),
                "max_points": max_points,
                "test_score": round(test_score),
                "quality_score": 0,
                "feedback": "Код получен.",
                "code_issues": [],
                "suggestions": [],
                "score_percent": round(test_score / max_points * 100, 1) if max_points > 0 else 0
            }
    
    async def analyze_main_errors(
        self,
        history: List[Dict],
        scores: Dict[str, Dict]
    ) -> List[str]:
        """
        Analyze interview history to identify main errors/weaknesses.
        """
        
        # Find low-scoring answers
        low_scores = []
        for step_id, score in scores.items():
            if score.get("max", 0) > 0:
                percent = score.get("earned", 0) / score["max"] * 100
                if percent < 50:
                    low_scores.append({
                        "step_id": step_id,
                        "earned": score.get("earned", 0),
                        "max": score["max"],
                        "feedback": score.get("feedback", "")
                    })
        
        if not low_scores:
            return ["Серьёзных ошибок не выявлено"]
        
        # Build context for analysis
        context = json.dumps(low_scores[:5], ensure_ascii=False)
        
        prompt = f"""/no_think Проанализируй слабые места кандидата на собеседовании.

Низкие оценки:
{context}

Выдели 3-5 главных ошибок или пробелов в знаниях.
Формулируй конкретно и конструктивно.

Верни JSON:
{{
    "main_errors": ["ошибка 1", "ошибка 2", ...]
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )
            
            content = response.choices[0].message.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content)
            return result.get("main_errors", ["Требуется дополнительный анализ"])
            
        except:
            return ["Требуется дополнительный анализ результатов"]
    
    async def generate_recommendations(
        self,
        scores: Dict[str, Dict],
        sections: Dict[str, Any],
        overall_percent: float
    ) -> List[str]:
        """
        Generate recommendations for the candidate based on results.
        """
        
        # Identify weak sections
        weak_sections = []
        for section_name, section_data in sections.items():
            if section_data.get("max", 0) > 0:
                percent = section_data.get("earned", 0) / section_data["max"] * 100
                if percent < 60:
                    weak_sections.append({
                        "name": section_name,
                        "percent": round(percent, 1)
                    })
        
        prompt = f"""/no_think Сгенерируй рекомендации для кандидата после собеседования.

Общий результат: {overall_percent}%
Слабые секции: {json.dumps(weak_sections, ensure_ascii=False)}

Дай 3-5 конкретных рекомендаций:
1. Что изучить/подтянуть
2. Какие ресурсы использовать
3. На что обратить внимание

Верни JSON:
{{
    "recommendations": ["рекомендация 1", "рекомендация 2", ...]
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=400
            )
            
            content = response.choices[0].message.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content)
            return result.get("recommendations", ["Продолжайте развивать технические навыки"])
            
        except:
            recommendations = []
            if overall_percent < 60:
                recommendations.append("Рекомендуется углубить знания по основным темам")
            if weak_sections:
                for ws in weak_sections[:2]:
                    recommendations.append(f"Обратите внимание на раздел: {ws['name']}")
            if not recommendations:
                recommendations.append("Продолжайте развивать технические навыки")
            return recommendations
    
    async def compare_with_expected(
        self,
        answer: str,
        expected_keywords: List[str],
        expected_concepts: List[str]
    ) -> Dict[str, Any]:
        """
        Compare answer with expected keywords and concepts.
        Useful for structured evaluation.
        """
        
        answer_lower = answer.lower()
        
        # Check keywords
        found_keywords = [kw for kw in expected_keywords if kw.lower() in answer_lower]
        keyword_coverage = len(found_keywords) / len(expected_keywords) if expected_keywords else 1.0
        
        # Check concepts (more flexible matching)
        prompt = f"""/no_think Проверь, упоминает ли ответ следующие концепции.

Ответ: "{answer[:500]}"

Ожидаемые концепции: {expected_concepts}

Для каждой концепции определи: упомянута (true) или нет (false).

Верни JSON:
{{
    "concepts": {{
        "концепция1": true/false,
        "концепция2": true/false
    }},
    "coverage_percent": число от 0 до 100
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200
            )
            
            content = response.choices[0].message.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content)
            concept_coverage = result.get("coverage_percent", 50) / 100
            
            return {
                "keyword_coverage": keyword_coverage,
                "concept_coverage": concept_coverage,
                "found_keywords": found_keywords,
                "concepts_found": result.get("concepts", {}),
                "overall_coverage": (keyword_coverage + concept_coverage) / 2
            }
            
        except:
            return {
                "keyword_coverage": keyword_coverage,
                "concept_coverage": 0.5,
                "found_keywords": found_keywords,
                "concepts_found": {},
                "overall_coverage": keyword_coverage * 0.5 + 0.25
            }
