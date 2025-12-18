
import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Target, SkipForward, Save, Archive, Trash2 } from 'lucide-react';

interface AnnotationStats {
    count: number;
    target: number;
    phase_target: number;
    pending: number;
    skipped: number;
}

const Annotation = () => {
    const [stats, setStats] = useState<AnnotationStats | null>(null);
    const [currentImage, setCurrentImage] = useState<any>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [message, setMessage] = useState("");
    const [isPopulating, setIsPopulating] = useState(false);
    const [dataset, setDataset] = useState<"street" | "satellite">("street");

    // AI State
    const [isAIProcessing, setIsAIProcessing] = useState(false);
    const [aiLogs, setAiLogs] = useState<string[]>([]);

    // Canvas ref for click coordinates
    const imageRef = useRef<HTMLImageElement>(null);

    const apiHost = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;

    const fetchStats = async () => {
        try {
            const res = await fetch(`${apiHost}/api/v2/annotation/stats?dataset=${dataset}`);
            const data = await res.json();
            setStats(data);
            return data;
        } catch (e) {
            console.error("Failed to fetch stats", e);
            return null;
        }
    };

    // Polling Effect for Populating
    useEffect(() => {
        let interval: any;
        if (isPopulating) {
            interval = setInterval(async () => {
                const s = await fetchStats();
                // If we have pending images and no current image, grab one!
                if (s && s.pending > 0 && !currentImage && !isLoading) {
                    fetchNext();
                }
            }, 1000);
        }
        return () => clearInterval(interval);
    }, [isPopulating, currentImage, isLoading, dataset]);

    const fetchNext = async () => {
        setIsLoading(true);
        setMessage("");
        try {
            const res = await fetch(`${apiHost}/api/v2/annotation/next?dataset=${dataset}`);
            const data = await res.json();
            if (data.status === 'complete') {
                setMessage("All valid images annotated! Great job.");
                setCurrentImage(null);
            } else {
                setCurrentImage(data);
            }
        } catch (e) {
            console.error(e);
            setMessage("Error fetching image.");
        } finally {
            setIsLoading(false);
            fetchStats();
        }
    };

    useEffect(() => {
        fetchNext();
    }, [dataset]);

    // Annotations State (Top-Left X/Y, W/H)
    const [annotations, setAnnotations] = useState<Array<{ x: number, y: number, w: number, h: number }>>([]);
    const [dragStart, setDragStart] = useState<{ x: number, y: number } | null>(null);
    const [currentDrag, setCurrentDrag] = useState<{ x: number, y: number, w: number, h: number } | null>(null);

    // Reset when image changes
    useEffect(() => {
        setAnnotations([]);
        setDragStart(null);
        setCurrentDrag(null);
    }, [currentImage]);

    const getNormCoords = (e: React.MouseEvent) => {
        if (!imageRef.current) return null;
        const rect = imageRef.current.getBoundingClientRect();
        return {
            x: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
            y: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height))
        };
    };

    const handleMouseDown = (e: React.MouseEvent) => {
        const coords = getNormCoords(e);
        if (coords) setDragStart(coords);
    };

    const handleMouseMove = (e: React.MouseEvent) => {
        if (!dragStart) return;
        const coords = getNormCoords(e);
        if (!coords) return;

        const x = Math.min(dragStart.x, coords.x);
        const y = Math.min(dragStart.y, coords.y);
        const w = Math.abs(dragStart.x - coords.x);
        const h = Math.abs(dragStart.y - coords.y);

        setCurrentDrag({ x, y, w, h });
    };

    const handleMouseUp = (e: React.MouseEvent) => {
        if (!dragStart) return;
        const coords = getNormCoords(e); // Needed for click detection

        // Config based on dataset
        const isSat = dataset === 'satellite';

        let newBox;
        // Click Detection (Tiny Drag)
        if (!currentDrag || (currentDrag.w < 0.005 && currentDrag.h < 0.005)) {
            // Create default small box centered on click
            const w = 0.02;
            const h = isSat ? 0.02 : 0.06; // Taller defaults for Street View
            newBox = {
                x: dragStart.x - (w / 2),
                y: dragStart.y - (h / 2),
                w, h
            };
        } else {
            newBox = currentDrag;
        }

        setAnnotations(prev => [...prev, newBox]);
        setDragStart(null);
        setCurrentDrag(null);
    };

    const handleUndo = () => {
        setAnnotations(prev => prev.slice(0, -1));
    };

    const handleSave = async () => {
        if (!currentImage) return;

        // Convert TopLeft-WH to Center-XY-WH for YOLO
        const boxes = annotations.map(a => ({
            x: a.x + (a.w / 2),
            y: a.y + (a.h / 2),
            w: a.w,
            h: a.h
        }));

        await fetch(`${apiHost}/api/v2/annotation/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image_id: currentImage.image_id,
                boxes: boxes,
                phase: 1,
                dataset
            })
        });

        fetchNext();
    };

    const handleSkip = async () => {
        if (!currentImage) return;
        await fetch(`${apiHost}/api/v2/annotation/skip`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_id: currentImage.image_id, dataset })
        });
        fetchNext();
    };

    return (
        <div className="p-8 max-w-7xl mx-auto space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Manual Annotation</h1>
                    <p className="text-gray-400">Multi-Select Mode: Click all poles, then Submit.</p>
                    <div className="flex gap-4 mt-2 text-sm font-mono">
                        <span className="text-blue-400">Pending: {stats?.pending || 0}</span>
                        <span className="text-gray-500">Skipped: {stats?.skipped || 0}</span>
                    </div>
                </div>
                {/* Dataset Toggle */}
                <div className="flex gap-2">
                    <Button
                        variant={dataset === "street" ? "default" : "secondary"}
                        onClick={() => setDataset("street")}
                        className="text-xs"
                    >
                        Street
                    </Button>
                    <Button
                        variant={dataset === "satellite" ? "default" : "secondary"}
                        onClick={() => setDataset("satellite")}
                        className="text-xs"
                    >
                        Satellite
                    </Button>
                </div>
                <div className="text-right">
                    <p className="text-2xl font-mono text-green-400">{stats?.count || 0} / {stats?.phase_target || 500}</p>
                    <div className="w-64 h-2 bg-gray-700 rounded-full mt-2">
                        <div className="h-full bg-green-500 rounded-full transition-all" style={{ width: `${Math.min(100, (stats ? (stats.count / stats.phase_target) * 100 : 0))}%` }}></div>
                    </div>
                </div>
            </div>

            {message && (
                <Alert>
                    <Target className="h-4 w-4" />
                    <AlertTitle>System Status</AlertTitle>
                    <AlertDescription>{message}</AlertDescription>
                </Alert>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Main Canvas */}
                <Card className="lg:col-span-2 bg-gray-900 border-gray-800">
                    <CardHeader>
                        <CardTitle className="flex justify-between">
                            <span>Tile: {currentImage?.filename}</span>
                            <span className="text-sm font-mono text-yellow-400">{annotations.length} Selected</span>
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="flex justify-center p-6 bg-black">
                        {isLoading ? (
                            <div className="text-white animate-pulse">Loading Next Tile...</div>
                        ) : currentImage ? (
                            <div
                                className="relative group inline-block select-none"
                                onMouseDown={handleMouseDown}
                                onMouseMove={handleMouseMove}
                                onMouseUp={handleMouseUp}
                                onMouseLeave={() => { setDragStart(null); setCurrentDrag(null); }}
                            >
                                <img
                                    ref={imageRef}
                                    src={`${apiHost}${currentImage.image_url}&t=${Date.now()}`}
                                    alt="Annotation Target"
                                    className="max-h-[600px] object-contain border border-gray-700 cursor-crosshair"
                                    draggable={false}
                                />
                                {/* Render Boxes */}
                                {annotations.map((box, i) => (
                                    <div
                                        key={i}
                                        className="absolute border-2 border-green-500 bg-green-500/20"
                                        style={{
                                            left: `${box.x * 100}%`,
                                            top: `${box.y * 100}%`,
                                            width: `${box.w * 100}%`,
                                            height: `${box.h * 100}%`
                                        }}
                                    />
                                ))}
                                {/* Drag Preview */}
                                {currentDrag && (
                                    <div
                                        className="absolute border-2 border-yellow-400 bg-yellow-400/20"
                                        style={{
                                            left: `${currentDrag.x * 100}%`,
                                            top: `${currentDrag.y * 100}%`,
                                            width: `${currentDrag.w * 100}%`,
                                            height: `${currentDrag.h * 100}%`
                                        }}
                                    />
                                )}
                            </div>
                        ) : (
                            <div className="text-gray-500">No image loaded.</div>
                        )}
                    </CardContent>
                </Card>

                {/* Controls */}
                <div className="space-y-4">
                    <Card className="bg-gray-900 border-gray-800">
                        <CardHeader><CardTitle>Controls</CardTitle></CardHeader>
                        <CardContent className="space-y-4">

                            {/* Primary Action */}
                            <Button
                                className="w-full bg-green-600 hover:bg-green-700 text-white font-bold h-12 text-lg"
                                onClick={handleSave}
                                disabled={annotations.length === 0}
                            >
                                <Save className="mr-2 h-5 w-5" /> Submit ({annotations.length})
                            </Button>

                            <div className="grid grid-cols-2 gap-2">
                                <Button variant="secondary" onClick={handleUndo} disabled={annotations.length === 0}>
                                    Undo Last
                                </Button>
                                <Button variant="destructive" onClick={handleSkip}>
                                    <SkipForward className="mr-2 h-4 w-4" /> Skip
                                </Button>
                            </div>

                            {/* AI Console */}
                            {isAIProcessing && (
                                <div className="p-3 bg-black rounded border border-green-900 font-mono text-[10px] text-green-400 h-32 overflow-y-auto" ref={(el) => { if (el) el.scrollTop = el.scrollHeight }}>
                                    <div className="border-b border-green-900 pb-1 mb-1 flex items-center gap-2">
                                        <span className="animate-pulse text-green-500">●</span> GEMINI 2.0 AGENT
                                    </div>
                                    {aiLogs.map((log, i) => (
                                        <div key={i} className="whitespace-nowrap">{`> ${log}`}</div>
                                    ))}
                                </div>
                            )}

                            <div className="pt-4 border-t border-gray-800 space-y-3">
                                <Button
                                    className="w-full bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white shadow-lg border-0"
                                    disabled={isAIProcessing || !currentImage}
                                    onClick={async () => {
                                        if (!currentImage) return;
                                        setIsAIProcessing(true);
                                        setAiLogs([]);

                                        try {
                                            const response = await fetch(`${apiHost}/api/v2/annotation/llm-stream?image_id=${currentImage.image_id}&dataset=${dataset}`);
                                            const reader = response.body?.getReader();
                                            const decoder = new TextDecoder();
                                            if (!reader) throw new Error("No reader");

                                            while (true) {
                                                const { value, done } = await reader.read();
                                                if (done) break;
                                                const chunk = decoder.decode(value);
                                                const lines = chunk.split("\n");
                                                for (const line of lines) {
                                                    if (!line.trim()) continue;
                                                    try {
                                                        const msg = JSON.parse(line);
                                                        if (msg.log) setAiLogs(prev => [...prev, msg.log]);
                                                        if (msg.error) setAiLogs(prev => [...prev, `❌ ${msg.error}`]);
                                                        if (msg.action === "saved" || msg.action === "skipped") {
                                                            setTimeout(() => { setIsAIProcessing(false); fetchNext(); }, 1500);
                                                        }
                                                    } catch (e) { }
                                                }
                                            }
                                        } catch (e) {
                                            setAiLogs(prev => [...prev, `ERR: ${e}`]);
                                            setIsAIProcessing(false);
                                        }
                                    }}
                                >
                                    ✨ AI Annotate (Gemini 2.5)
                                </Button>

                                <div className="grid grid-cols-2 gap-2">
                                    <Button variant="outline" className="w-full text-xs" disabled={isPopulating} onClick={async () => {
                                        setMessage("Starting Download Background Job...");
                                        setIsPopulating(true);
                                        await fetch(`${apiHost}/api/v2/annotation/populate`, {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ dataset })
                                        });
                                        setTimeout(() => setIsPopulating(false), 60000);
                                    }}>
                                        <Archive className={`mr-2 h-3 w-3 ${isPopulating ? 'animate-spin' : ''}`} />
                                        {isPopulating ? 'Mining...' : 'Populate Feed'}
                                    </Button>
                                    <Button variant="outline" className="w-full text-xs text-red-400 hover:text-red-300" onClick={async () => {
                                        if (!confirm("Clear all un-labeled images?")) return;
                                        await fetch(`${apiHost}/api/v2/annotation/clear`, {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ dataset })
                                        });
                                        setCurrentImage(null);
                                        setStats(null);
                                        fetchNext();
                                    }}>
                                        <Trash2 className="mr-2 h-3 w-3" /> Clear Pending
                                    </Button>
                                </div>
                            </div>

                            <div className="text-xs text-gray-500 mt-2">
                                <p className="font-bold">Instructions:</p>
                                <ul className="list-disc list-inside space-y-1 mt-2">
                                    <li><strong>Click & Drag</strong> to box poles.</li>
                                    <li>Click once for a standard box. (Tall for street, square for sat).</li>
                                    <li>Submit to save detections.</li>
                                </ul>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
};

export default Annotation;
