import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Activity, Database, Disc, Zap, AlertTriangle } from 'lucide-react'
import { Card } from "@/components/ui/card"

// Reuse the image helper from LiveMap
const getStaticMapUrl = (lat: number, lng: number, width: number, height: number, zoom = 0.001) => {
    const bbox = `${lng - zoom},${lat - zoom},${lng + zoom},${lat + zoom}`;
    return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox=${bbox}&bboxSR=4326&size=${width},${height}&f=image`;
};

// Mock "Live" locations to scan through
const LOCATIONS = [
    { id: 'MT-4021', lat: 40.18985, lng: -76.72940 },
    { id: 'MT-4022', lat: 40.19200, lng: -76.73100 },
    { id: 'MT-4023', lat: 40.18800, lng: -76.72800 },
    { id: 'MT-4025', lat: 40.19050, lng: -76.73200 },
    { id: 'MT-4028', lat: 40.19150, lng: -76.73500 },
    { id: 'MT-4030', lat: 40.23000, lng: -76.73000 },
]

export default function CommandCenter() {
    const [currentLock, setCurrentLock] = useState(LOCATIONS[0])
    const [scanProgress, setScanProgress] = useState(0)

    // Simulate "Scanning" rotation
    useEffect(() => {
        const interval = setInterval(() => {
            const nextIdx = Math.floor(Math.random() * LOCATIONS.length)
            setCurrentLock(LOCATIONS[nextIdx])
            setScanProgress(0) // Reset bar
        }, 5000)
        return () => clearInterval(interval)
    }, [])

    // Simulate Scan Progress
    useEffect(() => {
        const interval = setInterval(() => {
            setScanProgress(prev => Math.min(prev + 2, 100))
        }, 100) // 5 seconds to fill
        return () => clearInterval(interval)
    }, [currentLock])


    return (
        <div className="w-full h-full bg-black/40 backdrop-blur-sm border border-white/10 rounded-xl overflow-hidden flex flex-col md:flex-row">

            {/* LEFT: VISUAL INTEL FEED (70%) */}
            <div className="flex-1 relative bg-black overflow-hidden group">
                <AnimatePresence mode="wait">
                    <motion.div
                        key={currentLock.id}
                        initial={{ opacity: 0, scale: 1.1 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.5 }}
                        className="absolute inset-0 bg-cover bg-center opacity-60"
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
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="w-[300px] h-[300px] border border-emerald-500/30 rounded-full flex items-center justify-center relative animate-[spin_10s_linear_infinite]">
                        <div className="absolute top-0 w-1 h-2 bg-emerald-500/50"></div>
                        <div className="absolute bottom-0 w-1 h-2 bg-emerald-500/50"></div>
                        <div className="absolute left-0 h-1 w-2 bg-emerald-500/50"></div>
                        <div className="absolute right-0 h-1 w-2 bg-emerald-500/50"></div>
                    </div>
                    <div className="absolute w-[280px] h-[280px] border border-dashed border-emerald-500/20 rounded-full animate-[spin_15s_linear_infinite_reverse]"></div>
                </div>

                {/* Info Text */}
                <div className="absolute top-6 left-6 z-10">
                    <div className="flex items-center gap-2 mb-2">
                        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
                        <span className="text-red-500 font-mono text-xs font-bold tracking-widest">LIVE UPLINK</span>
                    </div>
                    <h3 className="text-white text-2xl font-black tracking-tighter">SATELLITE INTEL FEED</h3>
                    <div className="font-mono text-emerald-500 text-sm mt-1">TARGET: {currentLock.id} // {currentLock.lat.toFixed(4)}, {currentLock.lng.toFixed(4)}</div>
                </div>

                {/* Analysis Status */}
                <div className="absolute bottom-6 left-6 z-10 w-64">
                    <div className="flex justify-between text-[10px] text-emerald-400 font-mono mb-1">
                        <span>ANALYSIS PROGRESS</span>
                        <span>{scanProgress}%</span>
                    </div>
                    <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
                        <div className="h-full bg-emerald-500 transition-all duration-100 ease-linear" style={{ width: `${scanProgress}%` }}></div>
                    </div>
                    <div className="flex gap-2 mt-2">
                        <span className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[10px] px-1.5 py-0.5 rounded">OBJ IDENTIFIED</span>
                        <span className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[10px] px-1.5 py-0.5 rounded">HIGH CONFIDENCE</span>
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
                            <span className="text-xs font-bold text-white">99.8%</span>
                        </div>
                        <div className="h-1.5 w-full bg-gray-800 rounded-full overflow-hidden">
                            <div className="h-full w-[99.8%] bg-emerald-500 shadow-[0_0_10px_#10b981]"></div>
                        </div>
                    </div>

                    {/* Metric 2 */}
                    <div className="group">
                        <div className="flex justify-between items-center mb-1">
                            <span className="text-xs font-mono text-gray-400 group-hover:text-blue-400 transition-colors flex items-center gap-2">
                                <Database className="w-3 h-3" /> DAILY AUDIT COUNT
                            </span>
                            <span className="text-xs font-bold text-white">12,450</span>
                        </div>
                        {/* Monthly Trend Simulation */}
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
                            <span className="text-xs font-bold text-amber-500 animate-pulse">3 DETECTED</span>
                        </div>
                        <div className="p-2 bg-amber-500/10 border border-amber-500/20 rounded text-[10px] text-amber-200 font-mono mt-2">
                            ⚠ SEVERE LEAN DETECTED (ID: MT-4030) <br />
                            ⚠ VEGETATION ENCROACHMENT (ID: MT-4022)
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
                        <div className="text-[10px] text-gray-500 font-mono">SECURE</div>
                    </div>
                </div>

            </div>
        </div>
    )
}
