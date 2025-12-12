import os
import re
import requests
import random
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pymongo import MongoClient
from bson.objectid import ObjectId

load_dotenv()

# ==========================
# CONFIG
# ==========================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MONGO_URL = os.getenv("MONGO_URL")  # MUST include database name
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

if not OPENROUTER_API_KEY:
    raise Exception("OPENROUTER_API_KEY missing in .env")

# ==========================
# MONGO CONNECTION (FIXED)
# ==========================

mongo_client = None
db = None

if MONGO_URL:
    try:
        mongo_client = MongoClient(
            MONGO_URL,
            tls=True,
            tlsAllowInvalidCertificates=True
        )
        db = mongo_client["trip_concierge"]  # ALWAYS use explicit DB
        print("✅ MongoDB connected")
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        db = None
else:
    print("⚠️ No MONGO_URL provided — DB disabled.")


# ==========================
# HELPERS
# ==========================

def extract_markdown_images(text):
    """Find image URLs inside markdown ![](url)."""
    return re.findall(r'!\[.*?\]\((.*?)\)', text)


def clean_markdown_images(text):
    """Remove markdown images from bot reply."""
    return re.sub(r'!\[.*?\]\(.*?\)', '', text).strip()


def get_unsplash_image(place):
    """Unsplash random image fix using &sig=randomNumber."""
    sig = random.randint(1, 9999999)
    return f"https://source.unsplash.com/900x600/?{place.replace(' ', '%20')}&sig={sig}"


def extract_places(text):
    """Extract place-like proper nouns."""
    raw = re.findall(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2})\b', text)

    blacklist = {
        "Summary","Options","Best","Quick","Here","Morning","Evening",
        "Night","Cost","Who","Ideal","Plan","Day","You","Your","Trip"
    }

    places = [p for p in raw if p not in blacklist and len(p) > 2]
    return list(dict.fromkeys(places))[:6]


SYSTEM_PROMPT = """
You are Trip Concierge Pro — friendly, helpful, and concise.
Every answer MUST include:
- A short summary
- 3 strong options with timing, cost & who will enjoy it
- Include image tags like: ![](https://...)
- Ask one follow-up question
"""

DEFAULT_ITINERARY = "No itinerary uploaded yet."


# ==========================
# FASTAPI APP
# ==========================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================
# CHAT ENDPOINT
# ==========================

@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()

    question = body.get("question")
    history = body.get("history", [])
    itinerary = body.get("itinerary_content", DEFAULT_ITINERARY)

    if not question:
        raise HTTPException(status_code=400, detail="Missing question")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n--- USER ITINERARY ---\n" + itinerary}
    ]

    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})

    messages.append({"role": "user", "content": question})

    payload = {"model": "openrouter/auto", "messages": messages}
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}

    try:
        resp = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=30)
    except Exception as e:
        return {"answer": f"⚠️ Network error: {e}", "images": []}

    if resp.status_code != 200:
        return {"answer": f"⚠️ Model error {resp.status_code}: {resp.text}", "images": []}

    data = resp.json()
    if "choices" not in data:
        return {"answer": f"⚠️ Unexpected response: {data}", "images": []}

    raw_answer = data["choices"][0]["message"]["content"]

    llm_images = extract_markdown_images(raw_answer)
    answer_clean = clean_markdown_images(raw_answer)

    # Auto place detection
    places = extract_places(answer_clean)
    auto_imgs = [get_unsplash_image(p) for p in places]

    full_images = llm_images + auto_imgs

    return {"answer": answer_clean, "images": full_images, "places": places}


# ==========================
# SAVE TRIP
# ==========================

@app.post("/api/trips")
async def save_trip(request: Request):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    body = await request.json()
    doc = {
        "name": body.get("name", "Untitled Trip"),
        "itinerary": body.get("itinerary", ""),
        "metadata": body.get("metadata", {})
    }

    res = db.trips.insert_one(doc)
    return {"id": str(res.inserted_id)}


# ==========================
# GET TRIP
# ==========================

@app.get("/api/trips/{trip_id}")
async def get_trip(trip_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    try:
        doc = db.trips.find_one({"_id": ObjectId(trip_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid trip ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Trip not found")

    doc["_id"] = str(doc["_id"])
    return doc


# ==========================
# LIST TRIPS (FIXED)
# ==========================

@app.get("/api/trips")
async def list_trips():
    if db is None:
        return {"trips": []}

    try:
        docs = db.trips.find().sort("name", 1)
        trips = [
            {"id": str(d["_id"]), "name": d.get("name"), "metadata": d.get("metadata", {})}
            for d in docs
        ]
        return {"trips": trips}

    except Exception as e:
        return {"trips": [], "error": str(e)}


# ==========================
# WEATHER
# ==========================

@app.get("/api/weather")
async def get_weather(lat: float, lon: float):
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,weathercode",
        "timezone": "auto"
    }

    try:
        r = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ==========================
# SUMMARY
# ==========================

@app.post("/api/summary")
async def summary(request: Request):
    body = await request.json()
    itinerary = body.get("itinerary", DEFAULT_ITINERARY)

    prompt = f"Summarize this itinerary in 5 lines:\n\n{itinerary}"

    payload = {
        "model": "openrouter/auto",
        "messages": [
            {"role": "system", "content": "You summarize clearly and concisely."},
            {"role": "user", "content": prompt}
        ]
    }

    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}

    r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=20)

    if r.status_code != 200:
        return {"error": r.text}

    data = r.json()
    return {"summary": data["choices"][0]["message"]["content"]}
