import { useState, useEffect } from 'react'
import { useStore } from '../store/useStore'
import { Play, Send, Loader2 } from 'lucide-react'

export default function CodeEditor() {
  const { scenario, runCode, submitSolution, runOutput } = useStore()
  const [code, setCode] = useState('')
  const [testInput, setTestInput] = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Pre-fill code from scenario
  useEffect(() => {
    const codeStep = scenario?.steps?.find(s => s.step_type === 'show_code')
    if (codeStep?.content) {
      setCode(codeStep.content)
    }
  }, [scenario])

  const handleRun = async () => {
    setIsRunning(true)
    await runCode(code, testInput)
    setIsRunning(false)
  }

  const handleSubmit = async () => {
    if (!code.trim()) return
    setIsSubmitting(true)
    await submitSolution(code)
    setIsSubmitting(false)
  }

  return (
    <div className="bg-bento-card border border-bento-border rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-bento-border">
        <h3 className="text-xs font-medium text-bento-muted uppercase tracking-wider">
          Редактор кода
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRun}
            disabled={isRunning}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-bento-bg border border-bento-border rounded-lg text-xs hover:border-bento-subtle transition-colors disabled:opacity-50"
          >
            {isRunning ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
            <span>Тест</span>
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSubmitting || !code.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white text-black rounded-lg text-xs font-medium hover:bg-neutral-200 transition-colors disabled:opacity-50"
          >
            {isSubmitting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
            <span>Отправить</span>
          </button>
        </div>
      </div>

      {/* Editor */}
      <div className="grid lg:grid-cols-2 divide-x divide-bento-border">
        {/* Code Area */}
        <div className="p-4">
          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="code-editor w-full h-64 bg-bento-bg border border-bento-border rounded-xl p-4 text-sm text-green-400 resize-none focus:border-bento-subtle transition-colors"
            placeholder="Напишите код здесь..."
            spellCheck={false}
          />
        </div>

        {/* Test & Output */}
        <div className="p-4 space-y-4">
          {/* Test Input */}
          <div>
            <label className="text-[10px] text-bento-muted uppercase tracking-wider mb-2 block">
              Тестовый ввод
            </label>
            <textarea
              value={testInput}
              onChange={(e) => setTestInput(e.target.value)}
              className="code-editor w-full h-20 bg-bento-bg border border-bento-border rounded-xl p-3 text-sm resize-none focus:border-bento-subtle transition-colors"
              placeholder="stdin..."
            />
          </div>

          {/* Output */}
          <div>
            <label className="text-[10px] text-bento-muted uppercase tracking-wider mb-2 block">
              Результат
            </label>
            <div className={`
              h-32 bg-bento-bg border border-bento-border rounded-xl p-3 font-mono text-sm overflow-auto
              ${runOutput?.status === 'error' ? 'text-red-400' : ''}
              ${runOutput?.status === 'success' ? 'text-green-400' : ''}
              ${runOutput?.status === 'running' ? 'text-yellow-400' : ''}
              ${!runOutput ? 'text-bento-muted' : ''}
            `}>
              {runOutput?.status === 'running' && (
                <div className="flex items-center gap-2">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  <span>Выполнение...</span>
                </div>
              )}
              {runOutput?.output && <pre className="whitespace-pre-wrap">{runOutput.output}</pre>}
              {!runOutput && <span>Вывод появится здесь</span>}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
