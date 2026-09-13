"use client";

import { useQuery } from "@tanstack/react-query";

import { DirectionArrow } from "@/components/surf/DirectionArrow";
import { IconBack } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import {
  clockLabel,
  coefficientLabel,
  fullDayLabel,
  num,
  scoreClass,
  signed,
  tideLabel,
  windSideLabel,
} from "@/lib/format";

/**
 * **Le détail d'un créneau**, plein cadre.
 *
 * C'est le **seul** endroit du produit où les directions passent en degrés et
 * en lettres. Partout ailleurs elles sont des flèches, parce qu'on lit un
 * tableau à bout de bras et qu'une flèche se lit sans traduire. Ici on ne
 * balaie plus, on comprend : d'où vient la houle *par rapport au spot*,
 * combien de nœuds de vent viennent vraiment de la terre, et ce qui a changé
 * depuis qu'on a regardé hier soir.
 *
 * L'écart avec le run de la veille au soir est le bénéfice visible de
 * `run_ts` : sans historisation des runs, cette section n'existerait pas —
 * et « la houle de demain est annoncée 30 cm plus haute qu'hier soir » est
 * souvent l'information qui décide de la journée.
 */

/** Les écarts qu'on montre, dans l'ordre de ce qui décide une session. */
const DELTA_ROWS: {
  key: string;
  label: string;
  decimals: number;
  unit: string;
  direction?: boolean;
}[] = [
  { key: "wave_height_m", label: "Houle", decimals: 2, unit: " m" },
  { key: "wave_period_s", label: "Période", decimals: 1, unit: " s" },
  {
    key: "wave_direction_deg",
    label: "Direction de houle",
    decimals: 0,
    unit: "°",
    direction: true,
  },
  { key: "wind_speed_kt", label: "Vent", decimals: 1, unit: " kt" },
  { key: "wind_gust_kt", label: "Rafales", decimals: 1, unit: " kt" },
  {
    key: "wind_direction_deg",
    label: "Direction du vent",
    decimals: 0,
    unit: "°",
    direction: true,
  },
];

function Row({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-t border-line py-2.5">
      <dt className="shrink-0">
        <span className="block text-[12px] font-semibold uppercase tracking-wide text-mute">
          {label}
        </span>
        {hint ? (
          <span className="mt-0.5 block max-w-[170px] text-[11px] leading-tight text-mute">
            {hint}
          </span>
        ) : null}
      </dt>
      <dd className="tabular text-right text-[15px] font-medium text-ink">
        {children}
      </dd>
    </div>
  );
}

export function SlotDetailScreen({
  slug,
  ts,
  onClose,
  variant = "screen",
}: {
  slug: string;
  ts: string;
  onClose: () => void;
  /**
   * `panel` : rendu dans la colonne de droite de l'écran Surf, à côté du
   * tableau, sur desktop (décidé le 13/09). Le contenu ne change pas — c'est
   * le même créneau et les mêmes chiffres — seule la boîte change : pas de
   * `<main>` (il y en a déjà un sur la page), une bordure, et un libellé de
   * fermeture qui dit « fermer » plutôt que « retour », puisqu'on ne quitte
   * rien.
   */
  variant?: "screen" | "panel";
}) {
  const { data, isPending, error } = useQuery({
    queryKey: ["spot-slot", slug, ts],
    queryFn: () => api.spotSlot(slug, ts),
  });

  const panel = variant === "panel";
  const Frame = panel ? "div" : "main";
  const frameClass = panel
    ? "overflow-hidden rounded-card border border-line bg-card pb-6"
    : "pb-10";
  const backLabel = panel ? "Fermer le détail" : "Retour au tableau";

  if (isPending) {
    return (
      <Frame className={`${frameClass} px-5 py-10`}>
        <p className="text-[14px] text-mute">Lecture du créneau…</p>
      </Frame>
    );
  }

  if (error || !data) {
    return (
      <Frame className={`${frameClass} px-5 py-10 text-center`}>
        <p className="text-[16px] text-ink">Créneau indisponible.</p>
        <button
          type="button"
          onClick={onClose}
          className="mt-4 min-h-touch rounded-button border border-line bg-card px-5 text-[15px] font-semibold text-ink-2"
        >
          {backLabel}
        </button>
      </Frame>
    );
  }

  const { point, spot } = data;
  const side = windSideLabel(point.wind_offshore_kt);
  const deltas = DELTA_ROWS.filter((row) => data.delta[row.key] !== undefined);

  return (
    <Frame className={frameClass}>
      <header className="flex items-center gap-3 px-5 pb-1 pt-4">
        <button
          type="button"
          onClick={onClose}
          aria-label={backLabel}
          className="-ml-2 flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-ink-2"
        >
          <IconBack className="h-5 w-5" />
        </button>
        <p className="truncate text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          {spot.name}
        </p>
      </header>

      {/* Une seule information en grand : la note, et l'heure qu'elle qualifie. */}
      <section className="flex items-center gap-4 px-5 pb-5 pt-2">
        <p
          className={`tabular flex h-[96px] w-[96px] shrink-0 flex-col items-center justify-center rounded-card ${scoreClass(
            point.score_level,
          )}`}
        >
          <span className="font-display text-[44px] font-bold leading-none">
            {num(point.score, 1)}
          </span>
          <span className="text-[12px] font-semibold opacity-80">/ 5</span>
        </p>
        <div className="min-w-0">
          <p className="font-display text-[32px] font-bold leading-none tracking-tight text-ink">
            {clockLabel(point.ts)}
          </p>
          <p className="mt-1.5 text-[15px] font-semibold text-ink-2">
            {fullDayLabel(point.ts)}
          </p>
          {point.reasons.length > 0 ? (
            <p className="mt-1.5 text-[13px] leading-snug text-mute">
              {point.reasons.join(" · ")}
            </p>
          ) : null}
        </div>
      </section>

      {/* ── Houle ─────────────────────────────────────────────────────── */}
      <section className="px-5">
        <h2 className="pb-1 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Houle
        </h2>
        <dl>
          <Row label="Hauteur">{num(point.wave_height_m)} m</Row>
          <Row label="Période" hint="moyenne — la seule que sert MFWAM">
            {num(point.wave_period_s, 0)} s
          </Row>
          <Row
            label="Énergie"
            hint="0,49 × H² × T, en kJ/s par mètre de crête (kW/m)"
          >
            {point.wave_energy_kj === null ? "—" : num(point.wave_energy_kj, 1)}{" "}
            kJ
          </Row>
          <Row label="Direction" hint="d'où vient la houle">
            <span className="flex items-center justify-end gap-2">
              <DirectionArrow
                direction={point.wave_direction_deg}
                size={20}
                className="text-ink-2"
              />
              {data.wave_direction_label ?? "—"}
              {point.wave_direction_deg !== null ? (
                <span className="text-mute">
                  {Math.round(point.wave_direction_deg)}°
                </span>
              ) : null}
            </span>
          </Row>

          {/* L'écart à l'orientation du spot — feature 10 du registre. C'est
              elle qui explique qu'une belle houle ne rentre pas ici. */}
          {point.swell_alignment_deg !== null ? (
            <Row
              label="Écart au spot"
              hint={
                data.onshore_direction_label
                  ? `le spot regarde vers le ${data.onshore_direction_label}`
                  : undefined
              }
            >
              {Math.round(point.swell_alignment_deg)}°
              <span className="ml-2 text-mute">
                {point.swell_alignment_deg <= 30
                  ? "pile en face"
                  : point.swell_alignment_deg <= 60
                    ? "de biais"
                    : point.swell_alignment_deg <= 90
                      ? "très de biais"
                      : "derrière la terre"}
              </span>
            </Row>
          ) : null}

          {point.secondary_swell_height_m !== null &&
          point.secondary_swell_height_m > 0.05 ? (
            <Row label="2ᵉ houle" hint="train secondaire">
              <span className="flex items-center justify-end gap-2">
                <DirectionArrow
                  direction={point.secondary_swell_direction_deg}
                  size={18}
                  className="text-ink-2"
                />
                {num(point.secondary_swell_height_m)} m ·{" "}
                {num(point.secondary_swell_period_s, 0)} s
                {data.secondary_swell_direction_label ? (
                  <span className="text-mute">
                    {data.secondary_swell_direction_label}
                  </span>
                ) : null}
              </span>
            </Row>
          ) : null}
        </dl>
      </section>

      {/* ── Vent ──────────────────────────────────────────────────────── */}
      <section className="px-5 pt-5">
        <h2 className="pb-1 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Vent
        </h2>
        <dl>
          <Row label="Moyen">{num(point.wind_speed_kt, 0)} kt</Row>
          <Row label="Rafales">{num(point.wind_gust_kt, 0)} kt</Row>
          <Row label="Direction" hint="d'où vient le vent">
            <span className="flex items-center justify-end gap-2">
              <DirectionArrow
                direction={point.wind_direction_deg}
                size={20}
                className="text-ink-2"
              />
              {data.wind_direction_label ?? "—"}
              {point.wind_direction_deg !== null ? (
                <span className="text-mute">
                  {Math.round(point.wind_direction_deg)}°
                </span>
              ) : null}
            </span>
          </Row>
          {/* Feature 11 du registre : la projection du vent sur l'axe
              perpendiculaire à la côte. Un side-shore donne zéro, ce qui est
              exactement ce qu'il faut lire. */}
          {point.wind_offshore_kt !== null ? (
            <Row
              label="Composante"
              hint="projetée sur l'axe de la côte ; positive = de terre"
            >
              {signed(point.wind_offshore_kt, 1, " kt")}
              {side ? <span className="ml-2 text-mute">{side}</span> : null}
            </Row>
          ) : null}
        </dl>
      </section>

      {/* ── Marée, eau, soleil ────────────────────────────────────────── */}
      <section className="px-5 pt-5">
        <h2 className="pb-1 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Mer et lumière
        </h2>
        <dl>
          <Row label="Marée">
            {tideLabel(point.tide_rising)}
            {point.tide_position !== null ? (
              <span className="ml-2 text-mute">
                {Math.round(point.tide_position * 100)} % du marnage
              </span>
            ) : null}
          </Row>
          {/* Le coefficient, enfin (décidé le 13/09). Il se calcule au port de
              référence de Brest, et il vaut pour toute la côte : c'est sa
              définition. Le « ≈ » vient de l'écart mesuré contre l'annuaire
              SHOM — six points au pire (`docs/COEFFICIENT-MAREE.md`). */}
          {data.tide_coefficient !== null ? (
            <Row
              label="Coefficient"
              hint={
                data.tide_coefficient_approximate
                  ? "calculé à Brest, à quelques points près"
                  : "calculé à Brest, national par définition"
              }
            >
              {coefficientLabel(
                data.tide_coefficient,
                data.tide_coefficient_approximate,
              )}
            </Row>
          ) : null}
          <Row label="Marnage" hint="du jour — la grandeur mesurée ici">
            {point.tide_range_m === null ? "—" : `${num(point.tide_range_m)} m`}
          </Row>
          <Row label="Niveau">
            {point.sea_level_m === null ? "—" : `${num(point.sea_level_m)} m`}
          </Row>
          <Row label="Eau">{num(point.water_temperature_c, 0)} °C</Row>
          {data.sunrise && data.sunset ? (
            <Row label="Soleil">
              {clockLabel(data.sunrise)} – {clockLabel(data.sunset)}
            </Row>
          ) : null}
        </dl>
      </section>

      {/* ── Ce qui a changé depuis hier soir ──────────────────────────── */}
      <section className="px-5 pt-5">
        <h2 className="pb-1 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Cette prévision
        </h2>
        <dl>
          <Row label="Émise" hint="heure à laquelle on a capté ce run">
            {data.run_ts
              ? `${fullDayLabel(data.run_ts)} ${clockLabel(data.run_ts)}`
              : "—"}
          </Row>
          {data.previous_run_ts ? (
            <Row label="Comparée à" hint="le run de la veille, 20 h locale">
              {fullDayLabel(data.previous_run_ts)}{" "}
              {clockLabel(data.previous_run_ts)}
            </Row>
          ) : null}
        </dl>

        {deltas.length > 0 ? (
          <ul className="mt-3 overflow-hidden rounded-card border border-line bg-card">
            {deltas.map((row) => {
              const value = data.delta[row.key];
              const still = Math.abs(value) < (row.direction ? 5 : 0.05);
              return (
                <li
                  key={row.key}
                  className="flex items-center justify-between gap-3 border-b border-line px-4 py-2 last:border-0"
                >
                  <span className="text-[14px] text-ink-2">{row.label}</span>
                  <span
                    className={`tabular text-[15px] font-semibold ${
                      still ? "text-mute" : "text-ink"
                    }`}
                  >
                    {signed(value, row.decimals, row.unit)}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="mt-3 rounded-card border border-dashed border-line bg-soft px-4 py-3 text-[13px] leading-snug text-ink-2">
            {data.previous_run_ts
              ? "Rien n'a bougé depuis hier soir."
              : "Pas encore de run de la veille pour ce spot : l'écart apparaîtra dès la deuxième journée d'ingestion."}
          </p>
        )}
      </section>
    </Frame>
  );
}
