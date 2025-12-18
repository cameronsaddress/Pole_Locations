import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from 'framer-motion'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Activity, Database, Disc, Zap, AlertTriangle, FileText, Search, Play, Layers, Cpu, Terminal } from 'lucide-react';
import { RegionPickerModal } from "@/components/RegionPickerModal"

// Types
interface Dataset {
    id: string
    name: string
    status: 'available' | 'supported' | 'mining' | 'missing'
}

interface DatasetMap {
    [state: string]: Dataset[]
}

interface LogMessage {
    timestamp: string
    message: string
    type: 'info' | 'error' | 'success'
}

export default function Pipeline() {
    const [datasets, setDatasets] = useState<DatasetMap>({})

    // Selections
    const [selectedCounties, setSelectedCounties] = useState<string[]>(['dauphin_pa', 'cumberland_pa', 'york_pa'])
    const [miningCounties, setMiningCounties] = useState<string[]>([])

    // Stage States
    const [activeStage, setActiveStage] = useState<string | null>(null)
    const [logs, setLogs] = useState<LogMessage[]>([])
    const logsEndRef = useRef<HTMLDivElement>(null)

    const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`

    const fetchDatasets = () => {
        fetch(`${apiHost}/api/v2/pipeline/datasets`)
            .then(res => res.json())
            .then(data => setDatasets(data))
            .catch(err => console.error("Failed to load datasets", err))
    }

    const fetchLogs = () => {
        fetch(`${apiHost}/api/v2/pipeline/logs?lines=200`)
            .then(res => res.json())
            .then(data => {
                if (data.logs) {
                    const lines = data.logs.split('\n').filter(Boolean)
                    const newLogs = lines.map((l: string) => ({
                        timestamp: new Date().toLocaleTimeString(),
                        message: l,
                        type: l.toLowerCase().includes('error') ? 'error' : 'info' as 'info' | 'error'
                    }))
                    setLogs(newLogs)
                }
            })
    }

    // Polling for Status & Logs
    useEffect(() => {
        // Initial Fetch
        fetchDatasets()
        fetchLogs()

        // Status Poller
        const interval = setInterval(async () => {
            try {
                // 1. Check Backend Status
                const res = await fetch(`${apiHost}/api/v2/pipeline/status`)
                const status = await res.json()

                if (status.is_running) {
                    // Sync State: If running but frontend thinks idle, updating frontend
                    if (activeStage !== status.job_type) {
                        setActiveStage(status.job_type)
                    }
                    // Fetch Logs while running
                    fetchLogs()
                } else {
                    // Job Not Running
                    if (activeStage) {
                        // We think it's running, but backend says it's done.
                        // Transition: Running -> Done
                        console.log("Job finished, refreshing state...")
                        setActiveStage(null)
                        fetchDatasets() // Refresh datasets (vital for mining)
                        fetchLogs() // Get final logs
                    }
                }
            } catch (err) {
                console.error("Status check failed", err)
            }
        }, 1000)

        return () => clearInterval(interval)
    }, [activeStage])

    // Auto-scroll logs
    useEffect(() => {
        logsEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [logs])

    const runJob = async (jobType: string, params: any = {}) => {
        setActiveStage(jobType)
        setLogs(prev => [...prev, { timestamp: new Date().toLocaleTimeString(), message: `Starting Job: ${jobType}...`, type: 'info' }])

        const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
        try {
            await fetch(`${apiHost}/api/v2/pipeline/run/${jobType}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ params })
            })
        } catch (e) {
            console.error(e)
            setLogs(prev => [...prev, { timestamp: new Date().toLocaleTimeString(), message: "Failed to trigger job", type: 'error' }])
            setActiveStage(null)
        }
    }

    const stopJob = async () => {
        const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
        try {
            await fetch(`${apiHost}/api/v2/pipeline/stop`, { method: 'POST' })
            setLogs(prev => [...prev, { timestamp: new Date().toLocaleTimeString(), message: "🛑 Stopping Job...", type: 'error' }])
        } catch (e) { console.error(e) }
    }

    return (
        <div className="space-y-6 pb-20">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight text-white">Enterprise Pipeline Operations</h2>
                    <p className="text-muted-foreground">Orchestrate Data Ingestion, Model Training, and Unified Fusion</p>
                </div>
                <Badge variant="outline" className={`text-lg px-4 py-1 ${activeStage ? 'border-cyan-500 text-cyan-500 animate-pulse' : 'border-gray-700 text-gray-500'}`}>
                    <Activity className="mr-2 h-4 w-4" />
                    {activeStage ? `PIPELINE ACTIVE: ${activeStage.toUpperCase()}` : "SYSTEM IDLE"}
                </Badge>
            </div>

            <div className="grid grid-cols-12 gap-6">

                {/* LEFT COLUMN: CONTROL STACK */}
                <div className="col-span-8 space-y-6">

                    {/* 1. STAGE: MINING */}
                    <Card className={`border-l-4 ${activeStage === 'mining' ? 'border-l-pink-500 bg-pink-950/10' : 'border-l-gray-700 bg-card/50'}`}>
                        <CardContent className="p-4">
                            <div className="flex items-center justify-between mb-4">
                                <div className="flex gap-4 items-center">
                                    <div className="p-3 rounded-full bg-pink-900/30 text-pink-400">
                                        <Database className="w-6 h-6" />
                                    </div>
                                    <div>
                                        <h3 className="font-bold text-lg text-white">Stage 1: Data Mining & Ingestion</h3>
                                        <p className="text-sm text-gray-400">Fetch Grid/OSM Data → Download Street View Images → Register for Annotation.</p>
                                    </div>
                                </div>
                                <Button
                                    disabled={!!activeStage || miningCounties.length === 0}
                                    onClick={() => runJob('mining', { targets: miningCounties })}
                                    variant="secondary"
                                    className="bg-pink-900/40 text-pink-300 hover:bg-pink-900/60"
                                >
                                    <Play className="w-4 h-4 mr-2" /> Start Mining
                                </Button>
                            </div>

                            {/* Mining Targets Picker */}
                            <div className="bg-black/20 p-3 rounded border border-gray-800 flex items-center justify-between">
                                <RegionPickerModal
                                    mode="mining"
                                    datasets={datasets}
                                    selected={miningCounties}
                                    onSelectionChange={setMiningCounties}
                                    triggerText={miningCounties.length ? `${miningCounties.length} Regions Queued` : "Select Regions to Mine..."}
                                    disabled={!!activeStage}
                                />
                                <div className="text-xs text-gray-500 font-mono">
                                    {miningCounties.length > 0 ? "Targeting: " + miningCounties.join(", ") : "No targets queued."}
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* 2. DATA SELECTION */}
                    <Card className="border-l-4 border-l-cyan-500 bg-card/50">
                        <CardContent className="p-4">
                            <div className="flex gap-4 items-center mb-4">
                                <div className="p-3 rounded-full bg-cyan-900/30 text-cyan-400">
                                    <FileText className="w-6 h-6" />
                                </div>
                                <div>
                                    <h3 className="font-bold text-lg text-white">Stage 2: Target Datasets (Active)</h3>
                                    <p className="text-sm text-gray-400">Select processed datasets for downstream Inference Runs.</p>
                                </div>
                            </div>

                            {/* Active Targets Picker */}
                            <div className="bg-black/20 p-3 rounded border border-gray-800 flex items-center justify-between">
                                <RegionPickerModal
                                    mode="targets"
                                    datasets={datasets}
                                    selected={selectedCounties}
                                    onSelectionChange={setSelectedCounties}
                                    triggerText={selectedCounties.length ? `${selectedCounties.length} Datasets Active` : "Select Active Datasets..."}
                                    disabled={!!activeStage}
                                />
                                <div className="text-xs text-gray-500 font-mono">
                                    {selectedCounties.length > 0 ? "Active: " + selectedCounties.join(", ") : "No datasets active."}
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* 3. STAGE: INTEGRITY */}
                    <Card className={`border-l-4 ${activeStage === 'integrity' ? 'border-l-cyan-500 bg-cyan-950/10' : 'border-l-gray-700 bg-card/50'}`}>
                        <CardContent className="p-4 flex items-center justify-between">
                            <div className="flex gap-4 items-center">
                                <div className="p-3 rounded-full bg-blue-900/30 text-blue-400">
                                    <Layers className="w-6 h-6" />
                                </div>
                                <div>
                                    <h3 className="font-bold text-lg text-white">Stage 3: Data Integrity & Repair</h3>
                                    <p className="text-sm text-gray-400">Scan GeoTIFF headers, verify grid alignment, repair manifests.</p>
                                </div>
                            </div>
                            <Button disabled={!!activeStage} onClick={() => runJob('integrity')} variant="secondary">
                                <Play className="w-4 h-4 mr-2" /> Run Audit
                            </Button>
                        </CardContent>
                    </Card>

                    {/* 4. STAGE: TRAINING */}
                    <Card className={`border-l-4 ${activeStage?.includes('train') ? 'border-l-purple-500 bg-purple-950/10' : 'border-l-gray-700 bg-card/50'}`}>
                        <CardContent className="p-4">
                            <div className="flex gap-4 items-center mb-4">
                                <div className="p-3 rounded-full bg-purple-900/30 text-purple-400">
                                    <Cpu className="w-6 h-6" />
                                </div>
                                <div>
                                    <h3 className="font-bold text-lg text-white">Stage 4: Dual-Expert Training</h3>
                                    <p className="text-sm text-gray-400">Fine-tune YOLO11l specialists on the latest labeled data.</p>
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4 pl-16">
                                <div className="bg-black/40 p-3 rounded border border-gray-800 flex justify-between items-center">
                                    <span className="text-sm font-mono text-gray-300">Satellite Expert (Top-Down)</span>
                                    <Button size="sm" disabled={!!activeStage} onClick={() => runJob('train_satellite', { epochs: 50 })} className="h-7 text-xs bg-purple-900 hover:bg-purple-800">
                                        Train (50 ep)
                                    </Button>
                                </div>
                                <div className="bg-black/40 p-3 rounded border border-gray-800 flex justify-between items-center">
                                    <span className="text-sm font-mono text-gray-300">Street Expert (Ego-Centric)</span>
                                    <Button size="sm" disabled={!!activeStage} onClick={() => runJob('train_street', { epochs: 50 })} className="h-7 text-xs bg-purple-900 hover:bg-purple-800">
                                        Train (50 ep)
                                    </Button>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* 5. STAGE: INFERENCE */}
                    <Card className={`border-l-4 ${activeStage === 'inference' ? 'border-l-green-500 bg-green-950/10' : 'border-l-gray-700 bg-card/50'}`}>
                        <CardContent className="p-4 flex items-center justify-between">
                            <div className="flex gap-4 items-center">
                                <div className="p-3 rounded-full bg-green-900/30 text-green-400">
                                    <Zap className="w-6 h-6" />
                                </div>
                                <div>
                                    <h3 className="font-bold text-lg text-white">Stage 5: Unified Detection & Fusion</h3>
                                    <p className="text-sm text-gray-400">Detect → Enrich (Lidar/Roads) → Fuse → PostGIS Golden Record.</p>
                                    {selectedCounties.length > 0 && (
                                        <Badge variant="outline" className="mt-1 border-green-500/30 text-green-400">
                                            Targets: {selectedCounties.join(', ')}
                                        </Badge>
                                    )}
                                </div>
                            </div>
                            <Button
                                disabled={!!activeStage || selectedCounties.length === 0}
                                onClick={() => runJob('inference', { targets: selectedCounties })}
                                className="bg-green-600 hover:bg-green-500"
                            >
                                <Play className="w-4 h-4 mr-2" /> Start Pipeline
                            </Button>
                        </CardContent>
                    </Card>

                    {/* 6. FULL RUN ORCHESTRATOR */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.5 }}
                        className="mt-8 relative"
                    >
                        <div className="absolute inset-0 bg-gradient-to-r from-blue-500/10 via-purple-500/10 to-transparent blur-xl" />
                        <Card className="bg-black/80 border-blue-500/30 relative overflow-hidden">
                            <div className="absolute inset-0 bg-[linear-gradient(45deg,transparent_25%,rgba(59,130,246,0.05)_50%,transparent_75%)] bg-[length:250%_250%] animate-[gradient_8s_linear_infinite]" />
                            <CardContent className="p-6 flex items-center justify-between relative z-10">
                                <div className="flex items-center gap-6">
                                    <div className="p-4 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400">
                                        <Activity className="w-8 h-8" />
                                    </div>
                                    <div>
                                        <h2 className="text-xl font-black text-white uppercase tracking-widest flex items-center gap-3">
                                            Run Regional Extraction
                                            {activeStage && <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded border border-blue-500/30 animate-pulse">Running</span>}
                                        </h2>
                                        <p className="text-gray-400 font-mono text-sm mt-1">
                                            Execute End-to-End: Integrity → Detect → Fuse on <span className="text-blue-400">{selectedCounties.length > 0 ? selectedCounties.join(', ') : 'ALL'}</span> targets.
                                        </p>
                                        <div className="text-xs text-gray-500 italic mt-1">
                                            Uses current model weights. Training skipped by default.
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center gap-4">
                                    <div className="flex items-center gap-2 px-4 py-2 rounded bg-white/5 border border-white/10">
                                        <span className="text-xs text-gray-400 font-mono">TARGETS:</span>
                                        <span className="text-sm font-bold text-white">{selectedCounties.length > 0 ? selectedCounties.length : 'ALL'}</span>
                                    </div>

                                    {activeStage ? (
                                        <Button
                                            className="bg-red-600 hover:bg-red-700 text-white font-bold h-12 px-8 uppercase tracking-widest shadow-lg shadow-red-500/20 transition-all duration-200"
                                            onClick={() => stopJob()}
                                        >
                                            STOP
                                        </Button>
                                    ) : (
                                        <Button
                                            className="bg-blue-600 hover:bg-blue-500 text-white font-bold h-12 px-8 uppercase tracking-widest shadow-lg shadow-blue-500/20 transition-all duration-200"
                                            onClick={() => runJob('full_pipeline', { targets: selectedCounties })}
                                        >
                                            START EXTRACTION
                                        </Button>
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>

                </div>

                {/* RIGHT COLUMN: LOGS */}
                <div className="col-span-4">
                    <Card className="h-full bg-black border-primary/20 flex flex-col">
                        <CardHeader className="py-3 border-b border-primary/10 bg-muted/10 flex flex-row items-center justify-between">
                            <CardTitle className="text-sm flex items-center text-green-500 font-mono">
                                <Terminal className="mr-2 h-4 w-4" /> Live Console Output
                            </CardTitle>
                            <Button variant="ghost" size="sm" onClick={fetchLogs} className="h-6 w-8 p-0 hover:bg-white/10" title="Refresh Logs">
                                <FileText className="h-3 w-3 text-gray-400" />
                            </Button>
                        </CardHeader>
                        <CardContent className="p-0 flex-1 relative">
                            <div className="absolute inset-0 overflow-y-auto p-4 font-mono text-xs space-y-1">
                                {logs.length === 0 && (
                                    <span className="text-gray-600 italic">Waiting for process output...</span>
                                )}
                                {logs.map((log, i) => (
                                    <div key={i} className="break-all border-l-2 pl-2 border-gray-800 hover:bg-white/5 transition-colors">
                                        <span className="text-gray-600 text-[10px] block mb-0.5">{log.timestamp}</span>
                                        <span className={log.type === 'error' ? "text-red-400" : "text-gray-300"}>
                                            {log.message}
                                        </span>
                                    </div>
                                ))}
                                <div ref={logsEndRef} />
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    )
}
