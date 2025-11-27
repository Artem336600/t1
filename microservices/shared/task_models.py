"""
Shared Task Models
Defines task structures for single-file and multi-file tasks.
"""
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum


class TaskType(str, Enum):
    """Type of task"""
    SINGLE_FILE = "single_file"      # Classic: write one solution file
    MULTI_FILE = "multi_file"        # Multiple files to edit/fix
    FIX_BUG = "fix_bug"              # Find and fix bugs in code
    COMPLETE_FUNCTION = "complete"    # Complete function implementation
    REFACTOR = "refactor"            # Refactor existing code
    CODE_REVIEW = "review"           # Review and suggest improvements


class FileRole(str, Enum):
    """Role of a file in multi-file task"""
    MAIN = "main"           # Main entry point
    MODULE = "module"       # Module to import
    TEST = "test"           # Test file
    CONFIG = "config"       # Configuration file
    DATA = "data"           # Data file (JSON, etc.)
    READONLY = "readonly"   # Read-only context file


class TaskFile(BaseModel):
    """A file in a multi-file task"""
    filename: str = Field(..., description="File name with extension")
    path: str = Field(default="", description="Relative path (e.g., 'src/' or '')")
    content: str = Field(..., description="File content")
    language: str = Field(default="python", description="Programming language")
    role: FileRole = Field(default=FileRole.MODULE, description="Role of this file")
    editable: bool = Field(default=True, description="Can user edit this file?")
    
    # For fix/complete tasks
    solution_content: Optional[str] = Field(None, description="Expected solution content")
    hints_for_file: Optional[List[str]] = Field(None, description="Hints specific to this file")
    
    # Markers for what to fix/complete
    todo_markers: Optional[List[str]] = Field(
        default=None, 
        description="Markers like # TODO, # FIXME, # YOUR CODE HERE"
    )


class TestCase(BaseModel):
    """Test case for validation"""
    input: str = Field(default="", description="stdin input")
    output: str = Field(default="", description="Expected stdout output")
    description: Optional[str] = Field(None, description="Test description")
    category: str = Field(default="basic", description="basic, edge, performance")
    points: int = Field(default=10, description="Points for this test")
    hidden: bool = Field(default=False, description="Is this a hidden test?")


class UnitTest(BaseModel):
    """Unit test for function-level testing"""
    test_name: str = Field(..., description="Test function name")
    test_code: str = Field(..., description="Test code to run")
    description: Optional[str] = None
    points: int = Field(default=10)


class Hint(BaseModel):
    """Hint with penalty"""
    level: int = Field(default=1, description="Hint level (1=general, 2=specific, 3=solution)")
    text: str = Field(..., description="Hint text")
    penalty: float = Field(default=0.05, description="Score penalty for using this hint")
    for_file: Optional[str] = Field(None, description="Specific file this hint is for")


class Constraints(BaseModel):
    """Task constraints"""
    time_limit_ms: int = Field(default=2000)
    memory_limit_mb: int = Field(default=256)
    max_file_size_kb: int = Field(default=100)
    allowed_imports: Optional[List[str]] = Field(None, description="Allowed imports (None = all)")
    forbidden_imports: Optional[List[str]] = Field(None, description="Forbidden imports")


# ============== Single-File Task ==============

class SingleFileTask(BaseModel):
    """Classic single-file coding task"""
    task_type: TaskType = TaskType.SINGLE_FILE
    
    # Basic info
    title: str
    description: str
    hashtags: List[str] = []
    level: str = "middle"  # junior, middle, senior
    
    # Examples and tests
    examples: List[Dict[str, str]] = []  # {input, output, explanation}
    test_cases: List[TestCase] = []
    hidden_tests: List[TestCase] = []
    
    # Solution
    solution: Optional[str] = None
    solution_explanation: Optional[str] = None
    
    # Hints and constraints
    hints: List[Hint] = []
    constraints: Constraints = Field(default_factory=Constraints)
    
    # Metadata
    estimated_time_minutes: int = 20
    language: str = "python"


# ============== Multi-File Task ==============

class MultiFileTask(BaseModel):
    """Multi-file task (fix bugs, complete functions, etc.)"""
    task_type: TaskType = Field(default=TaskType.MULTI_FILE)
    
    # Basic info
    title: str
    description: str
    hashtags: List[str] = []
    level: str = "middle"
    
    # Files
    files: List[TaskFile] = Field(..., description="All files in the task")
    entry_point: str = Field(default="main.py", description="Main file to run")
    
    # What user needs to do
    objectives: List[str] = Field(
        default_factory=list,
        description="List of objectives user needs to complete"
    )
    
    # Testing
    test_cases: List[TestCase] = Field(default_factory=list, description="stdin/stdout tests")
    unit_tests: List[UnitTest] = Field(default_factory=list, description="Unit tests")
    test_file: Optional[str] = Field(None, description="Custom test file content")
    
    # Solution files (for validation)
    solution_files: Optional[List[TaskFile]] = Field(
        None, 
        description="Expected solution files"
    )
    
    # Hints and constraints
    hints: List[Hint] = []
    constraints: Constraints = Field(default_factory=Constraints)
    
    # Metadata
    estimated_time_minutes: int = 30
    language: str = "python"
    
    def get_editable_files(self) -> List[TaskFile]:
        """Get files that user can edit"""
        return [f for f in self.files if f.editable]
    
    def get_readonly_files(self) -> List[TaskFile]:
        """Get read-only context files"""
        return [f for f in self.files if not f.editable]
    
    def get_file_by_name(self, filename: str) -> Optional[TaskFile]:
        """Find file by name"""
        for f in self.files:
            if f.filename == filename:
                return f
        return None


# ============== Task Templates ==============

class BugFixTask(MultiFileTask):
    """Task to find and fix bugs"""
    task_type: TaskType = TaskType.FIX_BUG
    
    # Bug info
    bug_description: Optional[str] = Field(None, description="Description of the bug")
    bug_locations: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Hints about where bugs are: [{file, line, hint}]"
    )
    num_bugs: int = Field(default=1, description="Number of bugs to find")


class CompleteFunctionTask(MultiFileTask):
    """Task to complete function implementations"""
    task_type: TaskType = TaskType.COMPLETE_FUNCTION
    
    # Functions to complete
    functions_to_complete: List[Dict[str, str]] = Field(
        default_factory=list,
        description="[{file, function_name, signature, docstring}]"
    )


class RefactorTask(MultiFileTask):
    """Task to refactor code"""
    task_type: TaskType = TaskType.REFACTOR
    
    # Refactoring goals
    refactoring_goals: List[str] = Field(
        default_factory=list,
        description="What improvements to make"
    )
    quality_metrics: Optional[Dict[str, Any]] = Field(
        None,
        description="Metrics to check (complexity, duplication, etc.)"
    )


# ============== Union Type for Any Task ==============

Task = Union[SingleFileTask, MultiFileTask, BugFixTask, CompleteFunctionTask, RefactorTask]


# ============== Request/Response Models ==============

class MultiFileRunRequest(BaseModel):
    """Request to run multi-file code"""
    files: List[TaskFile]
    entry_point: str = "main.py"
    input: str = ""
    language: str = "python"
    timeout: int = Field(default=10, le=30)


class MultiFileValidateRequest(BaseModel):
    """Request to validate multi-file solution"""
    files: List[TaskFile]
    entry_point: str = "main.py"
    test_cases: List[TestCase] = []
    unit_tests: List[UnitTest] = []
    test_file: Optional[str] = None
    language: str = "python"
    timeout: int = Field(default=10, le=30)


class ValidationResult(BaseModel):
    """Result of code validation"""
    all_passed: bool
    passed: int
    failed: int
    total: int
    score: float = Field(default=0.0, description="Score 0-100")
    tests: List[Dict[str, Any]] = []
    errors: List[str] = []
