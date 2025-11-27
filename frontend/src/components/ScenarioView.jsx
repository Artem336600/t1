import { useStore } from '../store/useStore'
import ScenarioHeader from './ScenarioHeader'
import StepCard from './StepCard'
import CodeEditor from './CodeEditor'
import TestResults from './TestResults'
import HintsPanel from './HintsPanel'

export default function ScenarioView() {
  const { scenario } = useStore()

  if (!scenario) return null

  const hasInteractive = scenario.steps?.some(s => s.is_interactive)
  const hints = scenario.metadata?.hints || []

  return (
    <div className="space-y-4 animate-slide-up">
      {/* Header */}
      <ScenarioHeader />

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Steps Column */}
        <div className="lg:col-span-5 space-y-3">
          {scenario.steps?.map((step, i) => (
            <StepCard key={i} step={step} index={i} />
          ))}
        </div>

        {/* Editor Column */}
        <div className="lg:col-span-7 space-y-4">
          {hasInteractive && <CodeEditor />}
          <TestResults />
          {hints.length > 0 && <HintsPanel hints={hints} />}
        </div>
      </div>
    </div>
  )
}
