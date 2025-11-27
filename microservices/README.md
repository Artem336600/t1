# Interview Prep Microservices

Микросервисная архитектура для платформы подготовки к собеседованиям.

## Архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                         API Gateway (:8000)                          │
│                    Точка входа, маршрутизация                        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Library Service │     │ Task Generator  │     │   RAG Service   │
│    (:8001)      │     │    (:8002)      │     │    (:8004)      │
│                 │     │                 │     │                 │
│ • Sections      │     │ • Task Designer │     │ • Embeddings    │
│ • Folders       │     │ • Code Writer   │     │ • Vector Search │
│ • Tasks CRUD    │     │ • Validator     │     │ • Similarity    │
│ • SQLite DB     │     │ • Fixer         │     │                 │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 ▼
                      ┌─────────────────┐
                      │  Code Runner    │
                      │    (:8003)      │
                      │                 │
                      │ • Execute code  │
                      │ • Validate tests│
                      │ • Sandbox       │
                      └─────────────────┘
```

## Сервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| **Gateway** | 8000 | API Gateway, маршрутизация запросов |
| **Library** | 8001 | CRUD для секций, папок, задач |
| **Task Generator** | 8002 | Мультиагентная генерация задач |
| **Code Runner** | 8003 | Выполнение и валидация кода |
| **RAG** | 8004 | Векторный поиск по папкам |

## Быстрый старт

### Локальный запуск (для разработки)

```bash
cd microservices
python run_local.py
```

### Docker Compose

```bash
cd microservices

# Создать .env файл
cp .env.example .env
# Отредактировать .env, добавить LLM_API_KEY

# Запустить все сервисы
docker-compose up -d

# Проверить статус
docker-compose ps

# Логи
docker-compose logs -f
```

## API Endpoints

### Gateway (http://localhost:8000)

#### Health Check
```bash
GET /health
```

#### Sections & Folders
```bash
GET  /api/sections              # Все секции с папками
GET  /api/sections/{id}         # Секция по ID
GET  /api/folders/{id}          # Папка с задачами
POST /api/folders               # Создать папку
DELETE /api/folders/{id}        # Удалить папку
```

#### Tasks
```bash
GET    /api/tasks/{id}          # Задача по ID
POST   /api/tasks               # Создать задачу
PUT    /api/tasks/{id}          # Обновить задачу
DELETE /api/tasks/{id}          # Удалить задачу
POST   /api/tasks/{id}/toggle   # Переключить статус
```

#### AI Generation
```bash
POST /api/generate
{
  "query": "Найти максимальную сумму подмассива",
  "difficulty": "medium",
  "section_type": "live_coding"
}
```

#### Code Execution
```bash
POST /api/code/run
{
  "code": "print(sum(map(int, input().split())))",
  "input": "1 2 3 4 5"
}

POST /api/code/validate
{
  "code": "...",
  "test_cases": [{"input": "...", "output": "..."}]
}
```

#### RAG Search
```bash
POST /api/rag/search
{
  "query": "бинарный поиск",
  "section_type": "live_coding",
  "top_k": 5
}
```

## Переменные окружения

```env
# LLM API
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://llm.t1v.scibox.tech/v1

# Service URLs (для Docker)
LIBRARY_SERVICE_URL=http://library:8001
TASK_GENERATOR_URL=http://task-generator:8002
CODE_RUNNER_URL=http://code-runner:8003
RAG_SERVICE_URL=http://rag:8004
```

## Примеры использования

### Python Client

```python
import httpx

BASE_URL = "http://localhost:8000"

# Генерация задачи
response = httpx.post(f"{BASE_URL}/api/generate", json={
    "query": "Two Sum - найти два числа с заданной суммой",
    "difficulty": "easy",
    "section_type": "live_coding"
}, timeout=120)

result = response.json()
print(f"Task: {result['task']['title']}")
print(f"Solution: {result['solution'][:200]}...")
print(f"Validation: {result['validation']['passed']}/{result['validation']['passed'] + result['validation']['failed']}")
```

### cURL

```bash
# Генерация задачи
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"query": "Binary Search", "difficulty": "easy", "section_type": "live_coding"}'

# Запуск кода
curl -X POST http://localhost:8000/api/code/run \
  -H "Content-Type: application/json" \
  -d '{"code": "print(int(input()) * 2)", "input": "21"}'
```

## Разработка

### Структура проекта

```
microservices/
├── docker-compose.yml      # Оркестрация контейнеров
├── .env.example            # Пример переменных окружения
├── run_local.py            # Скрипт локального запуска
├── README.md
│
├── gateway/                # API Gateway
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── library_service/        # Library Service
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── task_generator/         # Task Generator
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── code_runner/            # Code Runner
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── rag_service/            # RAG Service
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
│
└── shared/                 # Shared models
    ├── __init__.py
    └── models.py
```

### Добавление нового сервиса

1. Создать директорию `microservices/new_service/`
2. Добавить `main.py`, `Dockerfile`, `requirements.txt`
3. Добавить сервис в `docker-compose.yml`
4. Добавить маршруты в `gateway/main.py`

## Лицензия

MIT
