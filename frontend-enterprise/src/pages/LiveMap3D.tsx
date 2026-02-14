import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { Card } from "@/components/ui/card"
import { Button } from '@/components/ui/button'
import { Badge } from "@/components/ui/badge"
import { Activity, ExternalLink, Map as MapIcon, Layers, Crosshair, Save } from "lucide-react"

interface Asset {
    id: string
    lat: number
    lng: number
    status: string
    confidence: number
    issues?: string[]
    height_m?: number
    detected_at?: string
    tags?: any
    mapillary_key?: string
}

// Helper: Get Tile URL for Satellite View
// const getTileUrl = (lat: number, lng: number, zoom: number) => {
//     const n = Math.pow(2, zoom);
//     const x = Math.floor((lng + 180) / 360 * n);
//     const latRad = lat * Math.PI / 180;
//     const y = Math.floor((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * n);
//     return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${zoom}/${y}/${x}`;
// };

const StatusHUD = ({ onComplete }: { onComplete?: () => void }) => {
    const [status, setStatus] = useState<any>(null)
    const [log, setLog] = useState<string>("")
    const wasRunningRef = useRef(false)

    useEffect(() => {
        const timer = setInterval(() => {
            const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
            fetch(`${apiHost}/api/v2/pipeline/status`).then(res => res.json()).then(data => {
                setStatus(data)

                const isRunning = data && data.status === 'running'

                // Trigger auto-refresh when job finishes
                if (wasRunningRef.current && !isRunning && onComplete) {
                    onComplete()
                }
                wasRunningRef.current = isRunning

                if (isRunning) {
                    fetch(`${apiHost}/api/v2/pipeline/logs?lines=5`).then(res => res.json()).then(l => {
                        const lines = l.logs || []
                        if (lines.length > 0) setLog(lines[lines.length - 1])
                    })
                }
            }).catch(() => { })
        }, 1000)
        return () => clearInterval(timer)
    }, [onComplete])
    if (!status || status.status !== 'running') return null
    let message = "Processing..."
    const lowerLog = log.toLowerCase()
    if (lowerLog.includes("epoch")) message = "Network Training (Fine-Tuning)..."
    else if (lowerLog.includes("ingestion")) message = "Ingesting Imagery..."
    else if (lowerLog.includes("unified detection")) message = "Re-Scanning Affected Tiles..."
    else if (lowerLog.includes("fusion")) message = "Fusing & Updating Map..."
    else if (lowerLog.includes("reset")) message = "Resetting Dataset..."
    return (
        <div className="fixed bottom-0 left-0 right-0 bg-slate-900/90 border-t border-cyan-500/30 p-2 z-[2000] flex items-center justify-center gap-4 text-sm text-cyan-400 font-mono shadow-[0_-4px_20px_rgba(0,0,0,0.5)] animate-in slide-in-from-bottom fade-in duration-300">
            <Activity className="h-4 w-4 animate-spin text-cyan-400" />
            <span className="font-bold tracking-wider uppercase">{message}</span>
            {log && log.length > 5 && (
                <span className="text-xs text-slate-500 hidden md:inline-block max-w-lg truncate border-l border-slate-700 pl-3 ml-3">{log}</span>
            )}
        </div>
    )
}

// Helper: Static Map for Thumbnails
const getStaticMapUrl = (lat: number, lng: number, width: number, height: number) => {
    const delta = 0.001;
    const bbox = `${lng - delta},${lat - delta},${lng + delta},${lat + delta}`;
    return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox=${bbox}&bboxSR=4326&size=${width},${height}&f=image`;
};

// Component to fetch and display Mapillary Image
const MapillaryImage = ({ imageKey }: { imageKey: string }) => {
    const [imageUrl, setImageUrl] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        if (!imageKey) return
        const token = import.meta.env.VITE_MAPILLARY_TOKEN
        if (!token) return

        fetch(`https://graph.mapillary.com/${imageKey}?access_token=${token}&fields=thumb_2048_url`)
            .then(res => res.json())
            .then(data => {
                if (data.thumb_2048_url) setImageUrl(data.thumb_2048_url)
                setLoading(false)
            })
            .catch(err => {
                console.error("Mapillary fetch error:", err)
                setLoading(false)
            })
    }, [imageKey])

    if (loading) return <div className="h-full flex items-center justify-center text-cyan-500 animate-pulse text-xs">Loading Mapillary...</div>
    if (!imageUrl) return <div className="h-full flex items-center justify-center text-gray-500 text-xs">Image Unavailable</div>

    return (
        <div className="relative w-full h-full bg-black overflow-hidden group">
            <img src={imageUrl} className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <a href={`https://www.mapillary.com/app/?pKey=${imageKey}`} target="_blank" className="text-white text-xs underline">Open in Mapillary</a>
            </div>
        </div>
    )
}


// ----------------------------------------------------------------------------
// FLOATING MARKER COMPONENT
// ----------------------------------------------------------------------------
const PoleMarker = ({ pole, onExpand, isExpanded, onHoverState }: {
    pole: Asset,
    onExpand: () => void,
    isExpanded: boolean,
    onHoverState: (isHovering: boolean) => void
}) => {
    const imageUrl = getStaticMapUrl(pole.lat, pole.lng, 200, 200)

    return (
        <div
            className={`flex flex-col items-center origin-bottom animate-in zoom-in-50 duration-500 ${isExpanded ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}
            onMouseEnter={() => onHoverState(true)}
            onMouseLeave={() => onHoverState(false)}
        >
            <div className="animate-in slide-in-from-bottom-10 fade-in duration-700 ease-out group perspective-1000 origin-bottom">
                <Card
                    className="w-[180px] backdrop-blur-3xl bg-black/90 border border-emerald-500/50 shadow-[0_20px_50px_rgba(0,0,0,0.5)] rounded-sm overflow-hidden cursor-pointer transition-transform duration-300 hover:scale-110 z-10"
                    onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        onExpand()
                    }}
                >
                    <div className="px-2 py-1.5 border-b border-white/10 flex justify-between items-center bg-gradient-to-r from-emerald-950 to-black">
                        <span className="text-[10px] font-mono text-emerald-400 font-bold tracking-widest pl-1">
                            #{pole.id.slice(-6).toUpperCase()}
                        </span>
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse box-shadow-[0_0_10px_#10b981]" />
                    </div>
                    <div className="relative h-20 w-full bg-neutral-900 group overflow-hidden">
                        <div
                            className="absolute inset-0 bg-cover bg-center transition-transform duration-500 hover:scale-110"
                            style={{ backgroundImage: `url(${imageUrl})`, filter: 'contrast(1.2) brightness(1.1)' }}
                        />
                        <div className="absolute bottom-0 right-0 p-1">
                            <span className="text-[10px] font-bold font-mono text-black bg-emerald-400 px-1 rounded-sm">
                                {(pole.confidence * 100).toFixed(0)}%
                            </span>
                        </div>
                    </div>
                </Card>
            </div>
            <div className="h-[80px] w-[2px] bg-gradient-to-b from-emerald-400 via-emerald-500/30 to-transparent shadow-[0_0_10px_#10b981] animate-in zoom-in-y duration-700 origin-bottom"></div>
            <div className="relative flex items-center justify-center w-8 h-8 pointer-events-auto cursor-pointer" onClick={(e) => { e.stopPropagation(); onExpand() }}>
                <div className="absolute inset-0 border border-emerald-500/30 rounded-full animate-[ping_2s_infinite]"></div>
                <div className="w-4 h-4 rounded-full bg-[radial-gradient(circle_at_30%_30%,_#4ade80,_#059669)] shadow-[0_0_20px_#22c55e] relative z-20 ring-1 ring-black/50"></div>
            </div>
        </div>
    )
}

export default function LiveMap3D({ mode = 'full' }: { mode?: 'full' | 'widget' }) {
    const mapContainer = useRef<HTMLDivElement>(null)
    const map = useRef<maplibregl.Map | null>(null)
    const removalTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
    const hoveredPoleIdRef = useRef<string | null>(null)
    const [activePoles, setActivePoles] = useState<Asset[]>([])
    const [expandedPoleId, setExpandedPoleId] = useState<string | null>(null)
    const expandedPoleIdRef = useRef<string | null>(null)
    useEffect(() => { expandedPoleIdRef.current = expandedPoleId }, [expandedPoleId])

    // UI Stats
    const [imgState, setImgState] = useState({ scale: 1, x: 0, y: 0, dragging: false, startX: 0, startY: 0 })
    const [streetViewOpen, setStreetViewOpen] = useState(false)
    const [slideOutMode, setSlideOutMode] = useState<'google' | 'mapillary'>('mapillary')

    // Zoom/Pan Handler for Main Modal Image
    const handleWheel = (e: React.WheelEvent) => {
        e.stopPropagation(); setImgState(prev => {
            let newScale = prev.scale - e.deltaY * 0.001; newScale = Math.min(Math.max(1, newScale), 5); return { ...prev, scale: newScale }
        })
    }
    const handleMouseDown = (e: React.MouseEvent) => { e.preventDefault(); setImgState(prev => ({ ...prev, dragging: true, startX: e.clientX - prev.x, startY: e.clientY - prev.y })) }
    const handleMouseMove = (e: React.MouseEvent) => { if (!imgState.dragging) return; setImgState(prev => ({ ...prev, x: e.clientX - prev.startX, y: e.clientY - prev.startY })) }
    const handleMouseUp = () => setImgState(prev => ({ ...prev, dragging: false }))

    // Auto-Open Logic
    useEffect(() => {
        setImgState({ scale: 2.5, x: 0, y: 0, dragging: false, startX: 0, startY: 0 }) // Reset Zoom
        if (expandedPoleId) {
            setStreetViewOpen(false)
            setSlideOutMode('mapillary') // Default to Mapillary
            setTimeout(() => setStreetViewOpen(true), 600) // Delay slide out
        } else {
            setStreetViewOpen(false)
        }
    }, [expandedPoleId])

    const expandedPole = activePoles.find(p => p.id === expandedPoleId)
    const sensors = expandedPole?.tags?.sensors || ['Satellite (Primary)']
    const pearlId = expandedPole?.tags?.pearl_string_id
    // Prioritize the verified image used for placement, then fallback to general key
    const streetKey = expandedPole?.tags?.confirmed_by_image || expandedPole?.mapillary_key

    const markersRef = useRef<Map<string, { marker: maplibregl.Marker, root: any }>>(new Map())
    const isRotatingRef = useRef(true)
    const isInteractingRef = useRef(false)
    const [assets, setAssets] = useState<Asset[]>([])
    useEffect(() => { void assets }, [assets]) // Dummy usageState(true)
    const [isRotating, setIsRotating] = useState(true)

    // TRAIN MODE STATE
    const [isTrainMode, setIsTrainMode] = useState(false)
    const isTrainModeRef = useRef(false)
    const [trainingClicks, setTrainingClicks] = useState<any[]>([])
    const trainTimeoutRef = useRef<any>(null)
    useEffect(() => { isTrainModeRef.current = isTrainMode }, [isTrainMode])

    // Auto-Pause Rotation same time as Cursor Change
    useEffect(() => {
        setIsRotating(!isTrainMode)
        if (map.current) {
            map.current.getCanvas().style.cursor = isTrainMode ? 'crosshair' : ''
        }
    }, [isTrainMode])

    const commitTraining = async (auto = false) => {
        if (trainTimeoutRef.current) clearTimeout(trainTimeoutRef.current)
        const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
        await fetch(`${apiHost}/api/v2/pipeline/run/train_satellite`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ params: { epochs: 20, batch_size: 16, continuous: true } })
        })
        if (!auto) { alert("Continuous Training Started!") } else { console.log("Auto-Training Started") }
        setTrainingClicks([])
        setIsTrainMode(false)
    }

    // Auto-Train Watcher
    useEffect(() => {
        if (trainingClicks.length === 0) return
        if (trainTimeoutRef.current) clearTimeout(trainTimeoutRef.current)
        trainTimeoutRef.current = setTimeout(() => { commitTraining(true) }, 5000)
    }, [trainingClicks])

    // Sync Map Source
    useEffect(() => {
        if (!map.current || !map.current.getSource('training-points')) return
        (map.current.getSource('training-points') as maplibregl.GeoJSONSource).setData({
            type: 'FeatureCollection',
            features: trainingClicks.map(p => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [p.lng, p.lat] }, properties: {} }))
        } as any)
    }, [trainingClicks])

    // Sync state to ref
    useEffect(() => { isRotatingRef.current = isRotating }, [isRotating])

    // 1. Initialize Map
    useEffect(() => {
        if (map.current || !mapContainer.current) return
        map.current = new maplibregl.Map({
            container: mapContainer.current,
            style: { version: 8, sources: { 'esri-satellite': { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, attribution: 'Esri, Maxar' } }, layers: [{ id: 'satellite-layer', type: 'raster', source: 'esri-satellite', paint: { 'raster-fade-duration': 0, 'raster-saturation': -0.3, 'raster-contrast': 0.1 } }] },
            center: [-98, 39], zoom: 2.5, pitch: 0, bearing: 0, maxPitch: 85,
            // @ts-ignore
            antialias: true
        })

        const handleInteractStart = () => { isInteractingRef.current = true }
        const handleInteractEnd = () => { isInteractingRef.current = false }
        map.current.on('mousedown', handleInteractStart); map.current.on('mouseup', handleInteractEnd)
        map.current.on('dragstart', handleInteractStart); map.current.on('dragend', handleInteractEnd)

        map.current.on('load', async () => {
            if (!map.current) return
            isRotatingRef.current = false; setIsRotating(false)
            map.current.addSource('terrain-source', { type: 'raster-dem', tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'], encoding: 'terrarium', tileSize: 256, maxzoom: 12 })
            map.current.addSource('assets', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
            map.current.addLayer({ id: 'assets-glow', type: 'circle', source: 'assets', paint: { 'circle-radius': 12, 'circle-color': ['match', ['get', 'status'], 'Verified', '#22c55e', 'Moved', '#f97316', 'New', '#06b6d4', 'Review', '#f59e0b', '#ef4444'], 'circle-opacity': 0.2, 'circle-blur': 0.8 } })

            // Context
            try {
                const cData = await fetch('/pa_counties.geojson').then(r => r.json())
                map.current?.addSource('counties', { type: 'geojson', data: cData })
                map.current?.addLayer({ id: 'counties-line', type: 'line', source: 'counties', paint: { 'line-color': '#22d3ee', 'line-width': 1, 'line-opacity': 0.3 } })
                const nData = await fetch('/pole_network_v2.geojson').then(r => r.json())
                map.current?.addSource('network', { type: 'geojson', data: nData })
                map.current?.addLayer({ id: 'network-line', type: 'line', source: 'network', paint: { 'line-color': '#22d3ee', 'line-width': 3, 'line-opacity': 0.6 } })

                // Training Layer
                if (!map.current.getSource('training-points')) {
                    map.current.addSource('training-points', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
                    map.current.addLayer({ id: 'training-points-circle', type: 'circle', source: 'training-points', paint: { 'circle-radius': 6, 'circle-color': '#9333ea', 'circle-stroke-width': 2, 'circle-stroke-color': '#d8b4fe' } })
                }

                // Click Handler
                map.current?.on('click', (e) => {
                    if (isTrainModeRef.current) {
                        const newClick = { lat: e.lngLat.lat, lng: e.lngLat.lng, id: Date.now() }
                        setTrainingClicks(prev => [...prev, newClick])
                        const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
                        fetch(`${apiHost}/api/v2/annotation/from_map`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ lat: e.lngLat.lat, lon: e.lngLat.lng, dataset: 'satellite' })
                        }).catch(console.error)
                    }
                })
            } catch (e) { console.error("Map Init Failed:", e) }

            // Landing
            const TARGET_LAT = 40.19; const TARGET_LNG = -76.73
            map.current?.flyTo({ center: [TARGET_LNG, TARGET_LAT], zoom: 11, pitch: 0, speed: 1.2, essential: true })
            map.current.once('moveend', () => {
                map.current?.setTerrain({ source: 'terrain-source', exaggeration: 1.5 })
                map.current?.easeTo({ center: [TARGET_LNG, TARGET_LAT], zoom: 15.5, pitch: 45, bearing: 25, duration: 4000, essential: true })
                setTimeout(() => { isRotatingRef.current = true; setIsRotating(true) }, 4500)
            })

            fetchAssets(null).then(loadedAssets => {
                if (loadedAssets.length > 0) {
                    const hero = loadedAssets.sort((a, b) => Math.sqrt((a.lat - TARGET_LAT) ** 2 + (a.lng - TARGET_LNG) ** 2) - Math.sqrt((b.lat - TARGET_LAT) ** 2 + (b.lng - TARGET_LNG) ** 2))[0]
                    setActivePoles([hero])
                }
            })
        })

        // Rotation Loop
        let animationFrameId: number; const rotate = () => { if (isRotatingRef.current && !isInteractingRef.current && map.current) map.current.setBearing(map.current.getBearing() + 0.04); animationFrameId = requestAnimationFrame(rotate) }
        rotate()
        return () => { cancelAnimationFrame(animationFrameId); if (map.current) { map.current.remove(); map.current = null } }
    }, [])

    // Hover Interaction Handlers (Simplified for brevity, same logic)
    useEffect(() => {
        if (!map.current) return
        const scheduleRemoval = (id: string) => { if (removalTimers.current.has(id)) clearTimeout(removalTimers.current.get(id)!); const t = setTimeout(() => { if (expandedPoleIdRef.current !== id) setActivePoles(p => p.filter(x => x.id !== id)); removalTimers.current.delete(id) }, 3000); removalTimers.current.set(id, t) }
        map.current.on('mouseenter', 'assets-glow', (e) => {
            const f = e.features?.[0]; if (!f) return
            const p = { id: f.properties?.id, lat: (f.geometry as any).coordinates[1], lng: (f.geometry as any).coordinates[0], status: f.properties?.status, confidence: f.properties?.confidence } as Asset
            hoveredPoleIdRef.current = p.id; clearTimeout(removalTimers.current.get(p.id)!); removalTimers.current.delete(p.id)
            setActivePoles(prev => prev.find(x => x.id === p.id) ? prev : [...prev.slice(-2), p])
        })
        map.current.on('mouseleave', 'assets-glow', () => { if (hoveredPoleIdRef.current) scheduleRemoval(hoveredPoleIdRef.current) })
    }, [])

    // --- DYNAMIC REGION MANAGEMENT ---
    interface RegionConfig {
        id: string
        label: string
        center: [number, number]
        zoom: number
        bbox: { min_lat: number, max_lat: number, min_lng: number, max_lng: number }
    }

    const [availableRegions, setAvailableRegions] = useState<RegionConfig[]>([])
    const [currentRegion, setCurrentRegion] = useState<string>('dauphin_pa') // Default ID

    // Fetch Regions from Backend
    useEffect(() => {
        const fetchRegions = async () => {
            const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
            try {
                const res = await fetch(`${apiHost}/api/v2/pipeline/datasets`)
                const data: Record<string, any[]> = await res.json()

                // Flatten and filter for regions with geo-metadata
                const validRegions: RegionConfig[] = []
                Object.values(data).forEach(stateList => {
                    stateList.forEach(d => {
                        if (d.bbox && d.center) {
                            validRegions.push({
                                id: d.id,
                                label: d.name,
                                center: d.center,
                                zoom: d.zoom || 11,
                                bbox: d.bbox
                            })
                        }
                    })
                })
                setAvailableRegions(validRegions)

                // Set initial Assets fetch if we have a default
                const def = validRegions.find(r => r.id === 'dauphin_pa') || validRegions[0]
                if (def && map.current) {
                    setCurrentRegion(def.id)
                    fetchAssets(def)
                }
            } catch (e) { console.error("Failed to fetch regions", e) }
        }

        fetchRegions()
    }, [])

    // Handle Region Change
    const handleRegionChange = (regionId: string) => {
        const r = availableRegions.find(rr => rr.id === regionId)
        if (!r || !map.current) return

        setCurrentRegion(regionId)

        // Fly to new region
        map.current.flyTo({
            center: r.center,
            zoom: r.zoom,
            pitch: 0,
            essential: true
        })

        // Refresh Assets
        fetchAssets(r)
    }

    // Portal Marker Rendering
    useEffect(() => {
        if (!map.current) return
        const activeIds = new Set(activePoles.map(p => p.id))
        markersRef.current.forEach((val, id) => { if (!activeIds.has(id)) { val.marker.remove(); setTimeout(() => val.root.unmount(), 0); markersRef.current.delete(id) } })
        activePoles.forEach(pole => {
            if (!markersRef.current.has(pole.id)) {
                const el = document.createElement('div'); el.className = 'pole-marker-root'
                const marker = new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat([pole.lng, pole.lat]).addTo(map.current!)
                markersRef.current.set(pole.id, { marker, root: createRoot(el) })
            }
            const { root } = markersRef.current.get(pole.id)!
            const handleHover = (h: boolean) => { if (h) { clearTimeout(removalTimers.current.get(pole.id)!); removalTimers.current.delete(pole.id) } else { const t = setTimeout(() => { if (expandedPoleIdRef.current !== pole.id) setActivePoles(prev => prev.filter(x => x.id !== pole.id)) }, 3000); removalTimers.current.set(pole.id, t) } }
            root.render(<PoleMarker pole={pole} isExpanded={expandedPoleId === pole.id} onExpand={() => setExpandedPoleId(pole.id)} onHoverState={handleHover} />)
        })
    }, [activePoles, expandedPoleId])

    const fetchAssets = async (region: RegionConfig | null) => {
        const r = region || availableRegions.find(x => x.id === currentRegion)
        if (!r) return []

        const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
        try {
            const res = await fetch(`${apiHost}/api/v2/assets?min_lat=${r.bbox.min_lat}&max_lat=${r.bbox.max_lat}&min_lng=${r.bbox.min_lng}&max_lng=${r.bbox.max_lng}`)
            const data: Asset[] = await res.json()
            setAssets(data)

            // Note: We are using a client-side filter for the "FeatureCollection" source update
            if (map.current?.getSource('assets')) {
                (map.current.getSource('assets') as maplibregl.GeoJSONSource).setData({
                    type: 'FeatureCollection',
                    features: data.map(a => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [a.lng, a.lat] }, properties: a }))
                } as any)
            }
            return data
        } catch { return [] }
    }

    // Initial Load - handled by fetchRegions effect now
    useEffect(() => { }, [])

    return (
        <div className={`relative w-full rounded-lg overflow-hidden border border-white/10 shadow-2xl bg-black ${mode === 'widget' ? 'h-full min-h-[400px]' : 'h-[calc(100vh-6rem)]'}`}>
            <StatusHUD />
            {/* CONTROLS */}
            <div className="absolute top-4 right-4 z-[2000] flex flex-col gap-2 pointer-events-auto">
                <Button
                    variant={isTrainMode ? "default" : "outline"}
                    size="sm"
                    onClick={() => setIsTrainMode(!isTrainMode)}
                    className={`backdrop-blur-md border-primary/20 ${isTrainMode ? 'bg-purple-600 hover:bg-purple-700 text-white' : 'bg-background/60 hover:bg-primary/20'}`}
                >
                    <Crosshair className="h-4 w-4 mr-2" />
                    {isTrainMode ? "Training Mode ON" : "Train Mode"}
                </Button>
                {trainingClicks.length > 0 && (
                    <Button size="sm" onClick={() => commitTraining(false)} className="bg-green-600 hover:bg-green-700 text-white animate-in slide-in-from-right fade-in duration-300">
                        <Save className="h-4 w-4 mr-2" />
                        Commit ({trainingClicks.length})
                    </Button>
                )}
            </div>

            <div ref={mapContainer} className={`w-full h-full ${isTrainMode ? 'cursor-crosshair' : ''}`} />

            {/* INSPECTOR MODAL + SLIDE-OUT WITH CENTERED ALIGNMENT */}
            {expandedPole && (
                <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in duration-300"
                    onClick={(e) => { e.stopPropagation(); setExpandedPoleId(null) }}
                >
                    {/* CENTERED CONTAINER - Animates Width to Include slide-out */}
                    <div
                        className="relative h-[550px] transition-all duration-500 ease-[cubic-bezier(0.23,1,0.32,1)] flex"
                        style={{ width: streetViewOpen ? '1400px' : '900px' }} // 900 + 500
                        onClick={(e) => e.stopPropagation()}
                    >

                        {/* MAIN CARD (Fixed 900px) */}
                        <div className="relative z-20 w-[900px] h-full bg-black border border-emerald-500/50 rounded-xl shadow-2xl overflow-hidden flex shrink-0">
                            {/* IMAGE SIDE (60%) */}
                            <div className="w-[60%] h-full relative bg-neutral-950 overflow-hidden border-r border-white/10"
                                onWheel={handleWheel} onMouseDown={handleMouseDown} onMouseMove={handleMouseMove} onMouseUp={handleMouseUp} onMouseLeave={handleMouseUp}>
                                <div className="absolute inset-0 bg-neutral-900 flex items-center justify-center cursor-crosshair">
                                    <div className="w-full h-full bg-cover bg-center transition-transform duration-75"
                                        style={{ backgroundImage: `url(${getStaticMapUrl(expandedPole.lat, expandedPole.lng, 800, 600)})`, filter: 'contrast(1.1) brightness(1.1)', transform: `scale(${imgState.scale}) translate(${imgState.x}px, ${imgState.y}px)`, cursor: imgState.dragging ? 'grabbing' : 'grab' }}
                                    />
                                </div>
                                <div className="absolute top-4 left-4 text-xs font-mono text-emerald-500 bg-black/70 px-2 py-1 rounded border border-emerald-500/20">RAW FEED // {imgState.scale.toFixed(1)}x ZOOM</div>
                            </div>

                            {/* DATA SIDE (40%) */}
                            <div className="w-[40%] h-full bg-gradient-to-br from-gray-900 to-black p-6 flex flex-col relative z-30">
                                <button onClick={() => setExpandedPoleId(null)} className="absolute top-4 right-4 text-gray-400 hover:text-white"><ExternalLink className="w-5 h-5" /></button>

                                <h2 className="text-2xl font-black text-white tracking-tight leading-none mb-1">ASSET DETECTED</h2>
                                <div className="text-emerald-500 font-mono text-xs mb-6">{expandedPole.id}</div>

                                <div className="space-y-5 overflow-y-auto pr-2 custom-scrollbar">
                                    {/* 1. STATUS & CONFIDENCE */}
                                    <div className="flex justify-between items-center bg-white/5 p-3 rounded">
                                        <div className="flex flex-col">
                                            <span className="text-[10px] text-gray-500 font-mono text-left">STATUS</span>
                                            <Badge className={`mt-1 ${expandedPole.status === 'Verified' ? 'bg-green-500' : 'bg-amber-500'}`}>{expandedPole.status}</Badge>
                                        </div>
                                        <div className="text-right">
                                            <span className="text-[10px] text-gray-500 font-mono">CONFIDENCE</span>
                                            <div className="text-2xl font-bold text-emerald-400">{(expandedPole.confidence * 100).toFixed(0)}%</div>
                                        </div>
                                    </div>

                                    {/* 2. FUSION */}
                                    <div>
                                        <div className="text-[10px] text-gray-500 font-mono mb-2 flex items-center gap-1"><Layers className="w-3 h-3" /> SENSOR FUSION</div>
                                        <div className="grid grid-cols-2 gap-2">
                                            {sensors.map((s: string) => (
                                                <div key={s} className="bg-emerald-950/30 border border-emerald-500/20 p-2 rounded text-xs text-emerald-300 flex items-center justify-center">{s}</div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* 3. PEARL STRING */}
                                    {pearlId && (
                                        <div className="bg-pink-950/20 border border-pink-500/30 p-3 rounded">
                                            <div className="flex items-center gap-2 text-pink-400 text-xs font-bold mb-1"><Activity className="w-3 h-3" /> WIRE NETWORK</div>
                                            <div className="text-[10px] text-gray-400 break-all">{pearlId}</div>
                                        </div>
                                    )}

                                    {/* 4. COORDINATES & HEIGHT */}
                                    <div className="grid grid-cols-2 gap-4 text-xs font-mono text-gray-400 pt-2 border-t border-white/10">
                                        <div>
                                            <div>LATITUDE</div>
                                            <div className="text-white">{expandedPole.lat.toFixed(6)}</div>
                                        </div>
                                        <div>
                                            <div>EST. HEIGHT</div>
                                            <div className="text-white">{expandedPole.height_m ? expandedPole.height_m.toFixed(1) + 'm' : 'N/A'}</div>
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-auto pt-4 text-[10px] text-center text-gray-600">Double-click map to recalibrate</div>
                            </div>
                        </div>

                        {/* SLIDE OUT PANEL (500px) */}
                        <div
                            className="relative z-10 w-[500px] h-full bg-zinc-950 border-y border-r border-zinc-800 rounded-r-xl shadow-2xl shrink-0 overflow-hidden flex flex-col"
                            style={{
                                opacity: streetViewOpen ? 1 : 0,
                                transform: streetViewOpen ? 'translateX(0)' : 'translateX(-50px)', // Subtle parallax
                                transition: 'all 0.5s ease-out 0.1s' // Slight delay to follow container expansion
                            }}
                        >
                            <div className="bg-black px-4 py-2 border-b border-zinc-800 flex items-center justify-between">
                                <span className="text-[10px] font-mono text-emerald-500 flex items-center gap-2"><MapIcon className="w-3 h-3" /> STREET VIEW VERIFICATION</span>
                                <div className="flex gap-1.5">
                                    <button
                                        onClick={() => setSlideOutMode('google')}
                                        className={`text-[9px] px-2 py-0.5 rounded border transition-colors font-mono tracking-wider ${slideOutMode === 'google' ? 'bg-zinc-800 text-white border-zinc-600' : 'text-zinc-500 border-transparent hover:text-zinc-300'}`}
                                    >
                                        GOOGLE
                                    </button>
                                    <button
                                        onClick={() => setSlideOutMode('mapillary')}
                                        className={`text-[9px] px-2 py-0.5 rounded border transition-colors font-mono tracking-wider ${slideOutMode === 'mapillary' ? 'bg-zinc-800 text-white border-zinc-600' : 'text-zinc-500 border-transparent hover:text-zinc-300'}`}
                                    >
                                        MAPILLARY
                                    </button>
                                </div>
                            </div>

                            <div className="flex-1 bg-zinc-900 relative">
                                {slideOutMode === 'google' ? (
                                    <>
                                        {import.meta.env.VITE_GOOGLE_MAPS_API_KEY ? (
                                            <iframe
                                                width="100%" height="100%"
                                                style={{ border: 0 }} loading="lazy" allowFullScreen
                                                src={`https://www.google.com/maps/embed/v1/streetview?key=${import.meta.env.VITE_GOOGLE_MAPS_API_KEY}&location=${expandedPole.lat},${expandedPole.lng}&heading=0&pitch=10&fov=90`}
                                            />
                                        ) : (
                                            <div className="flex flex-col items-center justify-center h-full text-center p-8">
                                                <div className="w-12 h-12 rounded-full border border-yellow-500/30 text-yellow-500 flex items-center justify-center mb-4"><ExternalLink /></div>
                                                <h3 className="text-yellow-500 text-xs font-bold mb-2">API KEY REQUIRED</h3>
                                                <p className="text-zinc-500 text-xs">Configure VITE_GOOGLE_MAPS_API_KEY to see live street view.</p>
                                            </div>
                                        )}
                                    </>
                                ) : (
                                    <>
                                        {streetKey ? (
                                            <MapillaryImage imageKey={streetKey} />
                                        ) : (
                                            <div className="flex flex-col items-center justify-center h-full text-center p-8">
                                                <div className="w-12 h-12 rounded-full border border-zinc-700 text-zinc-500 flex items-center justify-center mb-4"><ExternalLink /></div>
                                                <h3 className="text-zinc-400 text-xs font-bold mb-2">NO MAPILLARY DATA</h3>
                                                <p className="text-zinc-600 text-xs">No aligned street view image found.</p>
                                            </div>
                                        )}
                                    </>
                                )}
                            </div>
                        </div>

                    </div>
                </div>
            )}

            {/* UI OVERLAYS */}
            <div className="fixed inset-x-0 bottom-0 pointer-events-none z-[1900]">
                {/* This wrapper ensures HUD is above map but lets map be clicked */}
                <div className="pointer-events-auto">
                    <StatusHUD onComplete={() => fetchAssets(null)} />
                </div>
            </div>

            {mode === 'full' && (
                <div className="absolute bottom-8 left-8 flex gap-2 z-10 items-center">
                    {availableRegions.length > 0 && (
                        <div className="relative group">
                            <div className="flex items-center gap-2 px-3 py-2 bg-black/60 backdrop-blur-md border border-white/10 rounded-md text-white/80 hover:bg-black/80 hover:text-white transition-all cursor-pointer">
                                <span className="text-[10px] font-mono tracking-widest text-emerald-500">REGION_LOCK //</span>
                                <span className="text-xs font-bold">
                                    {availableRegions.find(r => r.id === currentRegion)?.label || "Select Region"}
                                </span>
                            </div>
                            {/* Dropdown Menu */}
                            <div className="absolute bottom-full mb-2 left-0 w-48 bg-black/90 border border-white/10 rounded-md shadow-xl overflow-hidden opacity-0 group-hover:opacity-100 pointer-events-none group-hover:pointer-events-auto transition-all">
                                {availableRegions.map((r) => (
                                    <div
                                        key={r.id}
                                        onClick={() => handleRegionChange(r.id)}
                                        className={`px-4 py-2 text-xs cursor-pointer hover:bg-emerald-900/30 hover:text-emerald-400 border-b border-white/5 last:border-0 ${currentRegion === r.id ? 'text-emerald-500 font-bold' : 'text-gray-400'}`}
                                    >
                                        {r.label}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    <Button variant="outline" className="backdrop-blur-md bg-white/5 border-white/10 hover:bg-white/10 text-white/70 hover:text-white transition-all duration-500 font-mono text-xs tracking-widest" onClick={() => setIsRotating(!isRotating)}>{isRotating ? 'FREEZE' : 'ORBIT'}</Button>
                </div>
            )}
        </div>
    )
}
