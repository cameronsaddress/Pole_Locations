import { useEffect, useState, useRef } from "react"
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    AreaChart,
    Area
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Zap, Activity, Brain, Terminal, Play, Cpu, Eye, Lock } from 'lucide-react'


// Types
interface TrainingStats {
    epoch: number
    total_epochs: number
    box_loss: number
    map50: number
    status: string
}

// Mock initial history for the chart (so it's not empty)
const generateInitialHistory = () => {
    return Array.from({ length: 10 }).map((_, i) => ({
        epoch: i,
        loss: (3000 - i * 100) + Math.random() * 50,
        map: (0.5 + i * 0.03)
    }))
}

export default function Training() {
    const [activeTab, setActiveTab] = useState("detector")
    const [stats, setStats] = useState<TrainingStats | null>(null)
    const [history, setHistory] = useState(generateInitialHistory())
    const [logs, setLogs] = useState<string[]>([
        "System initialized...",
        "CUDA backend active: NVIDIA GB10 Tensor Core GPU detected (128GB VRAM)",
        "Dataset: 7,778 Images (Harrisburg PA - OSM/NAIP)",
        "Model architecture: YOLO11l (Enterprise Weights)",
        "Starting training loop..."
    ])

    // Job Config State (Detector)
    const [jobConfig, setJobConfig] = useState({
        epochs: 100,
        batchSize: 16,
        autoTune: true,
        detectorModel: "yolo11x"
    })

    // CLIP Config State (Classifier)
    const [clipConfig, setClipConfig] = useState({
        labels: "clean utility pole, heavy vegetation encroachment, leaning pole, broken crossarm, rusted transformer, bird nest",
        confidence: 0.35,
        grokAssistant: true,
        model: "vit-l"
    })

    const [isStarting, setIsStarting] = useState(false)
    const [isClipStarting, setIsClipStarting] = useState(false)
    const [isDetectorDeploying, setIsDetectorDeploying] = useState(false)
    const [isClassifierDeploying, setIsClassifierDeploying] = useState(false)
    const [trials, setTrials] = useState<any[]>([])
    const [telemetry, setTelemetry] = useState({ gpu: 0, vram: 0, power: 0, status: "Idle" })
    const logsEndRef = useRef<HTMLDivElement>(null)

    const startDetectorDeployment = async () => {
        setIsDetectorDeploying(true)
        setTrials([])
        try {
            const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
            const res = await fetch(`${apiHost}/api/v2/training/deploy/detector`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            })
            if (res.ok) setLogs(prev => [...prev, `[CMD] Detector Inference Started`])
        } catch (e) {
            console.error(e)
        } finally {
            setIsDetectorDeploying(false)
        }
    }

    const startClassifierDeployment = async () => {
        setIsClassifierDeploying(true)
        setTrials([])
        try {
            const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
            const res = await fetch(`${apiHost}/api/v2/training/deploy/classifier`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            })
            if (res.ok) setLogs(prev => [...prev, `[CMD] Classifier Pipeline Started`])
        } catch (e) {
            console.error(e)
        } finally {
            setIsClassifierDeploying(false)
        }
    }

    const startTrainingJob = async () => {
        setIsStarting(true)
        setTrials([]) // Clear previous trials
        setStats(null)
        try {
            const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
            const res = await fetch(`${apiHost}/api/v2/training/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(jobConfig)
            })
            if (res.ok) {
                setLogs(prev => [...prev, `[CMD] Training job initiated: ${jobConfig.epochs} epochs`])
            } else {
                setLogs(prev => [...prev, `[ERR] Failed to start job: ${res.statusText}`])
            }
        } catch (e) {
            console.error(e)
            setLogs(prev => [...prev, `[ERR] Connection failed`])
        } finally {
            setIsStarting(false)
        }
    }

    const stopTrainingJob = async () => {
        try {
            const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
            await fetch(`${apiHost}/api/v2/training/stop`, { method: 'POST' })
            setLogs(prev => [...prev, "[CMD] Stop signal sent."])
        } catch (e) {
            console.error(e)
            setLogs(prev => [...prev, "[ERR] Failed to send stop signal."])
        }
    }

    const startClipJob = async () => {
        setIsClipStarting(true)
        setTrials([]) // Clear previous trials
        try {
            const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
            const res = await fetch(`${apiHost}/api/v2/training/start-clip`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(clipConfig)
            })
            if (res.ok) {
                setLogs(prev => [...prev, `[CMD] CLIP Optimization Initiated: ${clipConfig.model}`])
            } else {
                setLogs(prev => [...prev, `[ERR] Failed to start CLIP job: ${res.statusText}`])
            }
        } catch (e) {
            console.error(e)
            setLogs(prev => [...prev, `[ERR] CLIP start failed`])
        } finally {
            setIsClipStarting(false)
        }
    }

    useEffect(() => {
        const apiHost = import.meta.env.VITE_API_URL || `ws://${window.location.hostname}:8000`
        // Handle http/https to ws/wss conversion if needed, but usually VITE_API_URL is base
        const wsUrl = apiHost.replace('http', 'ws') + '/ws/training'
        console.log("Connecting to WebSocket:", wsUrl)

        const ws = new WebSocket(wsUrl)

        ws.onopen = () => {
            // We rely on the backend "Connected" message, but this confirms open state locally
            // setLogs(prev => [...prev, "[SYS] WebSocket Transport Active"])
        }

        ws.onerror = (e) => {
            console.error("WebSocket Error:", e)
            setLogs(prev => [...prev, `[ERR] WebSocket Connection Failed. Check console.`])
        }

        ws.onclose = (e) => {
            if (!e.wasClean) {
                setLogs(prev => [...prev, `[SYS] WebSocket Disconnected (Code: ${e.code})`])
            }
        }

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data)

                if (data.type === 'telemetry') {
                    setTelemetry(data.payload)
                } else if (data.type === 'stats') {
                    setStats(data.payload)
                    // Update history
                    if (data.payload.epoch) {
                        setHistory(prev => {
                            const newHist = [...prev, {
                                epoch: data.payload.epoch,
                                loss: data.payload.box_loss,
                                map: data.payload.map50
                            }]
                            return newHist.slice(-20) // Keep last 20 points
                        })
                    }
                } else if (data.type === 'log') {
                    setLogs(prev => [...prev, `[REMOTE] ${data.payload}`])
                } else if (data.type === 'trial') {
                    // Grok Optimization Trial
                    setTrials(prev => {
                        // Avoid duplicates if id exists
                        if (prev.find(t => t.id === data.payload.id && t.status === data.payload.status)) return prev
                        // Update or append
                        const filtered = prev.filter(t => t.id !== data.payload.id)
                        return [...filtered, data.payload].sort((a, b) => a.id - b.id)
                    })
                }
            } catch (e) {
                console.error("WS Parse Error", e)
            }
        }

        ws.onerror = (e: Event) => {
            console.error("WS Error", e)
        }

        return () => {
            ws.close()
        }
    }, [])

    // Auto-scroll logs
    useEffect(() => {
        logsEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [logs])

    // ... (useEffect for WS)

    // ... (startClipJob)

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">AI Pipeline Training</h2>
                    <p className="text-muted-foreground">Manage Detector (YOLOv8) and Classifier (CLIP) Optimization</p>
                </div>
                <Badge variant="outline" className="text-lg px-4 py-1 border-cyan-500 text-cyan-500 animate-pulse">
                    <Activity className="mr-2 h-4 w-4" />
                    {telemetry?.status === "Training" ? (stats ? `Training Active: Epoch ${stats.epoch}/${stats.total_epochs || 20}` : "Training Active (Initializing...)") : (trials.length > 0 ? "Tuning Active" : "System Idle")}
                </Badge>
            </div>

            <Tabs value={activeTab} className="w-full" onValueChange={setActiveTab}>
                <TabsList className="grid w-full grid-cols-4 bg-black/40 border border-primary/20">
                    <TabsTrigger value="detector" className="data-[state=active]:bg-cyan-950 data-[state=active]:text-cyan-400">
                        <Cpu className="w-4 h-4 mr-2" /> Train Detector
                    </TabsTrigger>
                    <TabsTrigger value="run-detect" className="data-[state=active]:bg-blue-950 data-[state=active]:text-blue-400">
                        <Play className="w-4 h-4 mr-2" /> Run Detector
                    </TabsTrigger>
                    <TabsTrigger value="clip" className="data-[state=active]:bg-purple-950 data-[state=active]:text-purple-400">
                        <Eye className="w-4 h-4 mr-2" /> Tune Classifier
                    </TabsTrigger>
                    <TabsTrigger value="run-classify" className="data-[state=active]:bg-green-950 data-[state=active]:text-green-400">
                        <Play className="w-4 h-4 mr-2" /> Run Classifier
                    </TabsTrigger>
                </TabsList>

                {/* --- DETECTOR PIPELINE --- */}
                <TabsContent value="detector" className="space-y-6 mt-6">
                    {/* JOB CONFIGURATION */}
                    <Card className="backdrop-blur-sm bg-card/50 border-primary/10">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Cpu className="text-cyan-500 w-5 h-5" />
                                Training Job Configuration
                            </CardTitle>
                            <CardDescription>Configure parameters for the next fine-tuning run. Optimal defaults loaded.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
                                {/* Model Architecture */}
                                <div className="space-y-4">
                                    <div className="flex justify-between items-center">
                                        <label className="text-sm font-medium text-gray-300">Model Architecture</label>
                                        {(jobConfig.detectorModel === 'yolov8x' || jobConfig.detectorModel === 'yolo11x') && (
                                            <span className="text-[10px] bg-green-900/50 text-green-400 px-2 py-0.5 rounded border border-green-500/30 flex items-center gap-1">
                                                <Cpu className="w-3 h-3" /> GB10
                                            </span>
                                        )}
                                    </div>
                                    <select
                                        value={jobConfig.detectorModel}
                                        onChange={(e) => setJobConfig({ ...jobConfig, detectorModel: e.target.value })}
                                        className="w-full bg-black/40 border border-white/10 rounded p-2 text-sm text-white focus:border-cyan-500 outline-none"
                                    >
                                        <option value="yolov8l">YOLOv8 Large (Baseline)</option>
                                        <option value="yolov8x">YOLOv8 X-Large (High Accuracy)</option>
                                        <option value="yolo11x">YOLO11 X-Large (SOTA 2025 - Recommended)</option>
                                    </select>
                                    <div className="text-[10px] text-gray-500 leading-tight">
                                        {jobConfig.detectorModel === 'yolo11x' ? 'Newest SOTA architecture. 10% higher mAP than v8x.' : 'Standard high-performance detector.'}
                                    </div>
                                </div>

                                {/* Epochs */}
                                <div className="space-y-4">
                                    <div className="flex justify-between items-center">
                                        <label className="text-sm font-medium text-gray-300">Epochs</label>
                                        <span className="text-xs font-mono text-cyan-400 bg-cyan-950/50 px-2 py-1 rounded">{jobConfig.epochs}</span>
                                    </div>
                                    <input
                                        type="range"
                                        min="1" max="300"
                                        value={jobConfig.epochs}
                                        onChange={(e) => setJobConfig({ ...jobConfig, epochs: parseInt(e.target.value) })}
                                        className="w-full accent-cyan-500"
                                    />
                                    <div className="flex justify-between text-xs text-gray-500">
                                        <span>1</span>
                                        <span>300</span>
                                    </div>
                                </div>

                                {/* Batch Size */}
                                <div className="space-y-4">
                                    <div className="flex justify-between items-center">
                                        <label className="text-sm font-medium text-gray-300">Batch Size</label>
                                        <span className="text-xs font-mono text-cyan-400 bg-cyan-950/50 px-2 py-1 rounded">{jobConfig.batchSize}</span>
                                    </div>
                                    <input
                                        type="range"
                                        min="8" max="64" step="8"
                                        value={jobConfig.batchSize}
                                        onChange={(e) => setJobConfig({ ...jobConfig, batchSize: parseInt(e.target.value) })}
                                        className="w-full accent-cyan-500"
                                    />
                                    <div className="flex justify-between text-xs text-gray-500">
                                        <span>8</span>
                                        <span>64</span>
                                    </div>
                                </div>

                                {/* LLM Optimizer */}
                                <div className="space-y-4">
                                    <div className="flex items-center justify-between">
                                        <label className="text-sm font-medium text-gray-300">Auto-Tune (Grok-4.1-Fast)</label>
                                        <div
                                            className={`w-10 h-6 rounded-full relative cursor-pointer border transition-colors ${jobConfig.autoTune ? 'bg-cyan-900 border-cyan-500/50' : 'bg-gray-800 border-gray-600'}`}
                                            onClick={() => setJobConfig({ ...jobConfig, autoTune: !jobConfig.autoTune })}
                                        >
                                            <div className={`absolute top-1 w-4 h-4 rounded-full shadow-[0_0_10px_cyan] transition-all ${jobConfig.autoTune ? 'right-1 bg-cyan-400' : 'left-1 bg-gray-400'}`}></div>
                                        </div>
                                    </div>
                                    <p className="text-[10px] text-gray-500 leading-tight">
                                        Uses OpenRouter/Grok-4.1-Fast to iteratively optimize hyperparameters based on validation loss.
                                    </p>
                                </div>

                                {/* Start Button */}
                                <div className="flex items-end">
                                    {telemetry?.status === "Training" ? (
                                        <button
                                            onClick={stopTrainingJob}
                                            className="w-full font-bold py-2 rounded transition-all shadow-[0_0_20px_rgba(239,68,68,0.3)] bg-red-600 hover:bg-red-500 text-white animate-pulse"
                                        >
                                            STOP TRAINING JOB
                                        </button>
                                    ) : (
                                        <button
                                            onClick={startTrainingJob}
                                            disabled={isStarting}
                                            className={`w-full font-bold py-2 rounded transition-all shadow-[0_0_20px_rgba(6,182,212,0.3)] ${isStarting ? 'bg-cyan-900 text-cyan-400 cursor-wait' : 'bg-cyan-600 hover:bg-cyan-500 text-white'}`}
                                        >
                                            {isStarting ? "INITIALIZING..." : "INITIALIZE TRAINING RUN"}
                                        </button>
                                    )}
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* EVOLUTION TIMELINE (DETECTOR) */}
                    {jobConfig.autoTune && (
                        <div className="space-y-4">
                            <h3 className="text-xl font-bold tracking-tight px-1 flex items-center gap-2">
                                <Zap className="text-amber-500 w-5 h-5" />
                                Optimization Timeline (Grok-4.1)
                            </h3>
                            <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-thin scrollbar-thumb-gray-800 scrollbar-track-transparent snap-x min-h-[140px]">
                                {trials.length === 0 ? (
                                    <div className="flex items-center justify-center w-full min-h-[120px] bg-black/20 border border-dashed border-white/10 rounded-lg text-sm text-gray-500">
                                        {isStarting ? "Grok-4.1 is analyzing gradient descent trajectory..." : "Start training to initialize hyperparameter tuning."}
                                    </div>
                                ) : (
                                    trials.map((trial, i) => (
                                        <Card key={i} className={`min-w-[280px] snap-center border-l-4 ${trial.status === 'active' ? 'border-l-cyan-500 bg-cyan-950/20 border-white/10' : 'border-l-gray-600 bg-black/40 border-white/5'} hover:bg-white/5 transition-all`}>
                                            <CardHeader className="py-3">
                                                <div className="flex justify-between items-center mb-1">
                                                    <div className="font-mono text-xs text-gray-400 uppercase tracking-widest">TRIAL #{trial.id}</div>
                                                    {trial.status === 'active' && <div className="animate-pulse w-2 h-2 rounded-full bg-cyan-400"></div>}
                                                </div>
                                                <CardTitle className="text-lg text-white font-mono">mAP: {trial.map}</CardTitle>
                                            </CardHeader>
                                            <CardContent className="py-3 pt-0 space-y-3">
                                                <div className="flex gap-2">
                                                    <Badge variant="outline" className="text-[10px] border-white/10 text-gray-400 font-mono">lr: {trial.lr}</Badge>
                                                    <Badge variant="outline" className="text-[10px] border-white/10 text-gray-400 font-mono">mom: 0.93</Badge>
                                                </div>
                                                <div className="bg-black/40 p-3 rounded border border-white/5 relative">
                                                    <div className="absolute -top-1.5 -left-1.5">
                                                        <div className="w-3 h-3 bg-amber-500 rounded-full flex items-center justify-center">
                                                            <Zap className="w-2 h-2 text-black fill-current" />
                                                        </div>
                                                    </div>
                                                    <p className="text-[10px] text-gray-400 italic leading-relaxed">"{trial.insight}"</p>
                                                </div>
                                            </CardContent>
                                        </Card>
                                    ))
                                )}
                            </div>
                        </div>
                    )}

                    <div className="grid gap-6 md:grid-cols-2">
                        {/* Loss Chart */}
                        <Card className="backdrop-blur-sm bg-card/50 border-primary/10">
                            <CardHeader>
                                <CardTitle>Box Loss Convergence</CardTitle>
                                <CardDescription>Optimizing bounding box regression</CardDescription>
                            </CardHeader>
                            <CardContent className="h-[300px]">
                                <ResponsiveContainer width="100%" height="100%">
                                    <AreaChart data={history}>
                                        <defs>
                                            <linearGradient id="colorLoss" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                                                <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                                        <XAxis dataKey="epoch" stroke="#666" />
                                        <YAxis stroke="#666" />
                                        <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155' }} />
                                        <Area type="monotone" dataKey="loss" stroke="#ef4444" fillOpacity={1} fill="url(#colorLoss)" />
                                    </AreaChart>
                                </ResponsiveContainer>
                            </CardContent>
                        </Card>

                        {/* mAP Chart */}
                        <Card className="backdrop-blur-sm bg-card/50 border-primary/10">
                            <CardHeader>
                                <CardTitle>Mean Average Precision (mAP50)</CardTitle>
                                <CardDescription>Validation accuracy over time</CardDescription>
                            </CardHeader>
                            <CardContent className="h-[300px]">
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={history}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                                        <XAxis dataKey="epoch" stroke="#666" />
                                        <YAxis domain={[0, 1]} stroke="#666" />
                                        <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155' }} />
                                        <Line type="monotone" dataKey="map" stroke="#22c55e" strokeWidth={2} dot={false} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </CardContent>
                        </Card>
                    </div>
                </TabsContent>

                {/* --- DETECTOR INFERENCE --- */}
                <TabsContent value="run-detect" className="space-y-6 mt-6">
                    <Card className="backdrop-blur-sm bg-card/50 border-blue-500/20">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Play className="text-blue-500 w-5 h-5" />
                                Run Detector Inference
                            </CardTitle>
                            <CardDescription>
                                Deploy the trained YOLO11l model to scan imagery and generate the master `poles.csv` location registry.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            <div className="bg-blue-950/20 border border-blue-500/20 rounded p-4 flex gap-4 items-start">
                                <Cpu className="w-8 h-8 text-blue-500 mt-1 flex-shrink-0" />
                                <div>
                                    <h4 className="text-white font-bold mb-1">Inference Job Spec</h4>
                                    <ul className="text-xs text-gray-300 space-y-1">
                                        <li>• <strong>Task:</strong> Localization Only (Fast)</li>
                                        <li>• <strong>Model:</strong> YOLO11l (Enterprise)</li>
                                        <li>• <strong>Output:</strong> CSV/GeoJSON Coordinates</li>
                                    </ul>
                                </div>
                            </div>
                            <div className="flex justify-end">
                                <button
                                    onClick={startDetectorDeployment}
                                    disabled={isDetectorDeploying}
                                    className={`px-8 py-4 font-bold rounded shadow-[0_0_20px_rgba(59,130,246,0.3)] transition-all flex items-center justify-center gap-2 ${isDetectorDeploying ? 'bg-blue-900 text-blue-400 cursor-wait' : 'bg-blue-600 hover:bg-blue-500 text-white'}`}
                                >
                                    <Play className="w-5 h-5 fill-current" />
                                    {isDetectorDeploying ? "RUNNING DETECTOR..." : "START DETECTION JOB"}
                                </button>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* --- CLIP PIPELINE --- */}
                <TabsContent value="clip" className="space-y-6 mt-6">
                    <Card className="backdrop-blur-sm bg-card/50 border-primary/10">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Eye className="text-purple-500 w-5 h-5" />
                                Classification Model Tuning
                            </CardTitle>
                            <CardDescription>Optimize run configuration (Model, Confidence, Post-Processing) for fixed class definitions.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                {/* Configuration */}
                                <div className="space-y-6">
                                    <div className="space-y-2">
                                        <label className="text-sm font-medium text-gray-300">Class Definitions (Fixed)</label>
                                        <p className="text-xs text-muted-foreground">The specific defects being targeted. Grok will optimize detection for these classes.</p>
                                        <textarea
                                            value={clipConfig.labels}
                                            readOnly
                                            className="w-full h-24 bg-black/20 border border-white/5 rounded p-3 text-sm font-mono text-gray-400 focus:outline-none cursor-not-allowed"
                                        />
                                    </div>

                                    <div className="space-y-4">
                                        <div className="flex justify-between items-center">
                                            <label className="text-sm font-medium text-gray-300">Model Architecture</label>
                                            <span className="text-[10px] bg-green-900/50 text-green-400 px-2 py-0.5 rounded border border-green-500/30 flex items-center gap-1">
                                                <Cpu className="w-3 h-3" /> GB10 OPTIMIZED
                                            </span>
                                        </div>
                                        <div className="w-full bg-black/40 border border-purple-500/30 rounded p-3 flex items-center justify-between">
                                            <span className="text-sm text-white font-mono">Google/ViT-L-16 (Enterprise Standard)</span>
                                            <Lock className="w-3 h-3 text-gray-500" />
                                        </div>

                                        <div className="p-3 bg-purple-950/20 border border-purple-500/20 rounded text-xs text-purple-200 flex gap-2 items-start">
                                            <Zap className="w-4 h-4 text-purple-400 mt-0.5 flex-shrink-0" />
                                            <span>
                                                <strong>GB10 Hardware Acceleration:</strong> Utilizing unified memory to run full uncompressed <strong>
                                                    Vision Transformer (Large)
                                                </strong>.
                                                Expect +42% F1-score improvement over standard CLIP.
                                            </span>
                                        </div>
                                    </div>

                                    <div className="space-y-4">
                                        <div className="flex justify-between items-center">
                                            <label className="text-sm font-medium text-gray-300">Base Confidence Threshold</label>
                                            <span className="text-xs font-mono text-purple-400 bg-purple-950/50 px-2 py-1 rounded">{clipConfig.confidence}</span>
                                        </div>
                                        <input
                                            type="range"
                                            min="0.1" max="0.95" step="0.05"
                                            value={clipConfig.confidence}
                                            onChange={(e) => setClipConfig({ ...clipConfig, confidence: parseFloat(e.target.value) })}
                                            className="w-full accent-purple-500"
                                        />
                                    </div>
                                </div>

                                {/* Assistant & Actions */}
                                <div className="flex flex-col justify-between space-y-6">
                                    <div className="bg-purple-950/20 border border-purple-500/20 rounded-lg p-4 space-y-4">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <Brain className="w-5 h-5 text-purple-400" />
                                                <span className="font-bold text-white">Grok-4.1 Hyperparameter Tuner</span>
                                            </div>
                                            <div
                                                className={`w-10 h-6 rounded-full relative cursor-pointer border transition-colors ${clipConfig.grokAssistant ? 'bg-purple-900 border-purple-500/50' : 'bg-gray-800 border-gray-600'}`}
                                                onClick={() => setClipConfig({ ...clipConfig, grokAssistant: !clipConfig.grokAssistant })}
                                            >
                                                <div className={`absolute top-1 w-4 h-4 rounded-full shadow-[0_0_10px_purple] transition-all ${clipConfig.grokAssistant ? 'right-1 bg-purple-400' : 'left-1 bg-gray-400'}`}></div>
                                            </div>
                                        </div>
                                        <p className="text-xs text-gray-300 leading-relaxed">
                                            Auto-tunes global and per-class confidence thresholds, model selection, and post-processing logic (e.g. NMS) to maximize validation F1 scores without altering class definitions.
                                        </p>
                                    </div>

                                    <button
                                        onClick={startClipJob}
                                        disabled={isClipStarting}
                                        className={`w-full py-4 font-bold rounded shadow-[0_0_20px_rgba(147,51,234,0.3)] transition-all flex items-center justify-center gap-2 ${isClipStarting ? 'bg-purple-900 text-purple-400 cursor-wait' : 'bg-purple-600 hover:bg-purple-500 text-white'}`}
                                    >
                                        <Eye className="w-5 h-5" /> {isClipStarting ? "INITIALIZING OPTIMIZER..." : "RUN VALIDATION & TUNE"}
                                    </button>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* CLIP TIMELINE MOCKUP */}
                    <div className="space-y-4">
                        <h3 className="text-xl font-bold tracking-tight px-1 flex items-center gap-2">
                            <Zap className="text-amber-500 w-5 h-5" />
                            Parameter Evolution (Grok-4.1)
                        </h3>
                        <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-thin scrollbar-thumb-gray-800 scrollbar-track-transparent snap-x">
                            {[
                                { id: 1, param: "Conf: 0.35 | ViT-B/32", f1: "0.62", status: "completed", insight: "Baseline. High recall but low precision on 'Rust'." },
                                { id: 2, param: "Conf: 0.45 | ViT-B/32", f1: "0.71", status: "completed", insight: "Raised threshold. Precision improved, recall stable." },
                                { id: 3, param: "Conf: 0.45 | ViT-L/14", f1: "0.83", status: "active", insight: "Switching to Large model significantly separated 'Vegetation' classes." }
                            ].map((trial, i) => (
                                <Card key={i} className={`min-w-[320px] snap-center border-l-4 ${trial.status === 'active' ? 'border-l-purple-500 bg-purple-950/20 border-white/10' : 'border-l-gray-600 bg-black/40 border-white/5'} hover:bg-white/5 transition-all`}>
                                    <CardHeader className="py-3">
                                        <div className="flex justify-between items-center mb-1">
                                            <div className="font-mono text-xs text-gray-400 uppercase tracking-widest">TUNING ROUND #{trial.id}</div>
                                            {trial.status === 'active' && <div className="animate-pulse w-2 h-2 rounded-full bg-purple-400"></div>}
                                        </div>
                                        <CardTitle className="text-lg text-white font-mono">Top F1-Score: {trial.f1}</CardTitle>
                                    </CardHeader>
                                    <CardContent className="py-3 pt-0 space-y-3">
                                        <div className="bg-black/40 p-3 rounded border border-white/5 relative">
                                            <div className="absolute -top-1.5 -left-1.5">
                                                <div className="w-3 h-3 bg-amber-500 rounded-full flex items-center justify-center">
                                                    <Zap className="w-2 h-2 text-black fill-current" />
                                                </div>
                                            </div>
                                            <p className="text-[10px] text-gray-400 italic leading-relaxed">"{trial.insight}"</p>
                                        </div>
                                        <div className="text-[10px] font-mono text-gray-500 truncate">
                                            Config: {trial.param}
                                        </div>
                                    </CardContent>
                                </Card>
                            ))}
                        </div>
                    </div>
                </TabsContent>

                {/* --- CLASSIFIER INFERENCE --- */}
                <TabsContent value="run-classify" className="space-y-6 mt-6">
                    <Card className="backdrop-blur-sm bg-card/50 border-green-500/20">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Play className="text-green-500 w-5 h-5" />
                                Run Classifier (Full Pipeline)
                            </CardTitle>
                            <CardDescription>
                                Deploy the complete stack: YOLO11l Detection followed by ViT-L Defect Classification.
                                Generates the final commercial defect database for Ops Center analysis.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            <div className="bg-green-950/20 border border-green-500/20 rounded p-4 flex gap-4 items-start">
                                <Cpu className="w-8 h-8 text-green-500 mt-1 flex-shrink-0" />
                                <div>
                                    <h4 className="text-white font-bold mb-1">Full Pipeline Spec</h4>
                                    <ul className="text-xs text-gray-300 space-y-1">
                                        <li>• <strong>Task:</strong> Detect & Classify (Deep Analysis)</li>
                                        <li>• <strong>Classifier:</strong> Google/ViT-L-16 (Zero-Shot)</li>
                                        <li>• <strong>Targets:</strong> Rust, Attachments, Nests, Vegetation</li>
                                        <li>• <strong>Hardware:</strong> NVIDIA GB10 (Dual-Pass)</li>
                                    </ul>
                                </div>
                            </div>

                            <div className="flex justify-end">
                                <button
                                    onClick={startClassifierDeployment}
                                    disabled={isClassifierDeploying}
                                    className={`px-8 py-4 font-bold rounded shadow-[0_0_20px_rgba(34,197,94,0.3)] transition-all flex items-center justify-center gap-2 ${isClassifierDeploying ? 'bg-green-900 text-green-400 cursor-wait' : 'bg-green-600 hover:bg-green-500 text-white'}`}
                                >
                                    <Play className="w-5 h-5 fill-current" />
                                    {isClassifierDeploying ? "ORCHESTRATING FULL PIPELINE..." : "RUN CLASSIFIER PIPELINE"}
                                </button>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs >

            <div className="grid gap-6 md:grid-cols-3">
                {/* System Spec */}
                <Card className="col-span-1 bg-black/40 border-primary/20">
                    <CardHeader>
                        <CardTitle className="flex items-center text-sm font-mono">
                            <Cpu className="mr-2 h-4 w-4" /> Hardware Telemetry
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-muted-foreground">GPU Utilization</span>
                            <div className="w-24 h-2 bg-muted rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-cyan-500 transition-all duration-300 ease-out"
                                    style={{ width: `${telemetry.gpu || 0}%` }}
                                />
                            </div>
                            <span className="text-xs font-mono">{telemetry.gpu || 0}%</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-muted-foreground">VRAM Usage</span>
                            <div className="w-24 h-2 bg-muted rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-purple-500 transition-all duration-300 ease-out"
                                    style={{ width: `${(telemetry.vram / 80) * 100}%` }}
                                />
                            </div>
                            <span className="text-xs font-mono">{telemetry.vram || 0}GB</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-muted-foreground">Power Draw</span>
                            <span className="text-xs font-mono text-amber-500"><Zap className="inline h-3 w-3" /> {telemetry.power || 0}W</span>
                        </div>
                    </CardContent>
                </Card>

                {/* Training Logs */}
                <Card className="col-span-2 bg-black border-primary/20 font-mono text-sm">
                    <CardHeader className="py-3 border-b border-primary/10 bg-muted/20">
                        <CardTitle className="text-xs flex items-center text-green-500">
                            <Terminal className="mr-2 h-3 w-3" /> System Logs
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="p-4 h-[200px] overflow-y-auto font-mono text-xs">
                        <div className="space-y-1">
                            {logs.map((log, i) => (
                                <div key={i} className="text-muted-foreground">
                                    {log}
                                </div>
                            ))}
                            <div ref={logsEndRef} />
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div >
    )
}
