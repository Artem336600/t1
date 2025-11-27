import { useStore } from '../store/useStore'
import * as Icons from 'lucide-react'

export default function ScenarioSelector() {
  const { scenarioTypes, selectedType, setSelectedType } = useStore()

  return (
    <div className="bg-bento-card border border-bento-border rounded-2xl p-4 h-full">
      <h2 className="text-xs font-medium text-bento-muted uppercase tracking-wider mb-4">
        Тип задачи
      </h2>
      
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(scenarioTypes).map(([id, type]) => {
          const Icon = Icons[type.icon] || Icons.Code
          const isSelected = selectedType === id
          
          return (
            <button
              key={id}
              onClick={() => setSelectedType(id)}
              className={`
                group relative p-3 rounded-xl text-left transition-all duration-200
                ${isSelected 
                  ? 'bg-white text-black' 
                  : 'bg-bento-bg border border-bento-border hover:border-bento-subtle'
                }
              `}
            >
              <Icon className={`w-4 h-4 mb-2 ${isSelected ? 'text-black' : 'text-bento-muted group-hover:text-white'}`} />
              <div className={`text-xs font-medium ${isSelected ? 'text-black' : 'text-white'}`}>
                {type.name}
              </div>
              <div className={`text-[10px] mt-0.5 ${isSelected ? 'text-neutral-600' : 'text-bento-muted'}`}>
                {type.desc}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
