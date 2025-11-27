# Interview Prep Platform - Frontend

Современный React фронтенд в строгом чёрном бенто стиле.

## Технологии

- **React 18** - UI библиотека
- **Vite** - сборщик
- **Tailwind CSS** - стилизация
- **Zustand** - управление состоянием
- **Lucide React** - иконки
- **Highlight.js** - подсветка кода

## Установка и запуск

```bash
# Установить зависимости
npm install

# Запустить dev сервер
npm run dev
```

Приложение будет доступно на http://localhost:3000

## Структура

```
frontend/
├── src/
│   ├── components/      # UI компоненты
│   │   ├── Header.jsx
│   │   ├── ScenarioSelector.jsx
│   │   ├── GeneratorPanel.jsx
│   │   ├── ScenarioView.jsx
│   │   ├── ScenarioHeader.jsx
│   │   ├── StepCard.jsx
│   │   ├── CodeEditor.jsx
│   │   ├── TestResults.jsx
│   │   ├── HintsPanel.jsx
│   │   └── EmptyState.jsx
│   ├── store/
│   │   └── useStore.js  # Zustand store
│   ├── App.jsx
│   ├── main.jsx
│   └── index.css
├── package.json
├── vite.config.js
├── tailwind.config.js
└── postcss.config.js
```

## API Proxy

Vite настроен на проксирование запросов к бэкенду:
- `/api/*` → `http://localhost:8000`
- `/health` → `http://localhost:8000`

Убедитесь, что gateway сервис запущен на порту 8000.
