import { useState, useEffect } from 'react'
import { Play, Send, Loader2, CheckCircle, XCircle, Clock, Lightbulb, ArrowRight } from 'lucide-react'
import { useInterviewStore } from '../../store/useInterviewStore'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'

hljs.registerLanguage('python', python)

export default function InterviewCodeEditor() {
  const [code, setCode] = useState('')
  const [runOutput, setRunOutput] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [showHints, setShowHints] = useState(false)
  const [usedHints, setUsedHints] = useState([])
  const [taskCompleted, setTaskCompleted] = useState(false)
  
  const {
    liveCodingTask,
    currentLevel,
    isLoading,
    submitCode,
    exitLiveCoding
  } = useInterviewStore()

  // Initialize code when task changes
  useEffect(() => {
    if (liveCodingTask) {
      // Set initial code template
      const template = `# ${liveCodingTask.title || 'Задача'}
# Уровень: ${currentLevel}

# Напишите ваше решение здесь

`
      setCode(template)
      setRunOutput(null)
      setUsedHints([])
    }
  }, [liveCodingTask, currentLevel])

  const runCode = async () => {
    setIsRunning(true)
    setRunOutput({ status: 'running' })

    try {
      const res = await fetch('/api/code/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code,
          input: liveCodingTask?.examples?.[0]?.input || ''
        })
      })

      const result = await res.json()
      
      setRunOutput({
        status: result.stderr ? 'error' : 'success',
        stdout: result.stdout || '',
        stderr: result.stderr || ''
      })
    } catch (e) {
      setRunOutput({
        status: 'error',
        stderr: e.message
      })
    } finally {
      setIsRunning(false)
    }
  }

  const handleSubmit = async () => {
    try {
      const result = await submitCode(code, 'python')
      if (result) {
        setTaskCompleted(true)
      }
    } catch (e) {
      console.error('Submit error:', e)
    }
  }

  const useHint = (index) => {
    if (!usedHints.includes(index)) {
      setUsedHints([...usedHints, index])
    }
  }

  if (!liveCodingTask) {
    return (
      <div className="h-full flex items-center justify-center bg-bento-card border border-bento-border rounded-xl">
        <div className="text-center text-bento-muted">
          <p>Ожидание задачи Live Coding...</p>
        </div>
      </div>
    )
  }

  const hints = liveCodingTask.hints || []
  const examples = liveCodingTask.examples || []
  const timeLimit = liveCodingTask.time_limit_minutes || 15

  return (
    <div className="h-full flex flex-col bg-gray-900 rounded-xl overflow-hidden relative">
      {/* Header */}
      <div className="bg-gray-800 px-4 py-3 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-white font-semibold">
              {liveCodingTask.title || 'Live Coding'}
            </h3>
            <div className="flex items-center gap-3 mt-1">
              <span className={`text-xs px-2 py-0.5 rounded ${
                currentLevel === 'junior' ? 'bg-green-500/20 text-green-400' :
                currentLevel === 'middle' ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-red-500/20 text-red-400'
              }`}>
                {currentLevel.toUpperCase()}
              </span>
              <span className="text-gray-400 text-sm flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {timeLimit} мин
              </span>
            </div>
          </div>
          
          <div className="flex gap-2">
            <button
              onClick={() => setShowHints(!showHints)}
              className={`px-3 py-1.5 rounded-lg text-sm flex items-center gap-1 ${
                showHints ? 'bg-amber-500/20 text-amber-400' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              <Lightbulb className="w-4 h-4" />
              Подсказки ({hints.length})
            </button>
          </div>
        </div>
      </div>

      {/* Task Description */}
      <div className="bg-gray-800/50 px-4 py-3 border-b border-gray-700 max-h-40 overflow-y-auto">
        <p className="text-gray-300 text-sm whitespace-pre-wrap">
          {liveCodingTask.description}
        </p>
        
        {examples.length > 0 && (
          <div className="mt-3 space-y-2">
            <p className="text-gray-400 text-xs font-medium">Примеры:</p>
            {examples.map((ex, i) => (
              <div key={i} className="bg-gray-900/50 rounded p-2 text-xs">
                <div className="text-gray-400">Вход:</div>
                <pre className="text-green-400">{ex.input}</pre>
                <div className="text-gray-400 mt-1">Выход:</div>
                <pre className="text-blue-400">{ex.output}</pre>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Hints Panel */}
      {showHints && hints.length > 0 && (
        <div className="bg-amber-900/20 px-4 py-3 border-b border-amber-700/30">
          <div className="space-y-2">
            {hints.map((hint, i) => (
              <div key={i} className="flex items-start gap-2">
                {usedHints.includes(i) ? (
                  <p className="text-amber-300 text-sm">{hint}</p>
                ) : (
                  <button
                    onClick={() => useHint(i)}
                    className="text-amber-400 text-sm hover:text-amber-300"
                  >
                    Показать подсказку {i + 1} (-10% баллов)
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Code Editor */}
      <div className="flex-1 overflow-hidden">
        <textarea
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="w-full h-full bg-gray-900 text-gray-100 font-mono text-sm p-4 resize-none focus:outline-none"
          spellCheck={false}
          placeholder="# Напишите ваш код здесь..."
        />
      </div>

      {/* Output Panel */}
      {runOutput && (
        <div className="bg-gray-800 border-t border-gray-700 max-h-32 overflow-y-auto">
          <div className="px-4 py-2 border-b border-gray-700 flex items-center gap-2">
            {runOutput.status === 'running' ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
                <span className="text-gray-400 text-sm">Выполнение...</span>
              </>
            ) : runOutput.status === 'success' ? (
              <>
                <CheckCircle className="w-4 h-4 text-green-400" />
                <span className="text-green-400 text-sm">Успешно</span>
              </>
            ) : (
              <>
                <XCircle className="w-4 h-4 text-red-400" />
                <span className="text-red-400 text-sm">Ошибка</span>
              </>
            )}
          </div>
          <pre className={`p-4 text-sm font-mono ${
            runOutput.status === 'error' ? 'text-red-400' : 'text-gray-300'
          }`}>
            {runOutput.stderr || runOutput.stdout || '(пустой вывод)'}
          </pre>
        </div>
      )}

      {/* Actions */}
      <div className="bg-gray-800 px-4 py-3 border-t border-gray-700 flex items-center justify-between">
        <button
          onClick={runCode}
          disabled={isRunning || isLoading || taskCompleted}
          className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {isRunning ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          Запустить
        </button>

        {taskCompleted ? (
          <button
            onClick={exitLiveCoding}
            className="px-6 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2"
          >
            <ArrowRight className="w-4 h-4" />
            Вернуться к интервью
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={isLoading || isRunning}
            className="px-6 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
            Отправить решение
          </button>
        )}
      </div>

      {/* Task Completed Overlay */}
      {taskCompleted && (
        <div className="absolute inset-0 bg-black/50 flex items-center justify-center rounded-xl">
          <div className="bg-gray-800 rounded-xl p-6 text-center max-w-md mx-4">
            <CheckCircle className="w-16 h-16 text-green-400 mx-auto mb-4" />
            <h3 className="text-xl font-bold text-white mb-2">Решение отправлено!</h3>
            <p className="text-gray-400 mb-6">
              Ваш код был отправлен на проверку. AI Судья оценит ваше решение.
            </p>
            <button
              onClick={exitLiveCoding}
              className="px-6 py-3 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 flex items-center gap-2 mx-auto"
            >
              <ArrowRight className="w-5 h-5" />
              Продолжить интервью
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
