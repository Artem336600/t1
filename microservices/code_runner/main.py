"""
Code Runner Service
Executes code safely in Docker sandbox with resource limits
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import os
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

from sandbox import (
    DockerSandbox, SubprocessSandbox, SandboxConfig, 
    SandboxMode, ExecutionResult, get_sandbox
)

app = FastAPI(
    title="Code Runner Service",
    description="Safe code execution in Docker sandbox",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
MAX_EXECUTION_TIME = int(os.getenv("MAX_EXECUTION_TIME", "10"))
MAX_MEMORY_MB = int(os.getenv("MAX_MEMORY_MB", "256"))
SANDBOX_MODE = os.getenv("SANDBOX_MODE", "docker")  # docker or subprocess

# Initialize sandbox
sandbox_config = SandboxConfig(
    mode=SandboxMode.DOCKER if SANDBOX_MODE == "docker" else SandboxMode.SUBPROCESS,
    timeout=MAX_EXECUTION_TIME,
    memory_limit=f"{MAX_MEMORY_MB}m",
    cpu_limit=0.5,
    network_disabled=True
)

# Thread pool for blocking Docker operations
executor = ThreadPoolExecutor(max_workers=10)


class RunRequest(BaseModel):
    code: str
    input: str = ""
    language: str = "python"
    timeout: int = Field(default=5, le=30)


class TestCase(BaseModel):
    input: str
    output: str
    description: Optional[str] = None
    time_limit_ms: Optional[int] = Field(default=2000, description="Time limit in milliseconds")
    points: Optional[int] = Field(default=10, description="Points for this test")


class ValidateRequest(BaseModel):
    code: str
    test_cases: List[TestCase]
    timeout: int = Field(default=5, le=30)
    strict_time: bool = Field(default=True, description="Fail test if time limit exceeded")
    original_code: Optional[str] = Field(default=None, description="Original code to check for unchanged submission")
    task_type: Optional[str] = Field(default=None, description="Task type (e.g., 'optimize') for special validation")


class FileInfo(BaseModel):
    """File in a multi-file project"""
    filename: str
    path: str = ""
    content: str


class MultiFileRunRequest(BaseModel):
    """Request to run multi-file project"""
    files: List[FileInfo]
    entry_point: str = "main.py"
    input: str = ""
    language: str = "python"
    timeout: int = Field(default=10, le=30)


class UnitTest(BaseModel):
    """Unit test definition"""
    test_name: str
    test_code: str
    description: Optional[str] = None
    points: int = 10


class MultiFileValidateRequest(BaseModel):
    """Request to validate multi-file project"""
    files: List[FileInfo]
    entry_point: str = "main.py"
    test_cases: List[TestCase] = []
    unit_tests: List[UnitTest] = []
    test_file: Optional[str] = None
    language: str = "python"
    timeout: int = Field(default=10, le=30)


@app.get("/health")
async def health():
    """Health check with sandbox status"""
    sandbox_status = "docker" if SANDBOX_MODE == "docker" else "subprocess (unsafe)"
    return {
        "status": "ok", 
        "service": "code-runner",
        "sandbox_mode": sandbox_status,
        "config": {
            "max_execution_time": MAX_EXECUTION_TIME,
            "max_memory_mb": MAX_MEMORY_MB,
            "network_disabled": sandbox_config.network_disabled
        }
    }


@app.post("/run")
async def run_code(req: RunRequest):
    """Execute code in secure sandbox"""
    loop = asyncio.get_event_loop()
    
    # Run sandbox in thread pool (Docker operations are blocking)
    sandbox = get_sandbox(SANDBOX_MODE)
    result = await loop.run_in_executor(
        executor,
        lambda: sandbox.execute(
            code=req.code,
            language=req.language,
            stdin=req.input,
            timeout=min(req.timeout, MAX_EXECUTION_TIME)
        )
    )
    
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.exit_code,
        "execution_time": result.execution_time,
        "success": result.success,
        "error": result.error
    }


def normalize_code(code: str) -> str:
    """Normalize code for comparison (remove comments, extra whitespace)"""
    import re
    # Remove single-line comments
    code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
    # Remove multi-line strings/comments
    code = re.sub(r'""".*?"""', '', code, flags=re.DOTALL)
    code = re.sub(r"'''.*?'''", '', code, flags=re.DOTALL)
    # Normalize whitespace
    code = re.sub(r'\s+', ' ', code)
    return code.strip().lower()


def codes_are_similar(code1: str, code2: str, threshold: float = 0.95) -> bool:
    """Check if two codes are similar (to detect unchanged submissions)"""
    norm1 = normalize_code(code1)
    norm2 = normalize_code(code2)
    
    if norm1 == norm2:
        return True
    
    # Simple similarity check based on common characters
    if not norm1 or not norm2:
        return False
    
    # Check if one is substring of another (with some tolerance)
    shorter = norm1 if len(norm1) < len(norm2) else norm2
    longer = norm1 if len(norm1) >= len(norm2) else norm2
    
    if shorter in longer:
        return True
    
    # Character-level similarity
    common = sum(1 for c in shorter if c in longer)
    similarity = common / max(len(shorter), 1)
    
    return similarity >= threshold


@app.post("/validate")
async def validate_code(req: ValidateRequest):
    """Validate code against test cases in secure sandbox with time limits"""
    loop = asyncio.get_event_loop()
    sandbox = get_sandbox(SANDBOX_MODE)
    
    # Check if user submitted unchanged original code (for optimization tasks)
    code_unchanged = False
    if req.original_code and req.task_type == "optimize":
        code_unchanged = codes_are_similar(req.code, req.original_code)
        if code_unchanged:
            # Return early with 0 points - user must optimize the code
            return {
                "all_passed": False,
                "passed": 0,
                "failed": len(req.test_cases),
                "total_points": sum(tc.points or 10 for tc in req.test_cases),
                "earned_points": 0,
                "score_percent": 0,
                "tests": [],
                "error": "unchanged_code",
                "message": "Вы сдали исходный неоптимизированный код. Для получения баллов необходимо оптимизировать алгоритм."
            }
    
    # Prepare test cases with time limits
    test_cases_with_limits = [
        {
            "input": tc.input, 
            "output": tc.output,
            "time_limit_ms": tc.time_limit_ms or 2000,
            "points": tc.points or 10,
            "description": tc.description
        } 
        for tc in req.test_cases[:10]
    ]
    
    # Run validation in thread pool
    validation_result = await loop.run_in_executor(
        executor,
        lambda: sandbox.validate_code(
            code=req.code,
            test_cases=test_cases_with_limits,
            language="python"
        )
    )
    
    # Format results with time limit checking
    passed_count = 0
    failed_count = 0
    total_points = 0
    earned_points = 0
    tests = []
    
    for i, r in enumerate(validation_result["results"]):
        tc = test_cases_with_limits[i] if i < len(test_cases_with_limits) else {}
        time_limit_ms = tc.get("time_limit_ms", 2000)
        points = tc.get("points", 10)
        execution_time_ms = r["execution_time"] * 1000 if r["execution_time"] else 0
        
        # Check if passed AND within time limit
        time_exceeded = execution_time_ms > time_limit_ms
        test_passed = r["passed"] and (not req.strict_time or not time_exceeded)
        
        if test_passed:
            passed_count += 1
            earned_points += points
        else:
            failed_count += 1
        
        total_points += points
        
        # Build failure reason
        failure_reason = None
        if not r["passed"]:
            failure_reason = "wrong_answer"
        elif time_exceeded and req.strict_time:
            failure_reason = "time_limit_exceeded"
        
        tests.append({
            "num": r["test_number"],
            "passed": test_passed,
            "expected": r["expected"][:100] + ("..." if len(r["expected"]) > 100 else ""),
            "actual": r["actual"][:100] + ("..." if len(r["actual"]) > 100 else ""),
            "error": r.get("error", "")[:200] if r.get("error") else None,
            "execution_time": r["execution_time"],
            "execution_time_ms": round(execution_time_ms, 2),
            "time_limit_ms": time_limit_ms,
            "time_exceeded": time_exceeded,
            "points": points,
            "earned_points": points if test_passed else 0,
            "failure_reason": failure_reason,
            "description": tc.get("description")
        })
    
    return {
        "all_passed": passed_count == len(tests) and failed_count == 0,
        "passed": passed_count,
        "failed": failed_count,
        "total_points": total_points,
        "earned_points": earned_points,
        "score_percent": round(earned_points / total_points * 100, 1) if total_points > 0 else 0,
        "tests": tests
    }


@app.get("/supported-languages")
async def supported_languages():
    """List supported programming languages"""
    return {
        "languages": ["python", "javascript", "go"],
        "default": "python"
    }


@app.post("/run/multifile")
async def run_multifile(req: MultiFileRunRequest):
    """
    Execute multi-file project in secure sandbox.
    
    Supports projects with multiple files and subdirectories.
    """
    loop = asyncio.get_event_loop()
    sandbox = get_sandbox(SANDBOX_MODE)
    
    # Convert to dict format for sandbox
    files = [f.dict() for f in req.files]
    
    result = await loop.run_in_executor(
        executor,
        lambda: sandbox.execute_multifile(
            files=files,
            entry_point=req.entry_point,
            language=req.language,
            stdin=req.input,
            timeout=min(req.timeout, MAX_EXECUTION_TIME)
        )
    )
    
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.exit_code,
        "execution_time": result.execution_time,
        "success": result.success,
        "error": result.error
    }


@app.post("/validate/multifile")
async def validate_multifile(req: MultiFileValidateRequest):
    """
    Validate multi-file project against test cases and unit tests.
    
    Supports:
    - stdin/stdout test cases
    - Unit tests (pytest-style)
    - Custom test files
    """
    loop = asyncio.get_event_loop()
    sandbox = get_sandbox(SANDBOX_MODE)
    
    # Convert to dict format
    files = [f.dict() for f in req.files]
    test_cases = [tc.dict() for tc in req.test_cases]
    unit_tests = [ut.dict() for ut in req.unit_tests] if req.unit_tests else None
    
    result = await loop.run_in_executor(
        executor,
        lambda: sandbox.validate_multifile(
            files=files,
            entry_point=req.entry_point,
            test_cases=test_cases,
            language=req.language,
            unit_tests=unit_tests,
            test_file=req.test_file
        )
    )
    
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
