# Interview Service - HR Bot

Сервис для проведения автоматизированных технических собеседований с AI.

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    Interview Service                         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Schema    │  │  Interview  │  │      AI Judge       │  │
│  │   Parser    │  │   Engine    │  │                     │  │
│  │             │  │             │  │  - Evaluate answers │  │
│  │ React Flow  │  │ - Questions │  │  - Score responses  │  │
│  │   → Steps   │  │ - Live Code │  │  - Recommendations  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │                  │                    │
         ▼                  ▼                    ▼
    ┌─────────┐      ┌─────────────┐      ┌───────────┐
    │ Gateway │      │Task Generator│      │Code Runner│
    └─────────┘      └─────────────┘      └───────────┘
```

## Формат входных данных

Схема собеседования приходит в формате React Flow:

```json
{
  "nodes": [
    {
      "id": "node-xxx",
      "type": "custom",
      "data": {
        "label": "Название этапа",
        "nodeType": "skill-check",
        "description": "Описание",
        "points": 5,
        "importance": "high",
        "groupName": "Hard Skills"
      }
    }
  ],
  "edges": [
    {
      "source": "node-1",
      "target": "node-2"
    }
  ]
}
```

### Типы узлов (nodeType)

| Тип | Описание |
|-----|----------|
| `start` | Начало интервью |
| `end` | Конец интервью |
| `greeting` | Приветствие |
| `question` | Общий вопрос |
| `section` | Секция/раздел |
| `skill-group` | Группа навыков (Hard Skills, Live Coding) |
| `skill-check` | Проверка конкретного навыка |

### Важность (importance)

- `high` - Критически важный навык, строгая оценка
- `medium` - Стандартная важность
- `low` - Желательный, но не обязательный навык

## API Endpoints

### Начать собеседование
```
POST /interview/start
{
  "nodes": [...],
  "edges": [...],
  "candidate_name": "Иван"
}
```

### Отправить сообщение
```
POST /interview/message
{
  "session_id": "uuid",
  "message": "Ответ кандидата"
}
```

### Отправить код (Live Coding)
```
POST /interview/code
{
  "session_id": "uuid",
  "code": "def solution(): ...",
  "language": "python"
}
```

### Получить статус
```
GET /interview/{session_id}/status
```

### Пропустить этап
```
POST /interview/{session_id}/skip
```

### Завершить досрочно
```
POST /interview/{session_id}/end
```

## Логика Live Coding

### Адаптивная сложность

1. **Начальный уровень**: junior
2. **При успехе**: уровень повышается (junior → middle → senior)
3. **При неудаче**: уровень понижается

```
junior  ──успех──▶  middle  ──успех──▶  senior
   ▲                   │                   │
   └───неудача─────────┴───────неудача─────┘
```

### Генерация задач

Для каждого skill-check в группе "Live Coding":
1. Берётся описание из схемы
2. Генерируется задача соответствующего уровня
3. Код проверяется через code_runner
4. AI Judge оценивает качество кода

## AI Judge

### Оценка текстовых ответов

```python
{
    "points": 4,           # Набранные баллы
    "max_points": 5,       # Максимум
    "feedback": "...",     # Отзыв для кандидата
    "strengths": [...],    # Сильные стороны
    "weaknesses": [...],   # Слабые стороны
    "step_complete": true  # Можно переходить дальше
}
```

### Оценка кода

- 70% - корректность (прохождение тестов)
- 30% - качество кода (читаемость, эффективность)

## Итоговый результат

```json
{
    "total_score": 45,
    "max_score": 50,
    "score_percent": 90.0,
    "passed": true,
    "sections": [
        {
            "name": "Hard Skills",
            "earned": 20,
            "max": 25,
            "steps": [...]
        }
    ],
    "main_errors": ["Ошибка 1", "Ошибка 2"],
    "recommendations": ["Рекомендация 1"],
    "duration_minutes": 35
}
```

## Запуск

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск
uvicorn main:app --host 0.0.0.0 --port 8011

# Или через Docker
docker build -t interview-service .
docker run -p 8011:8011 interview-service
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `LLM_API_KEY` | API ключ LLM | - |
| `LLM_BASE_URL` | URL LLM API | https://llm.t1v.scibox.tech/v1 |
| `LLM_CHAT_MODEL` | Модель для чата | qwen3-32b-awq |
| `LLM_CODE_MODEL` | Модель для кода | qwen3-coder-30b-a3b-instruct-fp8 |
| `TASK_GENERATOR_URL` | URL генератора задач | http://localhost:8002 |
| `CODE_RUNNER_URL` | URL исполнителя кода | http://localhost:8003 |
