"""
Library Service
Manages sections, folders, and tasks (CRUD operations)
"""
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
import os

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/library.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ============== Database Models ==============

class SectionDB(Base):
    __tablename__ = "sections"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    icon = Column(String(50), default="folder")
    color = Column(String(20), default="purple")
    order = Column(Integer, default=0)
    
    folders = relationship("FolderDB", back_populates="section", cascade="all, delete-orphan")


class FolderDB(Base):
    __tablename__ = "folders"
    
    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    icon = Column(String(50), default="folder")
    order = Column(Integer, default=0)
    
    section = relationship("SectionDB", back_populates="folders")
    tasks = relationship("TaskDB", back_populates="folder", cascade="all, delete-orphan")


class TaskDB(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    difficulty = Column(String(20), default="medium")
    tags = Column(JSON, default=list)
    content = Column(JSON, default=dict)
    is_completed = Column(Boolean, default=False)
    notes = Column(Text)
    my_answer = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    # Multi-file task support
    task_type = Column(String(50), default="single_file")  # single_file, fix_bug, complete, refactor, multi_file
    files = Column(JSON, default=list)  # List of {filename, path, content, role, editable}
    entry_point = Column(String(100), default="main.py")
    solution_files = Column(JSON, default=list)  # Correct solution files
    objectives = Column(JSON, default=list)  # List of objectives for multi-file tasks
    unit_tests = Column(JSON, default=list)  # Unit tests
    user_files = Column(JSON, default=list)  # User's current file versions
    
    folder = relationship("FolderDB", back_populates="tasks")


# Create tables
os.makedirs("data", exist_ok=True)
Base.metadata.create_all(bind=engine)


# Migrate existing database - add new columns if they don't exist
def migrate_database():
    """Add new columns to existing database"""
    from sqlalchemy import text, inspect
    
    inspector = inspect(engine)
    existing_columns = [col['name'] for col in inspector.get_columns('tasks')]
    
    new_columns = [
        ("task_type", "VARCHAR(50) DEFAULT 'single_file'"),
        ("files", "JSON DEFAULT '[]'"),
        ("entry_point", "VARCHAR(100) DEFAULT 'main.py'"),
        ("solution_files", "JSON DEFAULT '[]'"),
        ("objectives", "JSON DEFAULT '[]'"),
        ("unit_tests", "JSON DEFAULT '[]'"),
        ("user_files", "JSON DEFAULT '[]'"),
    ]
    
    with engine.connect() as conn:
        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                try:
                    conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    print(f"Added column: {col_name}")
                except Exception as e:
                    print(f"Column {col_name} might already exist: {e}")

try:
    migrate_database()
except Exception as e:
    print(f"Migration error (may be ok on first run): {e}")


# ============== Pydantic Models ==============

class FolderCreate(BaseModel):
    section_id: int
    name: str
    description: str = ""
    icon: str = "folder"


class TaskCreate(BaseModel):
    folder_id: int
    title: str
    description: str = ""
    difficulty: str = "medium"
    tags: List[str] = []
    content: dict = {}
    
    # Multi-file task fields
    task_type: str = "single_file"
    files: List[dict] = []
    entry_point: str = "main.py"
    solution_files: List[dict] = []
    objectives: List[str] = []
    unit_tests: List[dict] = []


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    difficulty: Optional[str] = None
    tags: Optional[List[str]] = None
    content: Optional[dict] = None
    is_completed: Optional[bool] = None
    notes: Optional[str] = None
    my_answer: Optional[str] = None
    
    # Multi-file task fields
    task_type: Optional[str] = None
    files: Optional[List[dict]] = None
    entry_point: Optional[str] = None
    solution_files: Optional[List[dict]] = None
    objectives: Optional[List[str]] = None
    unit_tests: Optional[List[dict]] = None
    user_files: Optional[List[dict]] = None


# ============== FastAPI App ==============

app = FastAPI(
    title="Library Service",
    description="Manages sections, folders, and tasks",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_default_data(db: Session):
    """Initialize default sections if empty"""
    if db.query(SectionDB).count() > 0:
        return
    
    sections = [
        {"name": "Live Coding", "description": "Алгоритмические задачи", "icon": "code", "color": "purple", "order": 1},
        {"name": "Hard Skills", "description": "Технические знания", "icon": "cog", "color": "blue", "order": 2},
        {"name": "Soft Skills", "description": "Поведенческие вопросы", "icon": "users", "color": "green", "order": 3},
        {"name": "Логика", "description": "Логические задачи", "icon": "brain", "color": "orange", "order": 4},
    ]
    
    for s in sections:
        db.add(SectionDB(**s))
    db.commit()


@app.on_event("startup")
async def startup():
    db = SessionLocal()
    init_default_data(db)
    db.close()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "library"}


# ============== Sections ==============

@app.get("/sections")
async def get_sections(db: Session = Depends(get_db)):
    sections = db.query(SectionDB).order_by(SectionDB.order).all()
    result = []
    for s in sections:
        folders = [{"id": f.id, "name": f.name, "description": f.description, "icon": f.icon, 
                   "task_count": len(f.tasks)} for f in s.folders]
        result.append({
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "icon": s.icon,
            "color": s.color,
            "order": s.order,
            "folders": folders,
            "folder_count": len(folders),
            "task_count": sum(len(f.tasks) for f in s.folders)
        })
    return result


@app.get("/sections/{section_id}")
async def get_section(section_id: int, db: Session = Depends(get_db)):
    section = db.query(SectionDB).filter(SectionDB.id == section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return {
        "id": section.id,
        "name": section.name,
        "description": section.description,
        "icon": section.icon,
        "color": section.color,
        "folders": [{"id": f.id, "name": f.name, "description": f.description} for f in section.folders]
    }


# ============== Folders ==============

@app.get("/folders/{folder_id}")
async def get_folder(folder_id: int, db: Session = Depends(get_db)):
    folder = db.query(FolderDB).filter(FolderDB.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {
        "id": folder.id,
        "section_id": folder.section_id,
        "name": folder.name,
        "description": folder.description,
        "icon": folder.icon,
        "tasks": [{
            "id": t.id,
            "title": t.title,
            "difficulty": t.difficulty,
            "tags": t.tags,
            "is_completed": t.is_completed
        } for t in folder.tasks]
    }


@app.post("/folders")
async def create_folder(folder: FolderCreate, db: Session = Depends(get_db)):
    db_folder = FolderDB(**folder.dict())
    db.add(db_folder)
    db.commit()
    db.refresh(db_folder)
    return {"id": db_folder.id, "name": db_folder.name}


@app.delete("/folders/{folder_id}")
async def delete_folder(folder_id: int, db: Session = Depends(get_db)):
    folder = db.query(FolderDB).filter(FolderDB.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    db.delete(folder)
    db.commit()
    return {"success": True}


# ============== Tasks ==============

@app.get("/tasks/{task_id}")
async def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    result = {
        "id": task.id,
        "folder_id": task.folder_id,
        "title": task.title,
        "description": task.description,
        "difficulty": task.difficulty,
        "tags": task.tags,
        "content": task.content,
        "is_completed": task.is_completed,
        "notes": task.notes,
        "my_answer": task.my_answer,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "task_type": task.task_type or "single_file"
    }
    
    # Add multi-file fields if present
    if task.task_type and task.task_type != "single_file":
        result.update({
            "files": task.files or [],
            "entry_point": task.entry_point or "main.py",
            "solution_files": task.solution_files or [],
            "objectives": task.objectives or [],
            "unit_tests": task.unit_tests or [],
            "user_files": task.user_files or []
        })
    
    return result


@app.post("/tasks")
async def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    db_task = TaskDB(**task.dict())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return {"id": db_task.id, "title": db_task.title}


@app.put("/tasks/{task_id}")
async def update_task(task_id: int, task: TaskUpdate, db: Session = Depends(get_db)):
    db_task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    for field, value in task.dict(exclude_unset=True).items():
        setattr(db_task, field, value)
    
    db.commit()
    db.refresh(db_task)
    return {"id": db_task.id, "title": db_task.title}


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"success": True}


@app.post("/tasks/{task_id}/toggle")
async def toggle_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.is_completed = not task.is_completed
    db.commit()
    return {"is_completed": task.is_completed}


# ============== Multi-File Task Endpoints ==============

class SaveFilesRequest(BaseModel):
    """Request to save user's file versions"""
    files: List[dict]  # [{filename, path, content}]


@app.post("/tasks/{task_id}/files")
async def save_user_files(task_id: int, req: SaveFilesRequest, db: Session = Depends(get_db)):
    """Save user's current file versions for a multi-file task"""
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.user_files = req.files
    db.commit()
    return {"success": True, "files_saved": len(req.files)}


@app.get("/tasks/{task_id}/files")
async def get_user_files(task_id: int, db: Session = Depends(get_db)):
    """Get user's current file versions or original files if not started"""
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Return user files if they exist, otherwise return original files
    if task.user_files:
        return {"files": task.user_files, "source": "user"}
    elif task.files:
        return {"files": task.files, "source": "original"}
    else:
        return {"files": [], "source": "none"}


@app.post("/tasks/{task_id}/reset")
async def reset_task_files(task_id: int, db: Session = Depends(get_db)):
    """Reset user's files to original state"""
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.user_files = []
    task.is_completed = False
    db.commit()
    return {"success": True, "message": "Task reset to original state"}


@app.get("/tasks/{task_id}/solution")
async def get_task_solution(task_id: int, db: Session = Depends(get_db)):
    """Get solution files for a task (for checking answers)"""
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "solution_files": task.solution_files or [],
        "has_solution": bool(task.solution_files)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
