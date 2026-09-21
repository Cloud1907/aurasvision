const paths = {
  camera: <><rect x="3" y="6" width="13" height="12" rx="3"/><path d="m16 10 5-3v10l-5-3"/></>,
  arrow: <><path d="M5 12h14m-6-6 6 6-6 6"/></>,
  alert: <><path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v4m0 3v.1"/></>,
  check: <><path d="m5 12 4 4L19 6"/></>,
  pulse: <><path d="M2 12h5l3-8 4 16 3-8h5"/></>,
  play: <><path d="m9 5 11 7-11 7V5Z"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  search: <><circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></>,
  disk: <><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 13h18m-5 3h2m-6 0h1"/></>,
  close: <><path d="m6 6 12 12M6 18 18 6"/></>,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 6a8 8 0 0 1 14 6M4 12a8 8 0 0 0 14 6"/></>,
};
export default function Icon({ name, size = 20, ...props }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.grid}</svg>;
}
