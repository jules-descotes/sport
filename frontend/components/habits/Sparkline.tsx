"use client";

/**
 * Une courbe fine — **une seule teinte, une grille discrète, aucun axe**.
 *
 * Les règles de dessin du projet valent ici comme ailleurs : trait de
 * 1,75 px, pas d'ombre portée, jamais d'emoji, et surtout **pas de seconde
 * couleur**. Une courbe de tendance qui passerait du vert au rouge selon la
 * valeur porterait un jugement, et c'est précisément ce qu'on s'interdit sur
 * les habitudes.
 *
 * SVG écrit à la main, comme `SwellChart` et `TileMap` : une bibliothèque de
 * graphes pèse plus lourd que tout le reste de l'écran, pour une polyligne.
 */
interface SparklineProps {
  values: number[];
  /** Deuxième série, rendue en pointillés — « prévu » contre « fait ». */
  reference?: number[];
  height?: number;
  label: string;
  /** Barres plutôt qu'une ligne : pour des comptes, une barre est plus juste
   *  qu'un trait qui interpolerait entre deux jours. */
  bars?: boolean;
}

const WIDTH = 240;
const PADDING = 3;

export function Sparkline({
  values,
  reference,
  height = 44,
  label,
  bars = false,
}: SparklineProps) {
  if (values.length === 0) return null;

  const all = reference ? [...values, ...reference] : values;
  const top = Math.max(1, ...all);
  const step = WIDTH / Math.max(1, values.length - (bars ? 0 : 1));

  const y = (value: number) =>
    height - PADDING - (value / top) * (height - PADDING * 2);

  const line = values
    .map((value, index) => `${index === 0 ? "M" : "L"}${index * step} ${y(value)}`)
    .join(" ");

  const dashed = reference
    ? reference
        .map(
          (value, index) => `${index === 0 ? "M" : "L"}${index * step} ${y(value)}`,
        )
        .join(" ")
    : null;

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${height}`}
      preserveAspectRatio="none"
      className="block h-[44px] w-full text-accent"
      role="img"
      aria-label={label}
    >
      {/* La grille : deux traits, et c'est tout. Assez pour donner une échelle,
          pas assez pour concurrencer la courbe. */}
      <line
        x1={0}
        y1={y(top)}
        x2={WIDTH}
        y2={y(top)}
        className="stroke-[var(--sport-line)]"
        strokeWidth={1}
      />
      <line
        x1={0}
        y1={y(0)}
        x2={WIDTH}
        y2={y(0)}
        className="stroke-[var(--sport-line)]"
        strokeWidth={1}
      />

      {dashed ? (
        <path
          d={dashed}
          fill="none"
          className="stroke-[var(--sport-mute)]"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />
      ) : null}

      {bars ? (
        values.map((value, index) => (
          <rect
            key={index}
            x={index * step + step * 0.2}
            y={y(value)}
            width={step * 0.6}
            height={Math.max(0, y(0) - y(value))}
            fill="currentColor"
          />
        ))
      ) : (
        <path
          d={line}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.75}
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  );
}
