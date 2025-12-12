# api/chat.py  (Vercel serverless)
import os
import httpx
import json

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")  # change if desired

DEFAULT_ITINERARY = """
Default generic itinerary reference:
- Basic Info: visa docs (passport >=6 months), insurance recommendation, transfers, local transport tips, timezone/currency.
- Flights & hotels: pick reasonable buffer times; stagger hotels by area as desired.
- Typical 5-night plan example:
  Day 0: depart -> arrive -> hotel
  Day 1: city center (museums, main landmark)
  Day 2: beach/relax or island/palm
  Day 3: adventure (desert safari / local excursion)
  Day 4: optional day trip to nearby city / theme park / museums
  Day 5: pack, check-out, departure
- Tips: book tickets ahead, modest dress where required, sun protection, Type G plugs in UAE etc.
"""

SYSTEM_BASE = (
    "You are an itinerary assistant. You MUST answer using only the itinerary provided to you "
    "in this request (itinerary_content) OR, if not provided, use the built-in default itinerary. "
    "Do NOT invent schedules or facts outside the given itinerary. If the user asks about something not in the itinerary, say it's not present and offer safe suggestions only based on the itinerary. "
    "If the itinerary contains image URLs or markdown image tags, you may reference them in your answer. "
)

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

async def call_openai(messages):
    if not OPENAI_API_KEY:
        return {"error": "OPENAI_API_KEY not set on server."}, 500
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.15,
        "max_tokens": 700,
    }
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(OPENAI_URL, json=payload, headers=headers)
        if r.status_code != 200:
            try:
                return {"error": r.json()}, 502
            except Exception:
                return {"error": r.text}, 502
        data = r.json()
        return {"data": data}, 200

async def handler(request):
    # Vercel passes a request object similar to ASGI; parse JSON
    try:
        body = await request.json()
    except Exception:
        body = {}
    question = body.get("question", "").strip()
    history = body.get("history", [])  # list of {"role":..., "content":...}
    itinerary_content = body.get("itinerary_content", None)  # full string (optional)
    # allow older clients that pass itinerary_id but we won't load server files here
    itinerary_id = body.get("itinerary_id", None)

    # Choose itinerary text
    if itinerary_content:
        itinerary_text = itinerary_content
    else:
        # fallback to default; if you add server itineraries, you can expand here
        itinerary_text = DEFAULT_ITINERARY

    if not question:
        return {"status": 400, "body": {"error": "question field is required"}}

    system_prompt = SYSTEM_BASE + "\n\nITINERARY:\n" + itinerary_text

    # Build messages: system, history, user
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        # basic validation
        if isinstance(h, dict) and "role" in h and "content" in h:
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    result, status = await call_openai(messages)
    if status != 200:
        return {"status": status, "body": result}
    # Extract assistant text
    try:
        assistant_text = result["data"]["choices"][0]["message"]["content"]
    except Exception as e:
        return {"status": 502, "body": {"error": "invalid openai response", "raw": result}}
    # Return assistant_text (may include markdown with images)
    return {"status": 200, "body": {"answer": assistant_text}}
