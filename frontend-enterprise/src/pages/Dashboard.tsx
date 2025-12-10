import { motion } from "framer-motion"
import { CheckCircle, AlertTriangle, Zap, DollarSign, Activity, FileText } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import CommandCenter from "../components/CommandCenter"

// Corporate Operational Stats
const corporateStats = [
    {
        label: "Total Assets Managed",
        value: "1,204,592",
        change: "+125 this week",
        trend: "up",
        icon: FileText,
        color: "text-blue-500",
        border: "border-blue-500/20"
    },
    {
        label: "Grid Health Score",
        value: "99.8%",
        change: "Optimal Range",
        trend: "up",
        icon: Zap,
        color: "text-emerald-500",
        border: "border-emerald-500/20"
    },
    {
        label: "Critical Anomalies",
        value: "3",
        change: "Requires Action",
        trend: "down",
        icon: AlertTriangle,
        color: "text-amber-500",
        border: "border-amber-500/50" // Highlight this
    },
    {
        label: "Est. Preventative Savings",
        value: "$2,450,000",
        change: "YTD Projection",
        trend: "up",
        icon: DollarSign,
        color: "text-green-400",
        border: "border-green-500/20"
    }
]

export default function Dashboard() {
    return (
        <div className="space-y-6 h-full flex flex-col">

            {/* 1. EXECUTIVE METRICS ROW */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {corporateStats.map((stat, i) => (
                    <motion.div
                        key={stat.label}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.1 }}
                    >
                        <Card className={`backdrop-blur-sm bg-black/40 border ${stat.border} shadow-lg hover:bg-white/5 transition-all duration-300`}>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium text-gray-400 font-mono tracking-wider">
                                    {stat.label.toUpperCase()}
                                </CardTitle>
                                <stat.icon className={`h-4 w-4 ${stat.color}`} />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold font-mono tracking-tight text-white">{stat.value}</div>
                                <div className="flex items-center text-xs text-muted-foreground mt-1">
                                    <span className={stat.trend === 'up' || stat.color.includes('amber') ? stat.color : 'text-green-500'}>
                                        {stat.change}
                                    </span>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                ))}
            </div>

            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-7 flex-1 min-h-[500px]">

                {/* 2. COMMAND CENTER (Main Visual) - 4 Columns */}
                <div className="col-span-4 h-full min-h-[500px] rounded-xl overflow-hidden shadow-2xl border border-white/10 relative group">
                    <CommandCenter />
                </div>

                {/* 3. AUDIT LOG FEED - 3 Columns */}
                <Card className="col-span-3 backdrop-blur-sm bg-black/40 border border-white/10 h-full flex flex-col">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Activity className="w-4 h-4 text-emerald-500" />
                            <span>Live Audit Log</span>
                        </CardTitle>
                        <CardDescription>
                            Real-time verification stream from field assets.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="flex-1 overflow-auto pr-2">
                        <div className="space-y-1">
                            {[
                                { id: "MT-4021", status: "VERIFIED", msg: "Visual confirmation 100%", time: "Just now", color: "text-emerald-400" },
                                { id: "MT-4022", status: "FLAGGED", msg: "Vegetation encroachment detected", time: "2m ago", color: "text-amber-400" },
                                { id: "MT-4023", status: "VERIFIED", msg: "Structural integrity OK", time: "5m ago", color: "text-emerald-400" },
                                { id: "MT-4025", status: "VERIFIED", msg: "Insulator check passed", time: "12m ago", color: "text-emerald-400" },
                                { id: "MT-4028", status: "VERIFIED", msg: "Grounding wire visible", time: "15m ago", color: "text-emerald-400" },
                                { id: "MT-4030", status: "CRITICAL", msg: "Severe lean (>15 deg)", time: "22m ago", color: "text-red-500 animate-pulse" },
                                { id: "MT-3998", status: "VERIFIED", msg: "Standard audit complete", time: "28m ago", color: "text-emerald-400" },
                                { id: "MT-3992", status: "VERIFIED", msg: "Cross-arm check passed", time: "35m ago", color: "text-emerald-400" },
                            ].map((log, i) => (
                                <div key={i} className="flex items-center p-3 rounded-lg hover:bg-white/5 transition-colors border-b border-white/5 last:border-0">
                                    <div className={`h-8 w-8 rounded flex items-center justify-center text-[10px] font-mono font-bold bg-white/5 ${log.color}`}>
                                        {log.status.slice(0, 1)}
                                    </div>
                                    <div className="ml-3 space-y-0.5 flex-1">
                                        <div className="flex justify-between items-center">
                                            <p className="text-sm font-medium text-white font-mono">{log.id}</p>
                                            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded bg-white/5 ${log.color}`}>{log.status}</span>
                                        </div>
                                        <p className="text-xs text-muted-foreground">{log.msg}</p>
                                    </div>
                                    <div className="ml-3 text-[10px] text-gray-600 font-mono whitespace-nowrap">
                                        {log.time}
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
