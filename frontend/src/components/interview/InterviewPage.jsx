import { useInterviewStore } from '../../store/useInterviewStore'
import InterviewStart from './InterviewStart'
import InterviewChat from './InterviewChat'
import InterviewCodeEditor from './InterviewCodeEditor'
import InterviewProgress from './InterviewProgress'
import InterviewResults from './InterviewResults'
import AIJudgePanel from './AIJudgePanel'
import LiveCodingAnnouncement from './LiveCodingAnnouncement'
import { LogOut, SkipForward, ArrowLeft } from 'lucide-react'

export default function InterviewPage() {
  const {
    sessionId,
    isLiveCoding,
    isLiveCodingPending,
    interviewComplete,
    skipStep,
    endInterview,
    exitLiveCoding,
    isLoading
  } = useInterviewStore()

  // Show results if interview is complete
  if (interviewComplete) {
    return <InterviewResults />
  }

  // Show start screen if no session
  if (!sessionId) {
    return <InterviewStart />
  }

  // Main interview view
  return (
    <div className="min-h-screen bg-bento-bg">
      {/* Header */}
      <header className="bg-bento-card border-b border-bento-border">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {isLiveCoding && (
              <button
                onClick={exitLiveCoding}
                className="px-3 py-1.5 text-sm text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10 rounded-lg flex items-center gap-1 transition-colors"
              >
                <ArrowLeft className="w-4 h-4" />
                К чату
              </button>
            )}
            <h1 className="text-xl font-bold text-white">
              {isLiveCoding ? 'Live Coding' : isLiveCodingPending ? 'Переход к Live Coding' : 'HR Интервью'}
            </h1>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={skipStep}
              disabled={isLoading}
              className="px-3 py-1.5 text-sm text-bento-muted hover:text-white hover:bg-bento-hover rounded-lg flex items-center gap-1 disabled:opacity-50 transition-colors"
            >
              <SkipForward className="w-4 h-4" />
              Пропустить
            </button>
            <button
              onClick={endInterview}
              disabled={isLoading}
              className="px-3 py-1.5 text-sm text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg flex items-center gap-1 disabled:opacity-50 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Завершить
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto p-4">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-[calc(100vh-120px)]">
          {/* Left: Progress */}
          <div className="lg:col-span-2 h-full overflow-hidden">
            <InterviewProgress />
          </div>

          {/* Center: Chat, Code Editor, or Live Coding Announcement */}
          <div className="lg:col-span-7 h-full">
            {isLiveCoding ? (
              <InterviewCodeEditor />
            ) : isLiveCodingPending ? (
              <LiveCodingAnnouncement />
            ) : (
              <InterviewChat />
            )}
          </div>

          {/* Right: AI Judge Panel */}
          <div className="lg:col-span-3 h-full">
            <AIJudgePanel />
          </div>
        </div>
      </main>
    </div>
  )
}
