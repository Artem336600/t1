import { useStore } from '../store/useStore'
import { Terminal, Circle, Star } from 'lucide-react'

export default function Header() {
  const { healthStatus, earnedPoints, scenario } = useStore()

  const statusColors = {
    online: 'text-green-500',
    partial: 'text-yellow-500',
    offline: 'text-red-500',
    checking: 'text-neutral-500'
  }

  const statusText = {
    online: 'Online',
    partial: 'Partial',
    offline: 'Offline',
    checking: '...'
  }

  return (
    <header className="border-b border-bento-border bg-bento-card/50 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 md:px-6 h-14 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-white rounded-lg flex items-center justify-center">
            <Terminal className="w-4 h-4 text-black" />
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-tight">Interview Prep</h1>
            <p className="text-[10px] text-bento-muted uppercase tracking-wider">Platform</p>
          </div>
        </div>

        {/* Status */}
        <div className="flex items-center gap-4">
          {/* Health Status */}
          <div className="flex items-center gap-2 text-xs text-bento-muted">
            <Circle className={`w-2 h-2 fill-current ${statusColors[healthStatus]}`} />
            <span>{statusText[healthStatus]}</span>
          </div>

          {/* Points */}
          {scenario && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-bento-card border border-bento-border rounded-lg">
              <Star className="w-3.5 h-3.5 text-white" />
              <span className="text-sm font-medium">{earnedPoints}</span>
              <span className="text-xs text-bento-muted">pts</span>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
