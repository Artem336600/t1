import { create } from 'zustand'

const API_BASE = ''

export const useStore = create((set, get) => ({
  // State
  scenario: null,
  currentStepIndex: 0,
  earnedPoints: 0,
  usedHints: [],
  selectedType: null,
  isGenerating: false,
  generationStep: null,
  healthStatus: 'checking',
  testResults: null,
  runOutput: null,
  error: null,
  
  // Scenario types
  scenarioTypes: {
    fix_code: { icon: 'Bug', name: 'Исправить баги', desc: 'Найти и исправить ошибки в коде' },
    complete: { icon: 'FileCode', name: 'Дописать код', desc: 'Завершить незаконченный код' },
    debug_output: { icon: 'Search', name: 'Найти баг', desc: 'Найти баг по неправильному выводу' },
    refactor: { icon: 'RefreshCw', name: 'Рефакторинг', desc: 'Улучшить качество кода' },
    multi_step: { icon: 'Layers', name: 'Многошаговая', desc: 'Несколько этапов решения' },
    code_review: { icon: 'Eye', name: 'Код-ревью', desc: 'Провести ревью кода' },
    explain: { icon: 'MessageSquare', name: 'Объяснить', desc: 'Объяснить работу кода' },
    optimize: { icon: 'Zap', name: 'Оптимизация', desc: 'Улучшить производительность' },
    write_tests: { icon: 'TestTube', name: 'Написать тесты', desc: 'Создать тесты для кода' },
    implement: { icon: 'Sparkles', name: 'С нуля', desc: 'Написать код с нуля' }
  },

  // Actions
  setSelectedType: (type) => set({ selectedType: type === get().selectedType ? null : type }),
  
  checkHealth: async () => {
    try {
      const res = await fetch(`${API_BASE}/health`)
      const data = await res.json()
      const allOk = Object.values(data.services || {}).every(s => s === 'ok')
      set({ healthStatus: allOk ? 'online' : 'partial' })
    } catch {
      set({ healthStatus: 'offline' })
    }
  },

  setError: (error) => set({ error }),
  clearError: () => set({ error: null }),

  generateScenario: async (query, difficulty, language) => {
    const { selectedType } = get()
    
    set({ isGenerating: true, generationStep: 'planning', scenario: null, testResults: null, error: null })
    
    try {
      set({ generationStep: 'generating' })
      
      const res = await fetch(`${API_BASE}/api/generate/scenario`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          difficulty,
          language,
          scenario_type: selectedType
        })
      })

      if (!res.ok) {
        throw new Error(`HTTP error: ${res.status}`)
      }
      
      const result = await res.json()
      
      // Check for error in response
      if (result.error) {
        throw new Error(result.error)
      }
      
      if (!result.id) {
        throw new Error('Invalid response: missing scenario id')
      }
      
      set({ 
        scenario: result, 
        currentStepIndex: 0, 
        earnedPoints: 0, 
        usedHints: [],
        generationStep: 'done'
      })
    } catch (e) {
      console.error('Generate scenario error:', e)
      set({ generationStep: null, error: e.message })
    } finally {
      set({ isGenerating: false })
    }
  },

  runCode: async (code, input) => {
    set({ runOutput: { status: 'running', output: '' } })
    
    try {
      const res = await fetch(`${API_BASE}/api/code/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, input })
      })

      const result = await res.json()
      
      if (result.stderr) {
        set({ runOutput: { status: 'error', output: result.stderr } })
      } else {
        set({ runOutput: { status: 'success', output: result.stdout || '(empty output)' } })
      }
    } catch (e) {
      set({ runOutput: { status: 'error', output: e.message } })
    }
  },

  submitSolution: async (code) => {
    const { scenario, usedHints } = get()
    
    set({ testResults: { status: 'running' } })
    
    try {
      const res = await fetch(`${API_BASE}/api/code/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          code, 
          test_cases: scenario?.metadata?.test_cases || [],
          original_code: scenario?.metadata?.original_code,
          task_type: scenario?.metadata?.task_type || scenario?.type
        })
      })

      const result = await res.json()
      
      if (result.error === 'unchanged_code') {
        set({ 
          testResults: { 
            status: 'unchanged', 
            message: result.message 
          },
          earnedPoints: 0
        })
        return
      }
      
      const maxPoints = scenario?.total_points || 100
      const hintPenalty = usedHints.reduce((sum, i) => {
        const hint = scenario?.metadata?.hints?.[i]
        return sum + (hint?.penalty_percent || 10)
      }, 0)
      
      let basePoints = result.earned_points !== undefined 
        ? result.earned_points 
        : (result.all_passed ? maxPoints : Math.floor(maxPoints * (result.passed / (result.passed + result.failed))))
      
      const earnedPoints = Math.max(0, Math.floor(basePoints * (1 - hintPenalty / 100)))
      
      set({ 
        testResults: { 
          status: 'done',
          ...result 
        },
        earnedPoints
      })
    } catch (e) {
      set({ testResults: { status: 'error', message: e.message } })
    }
  },

  useHint: (index) => {
    const { usedHints } = get()
    if (!usedHints.includes(index)) {
      set({ usedHints: [...usedHints, index] })
    }
  },

  reset: () => set({
    scenario: null,
    currentStepIndex: 0,
    earnedPoints: 0,
    usedHints: [],
    testResults: null,
    runOutput: null,
    error: null
  })
}))
