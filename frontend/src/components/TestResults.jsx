import { useStore } from '../store/useStore'
import { CheckCircle, XCircle, Clock, AlertTriangle, Loader2 } from 'lucide-react'

export default function TestResults() {
  const { testResults, earnedPoints } = useStore()

  if (!testResults) return null

  if (testResults.status === 'running') {
    return (
      <div className="bg-bento-card border border-bento-border rounded-2xl p-6">
        <div className="flex items-center gap-3 text-bento-muted">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Запуск тестов...</span>
        </div>
      </div>
    )
  }

  if (testResults.status === 'unchanged') {
    return (
      <div className="bg-bento-card border border-red-500/20 rounded-2xl p-6">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 bg-red-500/10 rounded-xl flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-red-400" />
          </div>
          <div>
            <h3 className="font-semibold text-red-400">Код не изменён</h3>
            <p className="text-sm text-bento-muted">{testResults.message}</p>
          </div>
        </div>
        <div className="text-3xl font-bold text-red-400">0 баллов</div>
      </div>
    )
  }

  if (testResults.status === 'error') {
    return (
      <div className="bg-bento-card border border-red-500/20 rounded-2xl p-6">
        <div className="flex items-center gap-3 text-red-400">
          <XCircle className="w-5 h-5" />
          <span>Ошибка: {testResults.message}</span>
        </div>
      </div>
    )
  }

  const { passed = 0, failed = 0, all_passed, tests = [] } = testResults
  const total = passed + failed

  return (
    <div className="bg-bento-card border border-bento-border rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-bento-border">
        <div className="flex items-center gap-3">
          <div className={`
            w-10 h-10 rounded-xl flex items-center justify-center
            ${all_passed ? 'bg-green-500/10' : 'bg-yellow-500/10'}
          `}>
            {all_passed ? (
              <CheckCircle className="w-5 h-5 text-green-400" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-yellow-400" />
            )}
          </div>
          <div>
            <h3 className="font-semibold">
              {passed}/{total} тестов пройдено
            </h3>
            <p className="text-xs text-bento-muted">
              {all_passed ? 'Все тесты успешно пройдены' : `${failed} тестов не пройдено`}
            </p>
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold">+{earnedPoints}</div>
          <div className="text-[10px] text-bento-muted uppercase tracking-wider">баллов</div>
        </div>
      </div>

      {/* Test List */}
      <div className="max-h-80 overflow-y-auto divide-y divide-bento-border">
        {tests.map((test, i) => (
          <TestItem key={i} test={test} index={i} />
        ))}
      </div>
    </div>
  )
}

function TestItem({ test, index }) {
  const isPassed = test.passed
  const isTimeExceeded = test.failure_reason === 'time_limit_exceeded'

  return (
    <div className={`p-4 ${!isPassed ? 'bg-red-500/5' : ''}`}>
      <div className="flex items-center gap-3 mb-3">
        <div className={`
          w-6 h-6 rounded-lg flex items-center justify-center
          ${isPassed ? 'bg-green-500/10 text-green-400' : isTimeExceeded ? 'bg-orange-500/10 text-orange-400' : 'bg-red-500/10 text-red-400'}
        `}>
          {isPassed ? <CheckCircle className="w-3.5 h-3.5" /> : isTimeExceeded ? <Clock className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
        </div>
        <span className="text-sm font-medium">Тест {test.num || index + 1}</span>
        {test.execution_time_ms && (
          <span className={`text-xs ${isTimeExceeded ? 'text-orange-400' : 'text-bento-muted'}`}>
            {test.execution_time_ms.toFixed(0)}ms
            {test.time_limit_ms && ` / ${test.time_limit_ms}ms`}
          </span>
        )}
        {test.points && (
          <span className={`text-xs ml-auto ${isPassed ? 'text-green-400' : 'text-bento-muted'}`}>
            +{isPassed ? test.points : 0} pts
          </span>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 text-xs">
        <div>
          <div className="text-[10px] text-bento-muted uppercase tracking-wider mb-1">Вход</div>
          <pre className="bg-bento-bg rounded-lg p-2 font-mono text-neutral-300 overflow-x-auto whitespace-pre-wrap max-h-20">
            {test.input || '-'}
          </pre>
        </div>
        <div>
          <div className="text-[10px] text-bento-muted uppercase tracking-wider mb-1">Ожидалось</div>
          <pre className="bg-bento-bg rounded-lg p-2 font-mono text-blue-400 overflow-x-auto whitespace-pre-wrap max-h-20">
            {test.expected || '-'}
          </pre>
        </div>
        <div>
          <div className="text-[10px] text-bento-muted uppercase tracking-wider mb-1">Получено</div>
          <pre className={`bg-bento-bg rounded-lg p-2 font-mono overflow-x-auto whitespace-pre-wrap max-h-20 ${isPassed ? 'text-green-400' : 'text-red-400'}`}>
            {test.actual || '-'}
          </pre>
        </div>
      </div>

      {test.error && (
        <div className="mt-2 text-xs text-red-400 bg-red-500/10 rounded-lg p-2">
          {test.error}
        </div>
      )}
    </div>
  )
}
