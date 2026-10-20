/**
 * Decorative line art fixed behind every page: the testosterone molecule and a
 * pair of vials with a syringe, drawn in the brand blue at low opacity so they
 * read as texture under the glass cards and never compete with content.
 */
export function BackgroundArt() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden text-brand-400">
      <Molecule className="absolute -bottom-6 -right-10 w-[300px] -rotate-6 opacity-[0.16] sm:w-[440px] lg:bottom-8 lg:right-8 lg:w-[540px]" />
      <VialsAndSyringe className="absolute -right-12 top-28 w-[220px] rotate-12 opacity-[0.12] sm:w-[280px] lg:bottom-6 lg:left-[20rem] lg:right-auto lg:top-auto lg:w-[320px] lg:-rotate-6" />
    </div>
  );
}

const GLOW = { filter: "drop-shadow(0 0 6px rgb(74 155 255 / 0.9))" };

// Skeletal formula: rings A, B, C (hexagons) and D (pentagon), with the C3
// ketone, the C4=C5 double bond, the C18/C19 methyls and the 17-OH.
const RING_VERTICES: [number, number][] = [
  [152, 170], [100, 140], [48, 170], [48, 230], [100, 260], [152, 230],
  [255.9, 170], [203.9, 140], [203.9, 260], [255.9, 230],
  [307.8, 80], [255.9, 50], [203.9, 80], [307.8, 140],
  [364.9, 158.5], [400.2, 110], [364.9, 61.5]
];

function Molecule({ className }: { className?: string }) {
  return (
    <svg
      viewBox="-24 0 460 285"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinejoin="round"
      strokeLinecap="round"
      style={GLOW}
    >
      <path d="M152 170 L100 140 L48 170 L48 230 L100 260 L152 230 Z" />
      <path d="M255.9 170 L203.9 140 L152 170 L152 230 L203.9 260 L255.9 230 Z" />
      <path d="M307.8 80 L255.9 50 L203.9 80 L203.9 140 L255.9 170 L307.8 140 Z" />
      <path d="M307.8 80 L307.8 140 L364.9 158.5 L400.2 110 L364.9 61.5 Z" />
      {/* C4=C5 double bond, drawn inside ring A */}
      <path d="M106 248 L143 226.5" />
      {/* C3=O ketone */}
      <path d="M48 230 L12 251 M42 220 L6 241" />
      <text x="-14" y="268" fill="currentColor" stroke="none" fontSize="26" fontWeight="700">
        O
      </text>
      {/* Angular methyls */}
      <path d="M152 170 L152 112 M307.8 80 L307.8 22" />
      {/* 17-OH */}
      <path d="M364.9 61.5 L390 26" />
      <text x="384" y="20" fill="currentColor" stroke="none" fontSize="26" fontWeight="700">
        OH
      </text>
      {RING_VERTICES.map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r="5" fill="currentColor" stroke="none" />
      ))}
    </svg>
  );
}

function Vial({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x="8" y="0" width="90" height="34" rx="9" fill="currentColor" fillOpacity="0.45" />
      <rect x="18" y="34" width="70" height="14" rx="3" />
      <path d="M30 48 V64 C30 74 0 76 0 96 V236 A18 18 0 0 0 18 254 H88 A18 18 0 0 0 106 236 V96 C106 76 76 74 76 64 V48" />
      {/* Liquid level and label */}
      <path d="M0 150 H106" strokeOpacity="0.6" />
      <rect x="0" y="168" width="106" height="58" fill="currentColor" fillOpacity="0.12" />
      <path d="M14 186 H70 M14 200 H92 M14 212 H56" strokeOpacity="0.7" />
    </g>
  );
}

function VialsAndSyringe({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 360 400"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinejoin="round"
      strokeLinecap="round"
      style={GLOW}
    >
      <Vial x={40} y={10} />
      <Vial x={190} y={40} />
      <g transform="translate(30 360) rotate(-24)">
        {/* Plunger, barrel with graduations, hub and needle */}
        <path d="M-48 2 V32 M-48 17 H0" />
        <rect x="0" y="0" width="200" height="34" rx="6" />
        <rect x="0" y="0" width="70" height="34" rx="6" fill="currentColor" fillOpacity="0.25" />
        <path d="M30 0 V12 M60 0 V16 M90 0 V12 M120 0 V16 M150 0 V12 M180 0 V16" />
        <path d="M200 8 H222 V26 H200" />
        <path d="M222 17 H300" strokeWidth="2" />
      </g>
    </svg>
  );
}
