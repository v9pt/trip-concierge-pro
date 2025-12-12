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
MONGO_URL = os.getenv("MONGO_URL")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "https://trip-concierge-pro-git-master-v9pts-projects.vercel.app"
)

if not OPENROUTER_API_KEY:
    raise Exception("OPENROUTER_API_KEY missing in environment")

# ==========================
# MONGO CONNECTION
# ==========================

mongo_client = None
db = None

if MONGO_URL:
    try:
        mongo_client = MongoClient(
            MONGO_URL,
            tls=True,
            tlsAllowInvalidCertificates=True,
            serverSelectionTimeoutMS=8000
        )

        mongo_client.admin.command("ping")
        print("✅ MongoDB CONNECTED")

        db_name = MONGO_URL.split("/")[-1].split("?")[0]
        db = mongo_client[db_name]

    except Exception as e:
        print(f"❌ MongoDB unreachable — running without DB: {e}")
        db = None

else:
    print("⚠️ MONGO_URL missing — DB disabled")


# ==========================
# HELPERS
# ==========================

def extract_markdown_images(text):
    return re.findall(r'!\[.*?\]\((.*?)\)', text)


def clean_markdown_images(text):
    return re.sub(r'!\[.*?\]\(.*?\)', '', text).strip()


def get_unsplash_image(place):
    sig = random.randint(1, 9999999)
    return f"https://source.unsplash.com/900x600/?{place}&sig={sig}"


def extract_places(text):
    raw = re.findall(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2})\b', text)
    blacklist = {"Summary","Options","Best","Quick","Here","Morning","Evening",
                 "Night","Cost","Who","Ideal","Plan","Day","You","Your","Trip"}
    places = [p for p in raw if p not in blacklist]
    return list(dict.fromkeys(places))[:6]


SYSTEM_PROMPT = """
You are Trip Concierge Pro — friendly, helpful, concise.
Include:
- A short summary
- 3 strong options with timing + cost
- Add image tags like: ![](https://...)
- End with one follow-up question
"""


# ==========================
# FASTAPI
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

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": body.get("question", "")}
    ]

    payload = {"model": "openrouter/auto", "messages": messages}

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",

        # REQUIRED — without these 502 forever
        "HTTP-Referer": FRONTEND_URL,
        "X-Title": "Trip Concierge PRO",
    }

    try:
        r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=45)
    except Exception as e:
        return {"answer": f"⚠️ Network error: {e}", "images": []}

    if r.status_code != 200:
        return {"answer": f"⚠️ API error {r.status_code}: {r.text}", "images": []}

    data = r.json()
    raw = data["choices"][0]["message"]["content"]

    clean = clean_markdown_images(raw)
    llm_imgs = extract_markdown_images(raw)
    places = extract_places(clean)
    auto_imgs = [get_unsplash_image(p) for p in places]

    return {
        "answer": clean,
        "images": llm_imgs + auto_imgs,
        "places": places
    }


# ==========================
# SAVE TRIP
# ==========================

@app.post("/api/trips")
async def save_trip(request: Request):
    if db is None:
        return {"error": "DB disabled"}
    body = await request.json()
    res = db.trips.insert_one(body)
    return {"id": str(res.inserted_id)}


# ==========================
# WEATHER
# ==========================

@app.get("/api/weather")
async def weather(lat: float, lon: float):
    try:
        r = requests.get(OPEN_METEO_URL, params={
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,weathercode",
            "timezone": "auto"
        })
        return r.json()
    except Exception as e:
        return {"error": str(e)}
