# server_pro.py (fixed)
import os
import re
import json
import random
import logging
from typing import List, Dict, Any, Optional

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pymongo import MongoClient
from bson.objectid import ObjectId

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("trip-concierge-pro")

# ---------------------
# CONFIG
# ---------------------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MONGO_URL = os.getenv("MONGO_URL")  # optional, if you want DB support
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

if not OPENROUTER_API_KEY:
    raise Exception("OPENROUTER_API_KEY missing in environment (.env)")

# ---------------------
# MONGO (Railway safe)
# ---------------------
mongo_client = None
db = None

if MONGO_URL:
    try:
        mongo_client = MongoClient(
            MONGO_URL,
            serverSelectionTimeoutMS=15000,
        )
        db = mongo_client.get_database("trip_concierge")
        mongo_client.admin.command("ping")
        log.info("✅ MongoDB connected (Railway)")
    except Exception as e:
        log.error("❌ MongoDB disabled: %s", e)
        db = None
else:
    log.warning("⚠️ No MONGO_URL provided — DB disabled.")


# ---------------------
# HELPERS
# ---------------------
IMAGE_SIG_MAX = 9999999


def extract_markdown_images(text: str) -> List[str]:
    """Extract image URLs from markdown like ![](url)."""
    return re.findall(r'!\[.*?\]\((.*?)\)', text or "")


def clean_markdown_images(text: str) -> str:
    """Return text with markdown image tags removed."""
    return re.sub(r'!\[.*?\]\(.*?\)', '', text or '').strip()


def get_unsplash_image(place: str) -> str:
    """Return a cache-busted Unsplash source url for 'place'."""
    if not place:
        place = "travel"
    sig = random.randint(1, IMAGE_SIG_MAX)
    return f"https://source.unsplash.com/900x600/?{place.replace(' ', '%20')}&sig={sig}"


def extract_places(text: str) -> List[str]:
    """
    Extract capitalized proper-noun-like phrases.
    This is imperfect but fine for generating Unsplash queries.
    """
    if not text:
        return []
    raw = re.findall(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,3})\b', text)
    blacklist = {
        "Summary", "Options", "Best", "Quick", "Here", "Morning", "Evening",
        "Night", "Cost", "Who", "Ideal", "Plan", "Day", "You", "Your", "Trip",
        "I", "The", "A"
    }
    places = [p for p in raw if p not in blacklist and len(p) > 2]
    # preserve order & dedupe
    seen = set()
    out = []
    for p in places:
        if p not in seen:
            seen.add(p)
            out.append(p)
        if len(out) >= 6:
            break
    return out


SYSTEM_PROMPT = """
You are Trip Concierge Pro — friendly, concise, and helpful.
When responding:
 - Provide a short Summary line.
 - Offer 3 clear options (timing, cost, who will enjoy).
 - When possible include markdown image tags e.g. ![](https://...)
 - Ask one short follow-up question if it helps.
"""

DEFAULT_ITINERARY = "No itinerary uploaded yet."

# ---------------------
# FASTAPI
# ---------------------
app = FastAPI(title="Trip Concierge PRO")

# Allow frontends to call the API. Replace ["*"] with your domain in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # consider restricting to your Vercel domain
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------
# CHAT ENDPOINT
# ---------------------
@app.post("/api/chat")
async def chat(request: Request):
    """
    Receives JSON:
    {
      "question": "...",
      "history": [{role, content}, ...],
      "itinerary_content": "..."
    }
    Returns:
    { "answer": "...", "images": [...], "places": [...] }
    """
    body = await request.json()
    question: str = body.get("question", "").strip()
    history = body.get("history", [])
    itinerary = body.get("itinerary_content", DEFAULT_ITINERARY)

    if not question:
        raise HTTPException(status_code=400, detail="Missing question")

    # Build messages array
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n--- USER ITINERARY ---\n" + (itinerary or "")}
    ]
    for h in history:
        # basic validation
        if isinstance(h, dict) and "role" in h and "content" in h:
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    payload = {"model": "openrouter/auto", "messages": messages}
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}

    try:
        resp = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=30)
    except requests.RequestException as e:
        log.exception("Network error contacting OpenRouter")
        return {"answer": f"⚠️ Network error contacting OpenRouter: {e}", "images": [], "places": []}

    if resp.status_code != 200:
        log.error("OpenRouter returned status %s: %s", resp.status_code, resp.text)
        return {"answer": f"⚠️ OpenRouter error {resp.status_code}: {resp.text}", "images": [], "places": []}

    try:
        data = resp.json()
    except Exception as e:
        log.exception("Failed to parse OpenRouter JSON")
        return {"answer": f"⚠️ Could not parse model response: {e}", "images": [], "places": []}

    # Robustly find the message text inside choices
    raw_answer = ""
    try:
        # common shapes: data["choices"][0]["message"]["content"] or data["choices"][0]["text"]
        if isinstance(data, dict) and "choices" in data and len(data["choices"]) > 0:
            first = data["choices"][0]
            if isinstance(first, dict):
                if "message" in first and isinstance(first["message"], dict) and "content" in first["message"]:
                    raw_answer = first["message"]["content"]
                elif "text" in first:
                    raw_answer = first.get("text", "")
                else:
                    # fallback to stringifying
                    raw_answer = json.dumps(first)
        if not raw_answer:
            raw_answer = json.dumps(data)
    except Exception:
        raw_answer = str(data)

    # Extract LLM-provided markdown images and clean text
    llm_images = extract_markdown_images(raw_answer)
    answer_clean = clean_markdown_images(raw_answer)

    # Auto-detect places (for Unsplash fallback)
    places = extract_places(answer_clean)
    auto_images = [get_unsplash_image(p) for p in places]

    images = llm_images + auto_images

    return {"answer": answer_clean, "images": images, "places": places}


# ---------------------
# TRIPS CRUD
# ---------------------
@app.post("/api/trips")
async def save_trip(request: Request):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    body = await request.json()
    name = body.get("name", "Untitled Trip")
    itinerary = body.get("itinerary", "")
    metadata = body.get("metadata", {})

    doc = {"name": name, "itinerary": itinerary, "metadata": metadata}
    try:
        res = db.trips.insert_one(doc)
        return {"id": str(res.inserted_id)}
    except Exception as e:
        log.exception("Failed to save trip")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trips/{trip_id}")
async def get_trip(trip_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        doc = db.trips.find_one({"_id": ObjectId(trip_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid trip ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Trip not found")
    doc["_id"] = str(doc["_id"])
    return doc


@app.get("/api/trips")
async def list_trips():
    if db is None:
        return {"trips": []}
    try:
        docs = db.trips.find().sort("name", 1)
        trips = [{"id": str(d["_id"]), "name": d.get("name"), "metadata": d.get("metadata", {})} for d in docs]
        return {"trips": trips}
    except Exception as e:
        log.exception("Failed to list trips")
        return {"trips": [], "error": str(e)}


# ---------------------
# WEATHER
# ---------------------
@app.get("/api/weather")
async def get_weather(lat: float, lon: float):
    params = {"latitude": lat, "longitude": lon, "hourly": "temperature_2m,weathercode", "timezone": "auto"}
    try:
        r = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.exception("Weather lookup failed")
        return {"error": str(e)}


# ---------------------
# SUMMARY
# ---------------------
@app.post("/api/summary")
async def summary(request: Request):
    body = await request.json()
    itinerary = body.get("itinerary", DEFAULT_ITINERARY)
    prompt = f"Summarize this itinerary in 5 lines:\n\n{itinerary}"

    payload = {"model": "openrouter/auto", "messages": [{"role": "system", "content": "You summarize clearly and concisely."}, {"role": "user", "content": prompt}]}
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}

    try:
        r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        # parse result
        if "choices" in data and len(data["choices"]) > 0:
            first = data["choices"][0]
            if isinstance(first, dict) and "message" in first and isinstance(first["message"], dict):
                return {"summary": first["message"].get("content", "")}
            elif isinstance(first, dict) and "text" in first:
                return {"summary": first.get("text", "")}
        return {"summary": json.dumps(data)}
    except Exception as e:
        log.exception("Summary request failed")
        return {"error": str(e)}
