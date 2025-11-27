import { useStore } from '../store/useStore'
import { Lightbulb, Lock, ChevronDown } from 'lucide-react'

export default function HintsPanel({ hints }) {
  const { usedHints, useHint } = useStore()

  const handleShowHint = (index) => {
    const hint = hints[index]
    const penalty = hint?.penalty_percent || 10
    
    if (confirm(`Показать подсказку? Это снизит баллы на ${penalty}%`)) {
      useHint(index)
    }
  }

  return (
    <div className="bg-bento-card border border-bento-border rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-bento-border">
        <div className="flex items-center gap-2">
          <Lightbulb className="w-4 h-4 text-yellow-400" />
          <h3 className="text-xs font-medium text-bento-muted uppercase tracking-wider">
            Подсказки
          </h3>
        </div>
        <span className="text-xs text-bento-muted">
          {hints.length - usedHints.length} доступно
        </span>
      </div>

      {/* Hints List */}
      <div className="divide-y divide-bento-border">
        {hints.map((hint, i) => {
          const isUnlocked = usedHints.includes(i)
          const penalty = hint?.penalty_percent || 10
          
          return (
            <div key={i} className="p-4">
              {isUnlocked ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Lightbulb className="w-4 h-4 text-yellow-400" />
                    <span className="text-sm font-medium">Подсказка {i + 1}</span>
                  </div>
                  <p className="text-sm text-neutral-300 pl-6">
                    {hint.hint_text || hint.text || hint}
                  </p>
                </div>
              ) : (
                <button
                  onClick={() => handleShowHint(i)}
                  className="w-full flex items-center justify-between group"
                >
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-bento-bg border border-bento-border rounded-lg flex items-center justify-center group-hover:border-bento-subtle transition-colors">
                      <Lock className="w-3.5 h-3.5 text-bento-muted" />
                    </div>
                    <div className="text-left">
                      <div className="text-sm font-medium group-hover:text-white transition-colors">
                        Подсказка {i + 1}
                      </div>
                      <div className="text-[10px] text-bento-muted">
                        -{penalty}% от баллов
                      </div>
                    </div>
                  </div>
                  <ChevronDown className="w-4 h-4 text-bento-muted group-hover:text-white transition-colors" />
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
