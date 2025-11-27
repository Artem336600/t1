import { create } from 'zustand'

const API_BASE = ''

export const useInterviewStore = create((set, get) => ({
  // State
  sessionId: null,
  candidateName: '',
  messages: [],
  currentStep: null,
  totalSteps: 0,
  currentLevel: 'junior',
  scores: {},
  isLoading: false,
  isLiveCoding: false,
  isLiveCodingPending: false,  // Waiting for user to click "Start Live Coding"
  liveCodingTask: null,
  interviewComplete: false,
  finalResult: null,
  error: null,
  
  // Interview schema (from React Flow)
  schema: null,

  // Actions
  setSchema: (schema) => set({ schema }),
  setCandidateName: (name) => set({ candidateName: name }),

  startInterview: async (schema, candidateName) => {
    set({ isLoading: true, error: null })
    
    // Add streaming message placeholder
    const streamingMessage = {
      role: 'assistant',
      content: '',
      isStreaming: true,
      timestamp: new Date().toISOString()
    }
    set({ messages: [streamingMessage] })
    
    try {
      const res = await fetch(`${API_BASE}/api/interview/start/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nodes: schema.nodes,
          edges: schema.edges,
          candidate_name: candidateName || 'Кандидат'
        })
      })

      if (!res.ok) {
        throw new Error(`HTTP error: ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let fullContent = ''
      let sessionId = null
      let currentStep = null
      let totalSteps = 0

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              
              if (data.type === 'session') {
                sessionId = data.session_id
                currentStep = data.current_step
                totalSteps = data.total_steps
              } else if (data.type === 'chunk') {
                fullContent += data.content
                // Update streaming message
                set({ 
                  messages: [{
                    role: 'assistant',
                    content: fullContent,
                    isStreaming: true,
                    timestamp: new Date().toISOString()
                  }]
                })
              } else if (data.type === 'done') {
                set({
                  sessionId,
                  currentStep,
                  totalSteps,
                  isLiveCoding: data.is_live_coding,
                  schema: schema,
                  messages: [{
                    role: 'assistant',
                    content: fullContent,
                    isStreaming: false,
                    timestamp: new Date().toISOString()
                  }],
                  isLoading: false
                })
                return { session_id: sessionId }
              } else if (data.type === 'error') {
                throw new Error(data.error)
              }
            } catch (parseError) {
              // Skip invalid JSON lines
            }
          }
        }
      }
    } catch (e) {
      set({ error: e.message, isLoading: false, messages: [] })
      throw e
    }
  },

  sendMessage: async (message) => {
    const { sessionId, messages } = get()
    
    if (!sessionId) {
      set({ error: 'No active session' })
      return
    }

    // Add user message immediately
    const userMessage = {
      role: 'user',
      content: message,
      timestamp: new Date().toISOString()
    }
    
    // Add placeholder for streaming response
    const streamingMessage = {
      role: 'assistant',
      content: '',
      isStreaming: true,
      timestamp: new Date().toISOString()
    }
    
    set({ 
      messages: [...messages, userMessage, streamingMessage], 
      isLoading: true, 
      error: null 
    })

    try {
      const res = await fetch(`${API_BASE}/api/interview/message/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          message
        })
      })

      if (!res.ok) {
        throw new Error(`HTTP error: ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let fullContent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              
              if (data.type === 'chunk') {
                fullContent += data.content
                // Update streaming message
                const currentMessages = get().messages
                const lastIdx = currentMessages.length - 1
                if (currentMessages[lastIdx]?.isStreaming) {
                  const updated = [...currentMessages]
                  updated[lastIdx] = {
                    ...updated[lastIdx],
                    content: fullContent
                  }
                  set({ messages: updated })
                }
              } else if (data.type === 'done') {
                // Finalize messages - user can now continue typing
                const currentMessages = get().messages
                const finalMessages = currentMessages.map(m => ({
                  ...m,
                  isStreaming: false,
                  isTransition: false
                }))

                set({
                  messages: finalMessages,
                  currentStep: data.next_step || data.current_step,
                  // If entering live coding, set pending state (user needs to click button)
                  isLiveCodingPending: data.entering_live_coding || false,
                  isLiveCoding: data.requires_code || false,
                  liveCodingTask: data.live_coding_task || null,
                  interviewComplete: data.interview_complete || false,
                  finalResult: data.final_result || null,
                  isLoading: false  // User can type now!
                })
                
                // Don't return yet - wait for evaluation event
              } else if (data.type === 'evaluation') {
                // Evaluation came in separately - update scores without blocking
                const { scores, messages: currentMsgs } = get()
                
                // Update scores
                if (data.step_id) {
                  set({
                    scores: {
                      ...scores,
                      [data.step_id]: {
                        earned: data.evaluation.points,
                        max: data.evaluation.max_points,
                        feedback: data.evaluation.feedback
                      }
                    }
                  })
                }
                
                // Add evaluation to the last assistant message for this step
                const updatedMsgs = currentMsgs.map(m => {
                  if (m.role === 'assistant' && m.content === fullContent && !m.evaluation) {
                    return { ...m, evaluation: data.evaluation }
                  }
                  return m
                })
                set({ messages: updatedMsgs })
                
                return data
              } else if (data.type === 'error') {
                throw new Error(data.error)
              }
            } catch (parseError) {
              // Skip invalid JSON lines
            }
          }
        }
      }
    } catch (e) {
      set({ error: e.message, isLoading: false })
      // Remove streaming message on error
      const currentMessages = get().messages
      set({ messages: currentMessages.filter(m => !m.isStreaming) })
      throw e
    }
  },

  // Start Live Coding mode (user clicked the button)
  startLiveCoding: async () => {
    const { sessionId, messages } = get()
    
    set({ 
      isLiveCodingPending: false, 
      isLiveCoding: true,
      isLoading: true 
    })
    
    // Request live coding task from server
    try {
      const res = await fetch(`${API_BASE}/api/interview/${sessionId}/start-live-coding`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      
      if (res.ok) {
        const result = await res.json()
        set({
          liveCodingTask: result.task,
          currentStep: result.current_step,
          messages: [...messages, {
            role: 'assistant',
            content: result.message || 'Отлично! Давайте приступим к практическому заданию. Внимательно прочитайте условие задачи и напишите решение.',
            timestamp: new Date().toISOString()
          }],
          isLoading: false
        })
      } else {
        set({ isLoading: false })
      }
    } catch (e) {
      set({ error: e.message, isLoading: false })
    }
  },

  // Exit Live Coding mode and return to chat
  exitLiveCoding: () => {
    set({ 
      isLiveCoding: false, 
      isLiveCodingPending: false,
      liveCodingTask: null 
    })
  },

  submitCode: async (code, language = 'python') => {
    const { sessionId, messages } = get()
    
    if (!sessionId) {
      set({ error: 'No active session' })
      return
    }

    // Add code submission message
    const codeMessage = {
      role: 'user',
      content: `\`\`\`${language}\n${code}\n\`\`\``,
      isCode: true,
      timestamp: new Date().toISOString()
    }
    set({ messages: [...messages, codeMessage], isLoading: true, error: null })

    try {
      const res = await fetch(`${API_BASE}/api/interview/code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          code,
          language
        })
      })

      if (!res.ok) {
        throw new Error(`HTTP error: ${res.status}`)
      }

      const result = await res.json()
      
      if (result.error) {
        throw new Error(result.error)
      }

      // Add evaluation response
      const evalMessage = {
        role: 'assistant',
        content: result.evaluation?.feedback || 'Код получен.',
        evaluation: result.evaluation,
        testResults: result.evaluation?.test_results,
        timestamp: new Date().toISOString()
      }

      const newMessages = [...get().messages, evalMessage]

      // Handle level change
      if (result.level_change) {
        newMessages.push({
          role: 'system',
          content: result.level_change === 'up' 
            ? `Уровень повышен до ${result.level}!` 
            : `Уровень понижен до ${result.level}`,
          timestamp: new Date().toISOString()
        })
      }

      // Handle next message
      if (result.next_message) {
        newMessages.push({
          role: 'assistant',
          content: result.next_message,
          timestamp: new Date().toISOString()
        })
      }

      set({
        messages: newMessages,
        currentStep: result.next_step || result.current_step,
        currentLevel: result.level || get().currentLevel,
        isLiveCoding: result.requires_code || false,
        liveCodingTask: result.live_coding_task || null,
        interviewComplete: result.interview_complete || false,
        finalResult: result.final_result || null
      })

      // Update scores
      if (result.evaluation && result.current_step) {
        const { scores } = get()
        set({
          scores: {
            ...scores,
            [result.current_step.id]: {
              earned: result.evaluation.points,
              max: result.evaluation.max_points
            }
          }
        })
      }

      return result
    } catch (e) {
      set({ error: e.message })
      throw e
    } finally {
      set({ isLoading: false })
    }
  },

  skipStep: async () => {
    const { sessionId, messages } = get()
    
    if (!sessionId) return

    set({ isLoading: true })

    try {
      const res = await fetch(`${API_BASE}/api/interview/${sessionId}/skip`, {
        method: 'POST'
      })

      const result = await res.json()

      set({
        messages: [...messages, {
          role: 'system',
          content: 'Этап пропущен',
          timestamp: new Date().toISOString()
        }],
        currentStep: result.next_step || get().currentStep,
        interviewComplete: result.interview_complete || false,
        finalResult: result.final_result || null,
        isLiveCoding: false,
        liveCodingTask: null
      })

      return result
    } catch (e) {
      set({ error: e.message })
    } finally {
      set({ isLoading: false })
    }
  },

  endInterview: async () => {
    const { sessionId } = get()
    
    if (!sessionId) return

    set({ isLoading: true })

    try {
      const res = await fetch(`${API_BASE}/api/interview/${sessionId}/end`, {
        method: 'POST'
      })

      const result = await res.json()

      set({
        interviewComplete: true,
        finalResult: result
      })

      return result
    } catch (e) {
      set({ error: e.message })
    } finally {
      set({ isLoading: false })
    }
  },

  getStatus: async () => {
    const { sessionId } = get()
    
    if (!sessionId) return null

    try {
      const res = await fetch(`${API_BASE}/api/interview/${sessionId}/status`)
      return await res.json()
    } catch (e) {
      set({ error: e.message })
      return null
    }
  },

  reset: () => set({
    sessionId: null,
    messages: [],
    currentStep: null,
    totalSteps: 0,
    currentLevel: 'junior',
    scores: {},
    isLoading: false,
    isLiveCoding: false,
    liveCodingTask: null,
    interviewComplete: false,
    finalResult: null,
    error: null,
    schema: null
  }),

  clearError: () => set({ error: null }),

  // Calculate total score
  getTotalScore: () => {
    const { scores } = get()
    let earned = 0
    let max = 0
    
    Object.values(scores).forEach(s => {
      earned += s.earned || 0
      max += s.max || 0
    })
    
    return { earned, max, percent: max > 0 ? Math.round(earned / max * 100) : 0 }
  }
}))
