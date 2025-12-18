
import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
// import { Shield, Server, Users, Key } from "lucide-react"

export default function Settings() {
    const [openRouterKey, setOpenRouterKey] = useState("")

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">System Settings</h2>
                    <p className="text-muted-foreground">Manage enterprise configuration and access controls</p>
                </div>
            </div>

            <Tabs defaultValue="general" className="w-full">
                <TabsList className="grid w-full grid-cols-4 bg-muted/20">
                    <TabsTrigger value="general">General</TabsTrigger>
                    <TabsTrigger value="integrations">Integrations</TabsTrigger>
                    <TabsTrigger value="security">Security</TabsTrigger>
                    <TabsTrigger value="api">API & Keys</TabsTrigger>
                </TabsList>

                {/* GENERAL TAB */}
                <TabsContent value="general" className="space-y-4 mt-6">
                    <Card className="bg-black/40 border-primary/10">
                        <CardHeader>
                            <CardTitle>Enterprise Profile</CardTitle>
                            <CardDescription>Main organization settings and thresholds.</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>Organization Name</Label>
                                    <Input defaultValue="Verizon / PPL Utility" className="bg-black/20" />
                                </div>
                                <div className="space-y-2">
                                    <Label>Primary Region</Label>
                                    <Input defaultValue="US-EAST-1 (Pennsylvania)" className="bg-black/20" />
                                </div>
                                <div className="space-y-2">
                                    <Label>Pilot County Code</Label>
                                    <Input defaultValue="PA-043 (Dauphin)" className="bg-black/20" />
                                </div>
                                <div className="space-y-2">
                                    <Label>Confidence Threshold (AI)</Label>
                                    <Input type="range" className="accent-emerald-500" defaultValue={85} />
                                    <div className="text-right text-xs text-emerald-500">85% Strict</div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* API TAB */}
                <TabsContent value="api" className="space-y-4 mt-6">
                    <Card className="bg-black/40 border-primary/10">
                        <CardHeader>
                            <CardTitle>API Access Tokens</CardTitle>
                            <CardDescription>Manage keys for internal and 3rd party integrations.</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            {/* Existing Internal Key (Read Only) */}
                            <div className="p-4 border border-white/5 rounded-lg flex justify-between items-center bg-white/5">
                                <div>
                                    <div className="font-mono text-sm text-emerald-400">sk-live-8d9f...4j2k</div>
                                    <div className="text-xs text-gray-500">Production Key • Active</div>
                                </div>
                                <Badge variant="outline" className="border-red-500 text-red-500 cursor-pointer hover:bg-red-500/10">Revoke</Badge>
                            </div>

                            {/* OpenRouter Key Input */}
                            <div className="space-y-2 pt-4 border-t border-white/10">
                                <Label>OpenRouter API Key (LLM Auto-Tuning)</Label>
                                <div className="flex gap-2">
                                    <Input
                                        type="password"
                                        placeholder="sk-or-v1-..."
                                        className="bg-black/20 font-mono text-xs"
                                        value={openRouterKey}
                                        onChange={(e) => {
                                            // Ideally verify format or store in state
                                            // For now we just mock the input interaction
                                            setOpenRouterKey(e.target.value);
                                        }}
                                    />
                                    <button
                                        className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-4 rounded whitespace-nowrap transition-colors"
                                        onClick={() => {
                                            // Mock send to backend
                                            alert("Securely encrypting and syncing OpenRouter key to backend vault...")
                                            console.log("Saving OpenRouter Key:", openRouterKey);
                                        }}
                                    >
                                        SAVE SECURELY
                                    </button>
                                </div>
                                <p className="text-[10px] text-gray-500">
                                    Required for Grok-4 hyperparameter optimization. Stored in AES-256 encrypted vault.
                                </p>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* SECURITY TAB */}
                <TabsContent value="security" className="space-y-4 mt-6">
                    <Card className="bg-black/40 border-primary/10">
                        <CardHeader>
                            <CardTitle>Access Control</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="flex items-center justify-between py-4 border-b border-white/10">
                                <div>
                                    <div className="font-medium text-white">SSO Enforcement</div>
                                    <div className="text-xs text-gray-400">Require SAML/Okta for all dashboard users</div>
                                </div>
                                <div className="w-10 h-6 bg-emerald-900 rounded-full relative">
                                    <div className="absolute right-1 top-1 w-4 h-4 bg-emerald-500 rounded-full"></div>
                                </div>
                            </div>
                            <div className="flex items-center justify-between py-4">
                                <div>
                                    <div className="font-medium text-white">Audit Log Retention</div>
                                    <div className="text-xs text-gray-400">Keep detailed access logs for compliance</div>
                                </div>
                                <select className="bg-black border border-white/20 text-xs rounded p-1">
                                    <option>7 Years (FCC Mandate)</option>
                                    <option>1 Year</option>
                                </select>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    )
}
