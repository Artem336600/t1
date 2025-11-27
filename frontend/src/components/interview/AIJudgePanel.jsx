import { Scale, Star, TrendingUp, AlertCircle, CheckCircle, Brain, Loader2 } from 'lucide-react'
import { useInterviewStore } from '../../store/useInterviewStore'

export default function AIJudgePanel() {
  const {
    messages,
    scores,
    currentStep,
    getTotalScore
  } = useInterviewStore()

  const { earned, max, percent } = getTotalScore()
  
  // Get last evaluation from messages
  const lastEvaluation = [...messages].reverse().find(m => m.evaluation)?.evaluation

  // Calculate stats
  const totalAnswers = messages.filter(m => m.role === 'user').length
  const evaluatedAnswers = Object.keys(scores).length
  
  // Check if there are pending evaluations (user answered but no evaluation yet)
  const pendingEvaluations = totalAnswers - evaluatedAnswers

  const getScoreColor = (pct) => {
    if (pct >= 70) return 'text-green-400'
    if (pct >= 40) return 'text-yellow-400'
    return 'text-red-400'
  }

  const getScoreBg = (pct) => {
    if (pct >= 70) return 'bg-green-500'
    if (pct >= 40) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  return (
    <div className="bg-bento-card border border-bento-border rounded-xl p-4 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center">
          <Brain className="w-4 h-4 text-purple-400" />
        </div>
        <div>
          <h3 className="text-white font-semibold text-sm">AI Судья</h3>
          <p className="text-bento-muted text-xs">Оценка ответов</p>
        </div>
      </div>

      {/* Overall Score */}
      <div className="bg-bento-hover rounded-lg p-3 mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-bento-muted text-sm">Общий балл</span>
          <span className={`text-xl font-bold ${getScoreColor(percent)}`}>
            {percent}%
          </span>
        </div>
        <div className="h-2 bg-bento-subtle rounded-full overflow-hidden">
          <div 
            className={`h-full ${getScoreBg(percent)} transition-all duration-500`}
            style={{ width: `${percent}%` }}
          />
        </div>
        <div className="flex justify-between mt-1 text-xs text-bento-muted">
          <span>{earned} из {max} баллов</span>
          <span>{evaluatedAnswers} оценок</span>
        </div>
      </div>

      {/* Pending Evaluations Indicator */}
      {pendingEvaluations > 0 && (
        <div className="mb-4 bg-amber-500/10 border border-amber-500/20 rounded-lg p-3">
          <div className="flex items-center gap-2">
            <Loader2 className="w-4 h-4 text-amber-400 animate-spin" />
            <div>
              <p className="text-amber-300 text-sm font-medium">
                Оценивается...
              </p>
              <p className="text-amber-400/70 text-xs">
                {pendingEvaluations} {pendingEvaluations === 1 ? 'ответ' : 'ответов'} в очереди
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Current Step Evaluation */}
      {currentStep && (
        <div className="mb-4">
          <p className="text-xs text-bento-muted mb-2">Текущий этап</p>
          <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-lg p-2">
            <p className="text-white text-sm font-medium truncate">
              {currentStep.label}
            </p>
            {currentStep.points && (
              <p className="text-indigo-400 text-xs mt-1">
                До {currentStep.points} баллов
              </p>
            )}
          </div>
        </div>
      )}

      {/* Last Evaluation */}
      {lastEvaluation && (
        <div className="flex-1 overflow-y-auto">
          <p className="text-xs text-bento-muted mb-2">Последняя оценка</p>
          <div className="bg-bento-hover rounded-lg p-3 space-y-2">
            {/* Score */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Scale className="w-4 h-4 text-bento-muted" />
                <span className="text-sm text-gray-300">Баллы</span>
              </div>
              <span className={`font-bold ${getScoreColor(
                lastEvaluation.max_points > 0 
                  ? (lastEvaluation.points / lastEvaluation.max_points) * 100 
                  : 0
              )}`}>
                {lastEvaluation.points}/{lastEvaluation.max_points}
              </span>
            </div>

            {/* Feedback */}
            {lastEvaluation.feedback && (
              <div className="pt-2 border-t border-bento-border">
                <p className="text-xs text-bento-muted mb-1">Комментарий:</p>
                <p className="text-sm text-gray-300">
                  {lastEvaluation.feedback}
                </p>
              </div>
            )}

            {/* Strengths */}
            {lastEvaluation.strengths && lastEvaluation.strengths.length > 0 && (
              <div className="pt-2 border-t border-bento-border">
                <p className="text-xs text-green-400 mb-1 flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />
                  Сильные стороны:
                </p>
                <ul className="text-xs text-gray-400 space-y-0.5">
                  {lastEvaluation.strengths.slice(0, 2).map((s, i) => (
                    <li key={i}>• {s}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Improvements */}
            {lastEvaluation.improvements && lastEvaluation.improvements.length > 0 && (
              <div className="pt-2 border-t border-bento-border">
                <p className="text-xs text-yellow-400 mb-1 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  Можно улучшить:
                </p>
                <ul className="text-xs text-gray-400 space-y-0.5">
                  {lastEvaluation.improvements.slice(0, 2).map((s, i) => (
                    <li key={i}>• {s}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* No evaluations yet */}
      {!lastEvaluation && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-bento-muted">
            <Star className="w-8 h-8 mx-auto mb-2 opacity-30" />
            <p className="text-sm">Оценки появятся</p>
            <p className="text-xs">после ваших ответов</p>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="mt-4 pt-4 border-t border-bento-border grid grid-cols-2 gap-2">
        <div className="bg-bento-hover rounded-lg p-2 text-center">
          <p className="text-lg font-bold text-white">{totalAnswers}</p>
          <p className="text-xs text-bento-muted">Ответов</p>
        </div>
        <div className="bg-bento-hover rounded-lg p-2 text-center">
          <p className="text-lg font-bold text-white">{evaluatedAnswers}</p>
          <p className="text-xs text-bento-muted">Оценено</p>
        </div>
      </div>
    </div>
  )
}
