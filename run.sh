#!/bin/bash

# Kill background processes on exit
trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT

# Skip PaddleOCR slow connectivity check
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

# Conda env python path
# CONDA_PYTHON="/home/tms/miniconda3/envs/comparedocs/bin/python3"

# Start Backend first
echo "Starting Backend on port 8005 (conda: comparedocs)..."
cd backend
# $CONDA_PYTHON -m uvicorn main:app --reload --port 8005 &
uv run main.py &
BACKEND_PID=$!
cd ..

# Wait for backend to be ready before starting frontend
echo "Waiting for backend to be ready..."
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:8005/api/stats > /dev/null 2>&1; then
        echo "Backend is ready!"
        break
    fi
    sleep 1
done

# Start Frontend
echo "Starting Frontend on port 5175..."
cd frontend
npm run dev -- --port 5175 &
FRONTEND_PID=$!
cd ..

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
