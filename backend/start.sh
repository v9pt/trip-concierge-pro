#!/bin/bash
echo "Starting Trip Concierge Pro Backend..."
python3 -m uvicorn server_pro:app --host 0.0.0.0 --port ${PORT:-8080}
