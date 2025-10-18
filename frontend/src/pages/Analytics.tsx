import { useEffect, useState } from 'react'

interface SummaryMetrics {
  total_poles_processed?: number
  total_poles_available?: number
  automation_rate?: number | null
  model_accuracy?: number | null
  processing_time_minutes?: number | null
  poles_auto_approved?: number
  poles_needing_review?: number
  poles_needing_inspection?: number
}

interface VerificationStats {
  total_poles: number
  verified_good: { count: number; percentage: number }
  in_question: { count: number; percentage: number }
  missing_new: { count: number; percentage: number }
  confidence_buckets: { high: number; medium: number; low: number }
  recency_breakdown: { under_1yr: number; one_to_three: number; three_to_five: number; over_five: number }
  single_source_count: number
}

const formatPercent = (value: number | null | undefined) =>
  value != null && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '--'

const formatNumber = (value: number | null | undefined) =>
  value != null && Number.isFinite(value) ? value.toLocaleString('en-US') : '--'

export default function Analytics() {
  const [summary, setSummary] = useState<SummaryMetrics | null>(null)
  const [stats, setStats] = useState<VerificationStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      fetch('/api/v1/metrics/summary').then(res => res.json()).catch(() => null),
      fetch('/api/v1/verification/stats').then(res => res.json()).catch(() => null)
    ]).then(([summaryData, statsData]) => {
      if (summaryData) setSummary(summaryData)
      if (statsData && statsData.status === 'complete') setStats(statsData)
      else setError('Verification stats are unavailable. Run the pipeline to refresh metrics.')
    }).catch(err => {
      console.error(err)
      setError('Unable to load analytics data. Ensure the API is running with recent outputs.')
    })
  }, [])

  if (!summary || !stats) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <h1 className="text-3xl font-semibold text-foreground mb-2">Analytics Unavailable</h1>
        <p className="text-muted">{error ?? 'Run the verification pipeline to populate analytics.'}</p>
      </div>
    )
  }

  const totalProcessed = summary.total_poles_processed ?? stats.total_poles
  const automationRate = summary.automation_rate ?? (totalProcessed ? (summary.poles_auto_approved ?? 0) / totalProcessed : null)
  const reviewRate = stats.in_question.count / stats.total_poles
  const verificationRate = stats.verified_good.count / stats.total_poles

  const confidenceTotal = stats.confidence_buckets.high + stats.confidence_buckets.medium + stats.confidence_buckets.low || 1
  const recencyTotal =
    stats.recency_breakdown.under_1yr +
    stats.recency_breakdown.one_to_three +
    stats.recency_breakdown.three_to_five +
    stats.recency_breakdown.over_five || 1

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Operational Analytics</h1>
          <p className="text-sm text-muted">High-level performance indicators for pole verification across the network.</p>
        </div>
        <div className="text-sm text-muted">
          <span className="font-semibold text-primary mr-2">Automation rate:</span>{formatPercent(automationRate)}
          <span className="font-semibold text-primary ml-6 mr-2">Review backlog:</span>{formatPercent(reviewRate)}
        </div>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-lg shadow-lg p-6 border-l-4 border-primary">
          <div className="text-sm text-muted mb-1">Poles processed</div>
          <div className="text-3xl font-bold text-foreground">{formatNumber(totalProcessed)}</div>
          <div className="text-xs text-muted mt-2">Total poles evaluated in the last verification run</div>
        </div>
        <div className="bg-white rounded-lg shadow-lg p-6 border-l-4 border-amber-500">
          <div className="text-sm text-muted mb-1">Review backlog</div>
          <div className="text-3xl font-bold text-foreground">{formatNumber(stats.in_question.count)}</div>
          <div className="text-xs text-muted mt-2">Poles requiring human decision</div>
        </div>
        <div className="bg-white rounded-lg shadow-lg p-6 border-l-4 border-emerald-500">
          <div className="text-sm text-muted mb-1">Verified automatically</div>
          <div className="text-3xl font-bold text-foreground">{formatNumber(stats.verified_good.count)}</div>
          <div className="text-xs text-muted mt-2">{formatPercent(verificationRate)} of network cleared without manual touch</div>
        </div>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow-lg p-6">
          <h2 className="text-lg font-semibold text-foreground mb-2">Confidence distribution</h2>
          <p className="text-sm text-muted mb-4">Combined confidence score mix across all detections.</p>
          <div className="space-y-3">
            {([
              { label: 'High (≥ 0.80)', value: stats.confidence_buckets.high, color: '#00897B' },
              { label: 'Moderate (0.60 – 0.79)', value: stats.confidence_buckets.medium, color: '#FFB300' },
              { label: 'Low (< 0.60)', value: stats.confidence_buckets.low, color: '#E53935' }
            ]).map(level => {
              const pct = (level.value / confidenceTotal) * 100
              return (
                <div key={level.label}>
                  <div className="flex justify-between text-xs text-muted mb-1">
                    <span>{level.label}</span>
                    <span>{formatNumber(level.value)}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div className="h-2 rounded-full" style={{ width: `${pct.toFixed(1)}%`, backgroundColor: level.color }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-lg p-6">
          <h2 className="text-lg font-semibold text-foreground mb-2">Inspection freshness</h2>
          <p className="text-sm text-muted mb-4">How recently each pole was last verified.</p>
          <div className="space-y-3">
            {([
              { label: 'Verified < 1 year', value: stats.recency_breakdown.under_1yr, color: '#00695C' },
              { label: '1 – 3 years', value: stats.recency_breakdown.one_to_three, color: '#00838F' },
              { label: '3 – 5 years', value: stats.recency_breakdown.three_to_five, color: '#FFC107' },
              { label: 'Over 5 years', value: stats.recency_breakdown.over_five, color: '#D32F2F' }
            ]).map(level => {
              const pct = (level.value / recencyTotal) * 100
              return (
                <div key={level.label}>
                  <div className="flex justify-between text-xs text-muted mb-1">
                    <span>{level.label}</span>
                    <span>{formatNumber(level.value)}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div className="h-2 rounded-full" style={{ width: `${pct.toFixed(1)}%`, backgroundColor: level.color }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <section className="bg-white rounded-lg shadow-lg p-6">
        <h2 className="text-lg font-semibold text-foreground mb-3">Operational focus areas</h2>
        <ul className="space-y-3 text-sm text-muted">
          <li>
            <span className="font-semibold text-foreground">Single-source detections:</span> {formatNumber(stats.single_source_count)} poles require additional corroboration.
          </li>
          <li>
            <span className="font-semibold text-foreground">Manual review ratio:</span> {formatPercent(reviewRate)} of poles currently awaiting action.
          </li>
          <li>
            <span className="font-semibold text-foreground">Automation uplift:</span> {formatPercent(automationRate)} cleared automatically in the latest cycle.
          </li>
        </ul>
      </section>

      <section className="bg-white rounded-lg shadow-lg p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">Exports</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <button className="bg-primary text-white py-3 px-6 rounded-lg hover:bg-primary/90">
            📥 Export review queue (CSV)
          </button>
          <button className="bg-info text-white py-3 px-6 rounded-lg hover:bg-info/90">
            🗺️ Export GeoJSON for GIS
          </button>
          <button className="bg-success text-white py-3 px-6 rounded-lg hover:bg-success/90">
            📑 Download compliance summary
          </button>
        </div>
      </section>
    </div>
  )
}
