"""
Shared Pydantic models for all microservices
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


# ============== Enums ==============

class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class SectionType(str, Enum):
    LIVE_CODING = "live_coding"
    HARD_SKILLS = "hard_skills"
    SOFT_SKILLS = "soft_skills"
    LOGIC = "logic"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


# ============== Library Models ==============

class SectionBase(BaseModel):
    name: str
    description: str
    icon: str = "folder"
    color: str = "purple"


class SectionCreate(SectionBase):
    pass


class Section(SectionBase):
    id: int
    order: int
    folder_count: int = 0
    task_count: int = 0

    class Config:
        from_attributes = True


class FolderBase(BaseModel):
    name: str
    description: str = ""
    icon: str = "folder"


class FolderCreate(FolderBase):
    section_id: int


class Folder(FolderBase):
    id: int
    section_id: int
    order: int
    task_count: int = 0

    class Config:
        from_attributes = True


class TestCase(BaseModel):
    input: str
    output: str
    description: Optional[str] = None


class TaskContent(BaseModel):
    """Content varies by section type"""
    # Live Coding
    test_cases: Optional[List[TestCase]] = None
    hidden_tests: Optional[List[TestCase]] = None
    hints: Optional[List[str]] = None
    time_limit: Optional[str] = None
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    constraints: Optional[str] = None
    
    # Hard Skills
    key_points: Optional[List[str]] = None
    example_answer: Optional[str] = None
    code_example: Optional[str] = None
    
    # Soft Skills
    structure: Optional[str] = None
    tips: Optional[List[str]] = None
    
    # Logic
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None


class TaskBase(BaseModel):
    title: str
    description: str = ""
    difficulty: Difficulty = Difficulty.MEDIUM
    tags: List[str] = []
    content: TaskContent = TaskContent()


class TaskCreate(TaskBase):
    folder_id: int


class Task(TaskBase):
    id: int
    folder_id: int
    is_completed: bool = False
    notes: Optional[str] = None
    my_answer: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============== Task Generator Models ==============

class GenerateRequest(BaseModel):
    query: str = Field(..., description="Task topic or description")
    difficulty: Difficulty = Difficulty.MEDIUM
    section_type: SectionType = SectionType.LIVE_CODING
    language: str = "python"


class AgentInfo(BaseModel):
    name: str
    status: AgentStatus
    model: Optional[str] = None
    execution_time: Optional[float] = None


class GeneratedTask(BaseModel):
    title: str
    description: str
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    constraints: Optional[str] = None
    test_cases: List[TestCase] = []
    hidden_tests: List[TestCase] = []
    hints: List[str] = []
    time_limit: str = "1 секунда"
    tags: List[str] = []
    complexity: Optional[Dict[str, str]] = None


class GenerateResponse(BaseModel):
    status: str  # success, partial, error
    execution_time: float
    agents: List[AgentInfo]
    task: Optional[GeneratedTask] = None
    solution: Optional[str] = None
    validation: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ============== Code Runner Models ==============

class RunCodeRequest(BaseModel):
    code: str
    input: str = ""
    language: str = "python"
    timeout: int = Field(default=5, le=30)


class RunCodeResponse(BaseModel):
    stdout: str
    stderr: str
    returncode: int
    execution_time: float


class ValidateRequest(BaseModel):
    code: str
    test_cases: List[TestCase]
    timeout: int = Field(default=5, le=30)


class TestResult(BaseModel):
    num: int
    passed: bool
    input: str
    expected: str
    actual: str
    error: Optional[str] = None
    execution_time: float = 0


class ValidateResponse(BaseModel):
    all_passed: bool
    passed: int
    failed: int
    tests: List[TestResult]


# ============== RAG Models ==============

class EmbeddingRequest(BaseModel):
    texts: List[str]


class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]


class SearchRequest(BaseModel):
    query: str
    section_type: Optional[SectionType] = None
    top_k: int = 5


class SearchResult(BaseModel):
    folder_id: int
    folder_name: str
    description: str
    score: float


class SearchResponse(BaseModel):
    results: List[SearchResult]
    query_embedding: Optional[List[float]] = None
