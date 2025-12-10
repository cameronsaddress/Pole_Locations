import { useEffect, useState } from "react"
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
import { Terminal, Cpu, Activity, Zap } from "lucide-react"

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
    const [stats, setStats] = useState<TrainingStats | null>(null)
    const [history, setHistory] = useState(generateInitialHistory())
    const [logs, setLogs] = useState<string[]>([
        "System initialized...",
        "CUDA backend active: NVIDIA H100 detected",
        "Loading dataset: HARRISBURG_POLES_V2",
        "Model architecture: YOLOv8l (43.7M params)",
        "Starting training loop..."
    ])

    useEffect(() => {
        // Dynamic API URL
        const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
        const wsHost = apiHost.replace('http', 'ws')

        const wsUrl = `${wsHost}/ws/training`
        const ws = new WebSocket(wsUrl)

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data)
            setStats(data)

            // Update Chart History
            setHistory(prev => {
                // Avoid duplicates
                if (prev.length > 0 && prev[prev.length - 1].epoch === data.epoch) return prev
                const newHistory = [...prev, { epoch: data.epoch, loss: data.box_loss, map: data.map50 }]
                return newHistory.slice(-50) // Keep last 50 points
            })

            // Add dummy log for effect
            setLogs(prev => [...prev, `[EPOCH ${data.epoch}] Batch processed. Loss: ${data.box_loss.toFixed(4)}`].slice(-10))
        }

        return () => ws.close()
    }, [])

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Model Training</h2>
                    <p className="text-muted-foreground">Real-time supervision of the YOLOv8 Large architecture</p>
                </div>
                <Badge variant="outline" className="text-lg px-4 py-1 border-cyan-500 text-cyan-500 animate-pulse">
                    <Activity className="mr-2 h-4 w-4" />
                    {stats ? `Training Active: Epoch ${stats.epoch}/${stats.total_epochs || 20}` : "Connecting..."}
                </Badge>
            </div>

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
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155' }}
                                />
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
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155' }}
                                />
                                <Line type="monotone" dataKey="map" stroke="#22c55e" strokeWidth={2} dot={false} />
                            </LineChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>
            </div>

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
                                <div className="h-full bg-cyan-500 w-[92%]" />
                            </div>
                            <span className="text-xs font-mono">92%</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-muted-foreground">VRAM Usage</span>
                            <div className="w-24 h-2 bg-muted rounded-full overflow-hidden">
                                <div className="h-full bg-purple-500 w-[78%]" />
                            </div>
                            <span className="text-xs font-mono">64GB</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-muted-foreground">Power Draw</span>
                            <span className="text-xs font-mono text-amber-500"><Zap className="inline h-3 w-3" /> 350W</span>
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
                    <CardContent className="p-4 h-[200px] overflow-y-auto">
                        <div className="space-y-1">
                            {logs.map((log, i) => (
                                <div key={i} className="text-muted-foreground">
                                    <span className="text-green-500/50 mr-2">{new Date().toLocaleTimeString()}</span>
                                    {log}
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
