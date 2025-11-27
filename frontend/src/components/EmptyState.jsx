import { Code2, Bug, FileCode, Search, RefreshCw, Layers, Eye, MessageSquare, Zap, TestTube, Sparkles } from 'lucide-react'

export default function EmptyState() {
  const examples = [
    { icon: Bug, label: 'Исправить баги' },
    { icon: FileCode, label: 'Дописать код' },
    { icon: Search, label: 'Найти баг' },
    { icon: RefreshCw, label: 'Рефакторинг' },
    { icon: Layers, label: 'Многошаговая' },
    { icon: Eye, label: 'Код-ревью' },
    { icon: MessageSquare, label: 'Объяснить' },
    { icon: Zap, label: 'Оптимизация' },
    { icon: TestTube, label: 'Тесты' },
    { icon: Sparkles, label: 'С нуля' },
  ]

  return (
    <div className="bg-bento-card border border-bento-border rounded-2xl p-8 md:p-12 text-center animate-fade-in">
      <div className="w-16 h-16 mx-auto mb-6 bg-bento-bg border border-bento-border rounded-2xl flex items-center justify-center">
        <Code2 className="w-8 h-8 text-bento-muted" />
      </div>
      
      <h3 className="text-lg font-semibold mb-2">Выберите тип задачи</h3>
      <p className="text-sm text-bento-muted mb-8 max-w-md mx-auto">
        Выберите тип сценария слева, введите тему и нажмите "Создать" для генерации задачи
      </p>

      {/* Example Types Grid */}
      <div className="grid grid-cols-5 md:grid-cols-10 gap-2 max-w-2xl mx-auto">
        {examples.map(({ icon: Icon, label }, i) => (
          <div 
            key={i}
            className="aspect-square bg-bento-bg border border-bento-border rounded-xl flex flex-col items-center justify-center p-2 group hover:border-bento-subtle transition-colors"
          >
            <Icon className="w-4 h-4 text-bento-muted group-hover:text-white transition-colors" />
            <span className="text-[8px] text-bento-muted mt-1 group-hover:text-white transition-colors hidden md:block">
              {label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
