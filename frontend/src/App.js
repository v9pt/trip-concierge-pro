// src/App.js (PRO) — overwrite your current App.js
import React, { useEffect, useState } from "react";
import "./App.css";
import ImageModal from "./ImageModal";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL ;
const API_BASE = process.env.REACT_APP_API_BASE ;

function App(){
  const [itinerary, setItinerary] = useState("");
  const [messages, setMessages] = useState([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [modalImg, setModalImg] = useState(null);
  const [trips, setTrips] = useState([]);

  useEffect(()=>{ fetchTrips(); }, []);

  const fetchTrips = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/trips`);
      const data = await res.json();
      setTrips(data.trips || []);
    } catch(e){ console.error("fetchTrips:", e); }
  };

  // SEND - fixed to include the most recent user message in the "history" we send
  const send = async () => {
    if(!q.trim()) return;
    const userMsg = { role:"user", content:q };
    // show locally immediately
    setMessages(prev => [...prev, userMsg]);
    // prepare history to send (include the new user message)
    const historyToSend = [...messages, userMsg];

    setQ(""); setLoading(true);
    try {
      const res = await fetch(BACKEND_URL, {
        method:"POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({ question: q, history: historyToSend, itinerary_content: itinerary })
      });
      const data = await res.json();

      const bot = {
        role:"assistant",
        content: data.answer || "No answer from server.",
        images: data.images || []
      };

      setMessages(prev => [...prev, bot]); // append bot reply
      // optionally auto-scroll (if you add a ref)
    } catch(e){
      console.error("send error:", e);
      setMessages(prev => [...prev, {role:"assistant", content:"Server error. Check console."}]);
    } finally { setLoading(false); }
  };

  const quick = async (t) => { setQ(t); setTimeout(()=>send(), 150); };

  const saveTrip = async () => {
    const name = prompt("Trip name?");
    if(!name) return;
    try{
      await fetch(`${API_BASE}/api/trips`, {
        method:"POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({ name, itinerary, metadata: {} })
      });
      fetchTrips();
      alert("Saved");
    }catch(e){ console.error("saveTrip", e); alert("Save failed"); }
  };

  const loadTrip = async (id) => {
    try {
      const res = await fetch(`${API_BASE}/api/trips/${id}`);
      const data = await res.json();
      setItinerary(data.itinerary || "");
    } catch(e){ console.error(e); alert("Load failed"); }
  };

  return (
    <div className="app-container">
      <div className="header">
        <h1>Trip Concierge PRO</h1>
        <p>Human-like travel assistant — save trips, get images, weather, and more</p>
      </div>

      <div className="box">
        <div style={{display:"flex", gap:10, marginBottom:10, alignItems:"flex-start"}}>
          <textarea className="textarea" rows={5} value={itinerary} onChange={e=>setItinerary(e.target.value)} placeholder="Paste itinerary or markdown"></textarea>
          <div style={{display:"flex",flexDirection:"column",gap:8}}>
            <button onClick={saveTrip} className="send-btn">Save Trip</button>
            <button onClick={fetchTrips} className="send-btn">Refresh Trips</button>
          </div>
        </div>
        <div style={{display:"flex",gap:8, flexWrap:"wrap"}}>
          {trips.map(t => <button key={t.id} onClick={()=>loadTrip(t.id)} className="chip">{t.name}</button>)}
        </div>
      </div>

      <div className="box chat-window">
        {messages.map((m,i)=>(
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble" dangerouslySetInnerHTML={{__html: m.content.replace(/\n/g, "<br/>")}} />
            {m.images && m.images.length>0 && (
              <div className="image-grid">
                {m.images.map((src,idx)=>(
                  <img key={idx} src={src} alt={`img-${idx}`} onClick={()=>setModalImg(src)}
                       onError={(e)=>{ e.currentTarget.src="/placeholder-blank.png"; }} />
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && <div className="msg bot"><div className="bubble">Trip Concierge is thinking<span className="dots">...</span></div></div>}
      </div>

      <div style={{marginTop:12, display:"flex", gap:10, alignItems:"center"}}>
        <input className="send-input" value={q} onChange={e=>setQ(e.target.value)} placeholder="Ask: Plan my evening..." />
        <button className="send-btn" onClick={send}>Send</button>
        <div style={{display:"flex", gap:8}}>
          <button className="chip" onClick={()=>quick("Recommend 3 fun things for the morning")}>Morning ideas</button>
          <button className="chip" onClick={()=>quick("Budget friendly activities")}>Budget</button>
          <button className="chip" onClick={()=>quick("Kid friendly options")}>Family</button>
        </div>
      </div>

      {modalImg && <ImageModal src={modalImg} onClose={()=>setModalImg(null)} />}
    </div>
  );
}

export default App;
