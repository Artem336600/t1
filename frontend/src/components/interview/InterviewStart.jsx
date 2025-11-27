import { useState } from 'react'
import { Play, Upload, User, AlertCircle, Loader2 } from 'lucide-react'
import { useInterviewStore } from '../../store/useInterviewStore'

// Example interview schema for demo
const DEMO_SCHEMA = {
  nodes: [
    {
      id: "node-start",
      type: "custom",
      data: {
        label: "Начало интервью",
        nodeType: "start",
        description: null
      }
    },
    {
      id: "node-greeting",
      type: "custom",
      data: {
        label: "Приветствие",
        nodeType: "greeting",
        description: "Знакомство с кандидатом"
      }
    },
    {
      id: "node-python",
      type: "custom",
      data: {
        label: "Знания Python",
        nodeType: "skill-check",
        description: "Основной язык разработки",
        points: 5,
        importance: "high",
        groupName: "Hard Skills"
      }
    },
    {
      id: "node-django",
      type: "custom",
      data: {
        label: "Опыт Django",
        nodeType: "skill-check",
        description: "Фреймворк для бэкенда",
        points: 5,
        importance: "high",
        groupName: "Hard Skills"
      }
    },
    {
      id: "node-livecoding-group",
      type: "custom",
      data: {
        label: "Live Coding",
        nodeType: "skill-group",
        description: "25 баллов",
        groupName: "Live Coding"
      }
    },
    {
      id: "node-livecoding-1",
      type: "custom",
      data: {
        label: "Написание чистого кода",
        nodeType: "skill-check",
        description: "Реализация функции с тестами",
        points: 10,
        importance: "high",
        groupName: "Live Coding"
      }
    },
    {
      id: "node-livecoding-2",
      type: "custom",
      data: {
        label: "Оптимизация алгоритма",
        nodeType: "skill-check",
        description: "Улучшение производительности",
        points: 8,
        importance: "high",
        groupName: "Live Coding"
      }
    },
    {
      id: "node-summary",
      type: "custom",
      data: {
        label: "Подведение итогов",
        nodeType: "section",
        description: "Обсуждение результатов"
      }
    },
    {
      id: "node-end",
      type: "custom",
      data: {
        label: "Конец интервью",
        nodeType: "end"
      }
    }
  ],
  edges: [
    { source: "node-start", target: "node-greeting" },
    { source: "node-greeting", target: "node-python" },
    { source: "node-python", target: "node-django" },
    { source: "node-django", target: "node-livecoding-group" },
    { source: "node-livecoding-group", target: "node-livecoding-1" },
    { source: "node-livecoding-1", target: "node-livecoding-2" },
    { source: "node-livecoding-2", target: "node-summary" },
    { source: "node-summary", target: "node-end" }
  ]
}

export default function InterviewStart() {
  const [candidateName, setCandidateName] = useState('')
  const [schemaJson, setSchemaJson] = useState('')
  const [useDemo, setUseDemo] = useState(true)
  const [error, setError] = useState(null)
  
  const { startInterview, isLoading } = useInterviewStore()

  const handleStart = async () => {
    setError(null)
    
    let schema
    if (useDemo) {
      schema = DEMO_SCHEMA
    } else {
      try {
        schema = JSON.parse(schemaJson)
        if (!schema.nodes || !schema.edges) {
          throw new Error('Schema must have nodes and edges')
        }
      } catch (e) {
        setError('Неверный формат JSON схемы: ' + e.message)
        return
      }
    }

    try {
      await startInterview(schema, candidateName || 'Кандидат')
    } catch (e) {
      setError(e.message)
    }
  }

  const handleFileUpload = (e) => {
    const file = e.target.files[0]
    if (file) {
      const reader = new FileReader()
      reader.onload = (event) => {
        setSchemaJson(event.target.result)
        setUseDemo(false)
      }
      reader.readAsText(file)
    }
  }

  return (
    <div className="min-h-screen bg-bento-bg flex items-center justify-center p-4">
      <div className="bg-bento-card border border-bento-border rounded-2xl max-w-lg w-full p-8">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Play className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">
            HR Интервью
          </h1>
          <p className="text-bento-muted mt-2">
            Автоматизированное техническое собеседование
          </p>
        </div>

        {/* Form */}
        <div className="space-y-6">
          {/* Candidate Name */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Имя кандидата
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-bento-muted" />
              <input
                type="text"
                value={candidateName}
                onChange={(e) => setCandidateName(e.target.value)}
                placeholder="Введите имя"
                className="w-full pl-10 pr-4 py-3 bg-bento-bg border border-bento-border rounded-xl text-white placeholder-bento-muted focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* Schema Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Схема собеседования
            </label>
            
            <div className="flex gap-2 mb-3">
              <button
                onClick={() => setUseDemo(true)}
                className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
                  useDemo 
                    ? 'bg-indigo-500 text-white' 
                    : 'bg-bento-hover text-bento-muted hover:text-white'
                }`}
              >
                Демо схема
              </button>
              <button
                onClick={() => setUseDemo(false)}
                className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
                  !useDemo 
                    ? 'bg-indigo-500 text-white' 
                    : 'bg-bento-hover text-bento-muted hover:text-white'
                }`}
              >
                Своя схема
              </button>
            </div>

            {!useDemo && (
              <div className="space-y-3">
                <label className="flex items-center justify-center gap-2 p-4 border-2 border-dashed border-bento-border rounded-xl cursor-pointer hover:border-indigo-500 transition-colors">
                  <Upload className="w-5 h-5 text-bento-muted" />
                  <span className="text-bento-muted">Загрузить JSON файл</span>
                  <input
                    type="file"
                    accept=".json"
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                </label>
                
                <textarea
                  value={schemaJson}
                  onChange={(e) => setSchemaJson(e.target.value)}
                  placeholder='{"nodes": [...], "edges": [...]}'
                  className="w-full h-32 p-3 bg-bento-bg border border-bento-border rounded-xl font-mono text-sm text-white placeholder-bento-muted focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>
            )}

            {useDemo && (
              <div className="bg-bento-hover rounded-xl p-4">
                <p className="text-sm text-gray-300 mb-2">
                  Демо схема включает:
                </p>
                <ul className="text-sm text-bento-muted space-y-1">
                  <li>• Приветствие и знакомство</li>
                  <li>• Hard Skills: Python, Django</li>
                  <li>• Live Coding: 2 задачи</li>
                  <li>• Подведение итогов</li>
                </ul>
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-xl">
              <AlertCircle className="w-5 h-5 text-red-400" />
              <span className="text-red-300 text-sm">{error}</span>
            </div>
          )}

          {/* Start Button */}
          <button
            onClick={handleStart}
            disabled={isLoading}
            className="w-full py-4 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-xl font-medium hover:from-indigo-600 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-all"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Запуск...
              </>
            ) : (
              <>
                <Play className="w-5 h-5" />
                Начать собеседование
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
