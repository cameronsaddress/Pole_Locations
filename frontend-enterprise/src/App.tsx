import { BrowserRouter, Routes, Route } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import DashboardLayout from "./layouts/DashboardLayout"
import Dashboard from "./pages/Dashboard"
import LiveMap3D from "./pages/LiveMap3D"
import DataAssets from "./pages/DataAssets"
import Pipeline from "./pages/Pipeline" // Replaced Training
import Settings from "./pages/Settings"

const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<DashboardLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="map" element={<LiveMap3D />} />
            <Route path="data" element={<DataAssets />} />
            <Route path="training" element={<Pipeline />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
