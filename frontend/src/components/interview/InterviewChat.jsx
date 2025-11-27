import { useState, useRef, useEffect } from 'react'
import { Send, Loader2, User, Bot, AlertCircle, CheckCircle, XCircle } from 'lucide-react'
import { useInterviewStore } from '../../store/useInterviewStore'

export default function InterviewChat() {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  
  const {
    messages,
    isLoading,
    currentStep,
    isLiveCoding,
    error,
    sendMessage,
    clearError
  } = useInterviewStore()

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || isLoading || isLiveCoding) return
    
    const message = input.trim()
    setInput('')
    
    try {
      await sendMessage(message)
    } catch (e) {
      console.error('Send message error:', e)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const renderMessage = (msg, index) => {
    const isUser = msg.role === 'user'
    const isSystem = msg.role === 'system'
    
    if (isSystem) {
      return (
        <div key={index} className="flex justify-center my-2">
          <div className="bg-indigo-500/20 text-indigo-300 px-4 py-2 rounded-full text-sm border border-indigo-500/30">
            {msg.content}
          </div>
        </div>
      )
    }

    return (
      <div
        key={index}
        className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
      >
        {/* Avatar */}
        <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? 'bg-indigo-500' : 'bg-bento-subtle'
        }`}>
          {isUser ? (
            <User className="w-4 h-4 text-white" />
          ) : (
            <Bot className="w-4 h-4 text-white" />
          )}
        </div>

        {/* Message bubble */}
        <div className={`max-w-[75%] ${isUser ? 'text-right' : ''}`}>
          <div className={`rounded-2xl px-4 py-2 ${
            isUser 
              ? 'bg-indigo-500 text-white rounded-tr-sm' 
              : 'bg-bento-hover text-gray-100 rounded-tl-sm'
          }`}>
            {msg.isCode ? (
              <pre className="text-sm overflow-x-auto whitespace-pre-wrap">
                <code>{msg.content}</code>
              </pre>
            ) : (
              <p className="whitespace-pre-wrap">
                {/* Filter out <think> tags from display */}
                {msg.content.replace(/<think>[\s\S]*?<\/think>/g, '').replace(/<\/?think>/g, '').trim()}
              </p>
            )}
            {msg.isStreaming && (
              <span className="inline-block w-2 h-4 bg-indigo-400 animate-pulse ml-1" />
            )}
          </div>

          {/* Evaluation badge */}
          {msg.evaluation && (
            <div className="mt-2 flex items-center gap-2 text-sm">
              {msg.evaluation.points >= msg.evaluation.max_points * 0.7 ? (
                <CheckCircle className="w-4 h-4 text-green-400" />
              ) : msg.evaluation.points >= msg.evaluation.max_points * 0.4 ? (
                <AlertCircle className="w-4 h-4 text-yellow-400" />
              ) : (
                <XCircle className="w-4 h-4 text-red-400" />
              )}
              <span className="text-gray-300">
                {msg.evaluation.points}/{msg.evaluation.max_points} баллов
              </span>
            </div>
          )}

          {/* Timestamp */}
          <div className={`text-xs text-bento-muted mt-1 ${isUser ? 'text-right' : ''}`}>
            {new Date(msg.timestamp).toLocaleTimeString('ru-RU', { 
              hour: '2-digit', 
              minute: '2-digit' 
            })}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-bento-card border border-bento-border rounded-xl overflow-hidden">
      {/* Header */}
      <div className="bg-bento-hover border-b border-bento-border px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-white font-semibold">HR Интервью</h2>
            {currentStep && (
              <p className="text-bento-muted text-sm">
                {currentStep.label}
              </p>
            )}
          </div>
          {currentStep?.points && (
            <div className="bg-indigo-500/20 border border-indigo-500/30 px-3 py-1 rounded-full">
              <span className="text-indigo-300 text-sm">
                {currentStep.points} баллов
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-bento-bg">
        {messages.map((msg, i) => renderMessage(msg, i))}
        
        {/* Only show loading if no streaming message exists */}
        {isLoading && !messages.some(m => m.isStreaming) && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-bento-subtle flex items-center justify-center">
              <Bot className="w-4 h-4 text-white" />
            </div>
            <div className="bg-bento-hover rounded-2xl rounded-tl-sm px-4 py-3">
              <Loader2 className="w-5 h-5 animate-spin text-bento-muted" />
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Error */}
      {error && (
        <div className="mx-4 mb-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-400" />
          <span className="text-red-300 text-sm">{error}</span>
          <button 
            onClick={clearError}
            className="ml-auto text-red-400 hover:text-red-300"
          >
            &times;
          </button>
        </div>
      )}

      {/* Live Coding Notice */}
      {isLiveCoding && (
        <div className="mx-4 mb-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
          <p className="text-amber-300 text-sm">
            Для этого этапа требуется написать код. Используйте редактор кода справа.
          </p>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-bento-border p-4 bg-bento-card">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={isLiveCoding ? "Используйте редактор кода..." : "Введите ответ..."}
            disabled={isLoading || isLiveCoding}
            className="flex-1 resize-none bg-bento-bg border border-bento-border rounded-xl px-4 py-2 text-white placeholder-bento-muted focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:bg-bento-hover disabled:text-bento-muted"
            rows={2}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading || isLiveCoding}
            className="px-4 py-2 bg-indigo-500 text-white rounded-xl hover:bg-indigo-600 disabled:bg-bento-subtle disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
