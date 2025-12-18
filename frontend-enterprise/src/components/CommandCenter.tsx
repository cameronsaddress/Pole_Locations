import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Activity, Database, Disc, Zap, AlertTriangle } from 'lucide-react'


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
    // const [cycleIndex, setCycleIndex] = useState(0)
    const [scanProgress, setScanProgress] = useState(0)

    const [isExpanded, setIsExpanded] = useState(false) // If user clicks feed to expand

    // Dispatch Logic
    const [dispatchStep, setDispatchStep] = useState(0) // 0=idle, 1=loading, 2=done

    const startDispatch = () => {
        setDispatchStep(1)
        setTimeout(() => {
            setDispatchStep(2)
        }, 2000)
    }

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
            // Cycle through assets
            // setCycleIndex(prev => {
            //    return (prev + 1) % data.length
            // })
            if (anomalyFeed.length > 0) {
                const currentIndex = anomalyFeed.findIndex(asset => asset.id === currentLock?.id);
                const nextIndex = (currentIndex + 1) % anomalyFeed.length;
                setCurrentLock(anomalyFeed[nextIndex]);
            }
            setScanProgress(0) // Reset bar
        }, 8000) // 8 seconds per lock
        return () => clearInterval(interval)
    }, [anomalyFeed, isExpanded, currentLock])

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

            {isExpanded && (
                <div className="absolute inset-0 z-50 bg-black/95 backdrop-blur-xl flex flex-col p-8">
                    {/* HEADER */}
                    <div className="flex items-center justify-between mb-8 border-b border-white/10 pb-4">
                        <div>
                            <h2 className="text-2xl font-black text-white tracking-widest uppercase flex items-center gap-3">
                                <AlertTriangle className="text-red-500 w-8 h-8" />
                                INCIDENT COMMAND: {currentLock.id}
                            </h2>
                            <p className="text-emerald-500 font-mono text-xs mt-1">
                                SECURE UPLINK ESTABLISHED
                            </p>
                        </div>
                        <button
                            onClick={(e) => { e.stopPropagation(); setIsExpanded(false); setDispatchStep(0); }}
                            className="bg-transparent border border-white/20 text-white hover:bg-white/10 px-6 py-2 rounded uppercase text-xs font-bold tracking-widest transition-colors"
                        >
                            ABORT / CLOSE
                        </button>
                    </div>

                    {/* CONTENT GRID */}
                    <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-8 overflow-hidden">
                        {/* LEFT: VISUAL */}
                        <div className="relative rounded-lg overflow-hidden border border-emerald-500/30">
                            <img
                                src={getStaticMapUrl(currentLock.lat, currentLock.lng, 800, 600)}
                                className="w-full h-full object-cover filter contrast-125 grayscale-[0.2]"
                            />
                            <div className="absolute inset-0 bg-[linear-gradient(rgba(0,0,0,0)_50%,rgba(16,185,129,0.1)_50%),linear-gradient(90deg,rgba(16,185,129,0.1)_50%,rgba(0,0,0,0)_50%)] bg-[size:4px_4px] pointer-events-none opacity-20" />
                            <div className="absolute bottom-0 left-0 right-0 bg-black/80 p-4 border-t border-emerald-500/50">
                                <div className="flex justify-between items-end">
                                    <div>
                                        <div className="text-[10px] text-gray-400 uppercase tracking-widest mb-1">AI CONFIDENCE</div>
                                        <div className="text-3xl font-black text-emerald-400">{(currentLock.confidence * 100).toFixed(1)}%</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-[10px] text-gray-400 uppercase tracking-widest mb-1">DEFECT TYPE</div>
                                        <div className="text-xl font-bold text-red-500 flex items-center justify-end gap-2">
                                            {currentLock.issues[0]?.toUpperCase() || "UNKNOWN"}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* RIGHT: ACTION PANEL */}
                        <div className="flex flex-col gap-6">
                            {/* RISK ANALYSIS WIDGET */}
                            <div className="bg-white/5 border border-white/10 p-6 rounded-lg relative overflow-hidden">
                                <div className="absolute top-0 right-0 w-32 h-32 bg-red-600/20 blur-3xl rounded-full translate-x-10 -translate-y-10" />

                                <h3 className="text-sm font-bold text-gray-400 uppercase tracking-widest mb-4">PREDICTIVE RISK ANALYSIS</h3>

                                <div className="space-y-4">
                                    <div className="flex justify-between items-center text-sm border-b border-white/5 pb-2">
                                        <span className="text-gray-300">Failure Probability (1yr)</span>
                                        <span className="text-red-400 font-mono font-bold">87.4%</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm border-b border-white/5 pb-2">
                                        <span className="text-gray-300">Potential Liability</span>
                                        <span className="text-red-400 font-mono font-bold">$245,000</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm border-b border-white/5 pb-2">
                                        <span className="text-gray-300">Customer Impact</span>
                                        <span className="text-amber-400 font-mono font-bold">1,240 Households</span>
                                    </div>
                                </div>
                            </div>

                            {/* DISPATCH CONTROLS */}
                            <div className="flex-1 bg-emerald-900/10 border border-emerald-500/20 p-6 rounded-lg flex flex-col justify-between relative overflow-hidden">
                                {dispatchStep === 0 && (
                                    <>
                                        <div>
                                            <h3 className="text-sm font-bold text-emerald-400 uppercase tracking-widest mb-2">RECOMMENDED ACTION</h3>
                                            <p className="text-white text-lg font-light leading-snug mb-6">
                                                Deploy Field Unit for <strong className="text-white font-bold underline decoration-emerald-500">priority maintenance</strong>.
                                                Drone verification confirms structural anomaly.
                                            </p>

                                            <div className="flex items-center gap-4 mb-8">
                                                <div className="bg-black/40 px-4 py-2 rounded text-xs font-mono text-gray-400 border border-white/10">
                                                    EST. COST: <span className="text-white font-bold ml-2">$450.00</span>
                                                </div>
                                                <div className="bg-black/40 px-4 py-2 rounded text-xs font-mono text-gray-400 border border-white/10">
                                                    SLA TARGET: <span className="text-white font-bold ml-2">48 HOURS</span>
                                                </div>
                                            </div>
                                        </div>

                                        <button
                                            onClick={(e) => { e.stopPropagation(); startDispatch(); }}
                                            className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-4 rounded-lg uppercase tracking-widest shadow-lg shadow-emerald-500/30 transition-all active:scale-95 flex items-center justify-center gap-3"
                                        >
                                            <Zap className="w-5 h-5 fill-current" />
                                            AUTHORIZE DISPATCH
                                        </button>
                                    </>
                                )}

                                {dispatchStep === 1 && (
                                    <div className="flex flex-col items-center justify-center h-full text-center animate-pulse">
                                        <div className="w-16 h-16 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin mb-6"></div>
                                        <h3 className="text-xl font-black text-white uppercase tracking-widest mb-2">ALLOCATING RESOURCES...</h3>
                                        <p className="text-emerald-400 font-mono text-sm">Searching nearest available crew...</p>
                                    </div>
                                )}

                                {dispatchStep === 2 && (
                                    <div className="flex flex-col items-center justify-center h-full text-center">
                                        <motion.div
                                            initial={{ scale: 0 }}
                                            animate={{ scale: 1 }}
                                            transition={{ type: "spring", stiffness: 200 }}
                                            className="w-20 h-20 bg-emerald-500 rounded-full flex items-center justify-center mb-6 shadow-[0_0_50px_rgba(16,185,129,0.5)]"
                                        >
                                            <Zap className="w-10 h-10 text-white fill-current" />
                                        </motion.div>
                                        <h3 className="text-2xl font-black text-white uppercase tracking-widest mb-2">DISPATCH CONFIRMED</h3>
                                        <p className="text-gray-300 font-mono text-sm mb-6">Work Order #WO-{Math.floor(Math.random() * 100000)} generated.</p>
                                        <div className="bg-emerald-500/20 text-emerald-300 text-xs px-4 py-2 rounded-full border border-emerald-500/30">
                                            UNIT 4-ALPHA EN ROUTE • ETA 14 MIN
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}

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
