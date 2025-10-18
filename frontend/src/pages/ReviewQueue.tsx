import { useState, useEffect } from 'react'

interface ReviewPole {
  pole_id: string
  lat: number
  lon: number
  classification: string
  total_confidence: number
  ai_confidence: number
  spatial_distance_m: number
  num_sources: number
  status_color: string
  review_priority: string
  recency_score?: number
  inspection_date?: string | null
  days_since_inspection?: number | null
  sla_days_remaining?: number | null
}

export default function ReviewQueue() {
  const [poles, setPoles] = useState<ReviewPole[]>([])
  const [loading, setLoading] = useState(true)
  const [currentPage, setCurrentPage] = useState(0)
  const [totalPoles, setTotalPoles] = useState(0)
  const [selectedPole, setSelectedPole] = useState<ReviewPole | null>(null)
  const itemsPerPage = 50

  useEffect(() => {
    loadReviewQueue(currentPage)
  }, [currentPage])

  const loadReviewQueue = (page: number) => {
    setLoading(true)
    const skip = page * itemsPerPage

    fetch(`/api/v1/verification/review-queue?skip=${skip}&limit=${itemsPerPage}`)
      .then(res => res.json())
      .then(data => {
        setPoles(data.poles || [])
        setTotalPoles(data.total || 0)
        setLoading(false)
      })
      .catch(err => {
        console.error('Failed to fetch review queue:', err)
        setLoading(false)
      })
  }

  const getPriorityBadge = (priority: string) => {
    if (priority === 'high') {
      return <span className="px-2 py-1 text-xs font-bold rounded-full bg-red-100 text-red-800">HIGH</span>
    }
    return <span className="px-2 py-1 text-xs font-bold rounded-full bg-yellow-100 text-yellow-800">MEDIUM</span>
  }

  const getConfidenceColor = (confidence: number) => {
    if (confidence < 0.3) return 'text-red-600'
    if (confidence < 0.5) return 'text-orange-600'
    return 'text-yellow-600'
  }

  const getRecencyLabel = (score?: number) => {
    if (score === 1 || score === 0.8) return 'Verified <3 years'
    if (score === 0.5) return '3–5 years'
    if (score === 0.2) return '>5 years'
    return 'Unknown'
  }

  const totalPages = Math.ceil(totalPoles / itemsPerPage)

  if (loading && poles.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-2xl font-bold text-primary">Loading Review Queue...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="relative overflow-hidden shadow-2xl" style={{
        background: 'linear-gradient(135deg, #003B5C 0%, #00658F 50%, #00A1DE 100%)',
      }}>
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div>
            <h1 className="text-4xl font-bold text-white tracking-tight">
              Review Queue
            </h1>
            <p className="mt-2 text-lg text-white/90 font-medium">
              Poles requiring human verification • Multi-source cross-validation
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Summary Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow-lg p-6 border-l-4" style={{ borderColor: '#FF9800' }}>
            <div className="text-sm font-medium text-muted mb-1">Total needing review</div>
            <div className="text-4xl font-bold" style={{ color: '#FF9800' }}>{totalPoles.toLocaleString()}</div>
            <div className="text-xs text-muted mt-1">Includes all geographic regions</div>
          </div>

          <div className="bg-white rounded-lg shadow-lg p-6 border-l-4 border-red-500">
            <div className="text-sm font-medium text-muted mb-1">Overdue inspections</div>
            <div className="text-4xl font-bold text-red-600">
              {poles.filter(p => (p.recency_score ?? 1) <= 0.2).length}
            </div>
            <div className="text-xs text-muted mt-1">Inspection &gt; 5 years old</div>
          </div>

          <div className="bg-white rounded-lg shadow-lg p-6 border-l-4 border-yellow-500">
            <div className="text-sm font-medium text-muted mb-1">Single-source detections</div>
            <div className="text-4xl font-bold text-yellow-600">
              {poles.filter(p => p.num_sources === 1).length}
            </div>
            <div className="text-xs text-muted mt-1">Requires secondary validation</div>
          </div>

          <div className="bg-white rounded-lg shadow-lg p-6 border-l-4 border-primary">
            <div className="text-sm font-medium text-muted mb-1">Avg spatial offset</div>
            <div className="text-4xl font-bold text-primary">
              {poles.length ? `${(poles.reduce((acc, p) => acc + p.spatial_distance_m, 0) / poles.length).toFixed(1)} m` : '--'}
            </div>
            <div className="text-xs text-muted mt-1">Lower is better alignment</div>
          </div>
        </div>

        {/* Review Table */}
        <div className="bg-white rounded-lg shadow-lg overflow-hidden">
          <div className="px-6 py-4 bg-primary text-white">
            <h2 className="text-xl font-bold">Poles Requiring Review</h2>
            <p className="text-sm opacity-90">Sorted by confidence (lowest first = highest priority)</p>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Priority
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Pole ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Confidence
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    AI Detection
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Spatial Distance
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Sources
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Inspection Age
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    SLA Remaining
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Location
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {poles.map((pole, idx) => (
                  <tr
                    key={pole.pole_id}
                    className={`hover:bg-gray-50 cursor-pointer ${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}`}
                    onClick={() => setSelectedPole(pole)}
                  >
                    <td className="px-6 py-4 whitespace-nowrap">
                      {getPriorityBadge(pole.review_priority)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900">{pole.pole_id}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className={`text-sm font-bold ${getConfidenceColor(pole.total_confidence)}`}>
                        {(pole.total_confidence * 100).toFixed(1)}%
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-600">
                        {pole.ai_confidence > 0 ? `${(pole.ai_confidence * 100).toFixed(1)}%` : 'No detection'}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-600">
                        {pole.spatial_distance_m.toFixed(1)}m
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className={`text-sm font-semibold ${pole.num_sources === 1 ? 'text-red-600' : 'text-blue-600'}`}>
                        {pole.num_sources} source{pole.num_sources !== 1 ? 's' : ''}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-600">
                        {pole.days_since_inspection != null ? `${pole.days_since_inspection} days` : 'Unknown'}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-600">
                        {pole.sla_days_remaining != null ? `${pole.sla_days_remaining} days` : 'N/A'}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-xs text-gray-500">
                        {pole.lat.toFixed(5)}, {pole.lon.toFixed(5)}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <button
                        className="text-primary hover:text-info font-medium mr-3"
                        onClick={(e) => {
                          e.stopPropagation()
                          window.open(`/map?pole=${pole.pole_id}`, '_blank')
                        }}
                      >
                        View Map
                      </button>
                      <button
                        className="text-success hover:text-green-700 font-medium"
                        onClick={(e) => {
                          e.stopPropagation()
                          alert(`Approve pole ${pole.pole_id}? (Feature coming soon)`)
                        }}
                      >
                        Approve
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex items-center justify-between">
            <div className="text-sm text-gray-700">
              Showing <span className="font-medium">{currentPage * itemsPerPage + 1}</span> to{' '}
              <span className="font-medium">
                {Math.min((currentPage + 1) * itemsPerPage, totalPoles)}
              </span>{' '}
              of <span className="font-medium">{totalPoles.toLocaleString()}</span> poles
            </div>
            <div className="flex space-x-2">
              <button
                onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
                disabled={currentPage === 0}
                className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-info disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <button
                onClick={() => setCurrentPage(Math.min(totalPages - 1, currentPage + 1))}
                disabled={currentPage >= totalPages - 1}
                className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-info disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        </div>

        {/* Pole Detail Modal */}
        {selectedPole && (
          <div
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
            onClick={() => setSelectedPole(null)}
          >
            <div
              className="bg-white rounded-lg shadow-2xl p-8 max-w-2xl w-full m-4"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex justify-between items-start mb-6">
                <div>
                  <h3 className="text-2xl font-bold text-primary mb-2">Pole Details</h3>
                  <p className="text-sm text-gray-600">{selectedPole.pole_id}</p>
                </div>
                <button
                  onClick={() => setSelectedPole(null)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="grid grid-cols-2 gap-6 mb-6">
                <div>
                  <div className="text-sm text-gray-600 mb-1">Total Confidence</div>
                  <div className={`text-3xl font-bold ${getConfidenceColor(selectedPole.total_confidence)}`}>
                    {(selectedPole.total_confidence * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600 mb-1">Priority Level</div>
                  <div className="text-xl font-bold">
                    {getPriorityBadge(selectedPole.review_priority)}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600 mb-1">AI Detection Confidence</div>
                  <div className="text-xl font-bold text-primary">
                    {selectedPole.ai_confidence > 0 ? `${(selectedPole.ai_confidence * 100).toFixed(1)}%` : 'No detection'}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600 mb-1">Spatial Distance</div>
                  <div className="text-xl font-bold text-primary">
                    {selectedPole.spatial_distance_m.toFixed(1)}m
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600 mb-1">Number of Sources</div>
                  <div className={`text-xl font-bold ${selectedPole.num_sources === 1 ? 'text-red-600' : 'text-green-600'}`}>
                    {selectedPole.num_sources} source{selectedPole.num_sources !== 1 ? 's' : ''}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600 mb-1">Classification</div>
                  <div className="text-xl font-bold" style={{ color: selectedPole.status_color }}>
                    {selectedPole.classification.replace('_', ' ').toUpperCase()}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-6 mb-6 text-sm">
                <div>
                  <div className="text-gray-600 mb-1">Inspection date</div>
                  <div className="font-semibold text-foreground">{selectedPole.inspection_date ?? 'Unknown'}</div>
                </div>
                <div>
                  <div className="text-gray-600 mb-1">Inspection age</div>
                  <div className="font-semibold text-foreground">{getRecencyLabel(selectedPole.recency_score)}</div>
                </div>
                <div>
                  <div className="text-gray-600 mb-1">Days since inspection</div>
                  <div className="font-semibold text-foreground">{selectedPole.days_since_inspection ?? '—'} days</div>
                </div>
                <div>
                  <div className="text-gray-600 mb-1">SLA remaining</div>
                  <div className="font-semibold text-foreground">{selectedPole.sla_days_remaining != null ? `${selectedPole.sla_days_remaining} days` : '—'}</div>
                </div>
                <div className="col-span-2">
                  <div className="text-gray-600 mb-1">Location coordinates</div>
                  <div className="text-lg font-mono bg-gray-100 p-3 rounded">
                    {selectedPole.lat.toFixed(6)}, {selectedPole.lon.toFixed(6)}
                  </div>
                </div>
              </div>

              <div className="flex space-x-4">
                <button
                  className="flex-1 bg-primary text-white px-6 py-3 rounded-lg hover:bg-info font-semibold"
                  onClick={() => window.open(`/map?pole=${selectedPole.pole_id}`, '_blank')}
                >
                  View on Map
                </button>
                <button
                  className="flex-1 text-white px-6 py-3 rounded-lg font-semibold"
                  style={{ backgroundColor: '#00897B' }}
                  onClick={() => {
                    alert(`Approve pole ${selectedPole.pole_id}? (Feature coming soon)`)
                    setSelectedPole(null)
                  }}
                >
                  Approve
                </button>
                <button
                  className="flex-1 bg-red-600 text-white px-6 py-3 rounded-lg hover:bg-red-700 font-semibold"
                  onClick={() => {
                    alert(`Reject pole ${selectedPole.pole_id}? (Feature coming soon)`)
                    setSelectedPole(null)
                  }}
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
