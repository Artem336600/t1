"""
Local development runner for all microservices
Starts all services in separate processes
"""
import subprocess
import sys
import os
import time
import signal
from pathlib import Path

BASE_DIR = Path(__file__).parent

SERVICES = [
    # Core services
    {"name": "Library", "dir": "library_service", "port": 8001},
    {"name": "Code Runner", "dir": "code_runner", "port": 8003},
    {"name": "RAG", "dir": "rag_service", "port": 8004},
    {"name": "Knowledge", "dir": "knowledge_service", "port": 8005},
    {"name": "Learning", "dir": "learning_service", "port": 8006},
    {"name": "Hashtag", "dir": "hashtag_service", "port": 8011},
    {"name": "Task Generator", "dir": "task_generator", "port": 8002},
    # Orchestration layer
    {"name": "Task API", "dir": "task_api", "port": 8010},
    # Gateway (use old gateway for now, or new api_gateway)
    {"name": "Gateway", "dir": "gateway", "port": 8000},
    # {"name": "API Gateway", "dir": "api_gateway", "port": 8000},  # New gateway
]

processes = []


def install_deps():
    """Install dependencies for all services"""
    print("Installing dependencies...")
    for service in SERVICES:
        req_file = BASE_DIR / service["dir"] / "requirements.txt"
        if req_file.exists():
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)])
    print("Dependencies installed!\n")


def start_services():
    """Start all services"""
    global processes
    
    for service in SERVICES:
        service_dir = BASE_DIR / service["dir"]
        port = service["port"]
        
        print(f"Starting {service['name']} on port {port}...")
        
        env = os.environ.copy()
        env["LIBRARY_SERVICE_URL"] = "http://localhost:8001"
        env["TASK_GENERATOR_URL"] = "http://localhost:8002"
        env["CODE_RUNNER_URL"] = "http://localhost:8003"
        env["RAG_SERVICE_URL"] = "http://localhost:8004"
        env["KNOWLEDGE_SERVICE_URL"] = "http://localhost:8005"
        env["LEARNING_SERVICE_URL"] = "http://localhost:8006"
        env["HASHTAG_SERVICE_URL"] = "http://localhost:8011"
        env["TASK_API_URL"] = "http://localhost:8010"
        env["SANDBOX_MODE"] = "subprocess"  # Use subprocess for local dev (no Docker)
        
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port), "--reload"],
            cwd=str(service_dir),
            env=env
            # No stdout/stderr redirect - logs go to terminal
        )
        processes.append({"name": service["name"], "proc": proc, "port": port})
        time.sleep(1)
    
    print("\n" + "=" * 60)
    print("All services started!")
    print("=" * 60)
    print("\n📡 Endpoints:")
    print(f"  Gateway:        http://localhost:8000  (entry point)")
    print(f"  Task API:       http://localhost:8010  (orchestration)")
    print(f"  Task Generator: http://localhost:8002  (flexible + hashtag)")
    print(f"  Hashtag:        http://localhost:8011  (taxonomy + RAG)")
    print(f"  Library:        http://localhost:8001")
    print(f"  Code Runner:    http://localhost:8003  (Docker sandbox)")
    print(f"  RAG:            http://localhost:8004  (embeddings)")
    print(f"  Knowledge:      http://localhost:8005  (FAISS vectors)")
    print(f"  Learning:       http://localhost:8006  (SM-2 algorithm)")
    print("\n📚 API Documentation:")
    print(f"  http://localhost:8000/docs")
    print("\n✨ Features (v3.0):")
    print(f"  🏷️  Hashtag taxonomy with RAG search")
    print(f"  🎯 Level-based filtering (junior/middle/senior)")
    print(f"  📝 Example-based task generation")
    print(f"  🆕 Auto-expansion of hashtag taxonomy")
    print(f"  🔒 Docker sandbox for code execution")
    print(f"  📈 SM-2 spaced repetition")
    print("\nPress Ctrl+C to stop all services")
    print("=" * 60 + "\n")


def stop_services():
    """Stop all services"""
    print("\nStopping services...")
    for p in processes:
        try:
            p["proc"].terminate()
            p["proc"].wait(timeout=5)
            print(f"  {p['name']} stopped")
        except:
            p["proc"].kill()
    print("All services stopped.")


def signal_handler(sig, frame):
    stop_services()
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("=" * 60)
    print("Interview Prep Microservices - Local Development")
    print("=" * 60 + "\n")
    
    install_deps()
    start_services()
    
    # Keep running
    try:
        while True:
            time.sleep(1)
            # Check if any process died
            for p in processes:
                if p["proc"].poll() is not None:
                    print(f"\n{p['name']} crashed! Restarting...")
                    # Could add restart logic here
    except KeyboardInterrupt:
        stop_services()


if __name__ == "__main__":
    main()
