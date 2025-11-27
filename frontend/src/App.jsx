import { useEffect, useState } from 'react'
import { useStore } from './store/useStore'
import Header from './components/Header'
import ScenarioSelector from './components/ScenarioSelector'
import GeneratorPanel from './components/GeneratorPanel'
import ScenarioView from './components/ScenarioView'
import EmptyState from './components/EmptyState'
import { InterviewPage } from './components/interview'
import { MessageSquare, Code } from 'lucide-react'

function App() {
  const { scenario, checkHealth } = useStore()
  const [mode, setMode] = useState('tasks') // 'tasks' or 'interview'

  useEffect(() => {
    checkHealth()
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [checkHealth])

  // Interview mode
  if (mode === 'interview') {
    return (
      <div>
        {/* Mode Switcher */}
        <div className="fixed top-4 right-4 z-50">
          <button
            onClick={() => setMode('tasks')}
            className="px-4 py-2 bg-white shadow-lg rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 flex items-center gap-2"
          >
            <Code className="w-4 h-4" />
            Режим задач
          </button>
        </div>
        <InterviewPage />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-bento-bg">
      <Header />
      
      {/* Mode Switcher */}
      <div className="fixed top-4 right-4 z-50">
        <button
          onClick={() => setMode('interview')}
          className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white shadow-lg rounded-lg text-sm font-medium hover:from-indigo-600 hover:to-purple-700 flex items-center gap-2"
        >
          <MessageSquare className="w-4 h-4" />
          HR Интервью
        </button>
      </div>
      
      <main className="max-w-7xl mx-auto p-4 md:p-6 space-y-4">
        {/* Bento Grid Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Left Column - Scenario Types */}
          <div className="lg:col-span-4">
            <ScenarioSelector />
          </div>
          
          {/* Right Column - Generator */}
          <div className="lg:col-span-8">
            <GeneratorPanel />
          </div>
        </div>

        {/* Scenario Content */}
        {scenario ? <ScenarioView /> : <EmptyState />}
      </main>
    </div>
  )
}

export default App
