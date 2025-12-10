import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Activity, Database, Disc, Zap, AlertTriangle } from 'lucide-react'
import LiveMap3D from '../pages/LiveMap3D' // Using LiveMap3D logic for modal

interface OpsMetrics {
    total_assets: number
    grid_integrity: number
    daily_audit_count: number
    critical_anomalies: number
    preventative_savings: number
}

interface Asset {
    id: string
    lat: number
    lng: number
    status: string
    confidence: number
    issues: string[]
    health_score: number
}

// Reuse the image helper from LiveMap
const getStaticMapUrl = (lat: number, lng: number, width: number, height: number, zoom = 0.001) => {
    const bbox = `${lng - zoom},${lat - zoom},${lng + zoom},${lat + zoom}`;
    return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox=${bbox}&bboxSR=4326&size=${width},${height}&f=image`;
};

export default function CommandCenter() {
    const [opsMetrics, setOpsMetrics] = useState<OpsMetrics | null>(null)
    const [anomalyFeed, setAnomalyFeed] = useState<Asset[]>([])

    // State for the "Satellite Feed" rotation
    const [currentLock, setCurrentLock] = useState<Asset | null>(null)
    const [cycleIndex, setCycleIndex] = useState(0)
    const [scanProgress, setScanProgress] = useState(0)

    const [isExpanded, setIsExpanded] = useState(false) // If user clicks feed to expand

    // 1. Fetch Operations Data
    useEffect(() => {
        const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`

        // Fetch Metrics
        fetch(`${apiHost}/api/v2/ops/metrics`)
            .then(res => res.json())
            .then(data => setOpsMetrics(data))
            .catch(err => console.error("Ops Metrics Error:", err))

        // Fetch Anomaly Feed
        fetch(`${apiHost}/api/v2/ops/feed/anomalies`)
            .then(res => res.json())
            .then(data => {
                setAnomalyFeed(data)
                if (data.length > 0) setCurrentLock(data[0])
            })
            .catch(err => console.error("Anomaly Feed Error:", err))
    }, [])

    // 2. Cycle Logic
    useEffect(() => {
        if (anomalyFeed.length === 0 || isExpanded) return

        const interval = setInterval(() => {
            setCycleIndex(prev => {
                const next = (prev + 1) % anomalyFeed.length
                setCurrentLock(anomalyFeed[next])
                return next
            })
            setScanProgress(0) // Reset bar
        }, 8000) // 8 seconds per lock
        return () => clearInterval(interval)
    }, [anomalyFeed, isExpanded])

    // 3. Scan Progress Animation
    useEffect(() => {
        if (!currentLock) return
        setScanProgress(0)
        const interval = setInterval(() => {
            setScanProgress(prev => Math.min(prev + 1, 100))
        }, 80) // fill in 8s
        return () => clearInterval(interval)
    }, [currentLock])


    // If no data yet
    if (!currentLock) return <div className="p-8 text-white font-mono text-xs opacity-50 text-center">INITIALIZING SATELLITE LINK...</div>

    return (
        <div className="w-full h-full bg-black/40 backdrop-blur-sm border border-white/10 rounded-xl overflow-hidden flex flex-col md:flex-row shadow-2xl relative">

            {/* EXPANDED MODAL OVERLAY (When clicked) */}
            <AnimatePresence>
                {isExpanded && (
                    <div className="absolute inset-0 z-50 bg-black">
                        {/* We can temporarily mount a widget mode map specifically for this asset, or just a detailed view */}
                        <div className="relative w-full h-full">
                            <LiveMap3D mode="widget" />
                            <button
                                onClick={(e) => { e.stopPropagation(); setIsExpanded(false); }}
                                className="absolute top-4 right-4 z-[60] bg-black/80 text-white border border-white/20 px-4 py-2 rounded hover:bg-white/20"
                            >
                                CLOSE FEED
                            </button>
                            {/* Force open specific pole? We might need to pass a prop to LiveMap or context. 
                                    For now the widget defaults to the region. 
                                    Ideally LiveMap accepts "initialPoleId" */}
                        </div>
                    </div>
                )}
            </AnimatePresence>

            {/* LEFT: VISUAL INTEL FEED (70%) */}
            <div
                className="flex-1 relative bg-black overflow-hidden group cursor-pointer"
                onClick={() => setIsExpanded(true)}
            >
                <AnimatePresence mode="wait">
                    <motion.div
                        key={currentLock.id}
                        initial={{ opacity: 0, scale: 1.1 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.5 }}
                        className="absolute inset-0 bg-cover bg-center opacity-60 transition-all duration-500 group-hover:opacity-80 group-hover:scale-105"
                        style={{
                            backgroundImage: `url(${getStaticMapUrl(currentLock.lat, currentLock.lng, 800, 600)})`,
                            filter: 'contrast(1.2) grayscale(0.3)'
                        }}
                    />
                </AnimatePresence>

                {/* Grid Overlay */}
                <div className="absolute inset-0 bg-[linear-gradient(rgba(16,185,129,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(16,185,129,0.03)_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none" />

                {/* Vignette */}
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(0,0,0,0.8)_100%)] pointer-events-none" />

                {/* Targeting HUD */}
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-50 group-hover:opacity-100 transition-opacity">
                    <div className="w-[300px] h-[300px] border border-emerald-500/30 rounded-full flex items-center justify-center relative animate-[spin_10s_linear_infinite]">
                        <div className="absolute top-0 w-1 h-2 bg-emerald-500/50"></div>
                        <div className="absolute bottom-0 w-1 h-2 bg-emerald-500/50"></div>
                        <div className="absolute left-0 h-1 w-2 bg-emerald-500/50"></div>
                        <div className="absolute right-0 h-1 w-2 bg-emerald-500/50"></div>
                    </div>
                </div>

                {/* Info Text */}
                <div className="absolute top-6 left-6 z-10 w-full pr-12">
                    <div className="flex items-center gap-2 mb-2">
                        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
                        <span className="text-red-500 font-mono text-xs font-bold tracking-widest">LIVE SATELLITE UPLINK</span>
                        <span className="ml-auto text-[10px] text-emerald-500 bg-black/50 px-2 py-1 rounded border border-emerald-500/20">CLICK TO INSPECT</span>
                    </div>
                    <h3 className="text-white text-3xl font-black tracking-tighter uppercase drop-shadow-md">TARGET: {currentLock.id}</h3>
                    <div className="font-mono text-emerald-500 text-sm mt-1">{currentLock.lat.toFixed(5)}, {currentLock.lng.toFixed(5)}</div>
                </div>

                {/* Analysis Status */}
                <div className="absolute bottom-6 left-6 z-10 w-[80%]">
                    <div className="flex justify-between text-[10px] text-emerald-400 font-mono mb-1">
                        <span>ANALYSIS PROGRESS</span>
                        <span>{scanProgress}%</span>
                    </div>
                    <div className="h-1 bg-gray-800 rounded-full overflow-hidden w-64">
                        <div className="h-full bg-emerald-500 transition-all duration-100 ease-linear" style={{ width: `${scanProgress}%` }}></div>
                    </div>

                    {/* Issues Tags */}
                    <div className="flex flex-wrap gap-2 mt-4">
                        <span className={`text-[10px] px-2 py-1 rounded font-bold border ${currentLock.status === 'Critical' ? 'bg-red-500/20 text-red-400 border-red-500/40 animate-pulse' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'}`}>
                            {currentLock.status.toUpperCase()}
                        </span>
                        {currentLock.issues.map((issue, i) => (
                            <span key={i} className="bg-amber-500/10 border border-amber-500/30 text-amber-400 text-[10px] px-2 py-1 rounded font-mono">
                                ⚠ {issue.toUpperCase()}
                            </span>
                        ))}
                    </div>
                </div>

            </div>

            {/* RIGHT: SYSTEM OPERATIONS (30%) */}
            <div className="w-full md:w-[320px] bg-black/80 border-l border-white/10 p-6 flex flex-col">
                <div className="flex items-center gap-2 mb-6 border-b border-white/10 pb-4">
                    <Activity className="text-emerald-500 w-5 h-5" />
                    <span className="text-white font-bold tracking-widest text-sm">NETWORK OPERATIONS</span>
                </div>

                <div className="space-y-6 flex-1">
                    {/* Metric 1 */}
                    <div className="group">
                        <div className="flex justify-between items-center mb-1">
                            <span className="text-xs font-mono text-gray-400 group-hover:text-emerald-400 transition-colors flex items-center gap-2">
                                <Zap className="w-3 h-3" /> GRID INTEGRITY
                            </span>
                            <span className="text-xs font-bold text-white">{opsMetrics?.grid_integrity || '...'}%</span>
                        </div>
                        <div className="h-1.5 w-full bg-gray-800 rounded-full overflow-hidden">
                            <div className="h-full bg-emerald-500 shadow-[0_0_10px_#10b981]" style={{ width: `${opsMetrics?.grid_integrity || 0}%` }}></div>
                        </div>
                    </div>

                    {/* Metric 2 */}
                    <div className="group">
                        <div className="flex justify-between items-center mb-1">
                            <span className="text-xs font-mono text-gray-400 group-hover:text-blue-400 transition-colors flex items-center gap-2">
                                <Database className="w-3 h-3" /> DAILY AUDIT COUNT
                            </span>
                            <span className="text-xs font-bold text-white">{opsMetrics?.daily_audit_count.toLocaleString() || '...'}</span>
                        </div>
                        {/* Traffic Graph */}
                        <div className="h-8 flex items-end gap-[2px]">
                            {[...Array(20)].map((_, i) => (
                                <motion.div
                                    key={i}
                                    className="w-full bg-blue-500/20"
                                    animate={{ height: `${Math.random() * 60 + 20}%` }}
                                    transition={{ duration: 2, repeat: Infinity, repeatType: "mirror", delay: i * 0.1 }}
                                />
                            ))}
                        </div>
                    </div>

                    {/* Metric 3 */}
                    <div className="group">
                        <div className="flex justify-between items-center mb-1">
                            <span className="text-xs font-mono text-gray-400 group-hover:text-red-400 transition-colors flex items-center gap-2">
                                <AlertTriangle className="w-3 h-3 text-amber-500" /> CRITICAL ANOMALIES
                            </span>
                            <span className="text-xs font-bold text-amber-500 animate-pulse">{opsMetrics?.critical_anomalies || 0} DETECTED</span>
                        </div>

                        {/* Live Issues List */}
                        <div className="p-2 bg-amber-500/10 border border-amber-500/20 rounded text-[10px] text-amber-200 font-mono mt-2 min-h-[60px]">
                            {anomalyFeed.filter(a => a.status === 'Critical').slice(0, 3).map(asset => (
                                <div key={asset.id} className="mb-1 truncate">
                                    ⚠ {asset.issues[0] || "Critical Error"} (ID: {asset.id})
                                </div>
                            ))}
                            {anomalyFeed.filter(a => a.status === 'Critical').length === 0 && (
                                <span className="text-emerald-400">System Secure. No critical faults.</span>
                            )}
                        </div>
                    </div>
                </div>

                {/* Bottom Status */}
                <div className="mt-auto pt-4 border-t border-white/10">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Disc className="w-4 h-4 text-emerald-500 animate-spin" />
                            <span className="text-xs font-bold text-white tracking-widest">REAL-TIME MONITOR</span>
                        </div>
                        <div className="text-[10px] text-gray-500 font-mono">V 2.5.0-LIVE</div>
                    </div>
                </div>

            </div>
        </div>
    )
}
