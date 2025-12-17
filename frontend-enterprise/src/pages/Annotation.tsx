
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
        let interval: NodeJS.Timeout;
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

    const handleImageClick = async (e: React.MouseEvent<HTMLImageElement>) => {
        if (!currentImage || !imageRef.current) return;

        const rect = imageRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        // Normalize
        const normX = x / rect.width;
        const normY = y / rect.height;

        const box = { x: normX, y: normY, w: 0.1, h: 0.85 };

        // Save
        await fetch(`${apiHost}/api/v2/annotation/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image_id: currentImage.image_id,
                box: box,
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
                    <p className="text-gray-400">One-Shot Human Verification Loop.</p>
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
                        <CardTitle>Current Tile: {currentImage?.filename}</CardTitle>
                    </CardHeader>
                    <CardContent className="flex justify-center p-6 bg-black">
                        {isLoading ? (
                            <div className="text-white animate-pulse">Loading Next Tile...</div>
                        ) : currentImage ? (
                            <div className="relative group cursor-crosshair">
                                <img
                                    ref={imageRef}
                                    src={`${apiHost}${currentImage.image_url}`}
                                    alt="Annotation Target"
                                    onClick={handleImageClick}
                                    className="max-h-[600px] object-contain border border-gray-700"
                                />
                                <div className="absolute top-2 right-2 bg-black/50 px-2 py-1 text-xs rounded text-white pointer-events-none">
                                    Click center of pole to save & next
                                </div>
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
                            <Button variant="destructive" className="w-full" onClick={handleSkip}>
                                <SkipForward className="mr-2 h-4 w-4" /> Skip (Unclear/No Pole)
                            </Button>

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
                                    ✨ AI Annotate (Gemini)
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
                                    <li>Click on center of pole (Manual).</li>
                                    <li>Or click <strong>AI Annotate</strong> for auto-detection.</li>
                                    <li>Use <strong>Skip</strong> if unclear.</li>
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
