import { useState } from "react"
import { Outlet, Link, useLocation } from "react-router-dom"
import {
    LayoutDashboard,
    // import { Map } from 'lucide-react'
    Database,
    Settings,
    Menu,
    Server,
    Activity,
    Disc,
    Target
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

const sidebarItems = [
    { icon: LayoutDashboard, label: "Overview", path: "/" },
    { icon: Activity, label: "Live Map", path: "/map" },
    { icon: Database, label: "Data Assets", path: "/data" },
    { icon: Disc, label: "Pipeline", path: "/training" },
    { icon: Target, label: "Mn. Annotation", path: "/annotation" },
    { icon: Settings, label: "Settings", path: "/settings" },
]

export default function DashboardLayout() {
    const [collapsed, setCollapsed] = useState(false)
    const location = useLocation()

    return (
        <div className="flex h-screen w-full bg-background text-foreground overflow-hidden">
            {/* Glass Sidebar */}
            <aside
                className={cn(
                    "relative z-20 h-full flex-col border-r border-border/40 bg-background/50 backdrop-blur-xl transition-all duration-300 ease-in-out",
                    collapsed ? "w-16" : "w-64"
                )}
            >
                <div className="flex h-16 items-center border-b border-border/40 px-4 backdrop-blur-sm">
                    <Server className="h-6 w-6 text-primary animate-pulse" />
                    {!collapsed && (
                        <span className="ml-3 text-lg font-bold tracking-tight bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
                            PoleVision
                        </span>
                    )}
                </div>

                <nav className="flex-1 space-y-1 p-2">
                    {sidebarItems.map((item) => {
                        const isActive = location.pathname === item.path
                        return (
                            <Link
                                key={item.path}
                                to={item.path}
                                className={cn(
                                    "flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent/50 hover:text-accent-foreground",
                                    isActive ? "bg-accent/80 text-accent-foreground shadow-glow" : "text-muted-foreground"
                                )}
                            >
                                <item.icon className={cn("h-5 w-5", isActive ? "text-primary" : "")} />
                                {!collapsed && <span className="ml-3">{item.label}</span>}
                            </Link>
                        )
                    })}
                </nav>

                <div className="p-2 border-t border-border/40">
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setCollapsed(!collapsed)}
                        className="w-full justify-center"
                    >
                        <Menu className="h-4 w-4" />
                    </Button>
                </div>
            </aside>

            {/* Main Content */}
            <main className="relative flex-1 flex flex-col overflow-hidden bg-gradient-to-br from-background via-slate-900/10 to-slate-950/20">
                {/* Top Header */}
                <header className="flex h-16 items-center justify-between border-b border-border/40 bg-background/30 px-6 backdrop-blur-md">
                    <h1 className="text-xl font-semibold tracking-tight">
                        {sidebarItems.find(i => i.path === location.pathname)?.label || "Dashboard"}
                    </h1>
                    <div className="flex items-center space-x-4">
                        <div className="flex items-center space-x-2">
                            <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                            <span className="text-xs text-muted-foreground font-mono">SYSTEM ONLINE</span>
                        </div>
                        <Button variant="outline" size="sm" className="hidden md:flex">
                            Export Report
                        </Button>
                    </div>
                </header>

                <div className="flex-1 overflow-auto p-6 scrollbar-hide">
                    <Outlet />
                </div>
            </main>
        </div>
    )
}
