import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { Card } from "@/components/ui/card"
import { Button } from '@/components/ui/button'

interface Asset {
    id: string
    lat: number
    lng: number
    status: string
    confidence: number
}

// Helper to get Centered Static Map Image (Export API)
// This guarantees the pole is exactly in the center, no tile edge issues.
const getStaticMapUrl = (lat: number, lng: number, width: number, height: number) => {
    // Define a small bounding box around the point.
    // 0.001 degrees is roughly 110 meters.
    // This provides a good context view (approx 20cm/pixel at 600px width)
    const delta = 0.001;
    const bbox = `${lng - delta},${lat - delta},${lng + delta},${lat + delta}`;
    return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox=${bbox}&bboxSR=4326&size=${width},${height}&f=image`;
};

// ... (PoleMarker definitions omitted for brevity - no changes needed inside component definition) ...

export default function LiveMap3D({ mode = 'full' }: { mode?: 'full' | 'widget' }) {
    // ... (state refs omitted) ...
    const mapContainer = useRef<HTMLDivElement>(null)
    const map = useRef<maplibregl.Map | null>(null)

    const [activePoles, setActivePoles] = useState<Asset[]>([])
    const [expandedPoleId, setExpandedPoleId] = useState<string | null>(null) // Track expanded

    // Derived selected pole
    const expandedPole = activePoles.find(p => p.id === expandedPoleId)

    const markersRef = useRef<Map<string, { marker: maplibregl.Marker, root: any }>>(new Map())

    // Animation Refs
    const isRotatingRef = useRef(true)
    const isInteractingRef = useRef(false) // Track user interaction to pause rotation
    const [assets, setAssets] = useState<Asset[]>([])
    const [isRotating, setIsRotating] = useState(true)

    // Sync state to ref
    useEffect(() => {
        isRotatingRef.current = isRotating
    }, [isRotating])

    // ... (Map Init logic omitted) ...

    // ... (Multi-marker scanner loop omitted) ...

    // SYNC ACTIVE POLES TO DOM MARKERS
    useEffect(() => {
        if (!map.current) return

        // 1. Remove markers not in activePoles
        const activeIds = new Set(activePoles.map(p => p.id))
        markersRef.current.forEach((val, id) => {
            if (!activeIds.has(id)) {
                val.marker.remove()
                setTimeout(() => val.root.unmount(), 0) // Clean up React root
                markersRef.current.delete(id)
            }
        })

        // 2. Add/Update markers
        activePoles.forEach(pole => {
            if (!markersRef.current.has(pole.id)) {
                // Create DOM Node
                const el = document.createElement('div')
                el.className = 'pole-marker-root'

                // Create Marker
                const marker = new maplibregl.Marker({
                    element: el,
                    anchor: 'bottom' // Tether grows up from bottom
                })
                    .setLngLat([pole.lng, pole.lat])
                    .addTo(map.current!) // Non-null assertion for map

                // Create React Root
                const root = createRoot(el)
                markersRef.current.set(pole.id, { marker, root })
            }

            // RENDER (Update props including expanded state)
            const { root } = markersRef.current.get(pole.id)!
            root.render(
                <PoleMarker
                    pole={pole}
                    isExpanded={expandedPoleId === pole.id}
                    onExpand={() => {
                        setExpandedPoleId(pole.id)
                        // Rotation CONTINUES during expand (per user request)
                    }}
                    onClose={() => {
                        setExpandedPoleId(null)
                    }}
                />
            )
        })

    }, [activePoles, expandedPoleId])


    return (
        <div className={`relative w-full rounded-lg overflow-hidden border border-white/10 shadow-2xl bg-black ${mode === 'widget' ? 'h-full min-h-[400px]' : 'h-[calc(100vh-6rem)]'}`}>

            {/* 3D Map Container */}
            <div ref={mapContainer} className="w-full h-full" />

            {/* EXPANDED MODAL (Hoisted out of Map DOM) */}
            {expandedPole && (
                <div
                    className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/30 backdrop-blur-[2px] animate-in fade-in duration-300"
                    onClick={(e) => {
                        e.stopPropagation()
                        setExpandedPoleId(null)
                    }}
                >
                    <div
                        className="relative w-[900px] h-[500px] bg-black border border-emerald-500/50 rounded-xl shadow-2xl overflow-hidden flex animate-in zoom-in-95 duration-300"
                        onClick={(e) => e.stopPropagation()}
                    >
                        {/* LEFT: IMAGE (60%) */}
                        <div className="w-[60%] h-full relative bg-neutral-900 overflow-hidden border-r border-white/10">
                            <div
                                className="w-full h-full bg-cover bg-center transition-transform duration-700 hover:scale-105"
                                style={{
                                    backgroundImage: `url(${getStaticMapUrl(expandedPole.lat, expandedPole.lng, 600, 500)})`,
                                    filter: 'contrast(1.1) brightness(1.1)'
                                }}
                            />
                            {/* Reticle */}
                            <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                                <div className="absolute w-[2px] h-20 bg-emerald-500/50"></div>
                                <div className="absolute w-20 h-[2px] bg-emerald-500/50"></div>
                                <div className="w-16 h-16 border-2 border-emerald-500/50 rounded-full"></div>
                                <div className="absolute top-4 left-4 text-xs font-mono text-emerald-500 bg-black/50 px-2 py-1 rounded">
                                    SOURCE: ESRI / MAXAR // {new Date().toLocaleDateString().toUpperCase()}
                                </div>
                            </div>
                        </div>

                        {/* RIGHT: DATA (40%) */}
                        <div className="w-[40%] h-full bg-gradient-to-br from-gray-900 to-black p-8 flex flex-col justify-between">
                            {/* Close */}
                            <button
                                onClick={(e) => {
                                    e.stopPropagation()
                                    setExpandedPoleId(null)
                                }}
                                className="absolute top-4 right-4 text-gray-400 hover:text-white transition-colors"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                            </button>

                            <div>
                                <h2 className="text-3xl font-black text-white tracking-tight mb-1">ASSET DETECTED</h2>
                                <div className="text-emerald-400 font-mono text-lg mb-8">ID: {expandedPole.id}</div>

                                <div className="space-y-6">
                                    <div>
                                        <div className="text-xs font-mono text-gray-500 mb-1">COORDINATES</div>
                                        <div className="text-xl font-mono text-white tracking-widest">{expandedPole.lat.toFixed(5)} N</div>
                                        <div className="text-xl font-mono text-white tracking-widest">{expandedPole.lng.toFixed(5)} W</div>
                                    </div>

                                    <div>
                                        <div className="text-xs font-mono text-gray-500 mb-1">CONFIDENCE SCORE</div>
                                        <div className="flex items-center gap-3">
                                            <div className="h-2 flex-1 bg-gray-800 rounded-full overflow-hidden">
                                                <div className="h-full bg-emerald-500 shadow-[0_0_10px_#10b981]" style={{ width: `${expandedPole.confidence * 100}%` }}></div>
                                            </div>
                                            <span className="text-2xl font-bold text-emerald-400">{(expandedPole.confidence * 100).toFixed(0)}%</span>
                                        </div>
                                    </div>

                                    <div>
                                        <div className="text-xs font-mono text-gray-500 mb-1">STATUS</div>
                                        <span className="inline-block px-3 py-1 bg-emerald-500/10 border border-emerald-500/40 text-emerald-400 rounded text-sm font-bold tracking-wider">
                                            VERIFIED ACTIVE
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <Button
                                className="w-full h-12 bg-white text-black hover:bg-gray-200 font-bold tracking-widest text-sm rounded-sm transition-all shadow-[0_0_20px_rgba(255,255,255,0.3)]"
                                onClick={() => window.open(`https://www.google.com/maps?q&layer=c&cbll=${expandedPole.lat},${expandedPole.lng}`, '_blank')}
                            >
                                OPEN STREET VIEW
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Controls (Only in Full Mode) */}
            {mode === 'full' && (
                <div className="absolute bottom-8 left-8 flex gap-2 z-10">
                    <Button variant="outline" className="backdrop-blur-md bg-white/5 border-white/10 hover:bg-white/10 text-white/70 hover:text-white transition-all duration-500 font-mono text-xs tracking-widest" onClick={() => setIsRotating(!isRotating)}>
                        {isRotating ? 'FREEZE_ORBIT' : 'RESUME_ORBIT'}
                    </Button>
                </div>
            )}

        </div>
    )
}
