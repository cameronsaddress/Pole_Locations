export default function DiffViewer() {
  const streamlitUrl = import.meta.env.VITE_DIFF_VIEWER_URL || 'http://localhost:8501'

  return (
    <div className="min-h-screen bg-background py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <h1 className="text-3xl font-bold text-foreground mb-4">Before / After Diff</h1>
        <p className="text-muted mb-6">
          Compare the current verification results to a baseline snapshot. Launch the diff viewer in a new tab:
        </p>
        <a
          href={streamlitUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center px-4 py-2 bg-primary text-white rounded shadow hover:bg-primary/90 transition-colors"
        >
          Open Diff Viewer
        </a>
        <p className="text-xs text-muted mt-4">
          The diff viewer runs as a separate FastAPI/Streamlit service. Set <code>VITE_DIFF_VIEWER_URL</code> to point at the deployed URL.
        </p>
      </div>
    </div>
  )
}
