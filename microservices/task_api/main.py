"""
Task API Service
Orchestration and aggregation layer for task generation
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import httpx
import os
import time
import asyncio

app = FastAPI(
    title="Task API Service",
    description="Task orchestration and aggregation",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service URLs
TASK_GENERATOR_URL = os.getenv("TASK_GENERATOR_URL", "http://localhost:8002")
LIBRARY_URL = os.getenv("LIBRARY_SERVICE_URL", "http://localhost:8001")
RAG_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8004")
KNOWLEDGE_URL = os.getenv("KNOWLEDGE_SERVICE_URL", "http://localhost:8005")
LEARNING_URL = os.getenv("LEARNING_SERVICE_URL", "http://localhost:8006")

http_client = httpx.AsyncClient(timeout=120.0)


class GenerateRequest(BaseModel):
    query: str
    difficulty: str = "medium"
    section_type: str = "live_coding"
    task_subtype: Optional[str] = None
    language: str = "python"
    user_id: Optional[str] = None
    save_to_library: bool = True


class GenerateResponse(BaseModel):
    status: str
    task: Optional[Dict] = None
    solution: Optional[str] = None
    validation: Optional[Dict] = None
    concepts: List[str] = []
    learning_path: List[str] = []
    folder_id: Optional[int] = None
    folder_name: Optional[str] = None
    execution_time: float = 0


@app.get("/health")
async def health():
    return {"status": "ok", "service": "task-api"}


@app.post("/generate")
async def generate_task(req: GenerateRequest):
    """
    Orchestrate task generation with optional library save.
    
    Flow:
    1. Find matching folder via RAG
    2. Generate task via Task Generator
    3. Save to library if requested
    4. Record attempt for learning
    """
    start_time = time.time()
    
    # 1. Search for matching folder using RAG (parallel with generation)
    rag_task = asyncio.create_task(find_matching_folder(req.query, req.section_type))
    
    # 2. Generate task
    gen_response = await http_client.post(
        f"{TASK_GENERATOR_URL}/generate",
        json={
            "query": req.query,
            "difficulty": req.difficulty,
            "section_type": req.section_type,
            "task_subtype": req.task_subtype,
            "language": req.language,
            "user_id": req.user_id
        }
    )
    
    result = gen_response.json()
    
    # Wait for RAG result
    rag_result = await rag_task
    
    # Add folder info
    if rag_result.get("folder_id"):
        result["folder_id"] = rag_result["folder_id"]
        result["folder_name"] = rag_result["folder_name"]
        result["action"] = "found"
    else:
        result["action"] = "created"
    
    # 3. Save to library if requested and task generated successfully
    if req.save_to_library and result.get("status") == "success" and result.get("task"):
        saved = await save_to_library(result, req.section_type)
        if saved:
            result["saved_task_id"] = saved.get("task_id")
            result["folder_id"] = saved.get("folder_id")
    
    result["total_time"] = round(time.time() - start_time, 2)
    
    return result


async def find_matching_folder(query: str, section_type: str) -> Dict:
    """Find matching folder using RAG service"""
    try:
        resp = await http_client.post(
            f"{RAG_URL}/search",
            json={"query": query, "section_type": section_type, "top_k": 1}
        )
        data = resp.json()
        
        if data.get("results") and data["results"][0].get("score", 0) > 0.45:
            best = data["results"][0]
            return {
                "folder_id": best.get("folder_id"),
                "folder_name": best.get("folder_name"),
                "score": best.get("score")
            }
    except Exception as e:
        print(f"RAG search error: {e}")
    
    return {}


async def save_to_library(result: Dict, section_type: str) -> Optional[Dict]:
    """Save generated task to library"""
    try:
        task = result.get("task", {})
        
        # Get or create folder
        folder_id = result.get("folder_id")
        
        if not folder_id:
            # Get section ID
            sections_resp = await http_client.get(f"{LIBRARY_URL}/sections")
            sections = sections_resp.json()
            
            section_map = {
                "live_coding": "Live Coding",
                "hard_skills": "Hard Skills",
                "soft_skills": "Soft Skills",
                "logic": "Логика"
            }
            
            section_name = section_map.get(section_type, "Live Coding")
            section_id = next(
                (s["id"] for s in sections if s["name"] == section_name),
                1
            )
            
            # Create folder
            folder_name = task.get("title", "Generated Task")[:50]
            folder_resp = await http_client.post(
                f"{LIBRARY_URL}/folders",
                json={"name": folder_name, "section_id": section_id}
            )
            folder_data = folder_resp.json()
            folder_id = folder_data.get("id")
        
        if not folder_id:
            return None
        
        # Create task
        task_resp = await http_client.post(
            f"{LIBRARY_URL}/tasks",
            json={
                "folder_id": folder_id,
                "title": task.get("title", "Task"),
                "description": task.get("description", ""),
                "solution": result.get("solution", ""),
                "test_cases": task.get("test_cases", []),
                "hints": task.get("hints", []),
                "difficulty": result.get("adaptive_difficulty", 0.5)
            }
        )
        
        task_data = task_resp.json()
        
        return {
            "task_id": task_data.get("id"),
            "folder_id": folder_id
        }
        
    except Exception as e:
        print(f"Save to library error: {e}")
        return None


@app.get("/templates")
async def list_templates():
    """Proxy to task generator templates"""
    resp = await http_client.get(f"{TASK_GENERATOR_URL}/templates")
    return resp.json()


@app.get("/templates/{section_type}")
async def get_section_templates(section_type: str):
    """Proxy to task generator templates"""
    resp = await http_client.get(f"{TASK_GENERATOR_URL}/templates/{section_type}")
    return resp.json()


@app.post("/batch-generate")
async def batch_generate(requests: List[GenerateRequest]):
    """Generate multiple tasks in parallel"""
    tasks = []
    for req in requests[:5]:  # Limit to 5 concurrent
        tasks.append(generate_task(req))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return {
        "results": [
            r if not isinstance(r, Exception) else {"error": str(r)}
            for r in results
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
