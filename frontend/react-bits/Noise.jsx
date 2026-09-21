import { useEffect, useRef } from 'react';
// React Bits Noise: sürekli yeniden çizim yerine bir kez oluşturulan küçük doku.
export default function Noise({ patternAlpha = 9 }) {
  const canvas = useRef(null);
  useEffect(() => {
    const ctx = canvas.current.getContext('2d');
    const pixels = ctx.createImageData(128, 128);
    for (let i = 0; i < pixels.data.length; i += 4) {
      pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = Math.random() * 255;
      pixels.data[i + 3] = patternAlpha;
    }
    ctx.putImageData(pixels, 0, 0);
  }, [patternAlpha]);
  return <canvas className="rb-noise" ref={canvas} width="128" height="128" aria-hidden="true"/>;
}
