"""
Adaptive Learning Service
Personalized learning paths and progress tracking
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json
import os
import math

app = FastAPI(
    title="Adaptive Learning Service",
    description="Personalized learning with spaced repetition and progress tracking",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = "data/learning_data.json"


# ============== Models ==============

class UserProgress(BaseModel):
    """User's progress on a concept with detailed statistics"""
    concept_id: str
    level: float = 0.0  # 0-1 mastery level
    attempts: int = 0
    successes: int = 0
    last_practice: Optional[str] = None
    next_review: Optional[str] = None  # Spaced repetition
    streak: int = 0
    max_streak: int = 0
    easiness: float = 2.5  # SM-2 algorithm factor
    interval: int = 1  # Current review interval in days
    repetitions: int = 0  # Number of successful reviews in a row
    
    # Detailed statistics
    total_time_spent: int = 0  # seconds on this concept
    avg_time_per_task: float = 0
    hints_total: int = 0
    last_difficulty: float = 0.5
    difficulty_history: List[float] = []  # Track difficulty progression
    success_rate: float = 0.0


class UserProfile(BaseModel):
    """User learning profile"""
    user_id: str
    created_at: str
    progress: Dict[str, UserProgress] = {}
    total_tasks_solved: int = 0
    total_time_spent: int = 0  # seconds
    preferred_difficulty: float = 0.5
    strengths: List[str] = []
    weaknesses: List[str] = []
    current_streak: int = 0
    last_active: Optional[str] = None


class TaskAttempt(BaseModel):
    user_id: str
    concept_ids: List[str]
    solved: bool
    time_spent: int = 0
    hints_used: int = 0
    difficulty: float = 0.5


class LearningRecommendation(BaseModel):
    concept_id: str
    concept_name: str
    reason: str
    priority: float
    suggested_difficulty: float


# ============== Learning Engine ==============

class LearningEngine:
    def __init__(self):
        self.users: Dict[str, UserProfile] = {}
        self.load()
    
    def load(self):
        os.makedirs("data", exist_ok=True)
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for uid, udata in data.get("users", {}).items():
                        # Convert progress dict
                        progress = {}
                        for cid, pdata in udata.get("progress", {}).items():
                            progress[cid] = UserProgress(**pdata)
                        udata["progress"] = progress
                        self.users[uid] = UserProfile(**udata)
                print(f"Loaded {len(self.users)} user profiles")
            except Exception as e:
                print(f"Failed to load learning data: {e}")
    
    def save(self):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            data = {"users": {}}
            for uid, user in self.users.items():
                udata = user.model_dump()
                udata["progress"] = {cid: p.model_dump() for cid, p in user.progress.items()}
                data["users"][uid] = udata
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_or_create_user(self, user_id: str) -> UserProfile:
        if user_id not in self.users:
            self.users[user_id] = UserProfile(
                user_id=user_id,
                created_at=datetime.now().isoformat()
            )
            self.save()
        return self.users[user_id]
    
    def record_attempt(self, attempt: TaskAttempt):
        """
        Record a task attempt and update user progress using SM-2 algorithm.
        
        SM-2 Algorithm:
        - quality: 0-5 rating of response quality
        - easiness factor (EF): >= 1.3, adjusted based on quality
        - interval: days until next review
        - repetitions: count of successful reviews
        """
        user = self.get_or_create_user(attempt.user_id)
        now = datetime.now()
        
        for concept_id in attempt.concept_ids:
            if concept_id not in user.progress:
                user.progress[concept_id] = UserProgress(concept_id=concept_id)
            
            prog = user.progress[concept_id]
            prog.attempts += 1
            prog.total_time_spent += attempt.time_spent
            prog.hints_total += attempt.hints_used
            prog.last_difficulty = attempt.difficulty
            
            # Track difficulty history (last 10)
            prog.difficulty_history.append(attempt.difficulty)
            if len(prog.difficulty_history) > 10:
                prog.difficulty_history = prog.difficulty_history[-10:]
            
            # Calculate quality score (0-5) for SM-2
            if attempt.solved:
                # Base quality on hints and time
                if attempt.hints_used == 0:
                    quality = 5  # Perfect
                elif attempt.hints_used == 1:
                    quality = 4  # Good with minor hesitation
                elif attempt.hints_used == 2:
                    quality = 3  # Correct with difficulty
                else:
                    quality = 2  # Barely correct
                
                prog.successes += 1
                prog.streak += 1
                prog.max_streak = max(prog.max_streak, prog.streak)
                prog.repetitions += 1
                
                # Update mastery level (weighted by difficulty and quality)
                difficulty_bonus = attempt.difficulty * 0.15
                quality_bonus = (quality / 5) * 0.1
                hint_penalty = min(0.15, attempt.hints_used * 0.05)
                gain = 0.08 + difficulty_bonus + quality_bonus - hint_penalty
                prog.level = min(1.0, prog.level + gain)
                
                # SM-2: Update easiness factor
                # EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
                prog.easiness = max(1.3, prog.easiness + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
                
                # SM-2: Calculate next interval
                if prog.repetitions == 1:
                    prog.interval = 1
                elif prog.repetitions == 2:
                    prog.interval = 6
                else:
                    prog.interval = int(prog.interval * prog.easiness)
                
                prog.next_review = (now + timedelta(days=prog.interval)).isoformat()
                
            else:
                # Failed - quality < 3
                quality = 1 if attempt.hints_used > 2 else 2
                
                prog.streak = 0
                prog.repetitions = 0
                prog.interval = 1  # Reset interval
                prog.level = max(0, prog.level - 0.08)
                prog.next_review = now.isoformat()  # Review immediately
                
                # Decrease easiness slightly on failure
                prog.easiness = max(1.3, prog.easiness - 0.2)
            
            # Update success rate
            prog.success_rate = prog.successes / prog.attempts if prog.attempts > 0 else 0
            
            # Update average time
            prog.avg_time_per_task = prog.total_time_spent / prog.attempts if prog.attempts > 0 else 0
            
            prog.last_practice = now.isoformat()
        
        # Update user stats
        user.total_tasks_solved += 1 if attempt.solved else 0
        user.total_time_spent += attempt.time_spent
        user.last_active = now.isoformat()
        
        # Update preferred difficulty based on performance
        if attempt.solved:
            user.preferred_difficulty = min(1.0, user.preferred_difficulty + 0.02)
        else:
            user.preferred_difficulty = max(0.1, user.preferred_difficulty - 0.03)
        
        # Update strengths/weaknesses
        self._update_strengths_weaknesses(user)
        
        self.save()
        return user
    
    def _update_strengths_weaknesses(self, user: UserProfile):
        """Analyze progress to identify strengths and weaknesses"""
        strengths = []
        weaknesses = []
        
        for cid, prog in user.progress.items():
            if prog.attempts >= 3:  # Need enough data
                success_rate = prog.successes / prog.attempts
                if success_rate >= 0.8 and prog.level >= 0.7:
                    strengths.append(cid)
                elif success_rate < 0.4 or prog.level < 0.3:
                    weaknesses.append(cid)
        
        user.strengths = strengths[:5]
        user.weaknesses = weaknesses[:5]
    
    def get_recommendations(self, user_id: str, concepts: Dict[str, Any], top_k: int = 5) -> List[Dict]:
        """Get personalized learning recommendations"""
        user = self.get_or_create_user(user_id)
        now = datetime.now()
        recommendations = []
        
        for cid, concept in concepts.items():
            priority = 0
            reason = ""
            
            if cid in user.progress:
                prog = user.progress[cid]
                
                # Due for review (spaced repetition)
                if prog.next_review:
                    review_date = datetime.fromisoformat(prog.next_review)
                    if review_date <= now:
                        days_overdue = (now - review_date).days
                        priority += 0.5 + min(0.3, days_overdue * 0.05)
                        reason = "Пора повторить"
                
                # Low mastery
                if prog.level < 0.5:
                    priority += (0.5 - prog.level) * 0.4
                    reason = reason or "Требует практики"
                
                # Weakness
                if cid in user.weaknesses:
                    priority += 0.3
                    reason = reason or "Слабое место"
            else:
                # New concept - check prerequisites
                prereqs = concept.get("prerequisites", [])
                prereqs_mastered = all(
                    user.progress.get(p, UserProgress(concept_id=p)).level >= 0.5 
                    for p in prereqs
                )
                
                if prereqs_mastered:
                    # Difficulty match
                    diff = concept.get("difficulty", 0.5)
                    diff_match = 1 - abs(diff - user.preferred_difficulty)
                    priority += diff_match * 0.3
                    reason = "Новая тема для изучения"
                else:
                    priority -= 0.5  # Prerequisites not met
                    reason = "Сначала изучите prerequisites"
            
            if priority > 0:
                recommendations.append({
                    "concept_id": cid,
                    "concept_name": concept.get("name", cid),
                    "reason": reason,
                    "priority": priority,
                    "suggested_difficulty": user.preferred_difficulty,
                    "current_level": user.progress.get(cid, UserProgress(concept_id=cid)).level
                })
        
        recommendations.sort(key=lambda x: x["priority"], reverse=True)
        return recommendations[:top_k]
    
    def get_adaptive_difficulty(self, user_id: str, concept_ids: List[str]) -> float:
        """Calculate adaptive difficulty for given concepts"""
        user = self.get_or_create_user(user_id)
        
        if not concept_ids:
            return user.preferred_difficulty
        
        # Average mastery of requested concepts
        levels = []
        for cid in concept_ids:
            if cid in user.progress:
                levels.append(user.progress[cid].level)
            else:
                levels.append(0.3)  # New concept - start easier
        
        avg_level = sum(levels) / len(levels)
        
        # Adjust difficulty based on mastery
        # High mastery -> harder tasks, low mastery -> easier tasks
        base_diff = user.preferred_difficulty
        adjustment = (avg_level - 0.5) * 0.3
        
        return max(0.1, min(1.0, base_diff + adjustment))


# Global instance
engine = LearningEngine()


# ============== API Endpoints ==============

@app.get("/health")
async def health():
    return {"status": "ok", "service": "learning", "users_count": len(engine.users)}


@app.get("/users/{user_id}")
async def get_user_profile(user_id: str):
    """Get user learning profile"""
    user = engine.get_or_create_user(user_id)
    return {
        "user_id": user.user_id,
        "total_tasks_solved": user.total_tasks_solved,
        "total_time_spent": user.total_time_spent,
        "preferred_difficulty": user.preferred_difficulty,
        "strengths": user.strengths,
        "weaknesses": user.weaknesses,
        "current_streak": user.current_streak,
        "concepts_learned": len([p for p in user.progress.values() if p.level >= 0.5]),
        "concepts_in_progress": len([p for p in user.progress.values() if 0 < p.level < 0.5])
    }


@app.get("/users/{user_id}/progress")
async def get_user_progress(user_id: str):
    """Get detailed progress for all concepts"""
    user = engine.get_or_create_user(user_id)
    return {
        cid: {
            "level": p.level,
            "attempts": p.attempts,
            "successes": p.successes,
            "streak": p.streak,
            "last_practice": p.last_practice,
            "next_review": p.next_review
        }
        for cid, p in user.progress.items()
    }


@app.post("/attempt")
async def record_attempt(attempt: TaskAttempt):
    """Record a task attempt"""
    user = engine.record_attempt(attempt)
    return {
        "success": True,
        "new_preferred_difficulty": user.preferred_difficulty,
        "concepts_updated": attempt.concept_ids
    }


@app.post("/recommendations/{user_id}")
async def get_recommendations(user_id: str, concepts: Dict[str, Any]):
    """Get personalized learning recommendations"""
    recs = engine.get_recommendations(user_id, concepts)
    return {"recommendations": recs}


@app.get("/adaptive-difficulty/{user_id}")
async def get_adaptive_difficulty(user_id: str, concepts: str = ""):
    """Get adaptive difficulty for concepts"""
    concept_list = [c.strip() for c in concepts.split(",") if c.strip()]
    difficulty = engine.get_adaptive_difficulty(user_id, concept_list)
    return {"difficulty": difficulty, "concepts": concept_list}


@app.get("/review-queue/{user_id}")
async def get_review_queue(user_id: str):
    """Get concepts due for review"""
    user = engine.get_or_create_user(user_id)
    now = datetime.now()
    
    due = []
    for cid, prog in user.progress.items():
        if prog.next_review:
            review_date = datetime.fromisoformat(prog.next_review)
            if review_date <= now:
                due.append({
                    "concept_id": cid,
                    "level": prog.level,
                    "days_overdue": (now - review_date).days,
                    "streak": prog.streak,
                    "easiness": prog.easiness
                })
    
    due.sort(key=lambda x: x["days_overdue"], reverse=True)
    return {"due_for_review": due}


@app.get("/stats/{user_id}")
async def get_detailed_stats(user_id: str):
    """Get detailed learning statistics"""
    user = engine.get_or_create_user(user_id)
    now = datetime.now()
    
    # Calculate overall stats
    total_attempts = sum(p.attempts for p in user.progress.values())
    total_successes = sum(p.successes for p in user.progress.values())
    overall_success_rate = total_successes / total_attempts if total_attempts > 0 else 0
    
    # Concepts by mastery level
    mastery_distribution = {
        "beginner": len([p for p in user.progress.values() if p.level < 0.3]),
        "intermediate": len([p for p in user.progress.values() if 0.3 <= p.level < 0.7]),
        "advanced": len([p for p in user.progress.values() if p.level >= 0.7])
    }
    
    # Due for review
    due_count = 0
    for prog in user.progress.values():
        if prog.next_review:
            review_date = datetime.fromisoformat(prog.next_review)
            if review_date <= now:
                due_count += 1
    
    # Best and worst concepts
    sorted_by_level = sorted(user.progress.values(), key=lambda p: p.level, reverse=True)
    best_concepts = [{"id": p.concept_id, "level": p.level, "streak": p.max_streak} 
                    for p in sorted_by_level[:5]]
    worst_concepts = [{"id": p.concept_id, "level": p.level, "success_rate": p.success_rate} 
                     for p in sorted_by_level[-5:] if p.level < 0.5]
    
    return {
        "user_id": user_id,
        "overview": {
            "total_concepts": len(user.progress),
            "total_attempts": total_attempts,
            "total_successes": total_successes,
            "overall_success_rate": round(overall_success_rate, 3),
            "total_time_spent_hours": round(user.total_time_spent / 3600, 1),
            "preferred_difficulty": user.preferred_difficulty
        },
        "mastery_distribution": mastery_distribution,
        "review_status": {
            "due_now": due_count,
            "total_tracked": len([p for p in user.progress.values() if p.next_review])
        },
        "best_concepts": best_concepts,
        "needs_work": worst_concepts,
        "strengths": user.strengths,
        "weaknesses": user.weaknesses
    }


@app.get("/concept-stats/{user_id}/{concept_id}")
async def get_concept_stats(user_id: str, concept_id: str):
    """Get detailed stats for a specific concept"""
    user = engine.get_or_create_user(user_id)
    
    if concept_id not in user.progress:
        return {"error": "No data for this concept", "concept_id": concept_id}
    
    prog = user.progress[concept_id]
    
    return {
        "concept_id": concept_id,
        "mastery_level": prog.level,
        "attempts": prog.attempts,
        "successes": prog.successes,
        "success_rate": prog.success_rate,
        "current_streak": prog.streak,
        "max_streak": prog.max_streak,
        "sm2_stats": {
            "easiness_factor": prog.easiness,
            "current_interval_days": prog.interval,
            "repetitions": prog.repetitions,
            "next_review": prog.next_review
        },
        "time_stats": {
            "total_time_seconds": prog.total_time_spent,
            "avg_time_per_task": prog.avg_time_per_task,
            "total_hints_used": prog.hints_total
        },
        "difficulty_progression": prog.difficulty_history,
        "last_practice": prog.last_practice
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
