import { useEffect, useState, useCallback } from 'react'

interface DatasetInfo {
  id: string
  name: string
  total: number
  remaining: number
}

interface QueueEntry {
  dataset: string
  image_id: string
  image_url: string
  pole_present: string | null
  confidence: number | null
  notes: string
  metadata: Record<string, string | number | null>
}

const confidencePresets: Record<string, number> = {
  pole: 0.9,
  negative: 0.1,
  unsure: 0.5,
}

export default function MapillaryLabeler() {
  const [datasets, setDatasets] = useState<DatasetInfo[]>([])
  const [selectedDataset, setSelectedDataset] = useState<string>('')
  const [entry, setEntry] = useState<QueueEntry | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [confidence, setConfidence] = useState<number>(0.9)
  const [notes, setNotes] = useState<string>('')

  const loadDatasets = useCallback(() => {
    fetch('/api/v1/mapillary/datasets')
      .then(res => {
        if (!res.ok) throw new Error('Failed to load datasets')
        return res.json()
      })
      .then(data => {
        const list: DatasetInfo[] = data.datasets || []
        setDatasets(list)
        if (list.length > 0) {
          setSelectedDataset(prev => (prev && list.find(d => d.id === prev) ? prev : list[0].id))
        }
      })
      .catch(err => {
        console.error(err)
        setError('Unable to load Mapillary datasets. Ensure the backend sync has run.')
      })
  }, [])

  const loadNextEntry = useCallback((datasetId: string) => {
    if (!datasetId) return
    setLoading(true)
    setError(null)
    fetch(`/api/v1/mapillary/queue?dataset=${encodeURIComponent(datasetId)}`)
      .then(async res => {
        if (res.status === 404) {
          setEntry(null)
          setLoading(false)
          setError('No images remaining to label in this dataset.')
          return
        }
        if (!res.ok) {
          const txt = await res.text()
          throw new Error(txt || 'Failed to fetch queue entry')
        }
        return res.json()
      })
      .then(data => {
        if (!data) return
        const record = data.entry as QueueEntry
        setEntry(record)
        setConfidence(record.confidence ?? confidencePresets.pole)
        setNotes(record.notes ?? '')
        setLoading(false)
      })
      .catch(err => {
        console.error(err)
        setError(err.message || 'Failed to load next image.')
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    loadDatasets()
  }, [loadDatasets])

  useEffect(() => {
    if (selectedDataset) {
      loadNextEntry(selectedDataset)
    }
  }, [selectedDataset, loadNextEntry])

  const submitLabel = (label: 'pole' | 'negative' | 'unsure', overrideConfidence?: number) => {
    if (!entry) return
    setLoading(true)
    setError(null)

    const effectiveConfidence = overrideConfidence ?? confidence

    const payload = {
      dataset: entry.dataset,
      image_id: entry.image_id,
      pole_present: label,
      confidence: effectiveConfidence,
      notes,
    }

    fetch('/api/v1/mapillary/label', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })
      .then(async res => {
        if (!res.ok) {
          const txt = await res.text()
          throw new Error(txt || 'Failed to save label')
        }
        return res.json()
      })
      .then(() => {
        loadDatasets()
        loadNextEntry(selectedDataset)
      })
      .catch(err => {
        console.error(err)
        setError(err.message || 'Failed to save label')
        setLoading(false)
      })
  }

  const handlePreset = (label: 'pole' | 'negative' | 'unsure') => {
    const preset = confidencePresets[label]
    setConfidence(preset)
    submitLabel(label, preset)
  }

  const handleSkip = () => {
    loadNextEntry(selectedDataset)
  }

  const renderMetadata = () => {
    if (!entry) return null
    const items = Object.entries(entry.metadata || {})
      .filter(([_, value]) => value !== null && value !== '')
      .map(([key, value]) => (
        <div key={key} className="flex justify-between text-sm text-muted">
          <span className="font-medium text-foreground capitalize">{key.replace(/_/g, ' ')}</span>
          <span>{String(value)}</span>
        </div>
      ))

    if (items.length === 0) return null

    return (
      <div className="bg-white rounded-lg shadow-md p-4 space-y-2">
        <h3 className="text-sm font-semibold text-primary uppercase tracking-wide">Metadata</h3>
        {items}
      </div>
    )
  }

  return (
    <div className="bg-background min-h-screen">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-primary">Mapillary Labeler</h1>
            <p className="text-muted mt-1">Tag street-level imagery to build the next training set.</p>
          </div>
          <div className="mt-4 md:mt-0">
            <label className="block text-sm font-medium text-muted mb-1">Dataset</label>
            <select
              value={selectedDataset}
              onChange={e => setSelectedDataset(e.target.value)}
              className="border border-border rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {datasets.map(ds => (
                <option key={ds.id} value={ds.id}>
                  {ds.name} ({ds.remaining}/{ds.total} remaining)
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded mb-4">
            {error}
          </div>
        )}

        {loading && !entry ? (
          <div className="flex items-center justify-center h-96">
            <div className="text-xl font-semibold text-primary animate-pulse">Loading imagery…</div>
          </div>
        ) : null}

        {!loading && !entry ? (
          <div className="flex flex-col items-center justify-center h-96 bg-white border border-dashed border-border rounded-lg">
            <div className="text-xl font-semibold text-muted">All caught up!</div>
            <p className="text-muted text-sm mt-2">Switch datasets or rerun the sync to load more imagery.</p>
          </div>
        ) : null}

        {entry && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 bg-white rounded-lg shadow-lg overflow-hidden">
              <div className="p-4 border-b border-border flex items-center justify-between">
                <div>
                  <div className="text-sm uppercase tracking-wide text-muted">Image ID</div>
                  <div className="text-lg font-semibold text-foreground">{entry.image_id}</div>
                </div>
                <div>
                  <span className="px-3 py-1 text-xs font-bold rounded-full bg-primary/10 text-primary">
                    {selectedDataset}
                  </span>
                </div>
              </div>
              <div className="bg-gray-900">
                <img
                  src={entry.image_url}
                  alt="Mapillary view"
                  className="w-full h-[520px] object-contain bg-gray-900"
                />
              </div>
            </div>

            <div className="space-y-6">
              {renderMetadata()}

              <div className="bg-white rounded-lg shadow-md p-4 space-y-4">
                <h3 className="text-lg font-semibold text-foreground">Confidence</h3>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={confidence}
                  onChange={e => setConfidence(parseFloat(e.target.value))}
                  className="w-full"
                />
                <div className="flex justify-between text-sm text-muted">
                  <span>0%</span>
                  <span>{Math.round(confidence * 100)}%</span>
                  <span>100%</span>
                </div>
              </div>

              <div className="bg-white rounded-lg shadow-md p-4">
                <label className="block text-sm font-medium text-muted mb-1">Notes (optional)</label>
                <textarea
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  rows={3}
                  className="w-full border border-border rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="Context for this annotation"
                />
              </div>

              <div className="bg-white rounded-lg shadow-md p-4 space-y-3">
                <h3 className="text-sm font-semibold text-muted uppercase tracking-wide">Label</h3>
                <div className="grid grid-cols-3 gap-3">
                  <button
                    onClick={() => handlePreset('pole')}
                    className="bg-primary text-white font-semibold py-2 rounded-md hover:bg-primary/90 transition"
                  >
                    Pole
                  </button>
                  <button
                    onClick={() => handlePreset('negative')}
                    className="bg-gray-200 text-gray-900 font-semibold py-2 rounded-md hover:bg-gray-300 transition"
                  >
                    Not a Pole
                  </button>
                  <button
                    onClick={() => handlePreset('unsure')}
                    className="bg-yellow-100 text-yellow-800 font-semibold py-2 rounded-md hover:bg-yellow-200 transition"
                  >
                    Unsure
                  </button>
                </div>
                <button
                  onClick={handleSkip}
                  className="w-full text-sm text-muted underline hover:text-foreground"
                >
                  Skip / Next Image
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
