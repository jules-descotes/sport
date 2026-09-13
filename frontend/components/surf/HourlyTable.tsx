"use client";

import { useMemo } from "react";

import { DirectionArrow } from "@/components/surf/DirectionArrow";
import {
  dayLabel,
  localDayKey,
  num,
  scoreClass,
  waveHeightClass,
  windSideShort,
  windSpeedClass,
} from "@/lib/format";
import type { ForecastPoint, SunDay } from "@/lib/types";

/**
 * **Le tableau horaire** — Windguru, en plus moderne (décidé le 13/09).
 *
 * Cinq jours heure par heure : colonnes = heures, lignes = variables,
 * défilement horizontal, jours en en-tête collante et colonne des libellés
 * figée. C'est la seule vue dense de l'app avec l'historique, et elle l'est
 * pour la bonne raison — on ne lit pas une prévision une information à la
 * fois, on la balaie pour trouver la fenêtre.
 *
 * Trois partis pris, et ils tiennent ensemble :
 *
 * 1. **Les directions sont des flèches, pas des degrés.** À bout de bras, au
 *    soleil, « 292° » ne se lit pas et « ONO » demande une traduction
 *    mentale ; une flèche se lit sans réfléchir. Les degrés existent, dans le
 *    détail d'un créneau, et là seulement.
 * 2. **Deux échelles de couleur, jamais mélangées.** Les hauteurs et les vents
 *    portent le séquentiel (l'intensité) ; seule la ligne du bas porte
 *    l'échelle 1 → 5 (la qualité). Une houle de 3 m est grosse, ce qui n'est
 *    pas la même chose que bonne.
 * 3. **La nuit est grisée, pas supprimée.** Une colonne manquante décalerait
 *    toute la lecture, et une matrice qui ne s'aligne pas ne se lit plus.
 *
 * Le tableau est en `table-layout: fixed` avec des largeurs connues : c'est ce
 * qui permet à la mini-courbe de marée, dessinée d'un seul trait sur toute la
 * largeur, de tomber pile sur ses colonnes.
 */

/**
 * Largeur d'une colonne d'heure — **46 px au doigt, 30 px à la souris**.
 *
 * 46 px sur téléphone : la cible tactile de 44 px du CLAUDE.md, et pas un
 * pixel de moins. Au-dessus de 1024 px, le pointeur est une souris et la règle
 * des 44 px ne s'applique plus en largeur ; la hauteur de ligne, elle, ne
 * bouge pas. Ce sont ces 30 px qui font tenir **deux jours entiers** — 48
 * heures — dans les 1 440 px demandés le 13/09, colonne des libellés figée
 * comprise. À 46 px il n'en tiendrait qu'un et demi, et une matinée coupée en
 * deux ne se compare pas.
 */
const COL_WIDTH = 46;
const DESKTOP_COL_WIDTH = 30;
/** Largeur de la colonne figée des libellés. */
const LABEL_WIDTH = 62;
/** Hauteur de la mini-courbe de marée. */
const TIDE_HEIGHT = 34;

interface Day {
  key: string;
  iso: string;
  points: ForecastPoint[];
  /** Meilleur créneau de jour de la journée — celui qui porte l'accent. */
  bestTs: string | null;
}

interface HourlyTableProps {
  points: ForecastPoint[];
  sun: SunDay[];
  /** Orientation du spot : elle décide de la teinte terre / mer du vent. */
  onshoreDirDeg: number | null;
  selectedTs: string | null;
  onSelect: (ts: string) => void;
  /** Ligne du swell secondaire, dépliée ou non. */
  secondaryOpen: boolean;
  onToggleSecondary: () => void;
  /** Largeur d'une colonne d'heure — `COL_WIDTH` au doigt, moins à la souris. */
  colWidth?: number;
}

function groupByDay(points: ForecastPoint[]): Day[] {
  const days = new Map<string, ForecastPoint[]>();
  for (const point of points) {
    const key = localDayKey(point.ts);
    const bucket = days.get(key);
    if (bucket) bucket.push(point);
    else days.set(key, [point]);
  }

  return [...days.entries()].map(([key, dayPoints]) => {
    let best: ForecastPoint | null = null;
    for (const point of dayPoints) {
      if (!point.daylight || point.score === null) continue;
      if (best === null || point.score > (best.score as number)) best = point;
    }
    return { key, iso: dayPoints[0].ts, points: dayPoints, bestTs: best?.ts ?? null };
  });
}

/** Libellé d'une ligne — figé à gauche, il ne défile jamais. */
function RowLabel({
  children,
  unit,
  title,
}: {
  children: React.ReactNode;
  unit?: string;
  title?: string;
}) {
  return (
    <th
      scope="row"
      title={title}
      className="sticky left-0 z-20 border-r border-line bg-card px-2 py-1 text-left align-middle"
      style={{ width: LABEL_WIDTH, minWidth: LABEL_WIDTH }}
    >
      <span className="block text-[12px] font-semibold leading-tight text-ink">
        {children}
      </span>
      {unit ? (
        <span className="block text-[11px] leading-tight text-mute">{unit}</span>
      ) : null}
    </th>
  );
}

/**
 * La mini-courbe de marée — un trait continu, pas une suite de cellules.
 *
 * C'est la seule façon de voir d'un coup d'œil que la bonne fenêtre est une
 * histoire de marée autant que de houle (`docs/DESIGN-EXPLORATION.md` §5,
 * emprunt à V3). Le niveau est normalisé sur la plage de toute la période
 * affichée, pas sur la journée : une courbe qui se remettrait à l'échelle à
 * chaque jour ferait croire à des marnages égaux.
 */
function TideCurve({
  points,
  colWidth,
}: {
  points: ForecastPoint[];
  colWidth: number;
}) {
  const levels = points.map((point) => point.sea_level_m);
  const known = levels.filter((value): value is number => value !== null);
  if (known.length < 2) {
    return (
      <span className="block px-2 text-[12px] text-mute">
        Niveau de la mer indisponible
      </span>
    );
  }

  const low = Math.min(...known);
  const high = Math.max(...known);
  const span = high - low || 1;
  const width = points.length * colWidth;

  // Le point est au centre de sa colonne : la courbe passe par les heures, pas
  // par les bords des cellules.
  const coords = points.map((point, index) => {
    const x = index * colWidth + colWidth / 2;
    const level = point.sea_level_m;
    const y =
      level === null
        ? null
        : TIDE_HEIGHT - 3 - ((level - low) / span) * (TIDE_HEIGHT - 8);
    return { x, y };
  });

  const line = coords
    .filter((coord): coord is { x: number; y: number } => coord.y !== null)
    .map((coord, index) => `${index === 0 ? "M" : "L"}${coord.x} ${coord.y}`)
    .join(" ");

  return (
    <svg
      width={width}
      height={TIDE_HEIGHT}
      viewBox={`0 0 ${width} ${TIDE_HEIGHT}`}
      className="block text-ink-2"
      role="img"
      aria-label={`Niveau de la mer, de ${num(low)} à ${num(high)} mètres`}
    >
      <path
        d={line}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Les extrêmes locaux — pleine et basse mer — marqués d'un point et
          chiffrés : c'est ce qu'on cherche sur cette ligne. */}
      {points.map((point, index) => {
        const level = point.sea_level_m;
        const coord = coords[index];
        if (level === null || coord.y === null) return null;

        const previous = points[index - 1]?.sea_level_m ?? null;
        const next = points[index + 1]?.sea_level_m ?? null;
        if (previous === null || next === null) return null;

        const isHigh = level >= previous && level >= next && level > previous;
        const isLow = level <= previous && level <= next && level < previous;
        if (!isHigh && !isLow) return null;

        return (
          <g key={point.ts}>
            <circle cx={coord.x} cy={coord.y} r={2.5} fill="currentColor" />
            <text
              x={coord.x}
              y={isHigh ? coord.y - 5 : coord.y + 11}
              textAnchor="middle"
              className="fill-current text-[10px] font-semibold"
            >
              {num(level)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function HourlyTable({
  points,
  sun,
  onshoreDirDeg,
  selectedTs,
  onSelect,
  secondaryOpen,
  onToggleSecondary,
  colWidth = COL_WIDTH,
}: HourlyTableProps) {
  const days = useMemo(() => groupByDay(points), [points]);

  const hasSecondary = useMemo(
    () => points.some((point) => (point.secondary_swell_height_m ?? 0) > 0.05),
    [points],
  );

  const sunByDay = useMemo(() => {
    const map = new Map<string, SunDay>();
    for (const entry of sun) map.set(entry.day, entry);
    return map;
  }, [sun]);

  if (points.length === 0) {
    return (
      <p className="mx-5 rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
        Pas encore de prévision pour ce spot.
      </p>
    );
  }

  const width = LABEL_WIDTH + points.length * colWidth;

  /** Classe commune d'une cellule d'heure : la nuit s'éteint. */
  const cellTone = (point: ForecastPoint, base: string) =>
    point.daylight ? base : `${base} opacity-45`;

  return (
    <div
      // L'écran Surf saute à une heure ou à un jour en posant `scrollLeft`
      // ici : c'est cet élément qui défile, et il faut pouvoir le désigner.
      data-hourly-scroller
      className="overflow-x-auto overflow-y-visible rounded-card border border-line bg-card"
      // Le défilement horizontal cale sur les colonnes : on ne s'arrête jamais
      // au milieu d'une heure.
      style={{ scrollSnapType: "x proximity" }}
    >
      <table
        className="tabular border-collapse"
        style={{ tableLayout: "fixed", width }}
      >
        <caption className="sr-only">
          Prévision heure par heure sur cinq jours : houle, vent, marée,
          température de l&apos;eau et note
        </caption>

        <colgroup>
          <col style={{ width: LABEL_WIDTH }} />
          {points.map((point) => (
            <col key={point.ts} style={{ width: colWidth }} />
          ))}
        </colgroup>

        <thead className="sticky top-0 z-30">
          {/* Jour — l'étiquette reste collée au bord gauche tant que la
              journée est à l'écran, comme un intertitre de liste. */}
          <tr className="bg-soft">
            <th
              className="sticky left-0 z-40 border-b border-r border-line bg-soft"
              style={{ width: LABEL_WIDTH }}
            />
            {days.map((day) => {
              const sunDay = sunByDay.get(day.key);
              return (
                <th
                  key={day.key}
                  colSpan={day.points.length}
                  scope="colgroup"
                  className="border-b border-l border-line bg-soft p-0 text-left"
                  style={{ scrollSnapAlign: "start" }}
                >
                  <span
                    className="sticky flex items-baseline gap-2 px-2 py-1.5"
                    style={{ left: LABEL_WIDTH }}
                  >
                    <span className="font-display text-[17px] font-semibold uppercase leading-none text-ink">
                      {dayLabel(day.iso)}
                    </span>
                    {sunDay?.sunrise && sunDay.sunset ? (
                      <span className="whitespace-nowrap text-[11px] text-mute">
                        {new Date(sunDay.sunrise).getHours()}h –{" "}
                        {new Date(sunDay.sunset).getHours()}h
                      </span>
                    ) : null}
                  </span>
                </th>
              );
            })}
          </tr>

          <tr className="bg-card">
            <th
              className="sticky left-0 z-40 border-b border-r border-line bg-card"
              style={{ width: LABEL_WIDTH }}
            />
            {points.map((point) => {
              const hour = new Date(point.ts).getHours();
              return (
                <th
                  key={point.ts}
                  scope="col"
                  className={`border-b border-line text-center text-[12px] font-semibold ${
                    point.daylight ? "text-ink-2" : "bg-soft text-mute"
                  }`}
                >
                  {String(hour).padStart(2, "0")}
                </th>
              );
            })}
          </tr>
        </thead>

        <tbody>
          {/* ── Houle ─────────────────────────────────────────────────── */}
          <tr>
            <RowLabel unit="m" title="Hauteur de houle significative">
              Houle
            </RowLabel>
            {points.map((point) => (
              <td key={point.ts} className="p-px">
                <span
                  className={cellTone(
                    point,
                    `flex h-8 items-center justify-center rounded-cell text-[14px] font-semibold ${waveHeightClass(
                      point.wave_height_m,
                    )}`,
                  )}
                >
                  {num(point.wave_height_m)}
                </span>
              </td>
            ))}
          </tr>

          <tr>
            <RowLabel unit="s" title="Période moyenne — la seule que sert MFWAM">
              Période
            </RowLabel>
            {points.map((point) => (
              <td
                key={point.ts}
                className={cellTone(
                  point,
                  "border-b border-line text-center text-[14px] font-semibold text-ink",
                )}
              >
                {num(point.wave_period_s, 0)}
              </td>
            ))}
          </tr>

          <tr>
            <RowLabel
              unit="kJ"
              title={
                "Flux d'énergie de la houle : P = 0,49 × H² × T, en kilojoules " +
                "par seconde et par mètre de crête (kW/m). Un mètre à 15 s " +
                "porte trois fois l'énergie d'un mètre à 7 s — c'est ce que la " +
                "hauteur seule ne dit pas. Feature 9 du registre."
              }
            >
              Énergie
            </RowLabel>
            {points.map((point) => (
              <td
                key={point.ts}
                className={cellTone(
                  point,
                  "border-b border-line text-center text-[14px] font-medium text-ink-2",
                )}
              >
                {point.wave_energy_kj === null
                  ? "—"
                  : num(point.wave_energy_kj, point.wave_energy_kj < 10 ? 1 : 0)}
              </td>
            ))}
          </tr>

          <tr>
            <RowLabel title="Direction d'où vient la houle">Dir.</RowLabel>
            {points.map((point) => (
              <td
                key={point.ts}
                className={cellTone(
                  point,
                  "border-b border-line text-ink-2",
                )}
              >
                <span className="flex justify-center py-1">
                  <DirectionArrow direction={point.wave_direction_deg} size={18} />
                </span>
              </td>
            ))}
          </tr>

          {/* ── Swell secondaire, repliable ───────────────────────────── */}
          {hasSecondary ? (
            <tr>
              <th
                scope="row"
                className="sticky left-0 z-20 border-r border-line bg-card p-0 text-left"
                style={{ width: LABEL_WIDTH }}
              >
                <button
                  type="button"
                  onClick={onToggleSecondary}
                  aria-expanded={secondaryOpen}
                  className="flex min-h-[34px] w-full items-center gap-1 px-2 text-left text-[12px] font-semibold text-ink-2"
                >
                  <span
                    aria-hidden
                    className={`inline-block transition-transform ${
                      secondaryOpen ? "rotate-90" : ""
                    }`}
                  >
                    ›
                  </span>
                  2ᵉ houle
                </button>
              </th>
              {points.map((point) => (
                <td
                  key={point.ts}
                  className={cellTone(
                    point,
                    "border-b border-line text-center text-ink-2",
                  )}
                >
                  {secondaryOpen ? (
                    <span className="flex flex-col items-center py-0.5">
                      <span className="text-[13px] font-semibold">
                        {num(point.secondary_swell_height_m)}
                      </span>
                      <DirectionArrow
                        direction={point.secondary_swell_direction_deg}
                        size={16}
                      />
                    </span>
                  ) : null}
                </td>
              ))}
            </tr>
          ) : null}

          {/* ── Vent ──────────────────────────────────────────────────── */}
          <tr>
            <RowLabel unit="kt" title="Vent moyen à 10 m">
              Vent
            </RowLabel>
            {points.map((point) => (
              <td key={point.ts} className="p-px">
                <span
                  className={cellTone(
                    point,
                    `flex h-8 items-center justify-center rounded-cell text-[14px] font-semibold ${windSpeedClass(
                      point.wind_speed_kt,
                    )}`,
                  )}
                >
                  {num(point.wind_speed_kt, 0)}
                </span>
              </td>
            ))}
          </tr>

          <tr>
            <RowLabel unit="kt" title="Rafales">
              Rafales
            </RowLabel>
            {points.map((point) => (
              <td
                key={point.ts}
                className={cellTone(
                  point,
                  "border-b border-line text-center text-[14px] font-medium text-ink-2",
                )}
              >
                {num(point.wind_gust_kt, 0)}
              </td>
            ))}
          </tr>

          <tr>
            <RowLabel
              title={
                onshoreDirDeg === null
                  ? "Direction d'où vient le vent"
                  : "Direction d'où vient le vent. Vert : de terre, il lisse la vague. Rouge : de mer, il la hache."
              }
            >
              Dir.
            </RowLabel>
            {points.map((point) => {
              const side = windSideShort(point.wind_offshore_kt);
              const tone =
                side === "terre"
                  ? "text-[#2F6B4F]"
                  : side === "mer"
                    ? "text-[#B4482E]"
                    : "text-ink-2";
              return (
                <td
                  key={point.ts}
                  className={cellTone(point, `border-b border-line ${tone}`)}
                >
                  <span className="flex justify-center py-1">
                    <DirectionArrow
                      direction={point.wind_direction_deg}
                      size={18}
                    />
                  </span>
                </td>
              );
            })}
          </tr>

          {/* ── Marée : un trait continu sur toute la largeur ─────────── */}
          <tr>
            <RowLabel unit="m" title="Niveau de la mer, et sens de la marée">
              Marée
            </RowLabel>
            <td colSpan={points.length} className="border-b border-line p-0">
              <TideCurve points={points} colWidth={colWidth} />
            </td>
          </tr>

          <tr>
            <RowLabel unit="°C" title="Température de l'eau">
              Eau
            </RowLabel>
            {points.map((point) => (
              <td
                key={point.ts}
                className={cellTone(
                  point,
                  "border-b border-line text-center text-[14px] font-medium text-ink-2",
                )}
              >
                {num(point.water_temperature_c, 0)}
              </td>
            ))}
          </tr>

          {/* ── Score : la ligne du bas, et la seule aux couleurs 1 → 5 ─ */}
          <tr>
            <RowLabel title="Note prévue, de 1 à 5">Note</RowLabel>
            {points.map((point) => {
              const usable = point.daylight && point.score !== null;
              const isBest = days.some((day) => day.bestTs === point.ts);
              const selected = point.ts === selectedTs;

              if (!usable) {
                return (
                  <td key={point.ts} className="p-px">
                    <span
                      aria-hidden
                      className="flex h-touch items-center justify-center rounded-cell border border-line bg-soft text-[12px] text-mute"
                    >
                      {point.daylight ? "" : "·"}
                    </span>
                  </td>
                );
              }

              return (
                <td key={point.ts} className="p-px">
                  <button
                    type="button"
                    onClick={() => onSelect(point.ts)}
                    aria-pressed={selected}
                    aria-label={`${dayLabel(point.ts)} ${new Date(
                      point.ts,
                    ).getHours()} h, note ${num(point.score, 1)} sur 5`}
                    className={`flex h-touch w-full items-center justify-center rounded-cell text-[15px] font-bold ${scoreClass(
                      point.score_level,
                    )} ${isBest ? "ring-2 ring-accent" : ""} ${
                      selected && !isBest ? "ring-2 ring-ink" : ""
                    }`}
                  >
                    {num(point.score, 1)}
                  </button>
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export { COL_WIDTH, DESKTOP_COL_WIDTH, LABEL_WIDTH };
