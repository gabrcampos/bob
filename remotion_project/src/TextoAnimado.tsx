import React, { useMemo } from "react";
import {
  AbsoluteFill,
  // eslint-disable-next-line @typescript-eslint/no-deprecated
  Audio,
  Img,
  Sequence,
  // eslint-disable-next-line @typescript-eslint/no-deprecated
  Video,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export type LegendaWord = {
  word: string;
  start: number;
  end: number;
};

export type BrollClip = {
  src: string;
  startFrame: number;
  endFrame: number;
};

export type TextoAnimadoProps = {
  audioSrc: string;
  legendas: LegendaWord[];
  assetsVisuais: string[];
  brollClips?: BrollClip[];
  opcoesVisuais?: {
    fontePrincipal?: string;
    corFundoTexto?: string;
  };
};

type Chunk = {
  words: LegendaWord[];
  startFrame: number;
  endFrame: number;
  startsNewSentence: boolean;
};

// ─── Agrupamento dinâmico de palavras ───────────────────────────────────────
//
// Regras (em ordem de prioridade):
//   1. Quebra após pontuação final de frase: . , ! ? ; :
//   2. Quebra quando a linha ultrapassaria MAX_CHARS caracteres
//
// Resultado: frases não são cortadas no meio de forma antiestética.
//
const MAX_CHARS = 24;

function buildChunks(legendas: LegendaWord[], fps: number): Chunk[] {
  if (!legendas.length) return [];

  const chunks: Chunk[] = [];
  let current: LegendaWord[] = [];
  let nextStartsNew = true;

  const flush = () => {
    if (!current.length) return;
    const lastWord = current[current.length - 1].word.trim();
    const endsSentence = /[.!?]$/.test(lastWord);
    chunks.push({
      words: [...current],
      startFrame: Math.round(current[0].start * fps),
      endFrame: Math.round(current[current.length - 1].end * fps),
      startsNewSentence: nextStartsNew,
    });
    nextStartsNew = endsSentence;
    current = [];
  };

  for (let i = 0; i < legendas.length; i++) {
    const word = legendas[i];
    const prospecto = [...current, word].map((w) => w.word).join(" ");

    // Se adicionar esta palavra ultrapassaria o limite E já temos pelo menos
    // uma palavra, fecha o chunk anterior antes de adicionar.
    if (prospecto.length > MAX_CHARS && current.length > 0) {
      flush();
    }

    current.push(word);

    const endsPhrase = /[.,!?;:]$/.test(word.word.trim());
    const isLast = i === legendas.length - 1;

    if (endsPhrase || isLast) {
      flush();
    }
  }

  return chunks;
}

function formatChunk(words: LegendaWord[], capitalize: boolean): string {
  const text = words.map((w) => w.word.toLowerCase()).join(" ");
  return capitalize ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

// ─── Componente ──────────────────────────────────────────────────────────────
export const TextoAnimado: React.FC<TextoAnimadoProps> = ({
  audioSrc,
  legendas,
  assetsVisuais,
  brollClips,
  opcoesVisuais,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const chunks = useMemo(
    () => buildChunks(legendas ?? [], fps),
    [legendas, fps],
  );

  const activeChunk = chunks.find(
    (c) => frame >= c.startFrame && frame <= c.endFrame,
  );

  const bgImage = assetsVisuais?.[0] ?? null;
  const corFundo = "#0d1353";

  return (
    <AbsoluteFill style={{ backgroundColor: "#0f172a" }}>
      {/* B-roll: um clip por frase, cada um na sua janela de tempo */}
      {brollClips && brollClips.length > 0
        ? brollClips.map((clip, i) => (
            <Sequence
              key={i}
              from={clip.startFrame}
              durationInFrames={clip.endFrame - clip.startFrame + 1}
            >
              <Video
                src={staticFile(clip.src)}
                style={{
                  position: "absolute",
                  inset: 0,
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                }}
              />
            </Sequence>
          ))
        : bgImage && (
            <Img
              src={staticFile(bgImage)}
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                objectFit: "cover",
              }}
            />
          )}

      {/* Poppins Bold via Google Fonts */}
      <link
        href="https://fonts.googleapis.com/css2?family=Poppins:wght@400&display=swap"
        rel="stylesheet"
      />

      {/* Áudio */}
      {audioSrc && <Audio src={staticFile(audioSrc)} />}

      {/* Legenda — centralizada com margens laterais garantidas */}
      <div
        style={{
          position: "absolute",
          top: 0,
          bottom: 0,
          left: 80,
          right: 80,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        {activeChunk && (
          <div
            style={{
              backgroundColor: corFundo,
              color: "#ffffff",
              fontFamily: "'Poppins', sans-serif",
              fontWeight: 700,
              fontSize: 46,
              lineHeight: 1.6,
              // Muito padding horizontal, pouco a mais na vertical
              paddingLeft: 45,
              paddingRight: 45,
              paddingTop: 18,
              paddingBottom: 26,
              borderRadius: 14,
              textAlign: "center",
              maxWidth: "100%",
              // Evita que o box quebre linha desnecessariamente
              whiteSpace: "nowrap",
            }}
          >
            {formatChunk(activeChunk.words, activeChunk.startsNewSentence)}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
