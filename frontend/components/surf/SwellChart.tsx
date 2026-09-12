"use client";

import { useId } from "react";

import { dayLabel, num } from "@/lib/format";
import type { ForecastPoint } from "@/lib/types";

/**
 * Courbe de houle et niveau de la mer sur cinq jours, en SVG à la main.
 *
 * Pas de librairie de graphes : le budget est d'un premier rendu utile en
 * moins de deux secondes en 4G (cf. PROJET.md §1), et deux polylignes ne
 * justifient pas 80 ko de JavaScript.
 */

const WIDTH = 720;
const HEIGHT = 180;
const PADDING = { top: 14, right: 8, bottom: 22, left: 30 };

interface SwellChartProps {
  points: ForecastPoint[];
  /** `sea_level` trace la marée sous la houle, sur son propre axe. */
  showSeaLevel?: boolean;
}

export function SwellChart({ points, showSeaLevel = true }: SwellChartProps) {
  const gradientId = useId();

  const usable = points.filter((point) => point.wave_height_m !== null);
  if (usable.length < 2) {
    return (
      <p className="rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
        Pas encore de prévision pour ce spot.
      </p>
    );
  }

  const innerWidth = WIDTH - PADDING.left - PADDING.right;
  const innerHeight = HEIGHT - PADDING.top - PADDING.bottom;

  const heights = usable.map((point) => point.wave_height_m as number);
  const maxHeight = Math.max(1.0, ...heights) * 1.15;

  const x = (index: number) =>
    PADDING.left + (index / (usable.length - 1)) * innerWidth;
  const y = (value: number) =>
    PADDING.top + innerHeight - (value / maxHeight) * innerHeight;

  const line = usable
    .map((point, index) => `${x(index)},${y(point.wave_height_m as number)}`)
    .join(" ");
  const area = `${PADDING.left},${PADDING.top + innerHeight} ${line} ${
    PADDING.left + innerWidth
  },${PADDING.top + innerHeight}`;

  // Le niveau de la mer a sa propre échelle : c'est une forme qu'on lit, pas
  // une valeur qu'on compare à la houle.
  const levels = usable
    .map((point) => point.sea_level_m)
    .filter((value): value is number => value !== null);
  const minLevel = levels.length ? Math.min(...levels) : 0;
  const maxLevel = levels.length ? Math.max(...levels) : 1;
  const levelSpan = Math.max(0.1, maxLevel - minLevel);
  const tideLine =
    showSeaLevel && levels.length > 2
      ? usable
          .map((point, index) =>
            point.sea_level_m === null
              ? null
              : `${x(index)},${
                  PADDING.top +
                  innerHeight -
                  ((point.sea_level_m - minLevel) / levelSpan) * innerHeight * 0.42
                }`,
          )
          .filter(Boolean)
          .join(" ")
      : null;

  // Un repère par jour, à midi : les heures exactes sont dans le comparateur.
  const dayMarks: { index: number; label: string }[] = [];
  let lastDay = "";
  usable.forEach((point, index) => {
    const date = new Date(point.ts);
    const key = date.toDateString();
    if (key !== lastDay && date.getHours() >= 11) {
      dayMarks.push({ index, label: dayLabel(point.ts) });
      lastDay = key;
    }
  });

  const gridValues = [0, maxHeight / 2, maxHeight];

  return (
    <figure className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-[180px] w-full min-w-[320px]"
        role="img"
        aria-label={`Houle sur ${dayMarks.length} jours, maximum ${num(
          Math.max(...heights),
        )} mètres`}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--sport-seq-4)" stopOpacity="0.45" />
            <stop offset="100%" stopColor="var(--sport-seq-4)" stopOpacity="0.05" />
          </linearGradient>
        </defs>

        {gridValues.map((value) => (
          <g key={value}>
            <line
              x1={PADDING.left}
              x2={WIDTH - PADDING.right}
              y1={y(value)}
              y2={y(value)}
              stroke="var(--sport-line)"
              strokeWidth="1"
            />
            <text
              x={4}
              y={y(value) + 4}
              className="tabular"
              fill="var(--sport-mute)"
              fontSize="10"
            >
              {num(value, 1)}
            </text>
          </g>
        ))}

        {dayMarks.map((mark) => (
          <text
            key={mark.label + mark.index}
            x={x(mark.index)}
            y={HEIGHT - 6}
            textAnchor="middle"
            fill="var(--sport-mute)"
            fontSize="11"
          >
            {mark.label}
          </text>
        ))}

        <polygon points={area} fill={`url(#${gradientId})`} />
        <polyline
          points={line}
          fill="none"
          stroke="var(--sport-seq-5)"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {tideLine ? (
          <polyline
            points={tideLine}
            fill="none"
            stroke="var(--sport-mute)"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            strokeLinejoin="round"
          />
        ) : null}
      </svg>

      <figcaption className="mt-1 flex gap-4 text-[11px] text-mute">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 bg-seq-5" aria-hidden />
          Houle (m)
        </span>
        {tideLine ? (
          <span className="flex items-center gap-1.5">
            <span
              className="h-0.5 w-4 border-t border-dashed border-mute"
              aria-hidden
            />
            Niveau de la mer
          </span>
        ) : null}
      </figcaption>
    </figure>
  );
}
