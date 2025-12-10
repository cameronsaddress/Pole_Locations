import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { CheckCircle, AlertTriangle, Zap, DollarSign, Activity, FileText } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import CommandCenter from "../components/CommandCenter"

interface OpsMetrics {
    total_assets: number
    grid_integrity: number
    daily_audit_count: number
    critical_anomalies: number
    preventative_savings: number
}

interface Asset {
    id: string
    status: string
    issues: string[]
    detected_at: string
}

export default function Dashboard() {
    const [opsMetrics, setOpsMetrics] = useState<OpsMetrics | null>(null)
    const [auditLog, setAuditLog] = useState<Asset[]>([])

    // 1. Fetch Real Data
    useEffect(() => {
        const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`

        fetch(`${apiHost}/api/v2/ops/metrics`)
            .then(res => res.json())
            .then(data => setOpsMetrics(data))
            .catch(err => console.error("Metrics Error:", err))

        fetch(`${apiHost}/api/v2/ops/audit-log`)
            .then(res => res.json())
            .then(data => setAuditLog(data))
            .catch(err => console.error("Audit Log Error:", err))
    }, [])

    const formatCurrency = (val: number) => {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val)
    }

    return (
        <div className="space-y-6 h-full flex flex-col">

            {/* 1. EXECUTIVE METRICS ROW (REAL DATA) */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">

                {/* Total Assets */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0 }}>
                    <Card className="backdrop-blur-sm bg-black/40 border border-blue-500/20 shadow-lg hover:bg-white/5 transition-all duration-300">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium text-gray-400 font-mono tracking-wider">TOTAL ASSETS</CardTitle>
                            <FileText className="h-4 w-4 text-blue-500" />
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold font-mono tracking-tight text-white">
                                {opsMetrics?.total_assets.toLocaleString() || "..."}
                            </div>
                            <div className="text-xs text-blue-500 mt-1">Live Database</div>
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Grid Health */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
                    <Card className="backdrop-blur-sm bg-black/40 border border-emerald-500/20 shadow-lg hover:bg-white/5 transition-all duration-300">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium text-gray-400 font-mono tracking-wider">GRID HEALTH</CardTitle>
                            <Zap className="h-4 w-4 text-emerald-500" />
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold font-mono tracking-tight text-white">
                                {opsMetrics?.grid_integrity || "..."}%
                            </div>
                            <div className="text-xs text-emerald-500 mt-1">Operational</div>
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Critical Anomalies */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
                    <Card className="backdrop-blur-sm bg-black/40 border border-amber-500/50 shadow-lg hover:bg-white/5 transition-all duration-300">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium text-gray-400 font-mono tracking-wider">CRITICAL ANOMALIES</CardTitle>
                            <AlertTriangle className="h-4 w-4 text-amber-500" />
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold font-mono tracking-tight text-amber-500 animate-pulse">
                                {opsMetrics?.critical_anomalies || 0}
                            </div>
                            <div className="text-xs text-amber-500 mt-1">Requires Action</div>
                        </CardContent>
                    </Card>
                </motion.div>

                {/* Savings */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
                    <Card className="backdrop-blur-sm bg-black/40 border border-green-500/20 shadow-lg hover:bg-white/5 transition-all duration-300">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium text-gray-400 font-mono tracking-wider">PREVENTATIVE ROI</CardTitle>
                            <DollarSign className="h-4 w-4 text-green-400" />
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold font-mono tracking-tight text-white">
                                {opsMetrics ? formatCurrency(opsMetrics.preventative_savings) : "..."}
                            </div>
                            <div className="text-xs text-green-400 mt-1">Projected Savings</div>
                        </CardContent>
                    </Card>
                </motion.div>

            </div>

            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-7 flex-1 min-h-[500px]">

                {/* 2. COMMAND CENTER (Main Visual) - 4 Columns */}
                <div className="col-span-4 h-full min-h-[500px] rounded-xl overflow-hidden shadow-2xl border border-white/10 relative group">
                    <CommandCenter />
                </div>

                {/* 3. AUDIT LOG FEED (REAL DATA) - 3 Columns */}
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
                            {auditLog.map((log, i) => {
                                const isCritical = log.status === "Critical"
                                const isFlagged = log.status === "Flagged"
                                const color = isCritical ? "text-red-500 animate-pulse" : isFlagged ? "text-amber-400" : "text-emerald-400"
                                const statusChar = isCritical ? "C" : isFlagged ? "F" : "V"

                                return (
                                    <div key={i} className="flex items-center p-3 rounded-lg hover:bg-white/5 transition-colors border-b border-white/5 last:border-0">
                                        <div className={`h-8 w-8 rounded flex items-center justify-center text-[10px] font-mono font-bold bg-white/5 ${color}`}>
                                            {statusChar}
                                        </div>
                                        <div className="ml-3 space-y-0.5 flex-1">
                                            <div className="flex justify-between items-center">
                                                <p className="text-sm font-medium text-white font-mono">{log.id}</p>
                                                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded bg-white/5 ${color}`}>{log.status.toUpperCase()}</span>
                                            </div>
                                            <p className="text-xs text-muted-foreground truncate max-w-[200px]">
                                                {log.issues.length > 0 ? log.issues.join(", ") : "Audit Passed: Structural Integrity OK"}
                                            </p>
                                        </div>
                                        <div className="ml-3 text-[10px] text-gray-600 font-mono whitespace-nowrap">
                                            {new Date(log.detected_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
