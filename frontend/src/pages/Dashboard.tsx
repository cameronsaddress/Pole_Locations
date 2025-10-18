import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip as RechartsTooltip,
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
} from 'recharts'
import type { LucideIcon } from 'lucide-react'
import {
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
  Radar,
  TrendingUp,
  Clock,
  Compass,
  Sparkles,
} from 'lucide-react'

interface MetricsSummary {
  total_poles_processed?: number
  total_poles_available?: number
  automation_rate?: number | null
  processing_time_minutes?: number | null
  model_accuracy?: number | null
  poles_auto_approved?: number
  poles_needing_review?: number
  poles_needing_inspection?: number
}

interface VerificationStats {
  status: string
  total_poles: number
  verified_good: {
    count: number
    percentage: number
    color: string
  }
  in_question: {
    count: number
    percentage: number
    color: string
  }
  missing_new?: {
    count: number
    percentage: number
    color: string
  }
  new_detection?: {
    count: number
    percentage: number
    color: string
  }
  average_confidence: number
  median_spatial_distance: number
  needs_review_count: number
  data_sources: {
    osm_poles: number
    ai_detections: number
    dc_reference_poles: number
  }
  confidence_buckets: {
    high: number
    medium: number
    low: number
  }
  recency_breakdown: {
    under_1yr: number
    one_to_three: number
    three_to_five: number
    over_five: number
  }
  single_source_count: number
  average_spatial_distance: number | null
  max_spatial_distance: number | null
  last_detection_run?: string
  detection_runtime_seconds?: number | null
}

type PipelineStatus = {
  state: string
  started_at?: string | null
  finished_at?: string | null
  message?: string | null
  error?: string | null
  traceback?: string | null
}

type AlertSeverity = 'critical' | 'warning' | 'info'

const CLASSIFICATION_COLORS = {
  verified: '#006E5A',
  review: '#FF9800',
  missing: '#7256D9',
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null)
  const [verificationStats, setVerificationStats] = useState<VerificationStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [refreshingDashboard, setRefreshingDashboard] = useState(false)
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>({ state: 'unknown' })
  const [pipelineRequestInFlight, setPipelineRequestInFlight] = useState(false)
  const lastPipelineFinishRef = useRef<string | null>(null)

  const loadDashboardData = useCallback(
    async (isRefresh = false) => {
      if (!isRefresh) {
        setLoading(true)
      }
      setRefreshingDashboard(isRefresh)
      setError(null)

      try {
        const [metricsResponse, statsResponse] = await Promise.all([
          fetch('/api/v1/metrics/summary'),
          fetch('/api/v1/verification/stats'),
        ])

        const nextMetrics = metricsResponse.ok ? ((await metricsResponse.json()) as MetricsSummary) : null
        const nextStats = statsResponse.ok ? ((await statsResponse.json()) as VerificationStats) : null

        if (nextStats && nextStats.status === 'complete') {
          setVerificationStats(nextStats)
          setMetrics(nextMetrics ?? null)
          setError(null)
          setMessage(null)
        } else {
          setVerificationStats(null)
          setMetrics(nextMetrics ?? null)
          if (nextStats && nextStats.status !== 'complete') {
            setError('Verification pipeline has not published a completed run yet.')
          } else if (!statsResponse.ok) {
            setError('Unable to load verification stats from the API.')
          } else {
            setError('Verification stats are unavailable.')
          }
          setMessage(null)
        }
      } catch (err) {
        console.error('Failed to load dashboard data', err)
        setVerificationStats(null)
        setMetrics(null)
        setError('Dashboard failed to load live data from the API.')
        setMessage(null)
      } finally {
        setLoading(false)
        setRefreshingDashboard(false)
      }
    },
    [],
  )

  const fetchPipelineStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/pipeline/status')
      if (!res.ok) return
      const data = (await res.json()) as PipelineStatus
      setPipelineStatus(data)
    } catch (err) {
      console.warn('Failed to fetch pipeline status', err)
    }
  }, [])

  useEffect(() => {
    loadDashboardData()
  }, [loadDashboardData])

  useEffect(() => {
    fetchPipelineStatus()
    const interval = setInterval(fetchPipelineStatus, 15000)
    return () => clearInterval(interval)
  }, [fetchPipelineStatus])

  useEffect(() => {
    if (!pipelineStatus.finished_at) return
    if (pipelineStatus.finished_at === lastPipelineFinishRef.current) return
    lastPipelineFinishRef.current = pipelineStatus.finished_at

    if (pipelineStatus.state === 'completed' || pipelineStatus.state === 'complete') {
      loadDashboardData(true)
    }
  }, [loadDashboardData, pipelineStatus.finished_at, pipelineStatus.state])

  const handlePipelineRun = useCallback(async () => {
    if (pipelineRequestInFlight) return
    setPipelineRequestInFlight(true)
    try {
      const res = await fetch('/api/v1/pipeline/run', { method: 'POST' })
      if (res.status === 409) {
        const detail = await res.json().catch(() => ({ detail: 'Pipeline already running.' }))
        setPipelineStatus(prev => ({ ...prev, state: 'running', message: detail.detail ?? 'Pipeline already running.' }))
        setMessage('Pipeline already running; the dashboard will refresh when the job finishes.')
      } else if (res.ok) {
        const data = (await res.json()) as PipelineStatus
        setPipelineStatus(data)
        setMessage('Pipeline run kicked off. The dashboard will update once new results land.')
      }
    } catch (err) {
      console.error('Failed to trigger pipeline', err)
      setPipelineStatus(prev => ({ ...prev, state: 'error', message: 'Failed to start pipeline.' }))
      setError('Failed to start the verification pipeline.')
    } finally {
      setPipelineRequestInFlight(false)
      setTimeout(fetchPipelineStatus, 2000)
    }
  }, [fetchPipelineStatus, pipelineRequestInFlight])

  const handleDashboardReload = useCallback(() => {
    if (!refreshingDashboard) {
      loadDashboardData(true)
    }
  }, [loadDashboardData, refreshingDashboard])

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <main className="mx-auto max-w-7xl px-6 py-16">
          <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, idx) => (
              <div key={idx} className="h-36 animate-pulse rounded-3xl bg-muted/30" />
            ))}
          </div>
        </main>
      </div>
    )
  }

  if (!verificationStats) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background px-8 text-center">
        <h1 className="text-3xl font-semibold text-foreground">Dashboard data is unavailable</h1>
        <p className="mt-4 max-w-xl text-muted-foreground">
          {error ?? 'Start the verification pipeline to populate fresh analytics.'}
        </p>
      </div>
    )
  }

  const stats = verificationStats
  const totalPoles =
    stats.total_poles || metrics?.total_poles_processed || metrics?.total_poles_available || 0
  const verifiedCount = stats.verified_good.count || metrics?.poles_auto_approved || 0
  const reviewCount = stats.in_question.count || metrics?.poles_needing_review || 0
  const missingSource = stats.missing_new ?? stats.new_detection
  const missingCount = missingSource?.count || metrics?.poles_needing_inspection || 0
  const missingColor = missingSource?.color ?? CLASSIFICATION_COLORS.missing
  const avgConfidence = typeof stats.average_confidence === 'number' ? stats.average_confidence : null
  const automationRate =
    typeof metrics?.automation_rate === 'number'
      ? metrics.automation_rate
      : totalPoles
        ? verifiedCount / totalPoles
        : null
  const runtimeMinutes =
    stats.detection_runtime_seconds != null
      ? stats.detection_runtime_seconds / 60
      : metrics?.processing_time_minutes ?? null
  const reviewRate = totalPoles ? reviewCount / totalPoles : null
  const missingRate = totalPoles ? missingCount / totalPoles : null

  const classificationData = [
    { name: 'Verified Good', value: verifiedCount, color: CLASSIFICATION_COLORS.verified },
    { name: 'Needs Review', value: reviewCount, color: CLASSIFICATION_COLORS.review },
    { name: 'New / Missing', value: missingCount, color: missingColor },
  ]

  const confidenceData = [
    { bucket: 'High (≥ 0.80)', count: stats.confidence_buckets.high, color: '#006E5A' },
    { bucket: 'Moderate (0.60 – 0.79)', count: stats.confidence_buckets.medium, color: '#FFB300' },
    { bucket: 'Low (< 0.60)', count: stats.confidence_buckets.low, color: '#E53935' },
  ]

  const recencyData = [
    { label: 'Verified <1 yr', count: stats.recency_breakdown.under_1yr, color: '#004D40' },
    { label: '1 – 3 yrs', count: stats.recency_breakdown.one_to_three, color: '#00796B' },
    { label: '3 – 5 yrs', count: stats.recency_breakdown.three_to_five, color: '#B28704' },
    { label: '> 5 yrs', count: stats.recency_breakdown.over_five, color: '#C62828' },
  ]

  const operationalAlerts: Array<{ title: string; description: string; severity: AlertSeverity }> = []
  if (reviewCount > 0) {
    operationalAlerts.push({
      title: 'Review backlog',
      description: `${formatNumber(reviewCount)} poles awaiting manual validation`,
      severity: 'warning',
    })
  }
  if (stats.recency_breakdown.over_five > 0) {
    operationalAlerts.push({
      title: 'Inspections overdue',
      description: `${formatNumber(stats.recency_breakdown.over_five)} poles exceed the 5-year FCC window`,
      severity: 'critical',
    })
  }
  if (stats.single_source_count > 0) {
    operationalAlerts.push({
      title: 'Single-source detections',
      description: `${formatNumber(stats.single_source_count)} poles rely on a single data source`,
      severity: 'warning',
    })
  }
  if (stats.average_spatial_distance != null && stats.average_spatial_distance > 5) {
    operationalAlerts.push({
      title: 'Spatial drift detected',
      description: `Average detection offset ${stats.average_spatial_distance.toFixed(1)} m (max ${
        stats.max_spatial_distance?.toFixed(1) ?? '--'
      } m)`,
      severity: 'info',
    })
  }

  const summaryCards = [
    {
      title: 'Automation coverage',
      metric: formatPercent(automationRate),
      caption: `${formatNumber(verifiedCount)} of ${formatNumber(totalPoles)} poles cleared without touch`,
      icon: ShieldCheck,
      accent: 'primary' as const,
    },
    {
      title: 'Human review queue',
      metric: formatNumber(reviewCount),
      caption: reviewRate != null ? `${formatPercent(reviewRate)} of inventory pending eyes-on` : 'Awaiting run output',
      icon: TriangleAlert,
      accent: 'warning' as const,
    },
    {
      title: 'Confidence uplift',
      metric: formatPercent(avgConfidence),
      caption: `Median offset ${stats.median_spatial_distance.toFixed(1)} m`,
      icon: TrendingUp,
      accent: 'info' as const,
    },
    {
      title: 'Pipeline runtime',
      metric: runtimeMinutes != null ? `${runtimeMinutes.toFixed(1)} min` : '--',
      caption: stats.last_detection_run ? `Last run ${formatDateTime(stats.last_detection_run)}` : 'Awaiting first run',
      icon: Clock,
      accent: 'neutral' as const,
    },
  ]

  return (
    <div className="min-h-screen bg-gradient-to-b from-background via-background to-background">
      <main className="mx-auto max-w-7xl space-y-8 px-6 py-10">
        <section className="rounded-3xl border border-border/60 bg-card/95 p-8 shadow-lg backdrop-blur-sm">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <LiveDataBadge />
                <PipelineBadge status={pipelineStatus} />
              </div>
              <div>
                <h1 className="text-4xl font-bold text-primary">PoleVision Operations Console</h1>
                <p className="mt-3 max-w-2xl text-base text-muted-foreground">
                  Track how the multi-source verification pipeline is progressing, where human review is still needed,
                  and whether FCC compliance clocks are on schedule. Everything you need to keep pole verification on
                  rails.
                </p>
              </div>
              {message && (
                <div className="inline-flex items-center gap-2 rounded-full bg-warning/10 px-4 py-2 text-sm font-medium text-warning">
                  <Sparkles className="h-4 w-4" />
                  {message}
                </div>
              )}
            </div>
            <div className="flex w-full flex-col gap-4 lg:w-80">
              <button
                type="button"
                onClick={handleDashboardReload}
                disabled={refreshingDashboard}
                className="inline-flex items-center justify-center rounded-xl border border-border bg-white px-4 py-3 text-sm font-semibold text-foreground shadow-sm transition hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:border-muted disabled:text-muted"
              >
                {refreshingDashboard ? 'Refreshing dashboard…' : 'Reload dashboard data'}
              </button>
              <button
                type="button"
                onClick={handlePipelineRun}
                disabled={pipelineRequestInFlight || pipelineStatus.state === 'running'}
                className="inline-flex items-center justify-center rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground"
              >
                {pipelineStatus.state === 'running'
                  ? 'Pipeline running…'
                  : pipelineRequestInFlight
                    ? 'Starting pipeline…'
                    : 'Run verification pipeline'}
              </button>
              <div className="rounded-2xl border border-dashed border-border/70 bg-muted/10 p-4 text-sm text-muted-foreground">
                <div className="flex items-center gap-2 text-foreground">
                  <Compass className="h-4 w-4 text-primary" />
                  <span className="font-semibold text-foreground">Pipeline status</span>
                </div>
                <div className="mt-2 space-y-1 text-xs">
                  <div className="flex items-center gap-2">
                    <RefreshCw className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="capitalize text-muted-foreground">
                      {pipelineStatus.state?.replace(/_/g, ' ') ?? 'unknown'}
                    </span>
                  </div>
                  {pipelineStatus.message && <div>{pipelineStatus.message}</div>}
                  <div>Started: {formatDateTime(pipelineStatus.started_at)}</div>
                  <div>Last finished: {formatDateTime(pipelineStatus.finished_at)}</div>
                  {pipelineStatus.error && <div className="text-danger">{pipelineStatus.error}</div>}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {summaryCards.map(card => (
            <SummaryCard key={card.title} {...card} />
          ))}
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
          <div className="rounded-3xl border border-border/60 bg-card p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">Verification status mix</h2>
              <span className="text-xs font-medium uppercase tracking-[0.25em] text-muted-foreground">Live feed</span>
            </div>
            <div className="mt-6 h-80">
              <ResponsiveContainer>
                <PieChart>
                  <Pie
                    data={classificationData}
                    cx="40%"
                    innerRadius={70}
                    outerRadius={110}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {classificationData.map(entry => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    formatter={value => [`${formatNumber(value as number)} poles`, 'Count']}
                    contentStyle={{ borderRadius: 12, border: '1px solid #CBD5F5' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-6 grid gap-4 sm:grid-cols-3">
              {classificationData.map(item => (
                <div key={item.name} className="rounded-2xl bg-muted/10 p-4">
                  <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                    {item.name}
                  </div>
                  <div className="mt-2 text-2xl font-semibold text-foreground">{formatNumber(item.value)}</div>
                  <div className="text-xs text-muted-foreground">
                    {formatPercent(totalPoles ? item.value / totalPoles : null)}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-6">
            <div className="rounded-3xl border border-border/60 bg-card p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-foreground">Confidence distribution</h2>
                <span className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">AI</span>
              </div>
              <div className="mt-5 h-56">
                <ResponsiveContainer>
                  <BarChart data={confidenceData} layout="vertical" margin={{ left: 32, right: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" hide />
                    <YAxis type="category" dataKey="bucket" width={160} tick={{ fill: '#64748B', fontSize: 12 }} />
                    <RechartsTooltip
                      formatter={value => [`${formatNumber(value as number)} poles`, 'Count']}
                      labelFormatter={label => label}
                      contentStyle={{ borderRadius: 12, border: '1px solid #CBD5F5' }}
                    />
                    <Bar dataKey="count" radius={[12, 12, 12, 12]}>
                      {confidenceData.map(item => (
                        <Cell key={item.bucket} fill={item.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-4 space-y-1 text-sm text-muted-foreground">
                <div>Model accuracy lift: {formatPercent(metrics?.model_accuracy)}</div>
                <div>Average AI confidence: {formatPercent(avgConfidence)}</div>
              </div>
            </div>

            <div className="rounded-3xl border border-border/60 bg-card p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-foreground">Data source coverage</h3>
              <dl className="mt-4 space-y-3 text-sm text-muted-foreground">
                <div className="flex items-center justify-between">
                  <dt className="flex items-center gap-2">
                    <Radar className="h-4 w-4 text-primary" />
                    Verizon inventory (OSM export)
                  </dt>
                  <dd className="font-semibold text-foreground">{formatNumber(stats.data_sources.osm_poles)}</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-primary" />
                    AI detections (latest run)
                  </dt>
                  <dd className="font-semibold text-foreground">{formatNumber(stats.data_sources.ai_detections)}</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-primary" />
                    Reference poles (DC archival)
                  </dt>
                  <dd className="font-semibold text-foreground">
                    {formatNumber(stats.data_sources.dc_reference_poles)}
                  </dd>
                </div>
              </dl>
              <p className="mt-4 text-xs text-muted-foreground">
                Single-source detections revert to the human queue automatically. Blend additional imagery or GIS
                sources to tighten coverage.
              </p>
            </div>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
          <div className="rounded-3xl border border-border/60 bg-card p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">Inspection recency (FCC clock)</h2>
              <span className="text-sm font-semibold text-success">
                Compliance freshness {formatPercent(1 - (stats.recency_breakdown.over_five / totalPoles || 0))}
              </span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Prioritise field re-drives where aging inspections and low AI confidence intersect.
            </p>
            <div className="mt-6 space-y-4">
              {recencyData.map(item => (
                <div key={item.label}>
                  <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span>{item.label}</span>
                    <span>{formatNumber(item.count)} poles</span>
                  </div>
                  <div className="mt-2 h-3 rounded-full bg-muted/20">
                    <div
                      className="h-3 rounded-full"
                      style={{
                        width: totalPoles ? `${Math.min((item.count / totalPoles) * 100, 100)}%` : '0%',
                        backgroundColor: item.color,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <InlineMetric label="Overdue inspections" value={formatNumber(stats.recency_breakdown.over_five)} />
              <InlineMetric label="Fresh (<1 yr)" value={formatNumber(stats.recency_breakdown.under_1yr)} />
              <InlineMetric label="Avg spatial drift" value={`${stats.average_spatial_distance?.toFixed(1) ?? '--'} m`} />
              <InlineMetric
                label="Max offset observed"
                value={`${stats.max_spatial_distance?.toFixed(1) ?? '--'} m`}
              />
              <InlineMetric
                label="Review rate"
                value={`${formatPercent(reviewRate)} (${formatNumber(reviewCount)} poles)`}
              />
              <InlineMetric
                label="New / missing rate"
                value={`${formatPercent(missingRate)} (${formatNumber(missingCount)} poles)`}
              />
            </div>
          </div>

          <div className="rounded-3xl border border-border/60 bg-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-foreground">Operational alerts</h2>
            {operationalAlerts.length === 0 ? (
              <div className="mt-4 rounded-2xl border border-success/40 bg-success/10 px-4 py-5 text-sm font-medium text-success">
                All systems nominal. No outstanding review blockers detected.
              </div>
            ) : (
              <ul className="mt-4 space-y-3">
                {operationalAlerts.map(alert => (
                  <li key={alert.title} className={alertStyles(alert.severity)}>
                    <div className="flex items-center gap-2 text-sm font-semibold">
                      <TriangleAlert className="h-4 w-4" />
                      {alert.title}
                    </div>
                    <div className="mt-1 text-sm opacity-90">{alert.description}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {error && (
          <div className="rounded-3xl border border-warning/40 bg-warning/10 px-6 py-4 text-sm text-warning">
            {error}
          </div>
        )}
      </main>
    </div>
  )
}

type SummaryCardProps = {
  title: string
  metric: string
  caption?: string
  icon: LucideIcon
  accent?: 'primary' | 'warning' | 'success' | 'info' | 'neutral'
}

function SummaryCard({ title, metric, caption, icon: Icon, accent = 'primary' }: SummaryCardProps) {
  const accentClasses: Record<NonNullable<SummaryCardProps['accent']>, string> = {
    primary: 'bg-primary/10 text-primary',
    warning: 'bg-warning/10 text-warning',
    success: 'bg-success/10 text-success',
    info: 'bg-info/10 text-info',
    neutral: 'bg-muted/30 text-foreground',
  }

  return (
    <div className="rounded-3xl border border-border/60 bg-card p-6 shadow-sm transition hover:border-primary/50 hover:shadow-md">
      <div className="flex items-center justify-between">
        <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${accentClasses[accent]}`}>
          <Icon className="h-6 w-6" />
        </div>
        <span className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">Now</span>
      </div>
      <div className="mt-4 text-sm font-semibold text-muted-foreground">{title}</div>
      <div className="mt-6 text-3xl font-bold text-foreground">{metric}</div>
      {caption && <p className="mt-2 text-sm text-muted-foreground">{caption}</p>}
    </div>
  )
}

function LiveDataBadge() {
  return (
    <span
      className="inline-flex items-center gap-2 rounded-full bg-success/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] text-success"
    >
      <ShieldCheck className="h-3.5 w-3.5" />
      Live API data
    </span>
  )
}

function PipelineBadge({ status }: { status: PipelineStatus }) {
  let classes = 'bg-muted/40 text-muted-foreground'
  if (status.state === 'running') classes = 'bg-warning/10 text-warning'
  else if (status.state === 'complete' || status.state === 'completed') classes = 'bg-success/10 text-success'
  else if (status.state === 'error') classes = 'bg-danger/10 text-danger'

  return (
    <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ${classes}`}>
      <RefreshCw className="h-3.5 w-3.5" />
      {status.state?.replace(/_/g, ' ') ?? 'unknown'}
    </span>
  )
}

function InlineMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-muted/10 p-4">
      <div className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">{label}</div>
      <div className="mt-2 text-lg font-semibold text-foreground">{value}</div>
    </div>
  )
}

function alertStyles(severity: AlertSeverity) {
  switch (severity) {
    case 'critical':
      return 'rounded-2xl border border-danger/40 bg-danger/10 px-4 py-4 text-danger'
    case 'warning':
      return 'rounded-2xl border border-warning/40 bg-warning/10 px-4 py-4 text-warning'
    case 'info':
    default:
      return 'rounded-2xl border border-info/40 bg-info/10 px-4 py-4 text-info'
  }
}

function formatNumber(value: number | null | undefined) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--'
  return value.toLocaleString()
}

function formatPercent(value: number | null | undefined, fractionDigits = 1) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--'
  return `${(value * 100).toFixed(fractionDigits)}%`
}

function formatDateTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}
