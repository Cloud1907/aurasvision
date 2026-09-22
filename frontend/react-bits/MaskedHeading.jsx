// Başlık yalnız girişte açılır; tekrar eden veya sonsuz hareket üretmez.
export default function MaskedHeading({ children }) {
  return <span className="rb-masked-heading">{children}</span>;
}
