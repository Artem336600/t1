"""
RAG Service
Vector embeddings and semantic search for folders
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
from openai import OpenAI
import numpy as np
import json
import os

app = FastAPI(
    title="RAG Service",
    description="Embeddings and semantic search",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config - use centralized LLM config
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

try:
    from llm_config import Models, get_client, API_KEY, BASE_URL
except ImportError:
    API_KEY = os.getenv("LLM_API_KEY", "sk-SSWP5NVJpHecmOFI_yxp7Q")
    BASE_URL = os.getenv("LLM_BASE_URL", "https://llm.t1v.scibox.tech/v1")
    class Models:
        CHAT = "qwen3-32b-awq"
        CODE = "qwen3-coder-30b-a3b-instruct-fp8"
        EMBEDDING = "bge-m3"
    def get_client(api_key=None, base_url=None):
        return OpenAI(api_key=api_key or API_KEY, base_url=base_url or BASE_URL)

DATA_FILE = "data/embeddings.json"

client = get_client()

# In-memory index
folder_index: Dict[int, Dict] = {}


class EmbeddingRequest(BaseModel):
    texts: List[str]


class IndexRequest(BaseModel):
    folders: List[Dict]  # [{id, name, description, section_type}]


class SearchRequest(BaseModel):
    query: str
    section_type: Optional[str] = None
    top_k: int = 5


class SearchResult(BaseModel):
    folder_id: int
    folder_name: str
    description: str
    score: float
    section_type: str


@app.get("/health")
async def health():
    return {"status": "ok", "service": "rag", "indexed_folders": len(folder_index)}


@app.on_event("startup")
async def startup():
    """Load saved embeddings"""
    global folder_index
    os.makedirs("data", exist_ok=True)
    
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                folder_index = {int(k): v for k, v in json.load(f).items()}
            print(f"Loaded {len(folder_index)} folder embeddings")
        except Exception as e:
            print(f"Failed to load embeddings: {e}")


def save_index():
    """Save embeddings to file"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(folder_index, f, ensure_ascii=False)


@app.post("/embed")
async def get_embeddings(req: EmbeddingRequest):
    """Get embeddings for texts"""
    try:
        response = client.embeddings.create(
            model=Models.EMBEDDING,
            input=req.texts
        )
        embeddings = [item.embedding for item in response.data]
        return {"embeddings": embeddings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/index")
async def index_folders(req: IndexRequest):
    """Index folders for search"""
    global folder_index
    
    indexed = 0
    for folder in req.folders:
        folder_id = folder.get("id")
        if not folder_id:
            continue
        
        # Create text for embedding
        text = f"{folder.get('name', '')} {folder.get('description', '')}"
        
        try:
            response = client.embeddings.create(
                model=Models.EMBEDDING,
                input=[text]
            )
            embedding = response.data[0].embedding
            
            folder_index[folder_id] = {
                "id": folder_id,
                "name": folder.get("name", ""),
                "description": folder.get("description", ""),
                "section_type": folder.get("section_type", ""),
                "embedding": embedding
            }
            indexed += 1
        except Exception as e:
            print(f"Failed to index folder {folder_id}: {e}")
    
    save_index()
    return {"indexed": indexed, "total": len(folder_index)}


@app.post("/search")
async def search_folders(req: SearchRequest):
    """Search for similar folders"""
    if not folder_index:
        return {"results": []}
    
    # Get query embedding
    try:
        response = client.embeddings.create(
            model=Models.EMBEDDING,
            input=[req.query]
        )
        query_embedding = np.array(response.data[0].embedding)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding error: {e}")
    
    # Calculate similarities
    results = []
    for folder_id, folder_data in folder_index.items():
        # Filter by section type if specified
        if req.section_type and folder_data.get("section_type") != req.section_type:
            continue
        
        folder_embedding = np.array(folder_data["embedding"])
        
        # Cosine similarity
        similarity = np.dot(query_embedding, folder_embedding) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(folder_embedding)
        )
        
        results.append({
            "folder_id": folder_id,
            "folder_name": folder_data["name"],
            "description": folder_data["description"],
            "section_type": folder_data.get("section_type", ""),
            "score": float(similarity)
        })
    
    # Sort by score and return top_k
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"results": results[:req.top_k]}


@app.delete("/index/{folder_id}")
async def remove_from_index(folder_id: int):
    """Remove folder from index"""
    if folder_id in folder_index:
        del folder_index[folder_id]
        save_index()
        return {"success": True}
    return {"success": False, "error": "Folder not found"}


@app.delete("/index")
async def clear_index():
    """Clear all embeddings"""
    global folder_index
    folder_index = {}
    save_index()
    return {"success": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
