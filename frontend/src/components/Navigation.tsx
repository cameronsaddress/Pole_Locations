interface NavigationProps {
  currentPage: string
  onNavigate: (page: string) => void
}

export default function Navigation({ currentPage, onNavigate }: NavigationProps) {
  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'map', label: 'Map View', icon: '🗺️' },
    { id: 'performance', label: 'AI Performance', icon: '🎯' },
    { id: 'review', label: 'Review Queue', icon: '✓' },
    { id: 'analytics', label: 'Analytics', icon: '📈' },
    { id: 'diff', label: 'Diff Viewer', icon: '🔄' },
    { id: 'labeler', label: 'Labeling Tool', icon: '🖱️' },
  ]

  return (
    <nav className="bg-white border-b border-border shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex space-x-8">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => onNavigate(tab.id)}
              className={`
                py-4 px-1 border-b-2 font-medium text-sm transition-colors
                ${currentPage === tab.id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted hover:text-foreground hover:border-gray-300'
                }
              `}
            >
              <span className="mr-2">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>
      </div>
    </nav>
  )
}
