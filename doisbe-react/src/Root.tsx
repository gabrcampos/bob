import React from "react";
import { Composition } from "remotion";
import { FakeCorteReact, FakeCorteReactProps } from "./FakeCorteReact";
import rawProps from "../public/current_props.json";

type PropsFile = FakeCorteReactProps & { durationInFrames?: number };

export const RemotionRoot: React.FC = () => {
  const { durationInFrames = 300, ...componentProps } = rawProps as PropsFile;

  return (
    <Composition
      id="FakeCorteReact"
      component={FakeCorteReact}
      durationInFrames={durationInFrames}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={componentProps}
    />
  );
};
