import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap, useMapEvents, GeoJSON } from 'react-leaflet'
// import MarkerClusterGroup from 'react-leaflet-cluster'
import L, { DomEvent } from 'leaflet'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Activity, Layers, Filter, Maximize2, ExternalLink } from "lucide-react"
import 'leaflet/dist/leaflet.css'
import { Button } from '@/components/ui/button'

interface Asset {
   id: string
   lat: number
   lng: number
   status: string
   confidence: number
   detected_at: string
   tags?: any
   mapillary_key?: string
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

   if (loading) return <div className="h-48 flex items-center justify-center text-cyan-500 animate-pulse">Loading Mapillary...</div>
   if (!imageUrl) return <div className="h-48 flex items-center justify-center text-gray-500">Image Unavailable</div>

   return (
      <div className="relative w-full h-64 bg-black rounded-lg overflow-hidden border border-cyan-500/30 group">
         <img src={imageUrl} className="w-full h-full object-cover" />
         <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <a href={`https://www.mapillary.com/app/?pKey=${imageKey}`} target="_blank" className="text-white text-xs underline">Open in Mapillary</a>
         </div>
      </div>
   )
}

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
            // Filter features where STATE val is '42' (PA)
            // We want to show ALL PA counties for context, but only highlight Supported ones in Cyan
            const paFeatures = data.features.filter((f: any) =>
               f.id && f.id.startsWith('42')
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
         const z = map.getZoom()
         // If user zooms out to State View (approx 8 or lower), reset focus mode
         if (z < 8) {
            setIsFocused(false)
         }
         fetchVisibleAssets()
      },
      moveend: () => {
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

      // Check if Supported
      const SUPPORTED_COUNTIES = ['Dauphin', 'York', 'Cumberland']
      const isSupported = SUPPORTED_COUNTIES.includes(feature.properties.NAME)

      // Initial Style
      layer.setStyle({
         weight: isSupported ? 2 : 1,
         color: isSupported ? '#22d3ee' : '#475569', // Cyan for supported, Slate-600 for others
         fillColor: '#0f172a',
         fillOpacity: isSupported ? 0.1 : 0.05,
         dashArray: isSupported ? null : '4'
      })

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
            // Revert to default style
            layer.setStyle({
               weight: isSupported ? 2 : 1,
               color: isSupported ? '#22d3ee' : '#475569',
               fillOpacity: isSupported ? 0.1 : 0.05
            });
         },
         click: (e: any) => {
            // Only focus on Supported counties for asset fetching? 
            // Or allow clicking any to zoom in? Let's allow zooming in.
            setIsFocused(true)
            map.fitBounds(e.target.getBounds(), { padding: [20, 20] });
         }
      });
   }

   // 1. Zoom/Move Logic
   useEffect(() => {
      fetchVisibleAssets()
   }, [zoomLevel])

   return (
      <>
         {/* Show Counties if Zoom < 12 */}
         {zoomLevel < 12 && counties && (
            <GeoJSON
               data={counties}
               onEachFeature={onEachCounty}
            />
         )}

         {/* State Label Layer */}
         {zoomLevel < 9 && (
            <>
               <StateLabel position={[40.9, -77.8]} name="Pennsylvania" />
               <StateLabel position={[42.6, -75.5]} name="New York" />
               <StateLabel position={[39.0, -76.8]} name="Maryland" />
               <StateLabel position={[40.1, -82.9]} name="Ohio" />
               <StateLabel position={[38.8, -80.5]} name="West Virginia" />
               <StateLabel position={[40.0, -74.5]} name="New Jersey" />
            </>
         )}

      </>
   )
}

const StateLabel = ({ position, name }: { position: [number, number], name: string }) => (
   <CircleMarker center={position} pathOptions={{ stroke: false, fill: false }} radius={0}>
      <Popup
         closeButton={false}
         autoClose={false}
         closeOnEscapeKey={false}
         closeOnClick={false}
         className="state-label-popup"
         offset={[0, 0]}
      >
         <span className="text-white/30 text-4xl md:text-6xl font-black tracking-[0.2em] uppercase select-none pointer-events-none drop-shadow-xl whitespace-nowrap" style={{ fontFamily: 'Inter, sans-serif' }}>
            {name}
         </span>
      </Popup>
   </CircleMarker>
)

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
                        className="cyber-popup p-0 border-none bg-transparent"
                        closeButton={false}
                        minWidth={350}
                        maxWidth={350}
                        offset={[0, 50]}
                     >
                        <Card className="w-[350px] border-cyan-500/50 bg-black/90 backdrop-blur-xl text-white">
                           <CardHeader className="py-2 border-b border-white/10">
                              <CardTitle className=" text-sm flex items-center justify-between">
                                 <span className="text-cyan-400 font-mono">{pole.id}</span>
                                 <span className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold ${pole.status === 'Verified' ? 'bg-green-500/20 text-green-400' : 'bg-amber-500/20 text-amber-400'
                                    }`}>{pole.status}</span>
                              </CardTitle>
                           </CardHeader>
                           <CardContent className="p-0">
                              <Tabs defaultValue={pole.mapillary_key ? "mapillary" : "satellite"} className="w-full">
                                 <TabsList className="w-full rounded-none bg-white/5 border-b border-white/10 grid grid-cols-3">
                                    <TabsTrigger value="mapillary">Mapillary</TabsTrigger>
                                    <TabsTrigger value="satellite">Satellite</TabsTrigger>
                                    <TabsTrigger value="google">Google</TabsTrigger>
                                 </TabsList>

                                 <div className="h-64 bg-black relative">
                                    <TabsContent value="mapillary" className="m-0 h-full p-2">
                                       {pole.mapillary_key ? (
                                          <MapillaryImage imageKey={pole.mapillary_key} />
                                       ) : (
                                          <div className="h-full flex flex-col items-center justify-center text-gray-500 text-xs">
                                             <Maximize2 className="w-8 h-8 mb-2 opacity-50" />
                                             No Mapillary Data
                                          </div>
                                       )}
                                    </TabsContent>

                                    <TabsContent value="satellite" className="m-0 h-full">
                                       <img
                                          src={getTileUrl(pole.lat, pole.lng, 19)}
                                          className="w-full h-full object-cover"
                                       />
                                       {/* Overlays */}
                                       <div className="absolute inset-0 border-[20px] border-black/20 pointer-events-none rounded-none" />
                                       <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 border-2 border-cyan-500 rounded-full animate-pulse shadow-[0_0_15px_rgba(34,211,238,0.5)]" />
                                    </TabsContent>

                                    <TabsContent value="google" className="m-0 h-full p-2 flex flex-col items-center justify-center">
                                       <a
                                          href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${pole.lat},${pole.lng}`}
                                          target="_blank"
                                          rel="noreferrer"
                                          className="flex items-center gap-2 bg-white/10 hover:bg-white/20 px-4 py-2 rounded text-sm transition-colors text-white no-underline"
                                       >
                                          <ExternalLink className="w-4 h-4" />
                                          Open Google Street View
                                       </a>
                                       <p className="text-[10px] text-gray-500 mt-2 text-center max-w-[200px]">
                                          Google Embed API requires Key. Click to open in new tab.
                                       </p>
                                    </TabsContent>
                                 </div>

                                 {/* Footer Info */}
                                 <div className="p-3 bg-white/5 border-t border-white/10 flex justify-between items-center text-xs font-mono">
                                    <span className="text-gray-400">CONF: {(pole.confidence * 100).toFixed(0)}%</span>
                                    <span className="text-gray-400">{pole.lat.toFixed(5)}, {pole.lng.toFixed(5)}</span>
                                 </div>
                              </Tabs>
                           </CardContent>
                        </Card>
                     </Popup>
                  )}
               </CircleMarker>
            ))}

         </MapContainer>
      </div>
   )
}

// Network Visualization layer etc...
const PoleLinesLayer = ({ zoom }: { zoom: number }) => {
   const [networkData, setNetworkData] = useState<any>(null)

   useEffect(() => {
      fetch('/pole_network.geojson') // Make sure this endpoint exists or mock it
         .then(res => res.json())
         .then(data => setNetworkData(data))
         .catch(err => console.error("Failed to load network layer:", err))
   }, [])

   if (zoom > 13 || !networkData) return null

   const opacity = zoom < 11 ? 0.6 : Math.max(0.1, 0.6 - ((zoom - 11) * 0.2))
   const weight = zoom < 11 ? 1.5 : 1

   return (
      <GeoJSON
         data={networkData}
         style={{
            color: '#22d3ee',
            weight: weight,
            opacity: opacity,
            interactive: false
         }}
      />
   )
}

const MapEventsHandler = ({ setZoomLevel }: { setZoomLevel: (z: number) => void }) => {
   const map = useMapEvents({
      zoomend: () => setZoomLevel(map.getZoom())
   })
   return null
}
