import { useEffect } from 'react'
import { useStore } from './store/useStore'
import Header from './components/Header'
import ScenarioSelector from './components/ScenarioSelector'
import GeneratorPanel from './components/GeneratorPanel'
import ScenarioView from './components/ScenarioView'
import EmptyState from './components/EmptyState'

function App() {
  const { scenario, checkHealth } = useStore()

  useEffect(() => {
    checkHealth()
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [checkHealth])

  return (
    <div className="min-h-screen bg-bento-bg">
      <Header />
      
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
