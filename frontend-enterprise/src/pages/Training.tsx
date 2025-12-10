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
import { Terminal, Cpu, Activity, Zap, Eye, Brain } from "lucide-react"

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
        "Loading dataset: HARRISBURG_POLES_V2",
        "Model architecture: YOLOv8l (43.7M params)",
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

    const startTrainingJob = async () => {
        setIsStarting(true)
        setTrials([]) // Clear previous trials
        try {
            const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
            const res = await fetch(`${apiHost}/api/v2/training/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(jobConfig)
            })
            if (res.ok) {
                setLogs(prev => [...prev, `[CMD] Training job initiated: ${jobConfig.epochs} epochs, Batch ${jobConfig.batchSize}`])
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

    // ... (telemetry state and refs)

    // ... (useEffect for WS)

    // ... (startClipJob)

    return (
        <div className="space-y-6">
            {/* ... (Header and Tabs) ... */}

            {/* ... (Detector Content) ... */}
            {/* ... (Job Config Card) ... */}

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

                {/* --- CLIP PIPELINE --- */ }
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
                            <select
                                value={clipConfig.model}
                                onChange={(e) => setClipConfig({ ...clipConfig, model: e.target.value })}
                                className="w-full bg-black/40 border border-white/10 rounded p-2 text-sm text-white focus:border-purple-500 outline-none"
                            >
                                <option value="clip-base">OpenAI/CLIP-ViT-B/32 (Discovery Mode - Low Accuracy)</option>
                                <option value="vit-l">Google/ViT-L-16 (Fine-Tuned - Recommended for GB10)</option>
                                <option value="vit-h-14">laion/CLIP-ViT-H-14 (Installed SOTA - 2.5B Params)</option>
                                <option value="convnext">Facebook/ConvNeXt-XXL (Maximum Accuracy - 128GB VRAM)</option>
                            </select>

                            {clipConfig.model !== 'clip-base' && (
                                <div className="p-3 bg-purple-950/20 border border-purple-500/20 rounded text-xs text-purple-200 flex gap-2 items-start">
                                    <Zap className="w-4 h-4 text-purple-400 mt-0.5 flex-shrink-0" />
                                    <span>
                                        <strong>GB10 Hardware Acceleration:</strong> Utilizing unified memory to run full uncompressed <strong>
                                            {clipConfig.model === 'vit-l' ? 'Vision Transformer (Large)' :
                                                clipConfig.model === 'vit-h-14' ? 'ViT-Huge (2.5B Params)' :
                                                    'ConvNeXt-XXL'}
                                        </strong>.
                                        {clipConfig.model === 'vit-h-14' ? ' Expect Near-Human zero-shot performance.' : ' Expect +42% F1-score improvement over standard CLIP.'}
                                    </span>
                                </div>
                            )}
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
                            className="w-full py-4 bg-purple-600 hover:bg-purple-500 text-white font-bold rounded shadow-[0_0_20px_rgba(147,51,234,0.3)] transition-all flex items-center justify-center gap-2"
                        >
                            <Eye className="w-5 h-5" /> RUN VALIDATION & TUNE
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
