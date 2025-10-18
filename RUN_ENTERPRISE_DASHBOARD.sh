#!/bin/bash

echo "🚀 Starting PoleVision AI Enterprise Dashboard"
echo "=============================================="
echo ""

# Kill any existing processes
pkill -f "uvicorn" 2>/dev/null
pkill -f "vite" 2>/dev/null
sleep 1

# Activate venv
source venv/bin/activate

# Start FastAPI backend on port 9000
echo "📡 Starting FastAPI backend on port 9000..."
cd backend
python3 -m app.main > ../api.log 2>&1 &
BACKEND_PID=$!
cd ..
echo "   Backend PID: $BACKEND_PID"
sleep 3

# Check if backend started
if curl -s http://localhost:9000/ > /dev/null 2>&1; then
    echo "   ✅ Backend is running!"
else
    echo "   ❌ Backend failed to start. Check api.log"
fi

# Install frontend dependencies if needed
if [ ! -d "frontend/node_modules" ]; then
    echo ""
    echo "📦 Installing frontend dependencies (this may take a minute)..."
    cd frontend
    npm install --silent
    cd ..
fi

# Start React frontend on port 3000
echo ""
echo "🎨 Starting React frontend on port 3000..."
cd frontend
npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..
echo "   Frontend PID: $FRONTEND_PID"

sleep 3

echo ""
echo "=============================================="
echo "✅ PoleVision AI Dashboard is LIVE!"
echo "=============================================="
echo ""
echo "📊 Backend API:  http://localhost:9000"
echo "📚 API Docs:     http://localhost:9000/api/docs"
echo "🎨 Dashboard:    http://localhost:3000"
echo ""
echo "Logs:"
echo "  Backend:  tail -f api.log"
echo "  Frontend: tail -f frontend.log"
echo ""
echo "To stop: pkill -f uvicorn && pkill -f vite"
echo ""
