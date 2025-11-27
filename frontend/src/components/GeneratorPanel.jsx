import { useState } from 'react'
import { useStore } from '../store/useStore'
import { Play, Loader2, Check, Sparkles, X, AlertTriangle } from 'lucide-react'

export default function GeneratorPanel() {
  const { 
    selectedType, 
    scenarioTypes, 
    isGenerating, 
    generationStep,
    generateScenario,
    error,
    clearError
  } = useStore()
  
  const [query, setQuery] = useState('')
  const [difficulty, setDifficulty] = useState('medium')
  const [language, setLanguage] = useState('python')

  const handleGenerate = async () => {
    if (!query.trim()) return
    await generateScenario(query, difficulty, language)
  }

  const selectedTypeInfo = selectedType ? scenarioTypes[selectedType] : null

  return (
    <div className="bg-bento-card border border-bento-border rounded-2xl p-4 h-full">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xs font-medium text-bento-muted uppercase tracking-wider">
          Генератор
        </h2>
        {selectedTypeInfo && (
          <span className="text-xs px-2 py-1 bg-white/10 rounded-lg text-white">
            {selectedTypeInfo.name}
          </span>
        )}
      </div>

      <div className="space-y-3">
        {/* Query Input */}
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleGenerate()}
          placeholder="Тема: бинарный поиск, ООП, рекурсия..."
          className="w-full px-4 py-3 bg-bento-bg border border-bento-border rounded-xl text-sm placeholder:text-bento-muted focus:border-bento-subtle transition-colors"
        />

        {/* Options Row */}
        <div className="flex gap-2">
          <select
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
            className="flex-1 px-3 py-2.5 bg-bento-bg border border-bento-border rounded-xl text-sm appearance-none cursor-pointer hover:border-bento-subtle transition-colors"
          >
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
            <option value="hard">Hard</option>
          </select>

          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="flex-1 px-3 py-2.5 bg-bento-bg border border-bento-border rounded-xl text-sm appearance-none cursor-pointer hover:border-bento-subtle transition-colors"
          >
            <option value="python">Python</option>
            <option value="javascript">JavaScript</option>
            <option value="java">Java</option>
            <option value="cpp">C++</option>
          </select>

          <button
            onClick={handleGenerate}
            disabled={isGenerating || !query.trim()}
            className="px-5 py-2.5 bg-white text-black rounded-xl text-sm font-medium flex items-center gap-2 hover:bg-neutral-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isGenerating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="hidden sm:inline">Генерация...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span className="hidden sm:inline">Создать</span>
              </>
            )}
          </button>
        </div>

        {/* Generation Progress */}
        {isGenerating && (
          <div className="flex items-center gap-3 pt-2">
            <ProgressStep 
              label="Планирование" 
              status={generationStep === 'planning' ? 'active' : generationStep === 'generating' || generationStep === 'done' ? 'done' : 'pending'} 
            />
            <div className="w-8 h-px bg-bento-border" />
            <ProgressStep 
              label="Генерация" 
              status={generationStep === 'generating' ? 'active' : generationStep === 'done' ? 'done' : 'pending'} 
            />
            <div className="w-8 h-px bg-bento-border" />
            <ProgressStep 
              label="Готово" 
              status={generationStep === 'done' ? 'done' : 'pending'} 
            />
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div className="flex items-start gap-3 p-3 bg-red-500/10 border border-red-500/20 rounded-xl">
            <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-red-400">{error}</p>
            </div>
            <button onClick={clearError} className="text-red-400 hover:text-red-300">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function ProgressStep({ label, status }) {
  return (
    <div className="flex items-center gap-2">
      <div className={`
        w-5 h-5 rounded-full flex items-center justify-center text-xs
        ${status === 'done' ? 'bg-white text-black' : ''}
        ${status === 'active' ? 'bg-bento-subtle text-white animate-pulse' : ''}
        ${status === 'pending' ? 'bg-bento-border text-bento-muted' : ''}
      `}>
        {status === 'done' ? <Check className="w-3 h-3" /> : null}
        {status === 'active' ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
      </div>
      <span className={`text-xs ${status === 'pending' ? 'text-bento-muted' : 'text-white'}`}>
        {label}
      </span>
    </div>
  )
}
