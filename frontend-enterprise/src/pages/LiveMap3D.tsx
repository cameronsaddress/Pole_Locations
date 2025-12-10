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

// ----------------------------------------------------------------------------
// FLOATING MARKER COMPONENT
// ----------------------------------------------------------------------------
const PoleMarker = ({ pole, onExpand, onClose, isExpanded }: {
    pole: Asset,
    onExpand: () => void,
    onClose?: () => void,
    isExpanded: boolean
}) => {
    // Fetch a centered 200x200 thumbnail
    const imageUrl = getStaticMapUrl(pole.lat, pole.lng, 200, 200)

    return (
        <div className={`flex flex-col items-center origin-bottom animate-in zoom-in-50 duration-500 ${isExpanded ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}>

            {/* 1. THE FLOATING CARD */}
            <div className="animate-in slide-in-from-bottom-10 fade-in duration-700 ease-out group perspective-1000 origin-bottom">
                <Card
                    className="w-[180px] backdrop-blur-3xl bg-black/90 border border-emerald-500/50 shadow-[0_20px_50px_rgba(0,0,0,0.5)] rounded-sm overflow-hidden cursor-pointer transition-transform duration-300 hover:scale-110 z-10"
                    onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        onExpand()
                    }}
                >

                    {/* Header */}
                    <div className="px-2 py-1.5 border-b border-white/10 flex justify-between items-center bg-gradient-to-r from-emerald-950 to-black">
                        <span className="text-[10px] font-mono text-emerald-400 font-bold tracking-widest pl-1">
                            #{pole.id.slice(-6).toUpperCase()}
                        </span>
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse box-shadow-[0_0_10px_#10b981]" />
                    </div>

                    {/* Image */}
                    <div className="relative h-20 w-full bg-neutral-900 group overflow-hidden">
                        <div
                            className="absolute inset-0 bg-cover bg-center transition-transform duration-500 hover:scale-110"
                            style={{
                                backgroundImage: `url(${imageUrl})`,
                                filter: 'contrast(1.2) brightness(1.1)'
                            }}
                        />
                        {/* Overlay Text */}
                        <div className="absolute bottom-0 right-0 p-1">
                            <span className="text-[10px] font-bold font-mono text-black bg-emerald-400 px-1 rounded-sm">
                                {(pole.confidence * 100).toFixed(0)}%
                            </span>
                        </div>
                    </div>
                </Card>
            </div>

            {/* 2. THE TETHER LINE */}
            <div className="h-[80px] w-[2px] bg-gradient-to-b from-emerald-400 via-emerald-500/30 to-transparent shadow-[0_0_10px_#10b981] animate-in zoom-in-y duration-700 origin-bottom"></div>

            {/* 3. THE GROUND DOT */}
            <div className="relative flex items-center justify-center w-8 h-8 pointer-events-auto cursor-pointer"
                onClick={(e) => {
                    e.stopPropagation()
                    onExpand()
                }}
            >
                <div className="absolute inset-0 border border-emerald-500/30 rounded-full animate-[ping_2s_infinite]"></div>
                <div className="w-4 h-4 rounded-full bg-[radial-gradient(circle_at_30%_30%,_#4ade80,_#059669)] shadow-[0_0_20px_#22c55e] relative z-20 ring-1 ring-black/50"></div>
            </div>

        </div>
    )
}

export default function LiveMap3D({ mode = 'full' }: { mode?: 'full' | 'widget' }) {
    const mapContainer = useRef<HTMLDivElement>(null)
    const map = useRef<maplibregl.Map | null>(null)

    // State for multiple active detections
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

    // 1. Initialize Map
    useEffect(() => {
        if (map.current || !mapContainer.current) return

        map.current = new maplibregl.Map({
            container: mapContainer.current,
            style: {
                version: 8,
                sources: {
                    'esri-satellite': {
                        type: 'raster',
                        tiles: [
                            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
                        ],
                        tileSize: 256,
                        attribution: 'Esri, Maxar, Earthstar Geographics'
                    }
                },
                layers: [
                    {
                        id: 'satellite-layer',
                        type: 'raster',
                        source: 'esri-satellite',
                        paint: {
                            'raster-fade-duration': 0,
                            'raster-saturation': -0.3,
                            'raster-contrast': 0.1
                        }
                    }
                ]
            },
            center: [-98, 39], // US Center (Initial)
            zoom: 2.5, // Globe view
            pitch: 0,
            bearing: 0,
            // @ts-ignore
            antialias: true
        })

        // Interaction Handlers for Fluid Drag
        const handleInteractStart = () => { isInteractingRef.current = true }
        const handleInteractEnd = () => { isInteractingRef.current = false }

        map.current.on('mousedown', handleInteractStart)
        map.current.on('touchstart', handleInteractStart)
        map.current.on('dragstart', handleInteractStart)

        map.current.on('mouseup', handleInteractEnd)
        map.current.on('touchend', handleInteractEnd)
        map.current.on('dragend', handleInteractEnd)
        map.current.on('moveend', handleInteractEnd)


        // On Load Sequence
        map.current.on('load', async () => {
            if (!map.current) return

            // STOP ROTATION to prevent fighting the FlyTo animation
            isRotatingRef.current = false
            setIsRotating(false)

            // ---------------------------------------------------------
            // 0. TERRAIN & LAYERS
            // ---------------------------------------------------------
            map.current.addSource('terrain-source', {
                type: 'raster-dem',
                tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
                encoding: 'terrarium',
                tileSize: 256,
                maxzoom: 13
            })
            map.current.setTerrain({ source: 'terrain-source', exaggeration: 2.5 })

            // Assets Source
            map.current.addSource('assets', {
                type: 'geojson',
                data: { type: 'FeatureCollection', features: [] },
                cluster: false
            })

            // Glow
            map.current.addLayer({
                id: 'assets-glow',
                type: 'circle',
                source: 'assets',
                paint: {
                    'circle-radius': 12,
                    'circle-color': ['match', ['get', 'status'], 'Verified', '#22c55e', 'Moved', '#f97316', 'New', '#06b6d4', 'Review', '#f59e0b', '#ef4444'],
                    'circle-opacity': 0.2,
                    'circle-blur': 0.8
                }
            })

            // Core Dot
            map.current.addLayer({
                id: 'assets-point',
                type: 'circle',
                source: 'assets',
                paint: {
                    'circle-radius': 4,
                    'circle-color': '#ffffff',
                    'circle-stroke-width': 1,
                    'circle-stroke-color': '#000000'
                }
            })

            // ---------------------------------------------------------
            // INTERACTION: CLICK TO INSPECT
            // ---------------------------------------------------------
            map.current.on('mouseenter', 'assets-glow', () => {
                if (map.current) map.current.getCanvas().style.cursor = 'pointer'
            })
            map.current.on('mouseleave', 'assets-glow', () => {
                if (map.current) map.current.getCanvas().style.cursor = ''
            })

            map.current.on('click', 'assets-glow', (e) => {
                const feature = e.features?.[0]
                if (!feature) return

                const props = feature.properties
                // @ts-ignore
                const [lng, lat] = feature.geometry.coordinates

                const clickedPole: Asset = {
                    id: props?.id,
                    lat: lat,
                    lng: lng,
                    status: props?.status,
                    confidence: props?.confidence
                }

                setActivePoles(prev => {
                    // If already active, don't duplicate
                    if (prev.find(p => p.id === clickedPole.id)) return prev

                    // Add new, cycle out oldest if > 3
                    const temp = [...prev, clickedPole]
                    if (temp.length > 3) temp.shift()
                    return temp
                })
            })

            // Context Layers
            const loadContext = async () => {
                try {
                    const cData = await fetch('/pa_counties.geojson').then(r => r.json())
                    map.current?.addSource('counties', { type: 'geojson', data: cData })
                    map.current?.addLayer({ id: 'counties-line', type: 'line', source: 'counties', paint: { 'line-color': '#22d3ee', 'line-width': 1, 'line-opacity': 0.3 } })

                    const nData = await fetch('/pole_network.geojson').then(r => r.json())
                    map.current?.addSource('network', { type: 'geojson', data: nData })
                    map.current?.addLayer({ id: 'network-line', type: 'line', source: 'network', paint: { 'line-color': '#22d3ee', 'line-width': 3, 'line-opacity': 0.6 } }, 'assets-glow')
                } catch (e) { console.warn(e) }
            }
            loadContext()

            // Atmosphere
            try {
                // @ts-ignore
                if (map.current.setFog) map.current.setFog({ 'range': [0.5, 10], 'color': 'rgb(10, 15, 30)', 'horizon-blend': 0.2, 'high-color': 'rgb(0, 0, 0)', 'space-color': 'rgb(0, 0, 0)', 'star-intensity': 0.8 })
            } catch (e) { }


            // ---------------------------------------------------------
            // 4. SMART TARGETING & CINEMATIC LANDING
            // ---------------------------------------------------------

            // Fetch first, then animate based on data
            const loadedAssets = await fetchAssets()

            if (loadedAssets && loadedAssets.length > 0) {
                // Find "Hero Pole" near our target region (Manchester/Mt Wolf)
                // Target: [-76.73, 40.19]
                const targetLat = 40.19
                const targetLng = -76.73

                // Sort by distance to target
                const heroPole = loadedAssets.sort((a, b) => {
                    const distA = Math.sqrt(Math.pow(a.lat - targetLat, 2) + Math.pow(a.lng - targetLng, 2))
                    const distB = Math.sqrt(Math.pow(b.lat - targetLat, 2) + Math.pow(b.lng - targetLng, 2))
                    return distA - distB
                })[0]

                console.log("Hero Target Identified:", heroPole.id)

                // Sequence
                setTimeout(() => {
                    // Phase 1: Fly to Region (High)
                    map.current?.flyTo({
                        center: [heroPole.lng, heroPole.lat],
                        zoom: 11,
                        pitch: 0,
                        bearing: 0,
                        speed: 1.2,
                        curve: 1.5,
                        essential: true
                    })

                    // VISUALIZE HERO EARLY (Before Landing)
                    setTimeout(() => {
                        setActivePoles([heroPole]) // Show it while high up!
                    }, 2000)

                    // Phase 2: Swoop DIRECTLY to Hero
                    setTimeout(() => {
                        map.current?.easeTo({
                            center: [heroPole.lng, heroPole.lat - 0.005], // Offset slightly south so pole is "above" center (bottom up)
                            zoom: 15,    // Tight zoom on THE pole
                            pitch: 78,
                            bearing: 25,
                            duration: 5000,
                            essential: true
                        })

                        // Resume Orbit
                        setTimeout(() => {
                            isRotatingRef.current = true
                            setIsRotating(true)
                        }, 5500)

                    }, 3000) // Start swoop

                }, 500)
            } else {
                console.warn("No assets found for sequence")
            }
        })

        // Animation Loop for Rotation
        const rotate = () => {
            // Only rotate if enabled AND map is active AND user is not interacting
            if (isRotatingRef.current && !isInteractingRef.current && map.current) {
                map.current.setBearing(map.current.getBearing() + 0.04) // 2x Faster Rotation
            }
            requestAnimationFrame(rotate)
        }
        rotate()

    }, [])

    // Fetch Assets Helper
    const fetchAssets = async () => {
        const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
        const query = `?min_lat=39.90&max_lat=40.50&min_lng=-77.20&max_lng=-76.20`

        try {
            const res = await fetch(`${apiHost}/api/v2/assets${query}`)
            const data: Asset[] = await res.json()
            setAssets(data)

            if (map.current?.getSource('assets')) {
                const geojson: any = {
                    type: 'FeatureCollection',
                    features: data.map((a: Asset) => ({
                        type: 'Feature',
                        geometry: { type: 'Point', coordinates: [a.lng, a.lat] },
                        properties: a
                    }))
                };
                (map.current.getSource('assets') as maplibregl.GeoJSONSource).setData(geojson)
            }
            return data
        } catch (err) {
            console.error("Asset fetch failed", err)
            return []
        }
    }

    // MULTI-MARKER SCANNER LOOP
    useEffect(() => {
        if (assets.length === 0 || !isRotating) return

        const cycle = setInterval(() => {
            if (!map.current) return
            // **** PAUSE SCANNING IF EXPANDED ****
            if (expandedPoleId) return

            // Smart Scan (Visible Bottom CENTER)
            const { width, height } = map.current.getCanvas()
            const visible = assets.filter(a => {
                const p = map.current!.project([a.lng, a.lat])
                return (
                    p.x >= width * 0.3 && p.x <= width * 0.7 && // Center 40% (Stay in frame long time)
                    p.y >= height * 0.4 && p.y <= height // Bottom section
                )
            })

            if (visible.length > 0) {
                // Pick one
                const next = visible[Math.floor(Math.random() * visible.length)]

                setActivePoles(prev => {
                    // Avoid dupes
                    if (prev.find(p => p.id === next.id)) return prev

                    // Maintain max 3, remove oldest (first)
                    const temp = [...prev, next]
                    if (temp.length > 3) temp.shift()
                    return temp
                })
            }
        }, 1200) // Faster feed (1.2s)

        return () => clearInterval(cycle)
    }, [assets, isRotating, expandedPoleId])


    // RENDER MARKERS (React Portals into MapLibre)
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
