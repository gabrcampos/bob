import React from "react";
import { Composition } from "remotion";
import { TextoAnimado, TextoAnimadoProps } from "./TextoAnimado";
import "./style.css"; // Importa o Tailwind CSS
import currentProps from "../public/current_props.json";

export const RemotionRoot: React.FC = () => {
  const props = currentProps as TextoAnimadoProps;

  // Duração dinâmica baseada no timing da última palavra
  const fps = 30;
  let durationInFrames = 150; // Valor padrão inicial

  if (props.legendas && props.legendas.length > 0) {
    const ultimaPalavra = props.legendas[props.legendas.length - 1];
    durationInFrames = Math.round(ultimaPalavra.end * fps) + 30; // Termina 1s após a fala
  }

  return (
    <>
      <Composition
        id="ComposicaoPrincipal"
        component={TextoAnimado}
        durationInFrames={durationInFrames}
        fps={fps}
        width={1080}
        height={1920} // Formato Reels / Shorts / TikTok
        defaultProps={{
          ...props,
          opcoesVisuais: props.opcoesVisuais || {
            fontePrincipal: "Poppins",
            corFundoTexto: "#131b71",
          },
        }}
      />
    </>
  );
};
