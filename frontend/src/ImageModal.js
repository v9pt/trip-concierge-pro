// src/ImageModal.js
import React from "react";
import "./ImageModal.css";

export default function ImageModal({src, onClose}){
  if(!src) return null;
  return (
    <div className="imgmodal-backdrop" onClick={onClose}>
      <div className="imgmodal-card" onClick={e=>e.stopPropagation()}>
        <button className="imgmodal-close" onClick={onClose}>✕</button>
        <img src={src} alt="preview" onError={(e)=> e.currentTarget.classList.add("img-error")} />
      </div>
    </div>
  );
}
