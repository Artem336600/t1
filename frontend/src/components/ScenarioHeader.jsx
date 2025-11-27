import { useStore } from '../store/useStore'
import { Clock, Star, RotateCcw } from 'lucide-react'

export default function ScenarioHeader() {
  const { scenario, currentStepIndex, earnedPoints, reset, scenarioTypes } = useStore()

  if (!scenario) return null

  const typeInfo = scenarioTypes[scenario.type] || { name: scenario.type }
  const progress = scenario.steps?.length > 0 
    ? ((currentStepIndex + 1) / scenario.steps.length) * 100 
    : 0

  const difficultyStyles = {
    easy: 'bg-green-500/10 text-green-400 border-green-500/20',
    medium: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    hard: 'bg-red-500/10 text-red-400 border-red-500/20'
  }

  return (
    <div className="bg-bento-card border border-bento-border rounded-2xl p-5">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex-1 min-w-0">
          {/* Badges */}
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs px-2 py-1 bg-white/10 border border-white/10 rounded-lg">
              {typeInfo.name}
            </span>
            <span className={`text-xs px-2 py-1 border rounded-lg capitalize ${difficultyStyles[scenario.difficulty] || difficultyStyles.medium}`}>
              {scenario.difficulty}
            </span>
          </div>
          
          {/* Title */}
          <h2 className="text-lg font-semibold mb-1 truncate">{scenario.title}</h2>
          <p className="text-sm text-bento-muted line-clamp-2">{scenario.description}</p>
        </div>

        {/* Stats */}
        <div className="flex flex-col items-end gap-2 shrink-0">
          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-2xl font-bold">
                {earnedPoints}<span className="text-bento-muted text-lg">/{scenario.total_points || 100}</span>
              </div>
              <div className="text-[10px] text-bento-muted uppercase tracking-wider">баллов</div>
            </div>
          </div>
          
          <div className="flex items-center gap-3 text-xs text-bento-muted">
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              <span>{scenario.time_limit_minutes || 20} мин</span>
            </div>
            <button 
              onClick={reset}
              className="flex items-center gap-1 hover:text-white transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Сброс</span>
            </button>
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="space-y-1">
        <div className="w-full h-1 bg-bento-bg rounded-full overflow-hidden">
          <div 
            className="h-full bg-white rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-bento-muted">
          <span>Шаг {currentStepIndex + 1} из {scenario.steps?.length || 1}</span>
          <span>{Math.round(progress)}%</span>
        </div>
      </div>
    </div>
  )
}
