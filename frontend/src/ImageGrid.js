import React, { useState } from "react";
import "./ImageGrid.css";

export default function ImageGrid({ images }) {
  const [selected, setSelected] = useState(null);

  return (
    <>
      <div className="img-grid">
        {images.map((src, idx) => (
          <div key={idx} className="img-wrapper" onClick={() => setSelected(src)}>
            <img
              src={src}
              alt="travel-spot"
              loading="lazy"
              onError={(e) => (e.target.style.display = "none")}
            />
          </div>
        ))}
      </div>

      {selected && (
        <div className="img-modal" onClick={() => setSelected(null)}>
          <img src={selected} alt="full-preview" className="img-modal-content" />
        </div>
      )}
    </>
  );
}
