import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Activity, CheckCircle, AlertTriangle, MapPin } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import LiveMap3D from "./LiveMap3D"

// Type definition for backend stats
interface TrainingStats {
    epoch: number
    total_epochs: number
    box_loss: number
    map50: number
    status: string
}

const initialStats = [
    {
        label: "Total Assets",
        value: "1,204,592",
        change: "+12.5%",
        trend: "up",
        icon: DatabaseIcon,
        color: "text-blue-500"
    },
    {
        label: "Verify Rate",
        value: "89.4%",
        change: "+2.1%",
        trend: "up",
        icon: CheckCircle,
        color: "text-green-500"
    },
    {
        label: "Anomalies",
        value: "142",
        change: "-5",
        trend: "down",
        icon: AlertTriangle,
        color: "text-amber-500"
    }
]

function DatabaseIcon(props: any) {
    return <MapPin {...props} /> // Generic icon for now
}

export default function Dashboard() {
    const [trainStats, setTrainStats] = useState<TrainingStats | null>(null)

    useEffect(() => {
        // Dynamically determine the API base URL based on the current browser location
        const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
        const wsHost = apiHost.replace('http', 'ws')

        // 1. Initial Fetch
        fetch(`${apiHost}/api/v2/stats/training`)
            .then(res => res.json())
            .then(data => setTrainStats(data))
            .catch(err => console.error("API Error:", err))

        // 2. WebSocket Subscription
        const wsUrl = `${wsHost}/ws/training`
        const ws = new WebSocket(wsUrl)

        ws.onopen = () => console.log("WebSocket Connected to", wsUrl)
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data)
            setTrainStats(data)
        }
        ws.onerror = (err) => console.error("WebSocket Error:", err)

        return () => ws.close()
    }, [])

    return (
        <div className="space-y-6">
            {/* Hero Stats */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {/* Static Business Metrics */}
                {initialStats.map((stat, i) => (
                    <motion.div
                        key={stat.label}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.1 }}
                    >
                        <Card className="backdrop-blur-sm bg-card/50 border-primary/10 shadow-glow hover:shadow-glow-lg transition-all duration-300">
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">
                                    {stat.label}
                                </CardTitle>
                                <stat.icon className={`h-4 w-4 ${stat.color}`} />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold font-mono tracking-tight">{stat.value}</div>
                                <div className="flex items-center text-xs text-muted-foreground mt-1">
                                    <span className={stat.trend === 'up' ? 'text-green-500' : 'text-red-500'}>
                                        {stat.change}
                                    </span>
                                    <span className="ml-1">from last sync</span>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                ))}

                {/* Live Training Metric */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                >
                    <Card className="backdrop-blur-sm bg-card/50 border-primary/10 shadow-glow hover:shadow-glow-lg transition-all duration-300 border-l-4 border-l-cyan-500">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">
                                Training Epoch
                            </CardTitle>
                            <Activity className="h-4 w-4 text-cyan-500 animate-pulse" />
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold font-mono tracking-tight">
                                {trainStats ? `${trainStats.epoch} / ${trainStats.total_epochs || 20}` : "Connecting..."}
                            </div>
                            <div className="flex items-center text-xs text-muted-foreground mt-1">
                                {trainStats && (
                                    <Badge variant="outline" className="mr-2 border-cyan-500/50 text-cyan-500 animate-pulse">
                                        {trainStats.status}
                                    </Badge>
                                )}
                                <span>Loss: {trainStats ? trainStats.box_loss.toFixed(3) : "..."}</span>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                {/* Main Map Preview - Now REAL 3D WIDGET */}
                <div className="col-span-4 h-[500px] rounded-xl overflow-hidden shadow-2xl border border-white/10">
                    <LiveMap3D mode="widget" />
                </div>

                {/* Recent Activity Feed */}
                <Card className="col-span-3 backdrop-blur-sm bg-card/30 border-primary/10 h-[500px]">
                    <CardHeader>
                        <CardTitle>Recent Detections</CardTitle>
                        <CardDescription>
                            Model: YOLOv8l (mAP: {trainStats?.map50.toFixed(2) || "0.00"})
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            {[1, 2, 3, 4, 5].map((_, i) => (
                                <div key={i} className="flex items-center">
                                    <div className="h-9 w-9 rounded bg-muted flex items-center justify-center text-xs font-mono">
                                        IMG
                                    </div>
                                    <div className="ml-4 space-y-1">
                                        <p className="text-sm font-medium leading-none">Pole Candidate #102{i}</p>
                                        <p className="text-xs text-muted-foreground">
                                            Conf: <span className="text-green-400">{(0.85 + i * 0.02).toFixed(2)}</span> • Lat: 40.2{i} • Lon: -76.8{i}
                                        </p>
                                    </div>
                                    <div className="ml-auto font-medium text-xs text-muted-foreground">
                                        Just now
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
