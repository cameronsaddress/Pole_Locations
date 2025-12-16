import { useState, useMemo } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Search, MapPin, Database, CheckCircle, AlertCircle } from "lucide-react"

// Types matching Backend
interface Region {
    id: string
    name: string
    status: 'available' | 'supported' | 'mining' | 'missing'
}

interface DatasetMap {
    [state: string]: Region[]
}

interface RegionPickerProps {
    mode: 'mining' | 'targets'
    datasets: DatasetMap
    selected: string[]
    onSelectionChange: (selected: string[]) => void
    triggerText?: string
    disabled?: boolean
}

export function RegionPickerModal({ mode, datasets, selected, onSelectionChange, triggerText, disabled }: RegionPickerProps) {
    const [open, setOpen] = useState(false)
    const [search, setSearch] = useState("")

    // Filter Logic
    // If Mode == 'mining': Show ALL regions (supported, available, mining)
    // If Mode == 'targets': Show ONLY 'available' regions
    const filteredDatasets = useMemo(() => {
        const filtered: DatasetMap = {}

        Object.keys(datasets).forEach(state => {
            const regions = datasets[state].filter(r => {
                const matchesSearch = r.name.toLowerCase().includes(search.toLowerCase()) || state.toLowerCase().includes(search.toLowerCase())
                const matchesMode = mode === 'mining' ? true : r.status === 'available'
                return matchesSearch && matchesMode
            })

            if (regions.length > 0) {
                filtered[state] = regions
            }
        })
        return filtered
    }, [datasets, search, mode])

    const toggle = (id: string) => {
        if (selected.includes(id)) {
            onSelectionChange(selected.filter(s => s !== id))
        } else {
            onSelectionChange([...selected, id])
        }
    }

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'available': return 'text-green-400 border-green-900 bg-green-950/30'
            case 'supported': return 'text-gray-400 border-gray-800 bg-gray-900/30'
            case 'mining': return 'text-amber-400 border-amber-900 bg-amber-950/30'
            default: return 'text-gray-600'
        }
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" disabled={disabled} className={`justify-between w-full md:w-auto min-w-[200px] border-dashed ${disabled ? 'opacity-50' : ''}`}>
                    <span className="flex items-center">
                        {mode === 'mining' ? <Search className="w-4 h-4 mr-2" /> : <Database className="w-4 h-4 mr-2" />}
                        {triggerText || (selected.length > 0 ? `${selected.length} Selected` : "Select Regions...")}
                    </span>
                    {selected.length > 0 && <Badge className="ml-2 bg-primary text-primary-foreground">{selected.length}</Badge>}
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-4xl bg-black/90 border-gray-800 text-white max-h-[80vh] overflow-hidden flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-xl">
                        {mode === 'mining' ? <MapPin className="text-pink-500" /> : <Database className="text-cyan-500" />}
                        {mode === 'mining' ? "Select Mining Targets" : "Select Dataset Targets"}
                    </DialogTitle>
                </DialogHeader>

                {/* Search Bar */}
                <div className="relative mb-4">
                    <Search className="absolute left-3 top-3 h-4 w-4 text-gray-500" />
                    <input
                        className="w-full bg-gray-900 border border-gray-700 rounded-md py-2 pl-10 pr-4 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-primary"
                        placeholder="Search states (e.g. Washington) or counties..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>

                {/* Grid */}
                <div className="flex-1 overflow-y-auto pr-2 space-y-6">
                    {Object.keys(filteredDatasets).length === 0 ? (
                        <div className="text-center py-10 text-gray-500 flex flex-col items-center">
                            <AlertCircle className="w-10 h-10 mb-4 opacity-20" />
                            <p>No matching regions found.</p>
                            {mode === 'targets' && <p className="text-xs mt-2">Try switching to Mining mode to create new datasets.</p>}
                        </div>
                    ) : (
                        Object.keys(filteredDatasets).map(state => (
                            <div key={state} className="space-y-3">
                                <h4 className="text-sm font-bold text-gray-400 uppercase tracking-widest border-b border-gray-800 pb-1">{state}</h4>
                                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                                    {filteredDatasets[state].map(region => (
                                        <div
                                            key={region.id}
                                            onClick={() => toggle(region.id)}
                                            className={`
                                                cursor-pointer p-3 rounded border text-sm flex flex-col justify-between h-24 transition-all
                                                ${selected.includes(region.id)
                                                    ? 'border-primary bg-primary/10 shadow-[0_0_10px_rgba(0,0,0,0.5)]'
                                                    : 'border-gray-800 bg-gray-900/40 hover:bg-gray-800 hover:border-gray-600'}
                                            `}
                                        >
                                            <span className="font-semibold truncate" title={region.name}>{region.name}</span>
                                            <div className="flex justify-between items-center mt-2">
                                                <Badge variant="outline" className={`text-[10px] px-1 py-0 h-4 border ${getStatusColor(region.status)}`}>
                                                    {region.status.toUpperCase()}
                                                </Badge>
                                                {selected.includes(region.id) && <CheckCircle className="w-4 h-4 text-green-400" />}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ))
                    )}
                </div>

                {/* Footer Actions */}
                <div className="pt-4 border-t border-gray-800 flex justify-end gap-2">
                    <Button variant="ghost" onClick={() => onSelectionChange([])}>Clear All</Button>
                    <Button onClick={() => setOpen(false)}>Done</Button>
                </div>
            </DialogContent>
        </Dialog>
    )
}
