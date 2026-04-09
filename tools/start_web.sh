#!/bin/bash
# KP Jyotish — Bloomberg-style web UI
# Usage: bash tools/start_web.sh
set -e
cd "$(dirname "$0")"

echo "Installing dependencies..."
pip install -r requirements.txt -q

echo "Starting KP Jyotish server on http://localhost:8501"
uvicorn api:app --host 0.0.0.0 --port 8501 --reload
