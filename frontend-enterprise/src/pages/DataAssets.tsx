import { useState, useEffect } from "react"
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Download, Filter, MoreHorizontal, Search, Zap, Loader2, CheckCircle } from "lucide-react"
import { Progress } from "@/components/ui/progress"

interface Asset {
    id: string
    lat: number
    lng: number
    status: string
    confidence: number
    detected_at: string
}

interface RepairJob {
    status: string
    job_id: number
    meta: {
        total_targets: number
        processed: number
        fixed: number
    }
}

export default function DataAssets() {
    const [data, setData] = useState<Asset[]>([])
    const [searchTerm, setSearchTerm] = useState("")
    const [repairJob, setRepairJob] = useState<RepairJob | null>(null)

    const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`

    // Load Assets
    const loadAssets = () => {
        fetch(`${apiHost}/api/v2/assets`)
            .then(res => res.json())
            .then(data => setData(data))
            .catch(err => console.error("Failed to load assets:", err))
    }

    useEffect(() => {
        loadAssets()

        // Poll Job Status
        const interval = setInterval(() => {
            fetch(`${apiHost}/api/v2/ops/jobs/repair/status`)
                .then(res => res.json())
                .then(job => {
                    if (job.status !== 'idle') {
                        setRepairJob(job)
                        // If job just finished, reload assets
                        if (job.status === 'Completed' && repairJob?.status !== 'Completed') {
                            loadAssets()
                        }
                    } else {
                        setRepairJob(null)
                    }
                })
                .catch(console.error)
        }, 3000)
        return () => clearInterval(interval)
    }, [])

    const triggerRepair = () => {
        fetch(`${apiHost}/api/v2/ops/jobs/repair`, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                // Force an immediate poll or set local state
                setRepairJob({ status: 'Pending', job_id: data.job_id, meta: { total_targets: 0, processed: 0, fixed: 0 } })
            })
    }

    const filteredData = data.filter(item =>
        item.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.status.toLowerCase().includes(searchTerm.toLowerCase())
    )

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Geospatial Database</h2>
                    <p className="text-muted-foreground">Manage and audit detected utility poles (fused with FAA/PASDA/Lidar)</p>
                </div>
                <div className="flex gap-2">
                    {repairJob && repairJob.status !== 'idle' ? (
                        <Card className="w-[300px] border-cyan-500/50 bg-black/40 backdrop-blur">
                            <CardContent className="p-3 flex items-center gap-3">
                                {repairJob.status === 'Running' || repairJob.status === 'Pending' ? (
                                    <Loader2 className="w-5 h-5 text-cyan-400 animate-spin" />
                                ) : (
                                    <CheckCircle className="w-5 h-5 text-green-400" />
                                )}
                                <div className="flex-1">
                                    <div className="flex justify-between text-xs mb-1 font-mono text-cyan-200">
                                        <span>AI NETWORK REPAIR</span>
                                        <span>{repairJob.status.toUpperCase()}</span>
                                    </div>
                                    <div className="w-full bg-gray-700 h-1.5 rounded-full overflow-hidden">
                                        <div
                                            className="bg-cyan-500 h-full transition-all duration-500"
                                            style={{ width: `${(repairJob.meta.processed / Math.max(1, repairJob.meta.total_targets)) * 100}%` }}
                                        />
                                    </div>
                                    <div className="text-[10px] text-gray-400 mt-1 flex justify-between">
                                        <span>Processed: {repairJob.meta.processed}/{repairJob.meta.total_targets}</span>
                                        <span className="text-green-400">Fixed: {repairJob.meta.fixed}</span>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    ) : (
                        <Button onClick={triggerRepair} className="bg-cyan-600 hover:bg-cyan-500 text-white border border-cyan-400/30 shadow-lg shadow-cyan-500/20">
                            <Zap className="mr-2 h-4 w-4" />
                            Run AI Network Repair
                        </Button>
                    )}

                    <Button variant="outline">
                        <Download className="mr-2 h-4 w-4" />
                        Export CSV
                    </Button>
                    <Button>
                        <Filter className="mr-2 h-4 w-4" />
                        Advanced Filter
                    </Button>
                </div>
            </div>

            <Card className="backdrop-blur-sm bg-card/50 border-primary/10">
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <CardTitle>Asset Inventory</CardTitle>
                        <div className="relative w-72">
                            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                            <form onSubmit={(e) => e.preventDefault()}>
                                <input
                                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 pl-8"
                                    placeholder="Search ID or Status..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                />
                            </form>
                        </div>
                    </div>
                    <CardDescription>
                        Showing {filteredData.length} records from the geospatial database.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead className="w-[100px]">Asset ID</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Confidence</TableHead>
                                <TableHead>Location (Lat, Lng)</TableHead>
                                <TableHead>Detected At</TableHead>
                                <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {filteredData.slice(0, 100).map((item) => (
                                <TableRow key={item.id}>
                                    <TableCell className="font-medium font-mono text-cyan-400">{item.id}</TableCell>
                                    <TableCell>
                                        <Badge variant={
                                            item.status === 'Verified' ? 'default' :
                                                item.status === 'Review' ? 'secondary' :
                                                    item.status === 'Missing' ? 'outline' : 'destructive'
                                        } className={item.status === 'Missing' ? 'border-amber-500 text-amber-500' : ''}>
                                            {item.status}
                                        </Badge>
                                    </TableCell>
                                    <TableCell>
                                        <div className="flex items-center gap-2">
                                            <div className="h-2 w-16 bg-muted rounded-full overflow-hidden">
                                                <div
                                                    className={`h-full ${item.status === 'Missing' ? 'bg-amber-500' : 'bg-green-500'}`}
                                                    style={{ width: `${item.confidence * 100}%` }}
                                                />
                                            </div>
                                            <span className="text-xs">{item.confidence}</span>
                                        </div>
                                    </TableCell>
                                    <TableCell className="font-mono text-xs text-muted-foreground">
                                        {item.lat}, {item.lng}
                                    </TableCell>
                                    <TableCell className="text-muted-foreground">{new Date(item.detected_at).toLocaleString()}</TableCell>
                                    <TableCell className="text-right">
                                        <Button variant="ghost" size="icon">
                                            <MoreHorizontal className="h-4 w-4" />
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </div>
    )
}

