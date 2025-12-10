import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap, useMapEvents, GeoJSON } from 'react-leaflet'
// import MarkerClusterGroup from 'react-leaflet-cluster'
import L, { DomEvent } from 'leaflet'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Activity, Layers, Filter } from "lucide-react"
import 'leaflet/dist/leaflet.css'
import { Button } from '@/components/ui/button'

interface Asset {
   id: string
   lat: number
   lng: number
   status: string
   confidence: number
   detected_at: string
}

// Helper to convert Lat/Lng to Tile Coordinates (Zoom 18 for high detail)
const getTileUrl = (lat: number, lng: number, zoom: number) => {
   const n = Math.pow(2, zoom);
   const x = Math.floor((lng + 180) / 360 * n);
   const latRad = lat * Math.PI / 180;
   const y = Math.floor((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * n);
   // Using Esri World Imagery for "Real Satellite" view
   return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${zoom}/${y}/${x}`;
};

// Map Controller for data fetching and view interactions
const MapController = ({
   setAssets,
   setLoading,
   selectedPole,
   setSelectedPole,
   zoomLevel // Now received as a prop
}: any) => {
   const map = useMap()
   // const [zoomLevel, setZoomLevel] = useState(map.getZoom()) // Removed, now a prop
   const [counties, setCounties] = useState<any>(null)
   const [assetsLoaded, setAssetsLoaded] = useState(false) // Track if we've fetched assets

   // 1. Fetch Counties on Mount
   useEffect(() => {
      // Fetch US Counties and filter for Pennsylvania (State FIPS '42')
      fetch('/pa_counties.geojson')
         .then(res => res.json())
         .then(data => {
            // Filter features where STATE val is '42' (PA) or properties.STATE is '42'
            // The plotly dataset uses id as FIPS. PA counties start with 42.
            // Filter features where STATE val is '42' (PA) AND matches our data coverage
            const SUPPORTED_COUNTIES = ['Dauphin', 'York', 'Cumberland']
            const paFeatures = data.features.filter((f: any) =>
               f.id && f.id.startsWith('42') &&
               SUPPORTED_COUNTIES.includes(f.properties.NAME)
            );
            setCounties({ ...data, features: paFeatures });
         })
         .catch(err => console.error("Failed to load counties:", err))
   }, [])

   const [isFocused, setIsFocused] = useState(false) // Track if user has drilled down into a county

   // 2. Fetch Assets (Viewport Based)
   const fetchVisibleAssets = () => {
      const z = map.getZoom()

      // LOGIC: Show assets if:
      // 1. Zoom is high enough (Standard exploration, z >= 9)
      // 2. OR User explicitly clicked a county (isFocused) and isn't totally zoomed out (z >= 7.5)
      const shouldShowAssets = z >= 9 || (isFocused && z >= 7.5)

      if (!shouldShowAssets) {
         setAssets([]) // Clear assets to save memory/visuals
         setAssetsLoaded(false)
         return
      }

      const bounds = map.getBounds()
      const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
      const query = `?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lng=${bounds.getWest()}&max_lng=${bounds.getEast()}`

      setLoading(true)
      fetch(`${apiHost}/api/v2/assets${query}`)
         .then(res => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            return res.json()
         })
         .then(data => {
            setAssets(data)
            setLoading(false)
            setAssetsLoaded(true)
         })
         .catch(err => {
            console.error("Failed to load assets:", err)
            setLoading(false)
         })
   }

   // Initial Load
   useEffect(() => {
      fetchVisibleAssets()
   }, [])

   // Zoom/Move Listeners
   useMapEvents({
      zoomend: () => {
         // setZoomLevel(map.getZoom()) // Removed, now handled by MapEventsHandler
         const z = map.getZoom()
         // If user zooms out to State View (approx 8 or lower), reset focus mode
         if (z < 8) {
            setIsFocused(false)
         }
         fetchVisibleAssets()
      },
      moveend: () => {
         // Debounce fetch
         const handler = setTimeout(() => {
            fetchVisibleAssets()
         }, 500)
         return () => clearTimeout(handler)
      },
      click: () => {
         if (selectedPole) setSelectedPole(null)
      }
   })

   // Style for Counties
   const onEachCounty = (feature: any, layer: any) => {
      // Add Tooltip Label
      if (feature.properties && feature.properties.NAME) {
         layer.bindTooltip(feature.properties.NAME, {
            permanent: true,
            direction: 'center',
            className: 'county-label'
         });
      }

      layer.on({
         mouseover: (e: any) => {
            const layer = e.target;
            layer.setStyle({
               weight: 3,
               color: '#ffffff', // White highlight on hover
               fillOpacity: 0.2
            });
         },
         mouseout: (e: any) => {
            const layer = e.target;
            // Revert to default style (Teal)
            layer.setStyle({
               weight: 1,
               color: '#22d3ee', // Cyan/Teal border
               fillOpacity: 0.1
            });
         },
         click: (e: any) => {
            setIsFocused(true) // Enable focused mode to show dots even if zoom is slightly low
            map.fitBounds(e.target.getBounds(), { padding: [20, 20] });
            // The moveend/zoomend event will trigger fetchVisibleAssets
         }
      });
   }

   // 1. Zoom/Move Logic
   // No special zoom logic for poles needed, just fetch on move
   // But we need to make sure we fetch if we just zoomed in
   useEffect(() => {
      fetchVisibleAssets()
   }, [zoomLevel]) // Re-fetch when zoom level changes (especially crossing the 11 threshold)

   useEffect(() => {
      // Force refresh of counties style on mount/update to ensure labels
      if (counties) {
         // Leaflet handles this via React binding usually
      }
   }, [counties])

   return (
      <>
         {/* Show Counties if Zoom < 11 */}
         {zoomLevel < 11 && counties && (
            <GeoJSON
               data={counties}
               style={{
                  color: '#22d3ee', // Cyan Border (Default)
                  weight: 1,
                  fillColor: '#0f172a', // Dark fill
                  fillOpacity: 0.1
               }}
               onEachFeature={onEachCounty}
            />
         )}

         {/* State Label - Only on very high level zoom */}
         {zoomLevel < 9 && (
            <CircleMarker center={[40.9, -77.8]} pathOptions={{ stroke: false, fill: false }}>
               <Popup
                  closeButton={false}
                  autoClose={false}
                  closeOnEscapeKey={false}
                  closeOnClick={false}
                  className="state-label-popup"
                  offset={[0, 0]}
               >
                  <span className="text-white/30 text-6xl font-black tracking-[0.5em] uppercase select-none pointer-events-none drop-shadow-xl" style={{ fontFamily: 'Inter, sans-serif' }}>
                     Pennsylvania
                  </span>
               </Popup>
            </CircleMarker>
         )}

      </>
   )
}

export default function LiveMap() {
   const [assets, setAssets] = useState<Asset[]>([])
   const [loading, setLoading] = useState(false) // Default false, MapController handles it
   const [error, setError] = useState<string | null>(null)
   const [selectedPole, setSelectedPole] = useState<Asset | null>(null)
   const [zoomLevel, setZoomLevel] = useState(8) // Lifted state for styling

   return (
      <div className="relative w-full h-[calc(100vh-6rem)] rounded-lg overflow-hidden border border-border/50 shadow-2xl">

         {/* GLOBAL HUD (Top Left) */}
         <div className="absolute top-4 left-4 z-[400] w-72 pointer-events-none">
            <Card className="backdrop-blur-md bg-background/60 border-primary/20 shadow-glow pointer-events-auto">
               <CardHeader className="py-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                     <Activity className="h-4 w-4 text-cyan-400 animate-pulse" />
                     Live Surveillance
                  </CardTitle>
                  <CardDescription className="text-xs">Harrisburg, PA Sector 7</CardDescription>
               </CardHeader>
               <CardContent className="py-2 space-y-2">
                  <div className="flex justify-between text-xs">
                     <span className="text-muted-foreground">Visible Units:</span>
                     <span className="font-mono text-cyan-400">
                        {loading ? "Scanning..." : assets.length}
                     </span>
                  </div>
                  <div className="flex justify-between text-xs">
                     <span className="text-muted-foreground">Signal Quality:</span>
                     <span className="font-mono text-green-400">STRONG</span>
                  </div>
               </CardContent>
            </Card>
         </div>

         {/* CONTROLS (Top Right) */}
         <div className="absolute top-4 right-4 z-[400] flex flex-col gap-2">
            <Button variant="outline" size="sm" className="backdrop-blur-md bg-background/60 border-primary/20 hover:bg-primary/20">
               <Layers className="h-4 w-4 mr-2" />
               Layers
            </Button>
            <Button variant="outline" size="sm" className="backdrop-blur-md bg-background/60 border-primary/20 hover:bg-primary/20">
               <Filter className="h-4 w-4 mr-2" />
               Filters
            </Button>
         </div>

         <MapContainer
            center={[40.9, -77.8]} // Center of PA
            zoom={8} // State View
            style={{ height: '100%', width: '100%' }}
            className="bg-slate-950"
         >
            <MapController
               setAssets={setAssets}
               setLoading={setLoading}
               selectedPole={selectedPole}
               setSelectedPole={setSelectedPole}
               zoomLevel={zoomLevel} // Pass zoomLevel to MapController
            />
            {/* Capture Zoom for Styling */}
            <MapEventsHandler setZoomLevel={setZoomLevel} />

            <TileLayer
               attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
               url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            />

            {/* 1. LAYER: LINES (Visible at Low Zoom) */}
            <PoleLinesLayer zoom={zoomLevel} />

            {/* 2. LAYER: DOTS (Visible at High Zoom) */}
            {/* Logic: 
                Zoom < 11: Hidden (Lines only)
                Zoom 11-13: Small dots + Lines
                Zoom > 13: Full dots
            */}
            {zoomLevel >= 11 && assets.map(pole => (
               <CircleMarker
                  key={pole.id}
                  center={[pole.lat, pole.lng]}
                  eventHandlers={{
                     click: (e) => {
                        DomEvent.stopPropagation(e.originalEvent)
                        setSelectedPole(pole)
                     }
                  }}
                  pathOptions={{
                     color: '#ffffff',
                     fillColor:
                        pole.status === 'Verified' || pole.status === 'verified_good' ? '#22c55e' :
                           pole.status === 'Moved' ? '#f97316' :
                              pole.status === 'New' ? '#06b6d4' :
                                 pole.status === 'Review' ? '#f59e0b' : '#ef4444',
                     fillOpacity: zoomLevel < 13 ? 0.5 : 0.9,
                     weight: zoomLevel < 13 ? 1 : 2
                  }}
                  radius={zoomLevel < 13 ? 3 : 6}
               >
                  {selectedPole && selectedPole.id === pole.id && (
                     <Popup
                        className="cyber-popup"
                        closeButton={false}
                        minWidth={300}
                        maxWidth={300}
                        offset={[0, 150]}
                     >
                        {/* SATELLITE LENS CONTAINER */}
                        <div className="relative w-[300px] h-[300px] flex items-center justify-center pointer-events-none">

                           {/* 1. GLOWING ROTATING OUTER RING */}
                           <div className="absolute inset-0 rounded-full border border-cyan-500/30 shadow-[0_0_30px_rgba(34,211,238,0.2)] animate-[spin_8s_linear_infinite]"></div>
                           <div className="absolute inset-[2px] rounded-full border border-cyan-400/50 border-dashed animate-[spin_12s_linear_infinite_reverse]"></div>

                           {/* 2. SOLID SATELLITE IMAGE (Cropped to Circle) */}
                           <div className="absolute inset-[6px] rounded-full overflow-hidden border border-white/10 shadow-inner bg-black">
                              <div
                                 className="w-full h-full"
                                 style={{
                                    backgroundImage: `url(${getTileUrl(pole.lat, pole.lng, 19)})`,
                                    backgroundSize: 'cover',
                                    backgroundPosition: 'center',
                                    filter: 'brightness(1.1) contrast(1.1)'
                                 }}
                              ></div>
                           </div>

                           {/* 3. TARGETING OVERLAYS */}
                           <div className="absolute w-12 h-12 rounded-full border-2 border-cyan-400 shadow-[0_0_15px_#22d3ee] animate-pulse z-10"></div>

                           {/* Decorative Crosshairs */}
                           <div className="absolute w-[280px] h-[1px] bg-gradient-to-r from-transparent via-cyan-500/20 to-transparent z-10"></div>
                           <div className="absolute h-[280px] w-[1px] bg-gradient-to-b from-transparent via-cyan-500/20 to-transparent z-10"></div>

                           {/* 4. DATA TAGS */}
                           <div className="absolute top-3/4 left-1/2 -translate-x-1/2 mt-4 text-center z-20">
                              <div className="bg-black/80 backdrop-blur-md px-3 py-1 rounded-full border border-cyan-500/50 shadow-lg">
                                 <span className="font-mono text-[10px] text-cyan-300 font-bold tracking-wider">CONFIDENCE: {(pole.confidence * 100).toFixed(0)}%</span>
                              </div>

                              {/* STREET VIEW LINK */}
                              <div className="mt-2 pointer-events-auto">
                                 <a
                                    href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${pole.lat},${pole.lng}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="bg-cyan-500/20 hover:bg-cyan-500/40 text-cyan-200 text-[10px] font-bold py-1 px-3 rounded-full border border-cyan-500/50 transition-colors flex items-center gap-1 no-underline"
                                 >
                                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg>
                                    STREET VIEW
                                 </a>
                              </div>
                           </div>

                        </div>
                     </Popup>
                  )}
               </CircleMarker>
            ))}

         </MapContainer>
      </div>
   )
}

// Network Visualization Layer (Low Zoom - Pre-computed Global)
const PoleLinesLayer = ({ zoom }: { zoom: number }) => {
   const [networkData, setNetworkData] = useState<any>(null)

   useEffect(() => {
      fetch('/pole_network.geojson')
         .then(res => res.json())
         .then(data => setNetworkData(data))
         .catch(err => console.error("Failed to load network layer:", err))
   }, [])

   // Logic: Show GLOBAL lines if zoomed out (High Level View)
   // Hide lines when zoomed in to focus on specific poles (Asset Level View)
   if (zoom > 13 || !networkData) return null

   // Dynamic Style based on Zoom
   const opacity = zoom < 11 ? 0.6 : Math.max(0.1, 0.6 - ((zoom - 11) * 0.2))
   const weight = zoom < 11 ? 1.5 : 1

   return (
      <GeoJSON
         data={networkData}
         style={{
            color: '#22d3ee', // Cyan "Electric" lines
            weight: weight,
            opacity: opacity,
            interactive: false
         }}
      />
   )
}

// Utility to bubble up zoom state
const MapEventsHandler = ({ setZoomLevel }: { setZoomLevel: (z: number) => void }) => {
   const map = useMapEvents({
      zoomend: () => setZoomLevel(map.getZoom())
   })
   return null
}
