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
import { Download, Filter, MoreHorizontal, Search } from "lucide-react"

interface Asset {
    id: string
    lat: number
    lng: number
    status: string
    confidence: number
    detected_at: string
}

export default function DataAssets() {
    const [data, setData] = useState<Asset[]>([])
    const [searchTerm, setSearchTerm] = useState("")

    useEffect(() => {
        const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`
        fetch(`${apiHost}/api/v2/assets`)
            .then(res => res.json())
            .then(data => setData(data))
            .catch(err => console.error("Failed to load assets:", err))
    }, [])

    const filteredData = data.filter(item =>
        item.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.status.toLowerCase().includes(searchTerm.toLowerCase())
    )

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Geospatial Database</h2>
                    <p className="text-muted-foreground">Manage and audit detected utility poles</p>
                </div>
                <div className="flex gap-2">
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
                                                item.status === 'Review' ? 'secondary' : 'destructive'
                                        }>
                                            {item.status}
                                        </Badge>
                                    </TableCell>
                                    <TableCell>
                                        <div className="flex items-center gap-2">
                                            <div className="h-2 w-16 bg-muted rounded-full overflow-hidden">
                                                <div
                                                    className="h-full bg-green-500"
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
