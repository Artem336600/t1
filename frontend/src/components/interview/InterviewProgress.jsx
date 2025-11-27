import { CheckCircle, Circle, Clock, Award, TrendingUp, Play, Flag } from 'lucide-react'
import { useInterviewStore } from '../../store/useInterviewStore'

export default function InterviewProgress() {
  const {
    currentStep,
    totalSteps,
    currentLevel,
    scores,
    schema,
    getTotalScore
  } = useInterviewStore()

  const { earned, max, percent } = getTotalScore()
  
  // Calculate step progress
  const completedSteps = Object.keys(scores).length
  const progressPercent = totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0

  // Get ordered steps from schema
  const getOrderedSteps = () => {
    if (!schema?.nodes || !schema?.edges) return []
    
    const nodes = schema.nodes
    const edges = schema.edges
    
    // Build adjacency map
    const nextMap = {}
    edges.forEach(e => {
      nextMap[e.source] = e.target
    })
    
    // Find start node
    const targetNodes = new Set(edges.map(e => e.target))
    let startNode = nodes.find(n => !targetNodes.has(n.id))
    
    if (!startNode) startNode = nodes[0]
    
    // Traverse in order
    const ordered = []
    let currentId = startNode?.id
    const visited = new Set()
    
    while (currentId && !visited.has(currentId)) {
      visited.add(currentId)
      const node = nodes.find(n => n.id === currentId)
      if (node) ordered.push(node)
      currentId = nextMap[currentId]
    }
    
    return ordered
  }

  const orderedSteps = getOrderedSteps()
  
  // Find current step index
  const currentStepIndex = orderedSteps.findIndex(s => s.id === currentStep?.id)

  const getLevelColor = (level) => {
    switch (level) {
      case 'junior': return 'text-green-400 bg-green-500/20 border-green-500/30'
      case 'middle': return 'text-yellow-400 bg-yellow-500/20 border-yellow-500/30'
      case 'senior': return 'text-red-400 bg-red-500/20 border-red-500/30'
      default: return 'text-gray-400 bg-gray-500/20 border-gray-500/30'
    }
  }

  const getLevelIcon = (level) => {
    switch (level) {
      case 'junior': return <TrendingUp className="w-4 h-4" />
      case 'middle': return <TrendingUp className="w-4 h-4" />
      case 'senior': return <Award className="w-4 h-4" />
      default: return <Circle className="w-4 h-4" />
    }
  }

  const getStepStatus = (step, index) => {
    if (scores[step.id]) return 'completed'
    if (index === currentStepIndex) return 'current'
    if (index < currentStepIndex) return 'completed'
    return 'pending'
  }

  const getStepIcon = (step, status) => {
    const nodeType = step.data?.nodeType
    
    if (nodeType === 'start') return <Play className="w-3 h-3" />
    if (nodeType === 'end') return <Flag className="w-3 h-3" />
    
    if (status === 'completed') return <CheckCircle className="w-3 h-3" />
    if (status === 'current') return <Clock className="w-3 h-3" />
    return <Circle className="w-3 h-3" />
  }

  return (
    <div className="bg-bento-card border border-bento-border rounded-xl p-4 space-y-4 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-white font-semibold">Прогресс</h3>
        <span className="text-bento-muted text-sm">
          {completedSteps}/{totalSteps}
        </span>
      </div>

      {/* Progress Bar */}
      <div>
        <div className="h-2 bg-bento-subtle rounded-full overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-500"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <div className="flex justify-between mt-1">
          <span className="text-xs text-bento-muted">
            {Math.round(progressPercent)}% завершено
          </span>
          <span className="text-xs text-bento-muted">
            {totalSteps - completedSteps} осталось
          </span>
        </div>
      </div>

      {/* Current Level */}
      <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${getLevelColor(currentLevel)}`}>
        {getLevelIcon(currentLevel)}
        <span className="font-medium capitalize">{currentLevel}</span>
        <span className="text-xs opacity-70">уровень</span>
      </div>

      {/* Score */}
      <div className="bg-bento-hover rounded-lg p-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-bento-muted">Набрано баллов</span>
          <span className="text-lg font-bold text-indigo-400">
            {earned}/{max}
          </span>
        </div>
        <div className="mt-2 h-1.5 bg-bento-subtle rounded-full overflow-hidden">
          <div 
            className={`h-full transition-all duration-500 ${
              percent >= 70 ? 'bg-green-500' :
              percent >= 40 ? 'bg-yellow-500' :
              'bg-red-500'
            }`}
            style={{ width: `${percent}%` }}
          />
        </div>
        <div className="mt-1 text-right text-xs text-bento-muted">
          {percent}%
        </div>
      </div>

      {/* Steps Timeline */}
      <div className="border-t border-bento-border pt-4">
        <p className="text-xs font-medium text-bento-muted mb-3">Этапы интервью</p>
        <div className="space-y-1">
          {orderedSteps.map((step, index) => {
            const status = getStepStatus(step, index)
            const isCurrent = status === 'current'
            const isCompleted = status === 'completed'
            const score = scores[step.id]
            
            return (
              <div 
                key={step.id}
                className={`flex items-center gap-2 px-2 py-1.5 rounded-lg transition-colors ${
                  isCurrent 
                    ? 'bg-indigo-500/20 border border-indigo-500/30' 
                    : isCompleted 
                      ? 'bg-bento-hover/50' 
                      : ''
                }`}
              >
                {/* Step indicator */}
                <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${
                  isCurrent 
                    ? 'bg-indigo-500 text-white' 
                    : isCompleted 
                      ? 'bg-green-500/20 text-green-400' 
                      : 'bg-bento-subtle text-bento-muted'
                }`}>
                  {getStepIcon(step, status)}
                </div>
                
                {/* Step info */}
                <div className="flex-1 min-w-0">
                  <p className={`text-sm truncate ${
                    isCurrent 
                      ? 'text-white font-medium' 
                      : isCompleted 
                        ? 'text-gray-400' 
                        : 'text-bento-muted'
                  }`}>
                    {step.data?.label || step.id}
                  </p>
                </div>
                
                {/* Score or points */}
                {score ? (
                  <span className={`text-xs font-medium ${
                    score.earned >= score.max * 0.7 ? 'text-green-400' :
                    score.earned >= score.max * 0.4 ? 'text-yellow-400' :
                    'text-red-400'
                  }`}>
                    {score.earned}/{score.max}
                  </span>
                ) : step.data?.points ? (
                  <span className="text-xs text-bento-muted">
                    {step.data.points}б
                  </span>
                ) : null}
              </div>
            )
          })}
        </div>
      </div>

      {/* Current Step Details */}
      {currentStep && (
        <div className="border-t border-bento-border pt-4">
          <p className="text-xs font-medium text-bento-muted mb-2">Текущий этап</p>
          <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-lg p-3">
            <p className="text-white font-medium text-sm">
              {currentStep.label}
            </p>
            {currentStep.description && (
              <p className="text-bento-muted text-xs mt-1">
                {currentStep.description}
              </p>
            )}
            {currentStep.points && (
              <div className="mt-2 flex items-center gap-1">
                <Award className="w-3 h-3 text-indigo-400" />
                <span className="text-xs text-indigo-400">
                  {currentStep.points} баллов
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
