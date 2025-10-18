import { useState } from 'react'
import Navigation from './components/Navigation'
import Dashboard from './pages/Dashboard'
import MapView from './pages/MapView'
import ModelPerformance from './pages/ModelPerformance'
import ReviewQueue from './pages/ReviewQueue'
import Analytics from './pages/Analytics'
import DiffViewer from './pages/DiffViewer'
import './App.css'

function App() {
  const [currentPage, setCurrentPage] = useState('dashboard')

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <Dashboard />
      case 'map':
        return <MapView />
      case 'performance':
        return <ModelPerformance />
      case 'review':
        return <ReviewQueue />
      case 'analytics':
        return <Analytics />
      case 'diff':
        return <DiffViewer />
      default:
        return <Dashboard />
    }
  }

  return (
    <div className="min-h-screen bg-background">
      {currentPage !== 'dashboard' && (
        <>
          <header className="bg-white border-b border-gray-200 shadow-sm">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="py-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h1 className="text-4xl font-bold text-primary">PoleVision AI</h1>
                    <p className="mt-1 text-lg text-muted">Enterprise Pole Verification System</p>
                  </div>
                  <div className="flex items-center space-x-4">
                    <div className="text-right">
                      <div className="text-sm text-muted">Powered by AI</div>
                      <div className="text-lg font-semibold text-foreground">95.4% Accurate</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </header>
        </>
      )}
      <Navigation currentPage={currentPage} onNavigate={setCurrentPage} />
      {renderPage()}
    </div>
  )
}

export default App
