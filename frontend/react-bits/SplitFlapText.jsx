// React Bits yönündeki split-flap fikrinin düşük maliyetli, reduced-motion uyumlu ürün uyarlaması.
export default function SplitFlapText({ value }) {
  const text = String(value ?? '—');
  return <span className="rb-split-flap" aria-label={text}>
    {[...text].map((character, index) => <span className="rb-flap-cell" aria-hidden="true" key={`${index}-${character}`}>
      <span>{character === ' ' ? '\u00a0' : character}</span>
    </span>)}
  </span>;
}
