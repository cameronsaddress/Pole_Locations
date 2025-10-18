#!/bin/bash

# PoleVision AI - Enterprise Dashboard Startup Script

echo "🚀 Starting PoleVision AI Enterprise Dashboard..."
echo ""

# Start FastAPI Backend
echo "📡 Starting FastAPI backend on port 8000..."
cd backend
python3 -m app.main &
BACKEND_PID=$!
cd ..

# Wait for backend to start
sleep 3

# Install frontend dependencies if needed
if [ ! -d "frontend/node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    cd frontend
    npm install
    cd ..
fi

# Start React Frontend
echo "🎨 Starting React frontend on port 5173..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ PoleVision AI Dashboard is starting!"
echo ""
echo "📊 Backend API:  http://localhost:8000"
echo "📚 API Docs:     http://localhost:8000/api/docs"
echo "🎨 Dashboard:    http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for user interrupt
wait
