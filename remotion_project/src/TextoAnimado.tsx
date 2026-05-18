import React, { useMemo } from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

// Essa é a estrutura que o seu editor.py em Python vai enviar via JSON
export type LegendaWord = {
  word: string;
  start: number;
  end: number;
};

export type TextoAnimadoProps = {
  audioSrc: string;
  legendas: LegendaWord[];
  assetsVisuais: string[];
  opcoesVisuais?: {
    fontePrincipal?: string;
    corFundoTexto?: string;
  };
};

export const TextoAnimado: React.FC<TextoAnimadoProps> = ({
  audioSrc,
  legendas,
  assetsVisuais,
  opcoesVisuais,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Fonte e cor dinâmicas enviadas pelo Python
  const fontFamily = opcoesVisuais?.fontePrincipal || "Poppins";
  const fontUrl = `https://fonts.googleapis.com/css2?family=${fontFamily.replace(/\s+/g, "+")}:wght@400;700;900&display=swap`;

  // Agrupa as legendas de 2 em 2 palavras (conforme solicitado)
  const WORDS_PER_CHUNK = 2;
  const chunks = useMemo(() => {
    const res = [];
    const safeLegendas = legendas || [];
    for (let i = 0; i < safeLegendas.length; i += WORDS_PER_CHUNK) {
      const slice = safeLegendas.slice(i, i + WORDS_PER_CHUNK);
      res.push({
        words: slice,
        // O bloco começa na primeira palavra e termina EXATAMENTE no fim da última
        startFrame: Math.round(slice[0].start * fps),
        endFrame: Math.round(slice[slice.length - 1].end * fps),
      });
    }
    return res;
  }, [legendas]);

  // Encontra qual grupo (chunk) deve estar na tela neste exato frame
  // Se ninguém estiver falando (pausa longa), a tela fica limpa!
  const activeChunk = chunks.find(
    (c) => frame >= c.startFrame && frame <= c.endFrame,
  );

  // Se o Python enviar o fundo.png gerado pelo PIL, pegamos o primeiro asset
  const bgImage =
    assetsVisuais && assetsVisuais.length > 0 ? assetsVisuais[0] : null;

  return (
    <AbsoluteFill className="bg-slate-900 justify-center items-center">
      {/* 1. Imagem de Fundo (gerada pelo PIL) */}
      {bgImage && (
        <Img
          src={staticFile(bgImage)}
          className="absolute z-0 inset-0 w-full h-full object-cover"
        />
      )}

      {/* Injeta a fonte do Google Fonts dinamicamente */}
      <link href={fontUrl} rel="stylesheet" />

      {/* 2. Áudio da Narração */}
      {audioSrc && <Audio src={staticFile(audioSrc)} />}

      {/* 3. Animação das Palavras (Estilo TikTok/Reels) */}
      <div
        className="relative z-10 w-full h-full flex flex-col justify-center items-center px-24 py-12 text-center font-bold uppercase tracking-tight"
        style={{ fontFamily }}
      >
        {activeChunk && (
          <div
            className="inline-flex flex-wrap justify-center px-24 py-100 rounded-[10px]"
            style={{
              backgroundColor: opcoesVisuais?.corFundoTexto || "#131b71",
              color: "#ffffff",
              fontSize: "65px",
              lineHeight: "1.3",
              gap: "24px",
            }}
          >
            {activeChunk.words.map((legenda, index) => (
              <span key={index}>{legenda.word}</span>
            ))}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
