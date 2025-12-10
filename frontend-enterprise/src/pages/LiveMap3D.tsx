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

// Helper to get Satellite Tile URL
const getTileUrl = (lat: number, lng: number, zoom: number) => {
    const n = Math.pow(2, zoom);
    const x = Math.floor((lng + 180) / 360 * n);
    const latRad = lat * Math.PI / 180;
    const y = Math.floor((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * n);
    return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${zoom}/${y}/${x}`;
};

// ----------------------------------------------------------------------------
// FLOATING MARKER COMPONENT (Rendered inside MapLibre Marker)
// ----------------------------------------------------------------------------
const PoleMarker = ({ pole }: { pole: Asset }) => {
    return (
        <div className="flex flex-col items-center pointer-events-none origin-bottom animate-in zoom-in-50 duration-500">
            {/* 1. THE FLOATING CARD - Spawns upwards */}
            <div className="animate-in slide-in-from-bottom-10 fade-in duration-700 ease-out group perspective-1000 origin-bottom">
                <Card className="w-[180px] backdrop-blur-3xl bg-black/80 border border-emerald-500/30 shadow-[0_20px_50px_rgba(0,0,0,0.5)] rounded-sm overflow-hidden pointer-events-auto transition-transform duration-500 hover:scale-110">

                    {/* Header */}
                    <div className="px-2 py-1.5 border-b border-white/5 flex justify-between items-center bg-gradient-to-r from-emerald-900/20 to-transparent">
                        <span className="text-[9px] font-mono text-emerald-200/80 tracking-widest pl-1">
                            IMG_DETECT
                        </span>
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse box-shadow-[0_0_10px_#10b981]" />
                    </div>

                    {/* Image */}
                    <div className="relative h-20 w-full bg-black group">
                        <div
                            className="absolute inset-0 bg-cover bg-center opacity-90 transition-opacity duration-500"
                            style={{
                                backgroundImage: `url(${getTileUrl(pole.lat, pole.lng, 19)})`,
                                filter: 'grayscale(10%) contrast(1.1)'
                            }}
                        />
                        {/* Scan Line */}
                        <div className="absolute top-0 left-0 w-full h-[2px] bg-emerald-500/50 animate-scan-fast shadow-[0_0_15px_#10b981]" />

                        {/* Overlay Text */}
                        <div className="absolute bottom-1 right-2">
                            <span className="text-[10px] font-bold font-mono text-emerald-400 bg-black/50 px-1 rounded">
                                {(pole.confidence * 100).toFixed(0)}%
                            </span>
                        </div>
                    </div>
                </Card>
            </div>

            {/* 2. THE TETHER LINE - Connects Card to Dot - Grows up */}
            <div className="h-[80px] w-[2px] bg-gradient-to-b from-emerald-400 via-emerald-500/30 to-transparent shadow-[0_0_10px_#10b981] animate-in zoom-in-y duration-700 origin-bottom"></div>

            {/* 3. THE GROUND DOT - 3D Green Sphere */}
            <div className="relative flex items-center justify-center w-8 h-8">
                 <div className="absolute inset-0 border border-emerald-500/30 rounded-full animate-[ping_2s_infinite]"></div>
                 {/* 3D Pearl */}
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
    }, [assets, isRotating])

    // SYNC ACTIVE POLES TO DOM MARKERS
    useEffect(() => {
        if (!map.current) return

        // 1. Remove markers not in state
        const activeIds = new Set(activePoles.map(p => p.id))
        markersRef.current.forEach((val, id) => {
            if (!activeIds.has(id)) {
                val.root.unmount()
                val.marker.remove()
                markersRef.current.delete(id)
            }
        })

        // 2. Add new markers
        activePoles.forEach(pole => {
            if (!markersRef.current.has(pole.id)) {
                // Create
                const el = document.createElement('div')
                el.className = 'pole-marker-host'
                const root = createRoot(el)
                root.render(<PoleMarker pole={pole} />)

                const marker = new maplibregl.Marker({
                    element: el,
                    anchor: 'bottom'
                })
                    .setLngLat([pole.lng, pole.lat])
                    .addTo(map.current)

                markersRef.current.set(pole.id, { marker, root })
            }
        })
    }, [activePoles])


    return (
        <div className={`relative w-full rounded-lg overflow-hidden border border-white/10 shadow-2xl bg-black ${mode === 'widget' ? 'h-full min-h-[400px]' : 'h-[calc(100vh-6rem)]'}`}>

            {/* 3D Map Container */}
            <div ref={mapContainer} className="w-full h-full" />

            {/* OVERLAYS */}

            {/* HUD REMOVED as requested */}

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
