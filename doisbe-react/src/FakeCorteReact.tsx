import React, { useState } from "react";
import {
  AbsoluteFill,
  // eslint-disable-next-line @typescript-eslint/no-deprecated
  Video,
  staticFile,
  useVideoConfig,
} from "remotion";

// ─── Canvas: 1080 × 1920 ─────────────────────────────────────────────────────
//
// ┌──────────────────────────────┐  y = 0
// │                              │
// │   broll_react  (background)  │  full-screen, atrás de tudo
// │                              │
// ├──────────────────────────────┤  y = 600
// │                              │
// │   youtube.mp4  (foreground)  │  por cima, preenche y=600..1920
// │                              │
// └──────────────────────────────┘  y = 1920

const YOUTUBE_TOP = 600;

export type FakeCorteReactProps = {
  brollSrc: string;
  youtubeSrc: string;
  youtubeStartFrom: number;
  brollStartFrom: number;
};

const Placeholder: React.FC<{ label: string; style: React.CSSProperties }> = ({
  label,
  style,
}) => (
  <div
    style={{
      ...style,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: "#1a1a2e",
      border: "2px dashed #444",
      color: "#666",
      fontSize: 28,
      fontFamily: "monospace",
    }}
  >
    {label}
  </div>
);

export const FakeCorteReact: React.FC<FakeCorteReactProps> = ({
  brollSrc,
  youtubeSrc,
  youtubeStartFrom,
  brollStartFrom,
}) => {
  const { width, height } = useVideoConfig();
  const [youtubeError, setYoutubeError] = useState(false);
  const [brollError, setBrollError] = useState(false);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* ── B-roll React — fundo full-screen ── */}
      {brollError ? (
        <Placeholder label="broll_react.mp4" style={{ position: "absolute", inset: 0 }} />
      ) : (
        <Video
          src={staticFile(brollSrc)}
          startFrom={Math.round(brollStartFrom * 30)}
          muted
          onError={() => setBrollError(true)}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
      )}

      {/* ── YouTube — por cima, a partir de y=600 ── */}
      <div
        style={{
          position: "absolute",
          top: YOUTUBE_TOP,
          left: 0,
          width,
          height: height - YOUTUBE_TOP,
          overflow: "hidden",
        }}
      >
        {youtubeError ? (
          <Placeholder label="youtube.mp4" style={{ position: "absolute", inset: 0 }} />
        ) : (
          <Video
            src={staticFile(youtubeSrc)}
            startFrom={Math.round(youtubeStartFrom * 30)}
            onError={() => setYoutubeError(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        )}
      </div>
    </AbsoluteFill>
  );
};
