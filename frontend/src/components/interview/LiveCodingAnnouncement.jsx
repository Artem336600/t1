import { Code2, ArrowRight, Terminal, Sparkles } from 'lucide-react'
import { useInterviewStore } from '../../store/useInterviewStore'

export default function LiveCodingAnnouncement() {
  const { startLiveCoding, currentStep, isLoading } = useInterviewStore()

  return (
    <div className="h-full flex items-center justify-center bg-bento-bg p-8">
      <div className="max-w-lg w-full">
        {/* Announcement Card */}
        <div className="bg-gradient-to-br from-indigo-500/20 to-purple-500/20 border border-indigo-500/30 rounded-2xl p-8 text-center">
          {/* Icon */}
          <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-indigo-500/20 flex items-center justify-center">
            <Code2 className="w-10 h-10 text-indigo-400" />
          </div>

          {/* Title */}
          <h2 className="text-2xl font-bold text-white mb-3">
            Переходим к Live Coding
          </h2>

          {/* Description */}
          <p className="text-gray-300 mb-6">
            Отличная работа на теоретической части! Теперь давайте проверим ваши 
            практические навыки программирования.
          </p>

          {/* Current Step Info */}
          {currentStep && (
            <div className="bg-bento-card/50 rounded-xl p-4 mb-6 text-left">
              <div className="flex items-center gap-2 text-indigo-400 text-sm mb-2">
                <Terminal className="w-4 h-4" />
                <span>Следующий этап</span>
              </div>
              <p className="text-white font-medium">{currentStep.label}</p>
              {currentStep.description && (
                <p className="text-gray-400 text-sm mt-1">{currentStep.description}</p>
              )}
            </div>
          )}

          {/* What to expect */}
          <div className="bg-bento-card/50 rounded-xl p-4 mb-6 text-left">
            <div className="flex items-center gap-2 text-purple-400 text-sm mb-3">
              <Sparkles className="w-4 h-4" />
              <span>Что вас ждёт</span>
            </div>
            <ul className="text-gray-300 text-sm space-y-2">
              <li className="flex items-start gap-2">
                <span className="text-indigo-400 mt-0.5">•</span>
                <span>Браузерная IDE с подсветкой синтаксиса</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-400 mt-0.5">•</span>
                <span>Возможность запустить и протестировать код</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-400 mt-0.5">•</span>
                <span>Подсказки от HR-бота при необходимости</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-400 mt-0.5">•</span>
                <span>Автоматическая оценка решения</span>
              </li>
            </ul>
          </div>

          {/* Start Button */}
          <button
            onClick={startLiveCoding}
            disabled={isLoading}
            className="w-full py-4 px-6 bg-indigo-500 hover:bg-indigo-600 disabled:bg-indigo-500/50 text-white font-semibold rounded-xl flex items-center justify-center gap-3 transition-all transform hover:scale-[1.02] disabled:scale-100"
          >
            {isLoading ? (
              <>
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Загрузка задания...
              </>
            ) : (
              <>
                Начать Live Coding
                <ArrowRight className="w-5 h-5" />
              </>
            )}
          </button>

          {/* Skip hint */}
          <p className="text-gray-500 text-xs mt-4">
            Вы можете пропустить этот этап, нажав "Пропустить" в верхнем меню
          </p>
        </div>
      </div>
    </div>
  )
}
