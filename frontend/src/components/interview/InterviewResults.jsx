import { Award, CheckCircle, XCircle, AlertTriangle, TrendingUp, BookOpen, Clock } from 'lucide-react'
import { useInterviewStore } from '../../store/useInterviewStore'

export default function InterviewResults() {
  const { finalResult, reset } = useInterviewStore()

  if (!finalResult) return null

  const {
    candidate_name,
    total_score,
    max_score,
    score_percent,
    passed,
    sections,
    main_errors,
    recommendations,
    duration_minutes
  } = finalResult

  const getScoreColor = (percent) => {
    if (percent >= 80) return 'text-green-400'
    if (percent >= 60) return 'text-yellow-400'
    return 'text-red-400'
  }

  const getScoreBg = (percent) => {
    if (percent >= 80) return 'bg-green-500'
    if (percent >= 60) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  return (
    <div className="min-h-screen bg-bento-bg py-8 px-4">
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Header */}
        <div className="bg-bento-card border border-bento-border rounded-2xl overflow-hidden">
          <div className={`p-6 ${passed ? 'bg-gradient-to-r from-green-500/20 to-emerald-600/20 border-b border-green-500/30' : 'bg-gradient-to-r from-red-500/20 to-rose-600/20 border-b border-red-500/30'}`}>
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold text-white">
                  Результаты собеседования
                </h1>
                <p className="text-bento-muted mt-1">
                  {candidate_name}
                </p>
              </div>
              <div className="text-right">
                {passed ? (
                  <div className="flex items-center gap-2 text-green-400">
                    <CheckCircle className="w-8 h-8" />
                    <span className="text-xl font-bold">ПРОЙДЕНО</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-red-400">
                    <XCircle className="w-8 h-8" />
                    <span className="text-xl font-bold">НЕ ПРОЙДЕНО</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Score Circle */}
          <div className="p-8 flex justify-center">
            <div className="relative w-40 h-40">
              <svg className="w-full h-full transform -rotate-90">
                <circle
                  cx="80"
                  cy="80"
                  r="70"
                  fill="none"
                  stroke="#333333"
                  strokeWidth="12"
                />
                <circle
                  cx="80"
                  cy="80"
                  r="70"
                  fill="none"
                  stroke={score_percent >= 80 ? '#22c55e' : score_percent >= 60 ? '#eab308' : '#ef4444'}
                  strokeWidth="12"
                  strokeLinecap="round"
                  strokeDasharray={`${score_percent * 4.4} 440`}
                  className="transition-all duration-1000"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className={`text-4xl font-bold ${getScoreColor(score_percent)}`}>
                  {Math.round(score_percent)}%
                </span>
                <span className="text-bento-muted text-sm">
                  {total_score}/{max_score}
                </span>
              </div>
            </div>
          </div>

          {/* Duration */}
          <div className="px-8 pb-6 flex justify-center">
            <div className="flex items-center gap-2 text-bento-muted">
              <Clock className="w-4 h-4" />
              <span>Длительность: {Math.round(duration_minutes)} мин</span>
            </div>
          </div>
        </div>

        {/* Sections */}
        <div className="bg-bento-card border border-bento-border rounded-2xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-indigo-400" />
            Результаты по разделам
          </h2>
          
          <div className="space-y-4">
            {sections.map((section, i) => {
              const sectionPercent = section.max > 0 
                ? Math.round(section.earned / section.max * 100) 
                : 0
              
              return (
                <div key={i} className="border border-bento-border rounded-xl p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-white">{section.name}</span>
                    <span className={`font-bold ${getScoreColor(sectionPercent)}`}>
                      {section.earned}/{section.max}
                    </span>
                  </div>
                  <div className="h-2 bg-bento-subtle rounded-full overflow-hidden">
                    <div 
                      className={`h-full ${getScoreBg(sectionPercent)} transition-all duration-500`}
                      style={{ width: `${sectionPercent}%` }}
                    />
                  </div>
                  
                  {/* Section steps */}
                  {section.steps && section.steps.length > 0 && (
                    <div className="mt-3 space-y-1">
                      {section.steps.map((step, j) => (
                        <div key={j} className="flex items-center justify-between text-sm">
                          <span className="text-bento-muted">{step.label}</span>
                          <span className={`${
                            step.earned >= step.max * 0.7 ? 'text-green-400' :
                            step.earned >= step.max * 0.4 ? 'text-yellow-400' :
                            'text-red-400'
                          }`}>
                            {step.earned}/{step.max}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Main Errors */}
        {main_errors && main_errors.length > 0 && (
          <div className="bg-bento-card border border-bento-border rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-400" />
              Основные ошибки
            </h2>
            
            <ul className="space-y-2">
              {main_errors.map((error, i) => (
                <li key={i} className="flex items-start gap-2">
                  <XCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                  <span className="text-gray-300">{error}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Recommendations */}
        {recommendations && recommendations.length > 0 && (
          <div className="bg-bento-card border border-bento-border rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-indigo-400" />
              Рекомендации
            </h2>
            
            <ul className="space-y-2">
              {recommendations.map((rec, i) => (
                <li key={i} className="flex items-start gap-2">
                  <CheckCircle className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
                  <span className="text-gray-300">{rec}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-center gap-4">
          <button
            onClick={reset}
            className="px-6 py-3 bg-indigo-500 text-white rounded-xl hover:bg-indigo-600 transition-colors font-medium"
          >
            Начать новое собеседование
          </button>
        </div>
      </div>
    </div>
  )
}
