import { useState, useEffect } from 'react'

export default function ModelPerformance() {
  const [metrics, setMetrics] = useState<any>(null)

  useEffect(() => {
    fetch('/api/v1/metrics/model')
      .then(res => res.json())
      .then(data => setMetrics(data))
      .catch(err => console.error('Failed to load metrics:', err))
  }, [])

  const formatPercent = (value: number | null | undefined, decimals = 1) => {
    if (value == null || !Number.isFinite(value)) return '--'
    const clamped = Math.max(0, Math.min(Number(value), 1))
    return `${(clamped * 100).toFixed(decimals)}%`
  }

  const formatNumber = (value: number | null | undefined) =>
    value != null && Number.isFinite(value) ? value.toLocaleString() : '--'

  const formatMs = (value: number | null | undefined) =>
    value != null && Number.isFinite(value) ? `${value.toFixed(2)} ms` : '--'

  const formatFps = (value: number | null | undefined) =>
    value != null && Number.isFinite(value) ? `${value.toFixed(2)} FPS` : '--'

  const modelMetrics = metrics?.metrics ?? {}
  const inferenceMetrics = metrics?.inference ?? {}
  const datasetInfo = metrics?.dataset ?? {}
  const trainingMinutes = metrics?.training_time_minutes != null ? Number(metrics.training_time_minutes) : null

  const metricRows: Array<[string, string]> = [
    ['Precision', formatPercent(modelMetrics.precision)],
    ['Recall', formatPercent(modelMetrics.recall)],
    ['mAP50', formatPercent(modelMetrics.map50)],
    ['mAP50-95', formatPercent(modelMetrics.map50_95)],
    ['F1 Score', formatPercent(modelMetrics.f1_score)],
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-foreground mb-8">AI Model Performance</h1>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-white rounded-lg shadow-lg p-6 text-center">
          <div className="text-6xl mb-4">●</div>
          <div className="text-4xl font-bold text-primary mb-2">{formatPercent(modelMetrics.precision)}</div>
          <div className="text-muted">Precision</div>
        </div>
        <div className="bg-white rounded-lg shadow-lg p-6 text-center">
          <div className="text-6xl mb-4">●</div>
          <div className="text-4xl font-bold text-secondary mb-2">{formatPercent(modelMetrics.recall)}</div>
          <div className="text-muted">Recall</div>
        </div>
        <div className="bg-white rounded-lg shadow-lg p-6 text-center">
          <div className="text-6xl mb-4">●</div>
          <div className="text-4xl font-bold text-warning mb-2">{formatPercent(modelMetrics.map50)}</div>
          <div className="text-muted">mAP50</div>
        </div>
      </div>

      {/* Training Info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <div className="bg-white rounded-lg shadow-lg p-6">
          <h3 className="text-lg font-bold text-foreground mb-4">Training Details</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted">Model:</span>
              <span className="font-mono">{metrics?.model_name || 'YOLOv8'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Training Time:</span>
              <span>{trainingMinutes != null && Number.isFinite(trainingMinutes) ? `${trainingMinutes.toFixed(2)} minutes` : '--'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Dataset:</span>
              <span>
                {datasetInfo.total_images != null
                  ? `${formatNumber(datasetInfo.total_images)} images (${formatNumber(datasetInfo.train_images)} train / ${formatNumber(datasetInfo.val_images)} val)`
                  : '--'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Image Size:</span>
              <span>{datasetInfo.image_size || '--'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Epochs:</span>
              <span>Not logged (real imagery fine-tuning)</span>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-lg p-6">
          <h3 className="text-lg font-bold text-foreground mb-4">Performance Metrics</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted">F1 Score:</span>
              <span className="font-bold">{formatPercent(modelMetrics.f1_score)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">mAP50-95:</span>
              <span className="font-bold">{formatPercent(modelMetrics.map50_95)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Inference Time:</span>
              <span>{formatMs(inferenceMetrics.avg_inference_time_ms)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Throughput:</span>
              <span>{formatFps(inferenceMetrics.throughput_fps)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Device:</span>
              <span>{inferenceMetrics.device || 'Not specified'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Metric Summary */}
      <div className="bg-white rounded-lg shadow-lg p-6">
        <h3 className="text-lg font-bold text-foreground mb-4">Latest Evaluation Summary</h3>
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase">Metric</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase">Value</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {metricRows.map(([label, value]) => (
                <tr key={label}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">{label}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
