"""
API Gateway Service
Entry point for all client requests, routes to appropriate microservices
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import httpx
import os
from pathlib import Path
from typing import Optional

app = FastAPI(
    title="Interview Prep API Gateway",
    description="API Gateway for Interview Preparation Platform",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service URLs
LIBRARY_URL = os.getenv("LIBRARY_SERVICE_URL", "http://localhost:8001")
TASK_GENERATOR_URL = os.getenv("TASK_GENERATOR_URL", "http://localhost:8002")
CODE_RUNNER_URL = os.getenv("CODE_RUNNER_URL", "http://localhost:8003")
RAG_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8004")
KNOWLEDGE_URL = os.getenv("KNOWLEDGE_SERVICE_URL", "http://localhost:8005")
LEARNING_URL = os.getenv("LEARNING_SERVICE_URL", "http://localhost:8006")
HASHTAG_URL = os.getenv("HASHTAG_SERVICE_URL", "http://localhost:8010")
TASK_ARCHITECT_URL = os.getenv("TASK_ARCHITECT_URL", "http://localhost:8007")

# HTTP Client
client = httpx.AsyncClient(timeout=300.0)

# Static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)


@app.get("/")
async def root():
    """Serve frontend"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Interview Prep API Gateway", "docs": "/docs"}


@app.get("/health")
async def health():
    """Health check for all services"""
    services = {}
    
    for name, url in [
        ("library", LIBRARY_URL),
        ("task-generator", TASK_GENERATOR_URL),
        ("code-runner", CODE_RUNNER_URL),
        ("rag", RAG_URL),
        ("knowledge", KNOWLEDGE_URL),
        ("learning", LEARNING_URL),
        ("hashtag", HASHTAG_URL),
        ("architect", TASK_ARCHITECT_URL)
    ]:
        try:
            resp = await client.get(f"{url}/health", timeout=5.0)
            services[name] = "ok" if resp.status_code == 200 else "error"
        except:
            services[name] = "unavailable"
    
    return {
        "status": "ok",
        "services": services
    }


# ============== Library Routes ==============

@app.get("/api/sections")
async def get_sections():
    """Get all sections with folders"""
    resp = await client.get(f"{LIBRARY_URL}/sections")
    return resp.json()


@app.get("/api/sections/{section_id}")
async def get_section(section_id: int):
    """Get section by ID"""
    resp = await client.get(f"{LIBRARY_URL}/sections/{section_id}")
    return resp.json()


@app.get("/api/folders/{folder_id}")
async def get_folder(folder_id: int):
    """Get folder with tasks"""
    resp = await client.get(f"{LIBRARY_URL}/folders/{folder_id}")
    return resp.json()


@app.post("/api/folders")
async def create_folder(request: Request):
    """Create new folder"""
    data = await request.json()
    resp = await client.post(f"{LIBRARY_URL}/folders", json=data)
    return resp.json()


@app.delete("/api/folders/{folder_id}")
async def delete_folder(folder_id: int):
    """Delete folder"""
    resp = await client.delete(f"{LIBRARY_URL}/folders/{folder_id}")
    return resp.json()


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: int):
    """Get task by ID"""
    resp = await client.get(f"{LIBRARY_URL}/tasks/{task_id}")
    return resp.json()


@app.post("/api/tasks")
async def create_task(request: Request):
    """Create new task"""
    data = await request.json()
    resp = await client.post(f"{LIBRARY_URL}/tasks", json=data)
    return resp.json()


@app.put("/api/tasks/{task_id}")
async def update_task(task_id: int, request: Request):
    """Update task"""
    data = await request.json()
    resp = await client.put(f"{LIBRARY_URL}/tasks/{task_id}", json=data)
    return resp.json()


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int):
    """Delete task"""
    resp = await client.delete(f"{LIBRARY_URL}/tasks/{task_id}")
    return resp.json()


@app.post("/api/tasks/{task_id}/toggle")
async def toggle_task(task_id: int):
    """Toggle task completion"""
    resp = await client.post(f"{LIBRARY_URL}/tasks/{task_id}/toggle")
    return resp.json()


# ============== Task Generator Routes ==============

@app.post("/api/generate")
async def generate_task(request: Request):
    """Generate task using multi-agent system"""
    data = await request.json()
    
    # First, analyze task structure using Architect
    try:
        architect_resp = await client.post(f"{TASK_ARCHITECT_URL}/analyze", json={
            "query": data.get("query", ""),
            "difficulty": data.get("difficulty", "medium")
        })
        analysis = architect_resp.json()
        strategy = analysis.get("strategy", "flexible")
    except Exception as e:
        print(f"Architect error: {e}")
        strategy = "flexible"
        
    # Route to appropriate generator
    if strategy == "multifile":
        resp = await client.post(f"{TASK_GENERATOR_URL}/generate/multifile", json=data)
    else:
        # Default flexible generator
        resp = await client.post(f"{TASK_GENERATOR_URL}/generate", json=data)
        
    result = resp.json()
    
    # First, search for matching folder using RAG
    try:
        rag_resp = await client.post(f"{RAG_URL}/search", json={
            "query": data.get("query", ""),
            "section_type": data.get("section_type"),
            "top_k": 1
        })
        rag_result = rag_resp.json()
    except:
        rag_result = {"results": []}
    
    # Generate task
    resp = await client.post(f"{TASK_GENERATOR_URL}/generate", json=data)
    result = resp.json()
    
    # Add RAG results
    if rag_result.get("results"):
        best_match = rag_result["results"][0]
        if best_match["score"] > 0.45:
            result["folder_id"] = best_match["folder_id"]
            result["folder_name"] = best_match["folder_name"]
            result["action"] = "found"
        else:
            result["action"] = "created"
    else:
        result["action"] = "created"
    
    # Save to library if task generated successfully
    if result.get("status") == "success" and result.get("task"):
        task_data = result["task"]
        
        # Create folder if needed
        if result.get("action") == "created":
            # Get section ID
            sections_resp = await client.get(f"{LIBRARY_URL}/sections")
            sections = sections_resp.json()
            section_map = {
                "live_coding": "Live Coding",
                "hard_skills": "Hard Skills",
                "soft_skills": "Soft Skills",
                "logic": "Логика"
            }
            section_name = section_map.get(data.get("section_type", "live_coding"))
            section = next((s for s in sections if s["name"] == section_name), None)
            
            if section:
                # Create folder
                folder_resp = await client.post(f"{LIBRARY_URL}/folders", json={
                    "section_id": section["id"],
                    "name": task_data.get("title", "New Folder")[:30],
                    "description": f"Auto-generated for: {data.get('query', '')}"
                })
                folder = folder_resp.json()
                result["folder_id"] = folder.get("id")
        
        # Create task
        if result.get("folder_id"):
            task_resp = await client.post(f"{LIBRARY_URL}/tasks", json={
                "folder_id": result["folder_id"],
                "title": task_data.get("title", ""),
                "description": task_data.get("description", ""),
                "difficulty": data.get("difficulty", "medium"),
                "tags": task_data.get("tags", []),
                "content": {
                    "test_cases": task_data.get("test_cases", []),
                    "hidden_tests": task_data.get("hidden_tests", []),
                    "hints": task_data.get("hints", []),
                    "time_limit": task_data.get("time_limit"),
                    "input_format": task_data.get("input_format"),
                    "output_format": task_data.get("output_format"),
                    "constraints": task_data.get("constraints")
                }
            })
            result["task_id"] = task_resp.json().get("id")
    
    return result


@app.post("/api/generate/hashtag")
async def generate_task_with_hashtags(request: Request):
    """Generate task using hashtag taxonomy and example tasks"""
    data = await request.json()
    
    # Call hashtag-based generator
    resp = await client.post(f"{TASK_GENERATOR_URL}/generate/hashtag", json=data)
    result = resp.json()
    
    # Save to library if successful
    if result.get("status") == "success" and result.get("task"):
        task_data = result["task"]
        section = data.get("section", "live_coding")
        
        # Get section ID
        sections_resp = await client.get(f"{LIBRARY_URL}/sections")
        sections = sections_resp.json()
        section_map = {
            "live_coding": "Live Coding",
            "hard_skills": "Hard Skills",
            "soft_skills": "Soft Skills",
            "logic": "Логика"
        }
        section_name = section_map.get(section)
        section_obj = next((s for s in sections if s["name"] == section_name), None)
        
        if section_obj:
            # Find or create folder based on hashtags
            hashtags = task_data.get("hashtags", [])
            folder_name = f"#{hashtags[0]}" if hashtags else task_data.get("title", "Generated")
            
            # Search for existing folder
            try:
                rag_resp = await client.post(f"{RAG_URL}/search", json={
                    "query": folder_name,
                    "section_type": section,
                    "top_k": 1
                })
                rag_result = rag_resp.json()
                
                if rag_result.get("results") and rag_result["results"][0]["score"] > 0.7:
                    folder_id = rag_result["results"][0]["folder_id"]
                else:
                    # Create new folder
                    folder_resp = await client.post(f"{LIBRARY_URL}/folders", json={
                        "section_id": section_obj["id"],
                        "name": folder_name,
                        "description": f"Задачи с хэштегами: {', '.join(['#' + h for h in hashtags])}"
                    })
                    folder_id = folder_resp.json().get("id")
            except:
                folder_id = None
            
            # Save task
            if folder_id:
                task_resp = await client.post(f"{LIBRARY_URL}/tasks", json={
                    "folder_id": folder_id,
                    "title": task_data.get("title", ""),
                    "description": task_data.get("description", ""),
                    "difficulty": data.get("level", "middle"),
                    "tags": hashtags,
                    "content": {
                        "test_cases": task_data.get("test_cases", []),
                        "hidden_tests": task_data.get("hidden_tests", []),
                        "hints": task_data.get("hints", []),
                        "constraints": task_data.get("constraints"),
                        "examples": task_data.get("examples", [])
                    }
                })
                result["task_id"] = task_resp.json().get("id")
                result["folder_id"] = folder_id
                
                # Index task for hashtag search
                try:
                    await client.post(f"{HASHTAG_URL}/tasks/index", json={
                        "id": str(result["task_id"]),
                        "title": task_data.get("title", ""),
                        "hashtags": hashtags,
                        "level": data.get("level", "middle"),
                        "section": section
                    })
                except:
                    pass
    
    return result


# ============== Hashtag Routes ==============

@app.get("/api/hashtags")
async def list_hashtags(section: str = None):
    """List all hashtags"""
    params = {"section": section} if section else {}
    resp = await client.get(f"{HASHTAG_URL}/hashtags", params=params)
    return resp.json()


@app.post("/api/hashtags/search")
async def search_hashtags(request: Request):
    """Search hashtags by semantic similarity"""
    data = await request.json()
    resp = await client.post(f"{HASHTAG_URL}/hashtags/search", json=data)
    return resp.json()


@app.get("/api/hashtags/stats")
async def hashtag_stats():
    """Get hashtag statistics"""
    resp = await client.get(f"{HASHTAG_URL}/stats")
    return resp.json()


@app.get("/api/hashtags/tasks/{hashtag_id}")
async def get_hashtag_tasks(hashtag_id: str):
    """Get tasks with specific hashtag"""
    try:
        resp = await client.post(f"{HASHTAG_URL}/tasks/search", json={
            "hashtags": [hashtag_id],
            "limit_per_hashtag": 10
        })
        data = resp.json()
        # Flatten tasks from hashtag grouping
        tasks = data.get("tasks_by_hashtag", {}).get(hashtag_id, [])
        return {"tasks": tasks}
    except Exception as e:
        return {"tasks": [], "error": str(e)}


@app.get("/api/hashtags/{hashtag_id}")
async def get_hashtag_details(hashtag_id: str):
    """Get hashtag details with related hashtags"""
    resp = await client.get(f"{HASHTAG_URL}/hashtags/{hashtag_id}")
    return resp.json()


# ============== Code Runner Routes ==============

@app.post("/api/code/run")
async def run_code(request: Request):
    """Run code with input"""
    data = await request.json()
    try:
        resp = await client.post(f"{CODE_RUNNER_URL}/run", json=data, timeout=30.0)
        return resp.json()
    except Exception as e:
        # Fallback: run code locally using subprocess
        import subprocess
        import tempfile
        import os
        
        code = data.get("code", "")
        input_data = data.get("input", "")
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(code)
                temp_file = f.name
            
            result = subprocess.run(
                ['python', temp_file],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            os.unlink(temp_file)
            
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "fallback": True
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "Timeout: код выполнялся слишком долго", "exit_code": -1}
        except Exception as ex:
            return {"stdout": "", "stderr": f"Ошибка выполнения: {str(ex)}", "exit_code": -1}


def normalize_code_for_comparison(code: str) -> str:
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
    norm1 = normalize_code_for_comparison(code1)
    norm2 = normalize_code_for_comparison(code2)
    
    if norm1 == norm2:
        return True
    
    if not norm1 or not norm2:
        return False
    
    # Check if one is substring of another
    shorter = norm1 if len(norm1) < len(norm2) else norm2
    longer = norm1 if len(norm1) >= len(norm2) else norm2
    
    if shorter in longer:
        return True
    
    # Character-level similarity
    common = sum(1 for c in shorter if c in longer)
    similarity = common / max(len(shorter), 1)
    
    return similarity >= threshold


@app.post("/api/code/validate")
async def validate_code(request: Request):
    """Validate code against test cases"""
    data = await request.json()
    try:
        resp = await client.post(f"{CODE_RUNNER_URL}/validate", json=data, timeout=60.0)
        return resp.json()
    except Exception as e:
        # Fallback: validate locally
        import subprocess
        import tempfile
        import os
        import time as time_module
        
        code = data.get("code", "")
        test_cases = data.get("test_cases", [])
        original_code = data.get("original_code")
        task_type = data.get("task_type")
        
        # Check for unchanged code in optimization tasks
        if original_code and task_type == "optimize":
            if codes_are_similar(code, original_code):
                return {
                    "all_passed": False,
                    "passed": 0,
                    "failed": len(test_cases),
                    "total_points": sum(tc.get("points", 10) for tc in test_cases),
                    "earned_points": 0,
                    "score_percent": 0,
                    "tests": [],
                    "error": "unchanged_code",
                    "message": "Вы сдали исходный неоптимизированный код. Для получения баллов необходимо оптимизировать алгоритм.",
                    "fallback": True
                }
        
        results = []
        passed = 0
        total_points = 0
        earned_points = 0
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(code)
                temp_file = f.name
            
            for i, tc in enumerate(test_cases[:10]):  # Limit to 10 tests
                tc_input = tc.get("input", "")
                tc_expected = tc.get("output", tc.get("expected", "")).strip()
                time_limit_ms = tc.get("time_limit_ms", 5000)  # Default 5 seconds
                points = tc.get("points", 10)
                total_points += points
                
                # Skip invalid test cases (placeholder data)
                if not tc_input or tc_input.strip() in ["...", "placeholder", ""]:
                    print(f"[TEST] Skipping test {i+1}: invalid input data")
                    results.append({
                        "num": i + 1,
                        "passed": False,
                        "input": tc_input[:100] if tc_input else "(empty)",
                        "expected": tc_expected[:100] if tc_expected else "(empty)",
                        "actual": "",
                        "error": "Invalid test data - skipped",
                        "points": points,
                        "earned_points": 0,
                        "failure_reason": "invalid_test"
                    })
                    continue
                
                # Convert ms to seconds for subprocess timeout
                timeout_seconds = max(1, time_limit_ms / 1000)
                
                try:
                    start_time = time_module.time()
                    result = subprocess.run(
                        ['python', temp_file],
                        input=tc_input,
                        capture_output=True,
                        text=True,
                        timeout=timeout_seconds
                    )
                    execution_time = time_module.time() - start_time
                    execution_time_ms = execution_time * 1000
                    
                    actual = result.stdout.strip()
                    
                    # Check for runtime errors
                    if result.returncode != 0 or result.stderr:
                        error_msg = result.stderr[:200] if result.stderr else f"Exit code: {result.returncode}"
                        print(f"[TEST] Test {i+1} runtime error: {error_msg}")
                        results.append({
                            "num": i + 1,
                            "passed": False,
                            "input": tc_input[:100],
                            "expected": tc_expected[:100],
                            "actual": actual[:100] if actual else "",
                            "error": error_msg,
                            "execution_time_ms": round(execution_time_ms, 2),
                            "time_limit_ms": time_limit_ms,
                            "points": points,
                            "earned_points": 0,
                            "failure_reason": "runtime_error"
                        })
                        continue
                    
                    output_correct = actual == tc_expected
                    time_exceeded = execution_time_ms > time_limit_ms
                    is_passed = output_correct and not time_exceeded
                    
                    if is_passed:
                        passed += 1
                        earned_points += points
                    
                    failure_reason = None
                    if not output_correct:
                        failure_reason = "wrong_answer"
                    elif time_exceeded:
                        failure_reason = "time_limit_exceeded"
                    
                    results.append({
                        "num": i + 1,
                        "passed": is_passed,
                        "input": tc_input[:100],
                        "expected": tc_expected[:100],
                        "actual": actual[:100],
                        "error": None,
                        "execution_time_ms": round(execution_time_ms, 2),
                        "time_limit_ms": time_limit_ms,
                        "time_exceeded": time_exceeded,
                        "points": points,
                        "earned_points": points if is_passed else 0,
                        "failure_reason": failure_reason
                    })
                except subprocess.TimeoutExpired:
                    results.append({
                        "num": i + 1, 
                        "passed": False, 
                        "input": tc_input[:100],
                        "expected": tc_expected[:100],
                        "actual": "",
                        "error": "Timeout - превышен лимит времени",
                        "time_limit_ms": time_limit_ms,
                        "time_exceeded": True,
                        "points": points,
                        "earned_points": 0,
                        "failure_reason": "time_limit_exceeded"
                    })
                except Exception as ex:
                    print(f"[TEST] Test {i+1} exception: {ex}")
                    results.append({
                        "num": i + 1, 
                        "passed": False, 
                        "input": tc_input[:100],
                        "expected": tc_expected[:100],
                        "actual": "",
                        "error": str(ex),
                        "points": points,
                        "earned_points": 0,
                        "failure_reason": "runtime_error"
                    })
            
            os.unlink(temp_file)
            
            return {
                "all_passed": passed == len(test_cases),
                "passed": passed,
                "failed": len(test_cases) - passed,
                "total_points": total_points,
                "earned_points": earned_points,
                "score_percent": round(earned_points / total_points * 100, 1) if total_points > 0 else 0,
                "tests": results,
                "fallback": True
            }
        except Exception as ex:
            return {"all_passed": False, "passed": 0, "failed": len(test_cases), "error": str(ex)}


# ============== RAG Routes ==============

@app.post("/api/rag/search")
async def rag_search(request: Request):
    """Search for similar folders"""
    data = await request.json()
    resp = await client.post(f"{RAG_URL}/search", json=data)
    return resp.json()


@app.post("/api/rag/index")
async def rag_index(request: Request):
    """Index folders for search"""
    data = await request.json()
    resp = await client.post(f"{RAG_URL}/index", json=data)
    return resp.json()


# ============== Scenario Routes ==============

@app.post("/api/generate/scenario")
async def generate_scenario(request: Request):
    """
    Generate dynamic scenario using AI tools.
    
    This is the most flexible generation method. The AI:
    1. Analyzes the query to decide the best way to test the candidate
    2. Uses tools to build the scenario step by step
    3. Creates multi-step, interactive tasks
    
    Request body:
    - query: What to test (e.g., "binary search", "ООП")
    - difficulty: easy/medium/hard
    - language: Programming language (default: python)
    - scenario_type: Optional - let AI decide if not specified
      Available: fix_code, complete, debug_output, refactor,
                 multi_step, code_review, explain, optimize,
                 write_tests, implement
    
    Returns scenario with steps that can be:
    - show_code: Display code to user
    - show_text: Display instructions
    - ask_fix: Ask user to fix code
    - ask_complete: Ask user to complete code
    - run_tests: Run tests on user's solution
    - etc.
    """
    data = await request.json()
    try:
        resp = await client.post(f"{TASK_GENERATOR_URL}/generate/scenario", json=data, timeout=120.0)
        return resp.json()
    except Exception as e:
        print(f"[SCENARIO] Error connecting to task_generator: {e}")
        return {"error": f"Task Generator service unavailable: {str(e)}", "id": None}


@app.get("/api/scenario-types")
async def list_scenario_types():
    """List all available scenario types with descriptions"""
    try:
        resp = await client.get(f"{TASK_GENERATOR_URL}/scenario-types")
        return resp.json()
    except Exception as e:
        # Return default types if service unavailable
        return {
            "scenario_types": [
                {"id": "fix_code", "name": "Исправление багов", "description": "Показывается код с багами, нужно найти и исправить"},
                {"id": "complete", "name": "Дополнение кода", "description": "Показывается частичный код с TODO, нужно дописать реализацию"},
                {"id": "debug_output", "name": "Отладка по выводу", "description": "Показывается код и неправильный вывод, нужно найти баг"},
                {"id": "refactor", "name": "Рефакторинг", "description": "Показывается рабочий но плохой код, нужно улучшить"},
                {"id": "multi_step", "name": "Многошаговая задача", "description": "Последовательные этапы: базовое решение → edge cases → оптимизация"},
                {"id": "code_review", "name": "Код-ревью", "description": "Провести ревью кода, найти проблемы и предложить улучшения"},
                {"id": "explain", "name": "Объяснение кода", "description": "Объяснить что делает данный код"},
                {"id": "optimize", "name": "Оптимизация", "description": "Улучшить производительность кода"},
                {"id": "write_tests", "name": "Написание тестов", "description": "Написать тесты для данного кода"},
                {"id": "implement", "name": "Реализация с нуля", "description": "Классическая задача - написать код с нуля"}
            ],
            "error": f"Service unavailable, showing defaults: {str(e)}"
        }


# ============== Templates Routes ==============

@app.get("/api/templates")
async def list_templates():
    """List all task templates"""
    resp = await client.get(f"{TASK_GENERATOR_URL}/templates")
    return resp.json()


@app.get("/api/templates/{section_type}")
async def get_section_templates(section_type: str):
    """Get templates for section"""
    resp = await client.get(f"{TASK_GENERATOR_URL}/templates/{section_type}")
    return resp.json()


# ============== Knowledge Routes ==============

@app.get("/api/concepts")
async def list_concepts(category: str = None):
    """List all concepts in knowledge graph"""
    params = {"category": category} if category else {}
    resp = await client.get(f"{KNOWLEDGE_URL}/concepts", params=params)
    return resp.json()


@app.get("/api/concepts/{concept_id}")
async def get_concept(concept_id: str):
    """Get concept details"""
    resp = await client.get(f"{KNOWLEDGE_URL}/concepts/{concept_id}")
    return resp.json()


@app.post("/api/concepts/analyze")
async def analyze_query(request: Request):
    """Analyze query to find/discover concepts"""
    data = await request.json()
    resp = await client.post(
        f"{KNOWLEDGE_URL}/analyze",
        params={"query": data.get("query", ""), "auto_learn": data.get("auto_learn", True)}
    )
    return resp.json()


@app.get("/api/learning-path/{concept_id}")
async def get_learning_path(concept_id: str, known: str = ""):
    """Get learning path to concept"""
    resp = await client.get(f"{KNOWLEDGE_URL}/learning-path/{concept_id}", params={"known": known})
    return resp.json()


@app.get("/api/suggest")
async def suggest_next(known: str = "", target_difficulty: float = 0.5):
    """Suggest next concept to learn"""
    resp = await client.get(f"{KNOWLEDGE_URL}/suggest", params={"known": known, "target_difficulty": target_difficulty})
    return resp.json()


# ============== Learning Routes ==============

@app.get("/api/users/{user_id}")
async def get_user_profile(user_id: str):
    """Get user learning profile"""
    resp = await client.get(f"{LEARNING_URL}/users/{user_id}")
    return resp.json()


@app.get("/api/users/{user_id}/progress")
async def get_user_progress(user_id: str):
    """Get user progress on all concepts"""
    resp = await client.get(f"{LEARNING_URL}/users/{user_id}/progress")
    return resp.json()


@app.post("/api/attempt")
async def record_attempt(request: Request):
    """Record a task attempt"""
    data = await request.json()
    resp = await client.post(f"{LEARNING_URL}/attempt", json=data)
    return resp.json()


@app.get("/api/recommendations/{user_id}")
async def get_recommendations(user_id: str):
    """Get personalized learning recommendations"""
    # Get concepts from knowledge service
    concepts_resp = await client.get(f"{KNOWLEDGE_URL}/concepts")
    concepts = {c["id"]: c for c in concepts_resp.json()}
    
    resp = await client.post(f"{LEARNING_URL}/recommendations/{user_id}", json=concepts)
    return resp.json()


@app.get("/api/review-queue/{user_id}")
async def get_review_queue(user_id: str):
    """Get concepts due for review"""
    resp = await client.get(f"{LEARNING_URL}/review-queue/{user_id}")
    return resp.json()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
