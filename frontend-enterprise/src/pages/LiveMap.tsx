import { useEffect, useState, useRef } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap, useMapEvents, GeoJSON } from 'react-leaflet'
import { DomEvent } from 'leaflet'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Activity, Layers, Filter, Crosshair, Save } from "lucide-react"
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
            setLoading(false)
         })
   }, [imageKey])

   if (loading) return <div className="h-48 flex items-center justify-center text-cyan-500 animate-pulse">Loading Mapillary...</div>
   if (!imageUrl) return <div className="h-48 flex items-center justify-center text-gray-500">Image Unavailable</div>

   return (
      <div className="relative w-full h-64 bg-black rounded-lg overflow-hidden border border-cyan-500/30 group">
         <img src={imageUrl} className="w-full h-full object-cover" alt="Street View" />
         <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <a href={`https://www.mapillary.com/app/?pKey=${imageKey}`} target="_blank" rel="noreferrer" className="text-white text-xs underline">Open in Mapillary</a>
         </div>
      </div>
   )
}

const MapController = ({
   setAssets,
   setLoading,
   selectedPole,
   setSelectedPole,
   zoomLevel,
   isTrainMode, // NEW
   onTrainClick // NEW
}: any) => {
   const map = useMap()
   const [counties, setCounties] = useState<any>(null)
   const [isFocused, setIsFocused] = useState(false)

   // 1. Fetch Counties on Mount
   useEffect(() => {
      fetch('/pa_counties.geojson')
         .then(res => res.json())
         .then(data => {
            const paFeatures = data.features.filter((f: any) => f.id && f.id.startsWith('42'));
            setCounties({ ...data, features: paFeatures });
         })
         .catch(err => console.error("Failed to load counties:", err))
   }, [])

   // 2. Fetch Assets (Viewport Based)
   const fetchVisibleAssets = () => {
      const z = map.getZoom()
      const shouldShowAssets = z >= 9 || (isFocused && z >= 7.5)

      if (!shouldShowAssets) {
         setAssets([])
         return
      }

      const bounds = map.getBounds()
      const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
      const query = `?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lng=${bounds.getWest()}&max_lng=${bounds.getEast()}`

      setLoading(true)
      fetch(`${apiHost}/api/v2/assets${query}`)
         .then(res => {
            if (!res.ok) throw new Error("API Error")
            return res.json()
         })
         .then(data => {
            setAssets(data)
            setLoading(false)
         })
         .catch(err => {
            setLoading(false)
         })
   }

   useEffect(() => { fetchVisibleAssets() }, [])

   useMapEvents({
      zoomend: () => {
         const z = map.getZoom()
         if (z < 8) setIsFocused(false)
         fetchVisibleAssets()
      },
      moveend: () => {
         const handler = setTimeout(() => { fetchVisibleAssets() }, 500)
         return () => clearTimeout(handler)
      },
      click: (e) => {
         if (isTrainMode) {
            onTrainClick(e.latlng)
         } else {
            if (selectedPole) setSelectedPole(null)
         }
      }
   })

   const onEachCounty = (feature: any, layer: any) => {
      if (feature.properties && feature.properties.NAME) {
         layer.bindTooltip(feature.properties.NAME, { permanent: true, direction: 'center', className: 'county-label', opacity: 1.0 });
      }
      const SUPPORTED = ['Dauphin', 'York', 'Cumberland']
      const isSupported = SUPPORTED.includes(feature.properties.NAME)

      layer.setStyle({
         weight: isSupported ? 2 : 1,
         color: isSupported ? '#22d3ee' : '#475569',
         fillColor: '#0f172a',
         fillOpacity: isSupported ? 0.1 : 0.05,
         dashArray: isSupported ? null : '4',
         interactive: !isTrainMode
      })

      if (!isTrainMode) {
         layer.on({
            mouseover: (e: any) => e.target.setStyle({ weight: 3, color: '#ffffff', fillOpacity: 0.2 }),
            mouseout: (e: any) => e.target.setStyle({ weight: isSupported ? 2 : 1, color: isSupported ? '#22d3ee' : '#475569', fillOpacity: isSupported ? 0.1 : 0.05 }),
            click: (e: any) => {
               setIsFocused(true)
               map.fitBounds(e.target.getBounds(), { padding: [20, 20] });
            }
         });
      }
   }

   // 1. Zoom/Move Logic
   useEffect(() => {
      fetchVisibleAssets()
   }, [zoomLevel])

   return (
      <>
         {zoomLevel < 12 && counties && (
            <GeoJSON key={`counties-${isTrainMode}`} data={counties} onEachFeature={onEachCounty} />
         )}
         {zoomLevel < 9 && (
            <>
               <StateLabel position={[40.9, -77.8]} name="Pennsylvania" />
               <StateLabel position={[39.0, -76.8]} name="Maryland" />
               <StateLabel position={[40.0, -74.5]} name="New Jersey" />
               <StateLabel position={[42.0, -75.5]} name="New York" />
               <StateLabel position={[39.0, -81.0]} name="West Virginia" />
            </>
         )}
      </>
   )
}

const StateLabel = ({ position, name }: { position: [number, number], name: string }) => (
   <CircleMarker center={position} pathOptions={{ stroke: false, fill: false }} radius={0}>
      <Popup closeButton={false} autoClose={false} closeOnEscapeKey={false} closeOnClick={false} className="state-label-popup" offset={[0, 0]}>
         <span className="text-white/30 text-4xl md:text-6xl font-black tracking-[0.2em] uppercase select-none pointer-events-none drop-shadow-xl whitespace-nowrap" style={{ fontFamily: 'Inter, sans-serif' }}>
            {name}
         </span>
      </Popup>
   </CircleMarker>
)

const AssetDetailsModal = ({ pole, onClose }: { pole: Asset | null, onClose: () => void }) => {
   if (!pole) return null;
   return (
      <div className="fixed inset-0 z-[500] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
         <div className="bg-slate-900 border border-slate-700 p-6 rounded-lg max-w-md w-full shadow-2xl" onClick={e => e.stopPropagation()}>
            <h2 className="text-xl font-bold text-white mb-4">Pole {pole.id}</h2>
            <div className="space-y-2 text-sm text-gray-300">
               <p>Status: <span className="text-cyan-400">{pole.status}</span></p>
               <p>Confidence: {(pole.confidence * 100).toFixed(1)}%</p>
               <p>Coords: {pole.lat.toFixed(6)}, {pole.lng.toFixed(6)}</p>
               {pole.mapillary_key && <MapillaryImage imageKey={pole.mapillary_key} />}
            </div>
            <Button className="mt-6 w-full" onClick={onClose}>Close</Button>
         </div>
      </div>
   )
}

const MapEventsHandler = ({ setZoomLevel }: { setZoomLevel: (z: number) => void }) => {
   const map = useMapEvents({ zoomend: () => setZoomLevel(map.getZoom()) })
   return null
}

const PoleLinesLayer = ({ zoom }: { zoom: number }) => {
   const [networkData, setNetworkData] = useState<any>(null)
   useEffect(() => {
      fetch('/pole_network.geojson').then(res => res.json()).then(data => setNetworkData(data)).catch(err => { })
   }, [])
   if (zoom > 13 || !networkData) return null
   const opacity = zoom < 11 ? 0.6 : Math.max(0.1, 0.6 - ((zoom - 11) * 0.2))
   const weight = zoom < 11 ? 1.5 : 1
   return <GeoJSON data={networkData} style={{ color: '#22d3ee', weight: weight, opacity: opacity, interactive: false }} />
}

const StatusHUD = () => {
   const [status, setStatus] = useState<any>(null)
   const [log, setLog] = useState<string>("")

   // Polling
   useEffect(() => {
      const timer = setInterval(() => {
         const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
         fetch(`${apiHost}/api/v2/pipeline/status`)
            .then(res => res.json())
            .then(data => {
               setStatus(data)
               if (data && data.status === 'running') {
                  fetch(`${apiHost}/api/v2/pipeline/logs?lines=5`)
                     .then(res => res.json())
                     .then(logData => {
                        const lines = logData.logs || []
                        if (lines.length > 0) setLog(lines[lines.length - 1])
                     })
               }
            })
            .catch(() => { })
      }, 1000)
      return () => clearInterval(timer)
   }, [])

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
         <span className="text-xs text-slate-500 hidden md:inline-block max-w-lg truncate">{log}</span>
      </div>
   )
}

export default function LiveMap() {
   const [assets, setAssets] = useState<Asset[]>([])
   const [loading, setLoading] = useState(false)
   const [selectedPole, setSelectedPole] = useState<Asset | null>(null)
   const [zoomLevel, setZoomLevel] = useState(8)

   // TRAIN MODE STATE
   const [isTrainMode, setIsTrainMode] = useState(false)
   const [trainingClicks, setTrainingClicks] = useState<any[]>([])
   const trainTimeoutRef = useRef<any>(null)

   const handleTrainClick = async (latlng: any) => {
      // Optimistic UI: Add marker
      const newClick = { lat: latlng.lat, lng: latlng.lng, id: Date.now() }
      setTrainingClicks(prev => [...prev, newClick])

      // Fire and Forget (or Queue)
      const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
      try {
         await fetch(`${apiHost}/api/v2/annotation/from_map`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lat: latlng.lat, lon: latlng.lng, dataset: 'satellite' })
         })

         // Auto-Run Debounce (5s)
         if (trainTimeoutRef.current) clearTimeout(trainTimeoutRef.current)
         trainTimeoutRef.current = setTimeout(() => {
            console.log("Auto-triggering continuous training...")
            commitTraining(true);
         }, 5000);

      } catch (err) {
         console.error("Failed to save annotation", err)
      }
   }

   const commitTraining = async (auto: boolean | any = false) => {
      // Handle the case where 'auto' is an Event object from onClick
      const isAuto = typeof auto === 'boolean' ? auto : false;

      if (trainTimeoutRef.current) clearTimeout(trainTimeoutRef.current)

      const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`

      // Use Continuous Training (Fine Tuning)
      await fetch(`${apiHost}/api/v2/pipeline/run/train_satellite`, {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify({ params: { epochs: 20, batch_size: 16, continuous: true } })
      })

      if (!isAuto) {
         alert("Continuous Training Started!")
         setIsTrainMode(false)
      } else {
         // Toast or non-intrusive notification ideally
         console.log("Continuous Training Autostarted")
      }

      setTrainingClicks([])
   }

   return (
      <div className="relative w-full h-[calc(100vh-6rem)] rounded-lg overflow-hidden border border-border/50 shadow-2xl">
         <StatusHUD />

         {/* GLOBAL HUD */}
         {/* ... (Existing HUD) ... */}



         <MapContainer
            center={[40.9, -77.8]}
            zoom={8}
            style={{ height: '100%', width: '100%', cursor: isTrainMode ? 'crosshair' : 'grab' }} // Crosshair cursor
            className="bg-slate-950"
         >
            <MapController
               setAssets={setAssets}
               setLoading={setLoading}
               selectedPole={selectedPole}
               setSelectedPole={setSelectedPole}
               zoomLevel={zoomLevel}
               isTrainMode={isTrainMode}
               onTrainClick={handleTrainClick}
            />
            <MapEventsHandler setZoomLevel={setZoomLevel} />

            <TileLayer
               attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
               url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            />

            <PoleLinesLayer zoom={zoomLevel} />

            {/* Existing Assets */}
            {zoomLevel >= 11 && assets.map(pole => (
               <CircleMarker
                  key={pole.id}
                  center={[pole.lat, pole.lng]}
                  // ... (Existing props) ...
                  eventHandlers={{
                     click: (e) => {
                        DomEvent.stopPropagation(e.originalEvent)
                        if (!isTrainMode) setSelectedPole(pole)
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
               />
            ))}

            {/* TRAINING MARKERS (Purple) */}
            {trainingClicks.map(p => (
               <CircleMarker
                  key={p.id}
                  center={[p.lat, p.lng]}
                  pathOptions={{
                     color: '#d8b4fe', // Purple-300
                     fillColor: '#9333ea', // Purple-600
                     fillOpacity: 1,
                     weight: 2
                  }}
                  radius={6}
               />
            ))}

         </MapContainer>

         {/* CONTROLS (Moved to end for Z-Indexing) */}
         <div className="absolute top-4 right-4 z-[2000] flex flex-col gap-2 pointer-events-auto">
            <Button variant="outline" size="sm" className="backdrop-blur-md bg-background/60 border-primary/20 hover:bg-primary/20">
               <Layers className="h-4 w-4 mr-2" />
               Layers
            </Button>

            {/* TRAIN MODE TOGGLE */}
            <Button
               variant={isTrainMode ? "default" : "outline"}
               size="sm"
               onClick={() => setIsTrainMode(!isTrainMode)}
               className={`backdrop-blur-md border-primary/20 ${isTrainMode ? 'bg-purple-600 hover:bg-purple-700 text-white' : 'bg-background/60 hover:bg-primary/20'}`}
            >
               <Crosshair className="h-4 w-4 mr-2" />
               {isTrainMode ? "Training Mode ON" : "Train Mode"}
            </Button>

            {/* COMMIT BUTTON */}
            {trainingClicks.length > 0 && (
               <Button
                  size="sm"
                  onClick={() => commitTraining(false)}
                  className="bg-green-600 hover:bg-green-700 text-white animate-in slide-in-from-right fade-in duration-300"
               >
                  <Save className="h-4 w-4 mr-2" />
                  Commit & Train ({trainingClicks.length})
               </Button>
            )}
         </div>

         {selectedPole && (
            <AssetDetailsModal pole={selectedPole} onClose={() => setSelectedPole(null)} />
         )}

      </div>
   )
}
