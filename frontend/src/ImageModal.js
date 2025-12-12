
import React from "react";

export default function ImageModal({ src, onClose }) {
  return (
    <div
      style={{
        position: "fixed",
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        backdropFilter: "blur(4px)",
        zIndex: 9999,
        padding: "20px"
      }}
      onClick={onClose}
    >
      <img
        src={src}
        alt="preview"
        style={{
          maxWidth: "90%",
          maxHeight: "90%",
          borderRadius: "16px",
          boxShadow: "0 0 25px rgba(0,0,0,0.4)"
        }}
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}
