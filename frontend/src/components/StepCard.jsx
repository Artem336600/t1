import { useEffect, useRef } from 'react'
import { useStore } from '../store/useStore'
import { 
  FileCode, FileText, Terminal, Wrench, Edit3, 
  MessageCircle, Keyboard, Search, TestTube, 
  Lightbulb, CheckCircle, Star
} from 'lucide-react'
import hljs from 'highlight.js'

const STEP_ICONS = {
  show_code: FileCode,
  show_text: FileText,
  show_output: Terminal,
  ask_fix: Wrench,
  ask_complete: Edit3,
  ask_explain: MessageCircle,
  ask_write: Keyboard,
  ask_review: Search,
  run_tests: TestTube,
  hint: Lightbulb,
  solution: CheckCircle
}

const STEP_TITLES = {
  show_code: 'Код',
  show_text: 'Инструкции',
  show_output: 'Вывод',
  ask_fix: 'Исправьте',
  ask_complete: 'Допишите',
  ask_explain: 'Объясните',
  ask_write: 'Напишите',
  ask_review: 'Ревью',
  run_tests: 'Тесты',
  hint: 'Подсказка',
  solution: 'Решение'
}

export default function StepCard({ step, index }) {
  const { currentStepIndex } = useStore()
  const codeRef = useRef(null)
  
  const Icon = STEP_ICONS[step.step_type] || FileText
  const title = STEP_TITLES[step.step_type] || step.step_type
  const isActive = index === currentStepIndex
  const isCompleted = index < currentStepIndex

  useEffect(() => {
    if (codeRef.current) {
      hljs.highlightElement(codeRef.current)
    }
  }, [step.content])

  const renderContent = () => {
    switch (step.step_type) {
      case 'show_code':
        return (
          <pre className="bg-bento-bg rounded-xl p-4 overflow-x-auto text-xs">
            <code ref={codeRef} className="language-python">
              {step.content}
            </code>
          </pre>
        )

      case 'show_text':
        return (
          <p className="text-sm text-neutral-300 leading-relaxed">
            {step.content}
          </p>
        )

      case 'show_output':
        const outputData = typeof step.content === 'object' ? step.content : { output: step.content }
        return (
          <div className="grid grid-cols-2 gap-3">
            {outputData.expected && (
              <div>
                <div className="text-[10px] text-bento-muted uppercase tracking-wider mb-1">Ожидаемый</div>
                <pre className="bg-bento-bg rounded-lg p-3 text-xs text-green-400 font-mono">
                  {outputData.expected}
                </pre>
              </div>
            )}
            {outputData.actual && (
              <div>
                <div className="text-[10px] text-bento-muted uppercase tracking-wider mb-1">Фактический</div>
                <pre className="bg-bento-bg rounded-lg p-3 text-xs text-red-400 font-mono">
                  {outputData.actual}
                </pre>
              </div>
            )}
          </div>
        )

      case 'ask_fix':
      case 'ask_complete':
      case 'ask_write':
        return (
          <div className="space-y-2">
            <p className="text-sm text-neutral-300">{step.content}</p>
            {step.points && (
              <div className="flex items-center gap-1 text-xs text-bento-muted">
                <Star className="w-3 h-3" />
                <span>{step.points} баллов</span>
              </div>
            )}
          </div>
        )

      case 'run_tests':
        const tests = Array.isArray(step.content) ? step.content : []
        return (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {tests.slice(0, 5).map((t, i) => (
              <div key={i} className="bg-bento-bg rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-bento-muted">Тест {i + 1}</span>
                  {t.points && <span className="text-[10px] text-bento-muted">{t.points} pts</span>}
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                  <div>
                    <div className="text-[10px] text-bento-muted mb-1">Вход</div>
                    <div className="text-green-400 truncate">{t.input || '-'}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-bento-muted mb-1">Выход</div>
                    <div className="text-blue-400 truncate">{t.output || t.expected || '-'}</div>
                  </div>
                </div>
              </div>
            ))}
            {tests.length > 5 && (
              <div className="text-xs text-bento-muted text-center py-2">
                + ещё {tests.length - 5} тестов
              </div>
            )}
          </div>
        )

      default:
        return (
          <p className="text-sm text-neutral-300">
            {typeof step.content === 'string' ? step.content : JSON.stringify(step.content)}
          </p>
        )
    }
  }

  return (
    <div 
      className={`
        bg-bento-card border rounded-2xl p-4 transition-all duration-200
        ${isActive ? 'border-white/20 bg-bento-hover' : 'border-bento-border'}
        ${isCompleted ? 'opacity-60' : ''}
      `}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <div className={`
          w-7 h-7 rounded-lg flex items-center justify-center
          ${isActive ? 'bg-white text-black' : 'bg-bento-bg text-bento-muted'}
        `}>
          <Icon className="w-3.5 h-3.5" />
        </div>
        <span className="text-sm font-medium">{title}</span>
        {step.is_interactive && (
          <span className="text-[10px] px-1.5 py-0.5 bg-white/10 rounded text-bento-muted">
            Интерактивный
          </span>
        )}
        {isCompleted && (
          <CheckCircle className="w-4 h-4 text-green-500 ml-auto" />
        )}
      </div>

      {/* Content */}
      {renderContent()}
    </div>
  )
}
