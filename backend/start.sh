#!/bin/bash
pip install -r requirements.txt
uvicorn server_pro:app --host 0.0.0.0 --port $PORT
