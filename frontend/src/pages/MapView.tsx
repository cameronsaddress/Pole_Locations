import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Popup, CircleMarker } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

interface Pole {
  id: string
  lat: number
  lon: number
  confidence: number | null
  status: string
  color: string
  classification: string
  recency_score: number | null
  inspection_date?: string | null
  num_sources?: number | null
  needs_review?: boolean
  verification_level?: string | null
  ndvi?: number | null
  road_distance_m?: number | null
  surface_elev_m?: number | null
}

interface PoleDetail {
  id: string
  lat: number
  lon: number
  confidence: number | null
  status: string
  imageUrl: string
  recencyScore: number | null
  inspectionDate: string | null
  numSources: number | null
  spatialDistance: number | null
  combinedConfidence: number | null
  verificationLevel: string | null
  ndvi: number | null
  roadDistance: number | null
  surfaceElev: number | null
}

export default function MapView() {
  const [poles, setPoles] = useState<Pole[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedPole, setSelectedPole] = useState<PoleDetail | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [classificationFilter, setClassificationFilter] = useState<'all' | 'verified' | 'review' | 'new'>('all')
  const [minConfidence, setMinConfidence] = useState(0)
  const [recencyFilter, setRecencyFilter] = useState<'all' | 'fresh' | 'aging' | 'overdue'>('all')
  const [singleSourceOnly, setSingleSourceOnly] = useState(false)

  const formatConfidence = (value: number | null | undefined) =>
    value != null ? `${(value * 100).toFixed(1)}%` : '—'

  const formatNdvi = (value: number | null | undefined) =>
    value != null ? value.toFixed(2) : '—'

  const formatDistance = (value: number | null | undefined) =>
    value != null ? `${value.toFixed(1)} m` : '—'

  const formatHeight = (value: number | null | undefined) =>
    value != null ? `${value.toFixed(1)} m` : '—'

  const getVerificationLabel = (level: string | null | undefined) => {
    switch (level) {
      case 'multi_source':
        return 'Multi-source (≥2 matches)'
      case 'ai_only':
        return 'AI detection only'
      case 'historical_only':
        return 'Historical only'
      case 'needs_review':
        return 'Needs review'
      default:
        return 'Unknown'
    }
  }

  useEffect(() => {
    // Load all poles (limit=0 returns the full dataset including AI-only records)
    fetch('/api/v1/maps/poles-geojson?limit=0')
      .then(res => res.json())
      .then(data => {
        const poleList = data.features?.map((f: any) => ({
          id: f.properties.id,
          lat: f.geometry.coordinates[1],
          lon: f.geometry.coordinates[0],
          confidence: f.properties.confidence ?? null,
          status: f.properties.status,
          color: f.properties.color,
          classification: f.properties.classification,
          recency_score: f.properties.recency_score ?? null,
          inspection_date: f.properties.inspection_date ?? null,
          num_sources: f.properties.num_sources ?? null,
          needs_review: f.properties.needs_review ?? false,
          verification_level: f.properties.verification_level ?? null,
          ndvi: f.properties.ndvi ?? null,
          road_distance_m: f.properties.road_distance_m ?? null,
          surface_elev_m: f.properties.surface_elev_m ?? null,
        })) || []
        setPoles(poleList)
        setLoading(false)
      })
      .catch(err => {
        console.error('Error loading poles:', err)
        setLoading(false)
      })
  }, [])

  const handlePoleClick = (pole: Pole) => {
    fetch(`/api/v1/poles/${pole.id}`)
      .then(res => res.json())
      .then(detail => {
        setSelectedPole({
          id: pole.id,
          lat: pole.lat,
          lon: pole.lon,
          confidence: detail?.confidence ?? pole.confidence ?? null,
          status: detail?.status ?? pole.status,
          imageUrl: `/api/v1/poles/${pole.id}/image`,
          recencyScore: detail?.recency_score ?? pole.recency_score ?? null,
          inspectionDate: detail?.inspection_date ?? pole.inspection_date ?? null,
          numSources: detail?.num_sources ?? pole.num_sources ?? null,
          spatialDistance: detail?.spatial_distance_m ?? null,
          combinedConfidence: detail?.combined_confidence ?? null,
          verificationLevel: detail?.verification_level ?? pole.verification_level ?? null,
          ndvi: detail?.ndvi ?? pole.ndvi ?? null,
          roadDistance: detail?.road_distance_m ?? pole.road_distance_m ?? null,
          surfaceElev: detail?.surface_elev_m ?? pole.surface_elev_m ?? null,
        })
      })
      .catch(err => {
        console.error('Failed to load pole detail', err)
        setSelectedPole({
          id: pole.id,
          lat: pole.lat,
          lon: pole.lon,
          confidence: pole.confidence,
          status: pole.status,
          imageUrl: `/api/v1/poles/${pole.id}/image`,
          recencyScore: pole.recency_score ?? null,
          inspectionDate: pole.inspection_date ?? null,
          numSources: pole.num_sources ?? null,
          spatialDistance: null,
          combinedConfidence: null,
          verificationLevel: pole.verification_level ?? null,
          ndvi: pole.ndvi ?? null,
          roadDistance: pole.road_distance_m ?? null,
          surfaceElev: pole.surface_elev_m ?? null,
        })
      })
  }

  const getRecencyBucket = (score: number | null) => {
    if (score === 1) return 'fresh'
    if (score === 0.8) return 'fresh'
    if (score === 0.5) return 'aging'
    if (score === 0.2) return 'overdue'
    return 'unknown'
  }

  const getRecencyLabel = (score: number | null) => {
    const bucket = getRecencyBucket(score)
    switch (bucket) {
      case 'fresh':
        return 'Verified <3 years'
      case 'aging':
        return '3–5 years'
      case 'overdue':
        return '>5 years'
      default:
        return 'Unknown'
    }
  }

  const filteredPoles = poles.filter(p => {
    const matchesSearch = p.id.toLowerCase().includes(searchTerm.toLowerCase())
    if (!matchesSearch) return false

    if (classificationFilter !== 'all' && p.status !== classificationFilter) return false

    if (p.confidence != null && p.confidence < minConfidence) return false

    const recencyBucket = getRecencyBucket(p.recency_score ?? null)
    if (recencyFilter === 'fresh' && recencyBucket !== 'fresh') return false
    if (recencyFilter === 'aging' && recencyBucket !== 'aging') return false
    if (recencyFilter === 'overdue' && recencyBucket !== 'overdue') return false

    if (singleSourceOnly && (p.num_sources ?? 2) !== 1) return false

    return true
  })

  const statusCounts = {
    verified: poles.filter(p => p.status === 'verified').length,
    review: poles.filter(p => p.status === 'review').length,
    inspect: poles.filter(p => p.status === 'new').length,
  }

  const verificationCounts = {
    multi: poles.filter(p => p.verification_level === 'multi_source').length,
    aiOnly: poles.filter(p => p.verification_level === 'ai_only').length,
  }

  // Harrisburg, PA center
  const center: [number, number] = [40.2732, -76.8867]

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Header with accent border instead of full red */}
      <div className="bg-white border-b-2 border-accent px-6 py-4">
        <h1 className="text-2xl font-bold text-primary">Interactive Pole Map</h1>
        <p className="text-muted text-sm">Click any pole to view details and detection images with red bounding boxes</p>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <div className="w-80 bg-white border-r border-border overflow-y-auto">
          <div className="p-4 border-b border-border">
            <input
              type="text"
              placeholder="Search poles..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full px-3 py-2 border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div className="p-4 border-b border-border space-y-4 text-sm text-muted">
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1">Status</label>
              <select
                value={classificationFilter}
                onChange={e => setClassificationFilter(e.target.value as typeof classificationFilter)}
                className="w-full px-2 py-1 border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="all">All statuses</option>
                <option value="verified">Verified good</option>
                <option value="review">Needs review</option>
                <option value="new">Missing / new</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-foreground mb-1">Minimum confidence</label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={minConfidence}
                onChange={e => setMinConfidence(parseFloat(e.target.value))}
                className="w-full"
              />
              <div className="text-xs text-muted mt-1">{(minConfidence * 100).toFixed(0)}%</div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-foreground mb-1">Inspection freshness</label>
              <select
                value={recencyFilter}
                onChange={e => setRecencyFilter(e.target.value as typeof recencyFilter)}
                className="w-full px-2 py-1 border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="all">All recency levels</option>
                <option value="fresh">Verified &lt; 3 years</option>
                <option value="aging">3 – 5 years</option>
                <option value="overdue">Over 5 years</option>
              </select>
            </div>

            <label className="flex items-center gap-2 text-xs text-foreground">
              <input
                type="checkbox"
                checked={singleSourceOnly}
                onChange={e => setSingleSourceOnly(e.target.checked)}
                className="rounded border-border"
              />
              Highlight single-source detections only
            </label>
          </div>

          {/* Status Summary - no red backgrounds, only borders */}
          <div className="p-4 border-b border-border">
            <h3 className="font-semibold text-foreground mb-2">Poles in View</h3>
            <div className="text-sm text-muted">
              {poles.length} total
            </div>
            <div className="mt-2 space-y-1">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-success"></div>
                  <span className="text-sm">Verified good</span>
                </div>
                <span className="text-sm font-semibold">{statusCounts.verified}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-warning"></div>
                  <span className="text-sm">Needs review</span>
                </div>
                <span className="text-sm font-semibold">{statusCounts.review}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: '#7E57C2' }}></div>
                  <span className="text-sm">Missing / new</span>
                </div>
                <span className="text-sm font-semibold">{statusCounts.inspect}</span>
              </div>
              <div className="pt-2 mt-2 border-t border-border space-y-1 text-xs text-muted">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: '#2E7D32' }}></div>
                    <span>Multi-source verified</span>
                  </div>
                  <span className="font-medium text-foreground">{verificationCounts.multi}</span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: '#1E88E5' }}></div>
                    <span>AI-only verified</span>
                  </div>
                  <span className="font-medium text-foreground">{verificationCounts.aiOnly}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Pole List */}
          <div className="divide-y divide-border">
            {loading ? (
              <div className="p-4 text-center text-muted">Loading poles...</div>
            ) : (
              filteredPoles.map(pole => (
                <button
                  key={pole.id}
                  onClick={() => handlePoleClick(pole)}
                  className="w-full p-3 text-left hover:bg-background transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="font-medium text-sm text-foreground">{pole.id}</div>
                      <div className="text-xs text-muted mt-1">
                        {pole.lat.toFixed(4)}°N, {Math.abs(pole.lon).toFixed(4)}°W
                      </div>
                      <div className="text-xs text-muted mt-1">
                        Confidence: {formatConfidence(pole.confidence)}
                      </div>
                      <div className="text-xs text-muted">
                        Verification: {getVerificationLabel(pole.verification_level)}
                      </div>
                    </div>
                    <div
                      className="w-3 h-3 rounded-full mt-1"
                      style={{ backgroundColor: pole.color }}
                    ></div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Map with Satellite Imagery */}
        <div className="flex-1 relative">
          {loading ? (
            <div className="flex items-center justify-center h-full bg-gray-100">
              <div className="text-center">
                <div className="text-4xl mb-2">🗺️</div>
                <div className="text-muted">Loading map...</div>
              </div>
            </div>
          ) : (
            <MapContainer
              center={center}
              zoom={13}
              className="h-full w-full"
              scrollWheelZoom={true}
            >
              {/* Satellite Imagery Layer */}
              <TileLayer
                attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
                url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              />

              {/* Optional: Street overlay for labels */}
              <TileLayer
                attribution='&copy; <a href="https://carto.com/">CARTO</a>'
                url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png"
                opacity={0.6}
              />

              {/* Pole Markers */}
              {filteredPoles.map(pole => {
                const isAiVerified = pole.verification_level === 'ai_only'
                const markerColor = pole.color || '#00897B'
                return (
                  <CircleMarker
                    key={pole.id}
                    center={[pole.lat, pole.lon]}
                    radius={isAiVerified ? 7 : 5}
                    pathOptions={{
                      color: markerColor,
                      fillColor: markerColor,
                      fillOpacity: 0.9,
                      weight: isAiVerified ? 2 : 1
                    }}
                    eventHandlers={{
                      click: () => handlePoleClick(pole)
                    }}
                  >
                    <Popup>
                      <div className="text-sm">
                        <div className="font-semibold">{pole.id}</div>
                        <div className="text-xs text-gray-600 mt-1">
                          Confidence: {formatConfidence(pole.confidence)}
                        </div>
                        <div className="text-xs text-gray-600">
                          Status: {pole.status}
                        </div>
                        <div className="text-xs text-gray-600">
                          Verification: {getVerificationLabel(pole.verification_level)}
                        </div>
                        <div className="text-xs text-gray-600">
                          NDVI: {formatNdvi(pole.ndvi)}
                        </div>
                        <div className="text-xs text-gray-600">
                          Road dist: {formatDistance(pole.road_distance_m)}
                        </div>
                        <div className="text-xs text-gray-600">
                          Surface elev: {formatHeight(pole.surface_elev_m)}
                        </div>
                        <div className="text-xs text-gray-600">
                          Last inspection: {pole.inspection_date ?? 'Unknown'} ({getRecencyLabel(pole.recency_score)})
                        </div>
                        <button
                          onClick={() => handlePoleClick(pole)}
                          className="mt-2 px-3 py-1 bg-primary text-white rounded text-xs hover:bg-primary/90"
                        >
                          View Details
                        </button>
                      </div>
                    </Popup>
                  </CircleMarker>
                )
              })}
            </MapContainer>
          )}
        </div>
      </div>

      {/* Pole Detail Modal - red only as accent border */}
      {selectedPole && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999] p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto border-4 border-accent/30">
            <div className="p-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-xl font-bold text-primary">Pole Details: {selectedPole.id}</h3>
                  <p className="text-sm text-muted mt-1">Detection image with red bounding box</p>
                </div>
                <button
                  onClick={() => setSelectedPole(null)}
                  className="text-muted hover:text-foreground text-2xl leading-none"
                >
                  ×
                </button>
              </div>

              {/* Detection Image with Red Box */}
              <div className="relative bg-gray-100 rounded-lg overflow-hidden border-2 border-accent">
                <img
                  src={selectedPole.imageUrl}
                  alt={`Detection for ${selectedPole.id}`}
                  className="w-full h-auto"
                  onError={(e) => {
                    (e.target as HTMLImageElement).src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="%23f0f0f0"/><text x="50%" y="50%" text-anchor="middle" dy=".3em" fill="%23999">Image not available</text></svg>'
                  }}
                />
                <div className="absolute top-2 right-2 bg-accent text-white px-2 py-1 rounded text-xs font-semibold">
                  RED BOX: Pole Detection
                </div>
              </div>

              {/* Pole Info */}
              <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-xs text-muted mb-1">Detection confidence</div>
                  <div className="text-lg font-semibold text-primary">
                    {formatConfidence(selectedPole.confidence)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted mb-1">Combined confidence</div>
                  <div className="text-lg font-semibold text-foreground">
                    {formatConfidence(selectedPole.combinedConfidence)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted mb-1">Status</div>
                  <div className="text-lg font-semibold capitalize text-foreground">
                    {selectedPole.status}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted mb-1">Verification tier</div>
                  <div className="text-sm font-semibold text-foreground">
                    {getVerificationLabel(selectedPole.verificationLevel)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted mb-1">NDVI context</div>
                  <div className="text-sm text-foreground">{formatNdvi(selectedPole.ndvi)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted mb-1">Road distance</div>
                  <div className="text-sm text-foreground">{formatDistance(selectedPole.roadDistance)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted mb-1">Surface elevation</div>
                  <div className="text-sm text-foreground">{formatHeight(selectedPole.surfaceElev)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted mb-1">Inspection age</div>
                  <div className="text-lg font-semibold text-foreground">
                    {getRecencyLabel(selectedPole.recencyScore ?? null)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted mb-1">Inspection date</div>
                  <div className="text-sm text-foreground">{selectedPole.inspectionDate ?? 'Unknown'}</div>
                </div>
                <div>
                  <div className="text-xs text-muted mb-1">Sources</div>
                  <div className="text-sm text-foreground">{selectedPole.numSources ?? 'N/A'}</div>
                </div>
                <div>
                  <div className="text-xs text-muted mb-1">Latitude</div>
                  <div className="text-sm font-mono text-foreground">{selectedPole.lat.toFixed(6)}°N</div>
                </div>
                <div>
                  <div className="text-xs text-muted mb-1">Longitude</div>
                  <div className="text-sm font-mono text-foreground">{Math.abs(selectedPole.lon).toFixed(6)}°W</div>
                </div>
                <div>
                  <div className="text-xs text-muted mb-1">Spatial distance</div>
                  <div className="text-sm text-foreground">{selectedPole.spatialDistance != null ? `${selectedPole.spatialDistance.toFixed(1)} m` : '--'}</div>
                </div>
              </div>

              <div className="mt-6 flex gap-3 text-sm">
                <button className="flex-1 px-4 py-2 bg-success text-white rounded hover:bg-success/90 transition-colors">
                  Mark Verified
                </button>
                <button className="flex-1 px-4 py-2 bg-warning text-white rounded hover:bg-warning/90 transition-colors">
                  Assign Follow-up
                </button>
                <button className="flex-1 px-4 py-2 bg-accent text-white rounded hover:bg-accent/90 transition-colors border-2 border-accent">
                  Flag Issue
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
