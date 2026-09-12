"use client";

import Link from "next/link";

import { SlotBand } from "@/components/surf/SlotBand";
import {
  compass,
  fullDayLabel,
  highTideAfter,
  num,
  scoreClass,
  tideLabel,
  windSideLabel,
} from "@/lib/format";
import type { Recommendation, Slot } from "@/lib/types";

/**
 * Le bloc de mer de l'écran Jour — un vrai tableau de bord, pas un verdict.
 *
 * Onze informations, et il se lit en deux secondes parce qu'**une seule est en
 * grand** : la note du meilleur créneau. Tout le reste est un tableau de
 * libellés et de valeurs, à chasse fixe, aligné sur une seule colonne — c'est
 * ce qui permet de sauter directement à la ligne qu'on cherche.
 *
 * Rendu plein cadre (V4 de `docs/DESIGN-EXPLORATION.md`), lisible au soleil,
 * à bout de bras, une main mouillée.
 */

/** Écart de note en dessous duquel un créneau appartient encore à la fenêtre. */
const WINDOW_TOLERANCE = 0.5;

function localHour(iso: string): number {
  return new Date(iso).getHours();
}

function isSameLocalDay(iso: string, day: Date): boolean {
  const date = new Date(iso);
  return (
    date.getFullYear() === day.getFullYear() &&
    date.getMonth() === day.getMonth() &&
    date.getDate() === day.getDate()
  );
}

/**
 * La fenêtre autour du meilleur créneau : « 09 – 11 h ».
 *
 * On étend de part et d'autre tant que la note reste à une demi-note du
 * sommet. Annoncer une heure pile serait faux — la mer ne bascule pas à 9 h 00
 * — et annoncer la journée entière ne servirait à rien.
 */
function bestWindow(slots: Slot[], best: Slot): string {
  const sameDay = slots
    .filter((slot) => isSameLocalDay(slot.ts, new Date(best.ts)) && slot.daylight)
    .sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());

  const index = sameDay.findIndex((slot) => slot.ts === best.ts);
  if (index < 0) return `${localHour(best.ts)} h`;

  const floor = best.score - WINDOW_TOLERANCE;
  let start = index;
  let end = index;
  while (start > 0 && sameDay[start - 1].score >= floor) start -= 1;
  while (end < sameDay.length - 1 && sameDay[end + 1].score >= floor) end += 1;

  const from = localHour(sameDay[start].ts);
  // Un créneau horaire couvre son heure : la fenêtre finit une heure après le
  // dernier créneau retenu.
  const to = localHour(sameDay[end].ts) + 1;
  if (to - from <= 1) return `${from} h`;
  return `${String(from).padStart(2, "0")} – ${String(to).padStart(2, "0")} h`;
}

function bestOfDay(slots: Slot[], day: Date): Slot | null {
  const usable = slots.filter(
    (slot) => slot.daylight && isSameLocalDay(slot.ts, day),
  );
  if (usable.length === 0) return null;
  return usable.reduce((top, slot) => (slot.score > top.score ? slot : top));
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-t border-line py-2.5">
      <dt className="shrink-0 text-[12px] font-semibold uppercase tracking-wide text-mute">
        {label}
      </dt>
      <dd className="tabular text-right text-[15px] font-medium text-ink">
        {children}
      </dd>
    </div>
  );
}

export function SeaBlock({ data }: { data: Recommendation }) {
  const spot = data.home_spot;
  const entry = data.spots.find((item) => item.spot.id === spot?.id);
  const slots = entry?.slots ?? [];

  const now = new Date();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);

  // Le créneau vedette est celui de la prochaine fenêtre de jour ; s'il est
  // déjà passé (on ouvre l'app le soir), on retombe sur le meilleur d'aujourd'hui.
  const best =
    data.headline && isSameLocalDay(data.headline.ts, now)
      ? data.headline
      : (bestOfDay(slots, now) ?? data.headline);
  const nextDay = bestOfDay(slots, tomorrow);

  if (!spot) return null;

  if (!best) {
    return (
      <section className="px-5">
        <article className="rounded-card border border-line bg-card px-5 py-6">
          <h2 className="font-display text-[24px] leading-none font-semibold uppercase text-ink">
            {spot.name}
          </h2>
          <p className="mt-3 text-[15px] text-ink-2">
            Pas encore de prévision pour ce spot. Elle se récupère à la première
            ouverture — laisse-lui quelques secondes, puis reviens.
          </p>
        </article>
      </section>
    );
  }

  const side = windSideLabel(best.wind_offshore_kt);
  const highTide = highTideAfter(slots, now);

  return (
    <section className="px-5">
      <article className="overflow-hidden rounded-card border border-line bg-card">
        <header className="flex items-baseline justify-between gap-3 px-5 pt-5">
          <h2 className="min-w-0 truncate font-display text-[24px] leading-none font-semibold uppercase text-ink">
            {spot.name}
          </h2>
          {data.run_ts ? (
            <p className="tabular shrink-0 text-[11px] text-mute">
              prévision de {localHour(data.run_ts)} h
            </p>
          ) : null}
        </header>

        {/* La seule information en grand de tout l'écran. */}
        <div className="flex items-center gap-4 px-5 pt-4">
          <p
            className={`tabular flex h-[104px] w-[104px] shrink-0 flex-col items-center justify-center rounded-card ${scoreClass(
              best.level,
            )}`}
          >
            <span className="font-display text-[48px] leading-none font-bold">
              {num(best.score, 1)}
            </span>
            <span className="text-[12px] font-semibold opacity-80">/ 5</span>
          </p>
          <div className="min-w-0">
            <p className="font-display text-[34px] leading-none font-bold tracking-tight text-ink">
              {bestWindow(slots, best)}
            </p>
            {/* Le verdict du créneau affiché, et pas celui du back : le soir,
                le créneau vedette retombe sur le meilleur d'aujourd'hui, et
                les deux ne coïncident plus. */}
            <p className="mt-2 text-[15px] font-semibold text-ink-2">
              {best.verdict}
            </p>
            {best.reasons.length > 0 ? (
              <p className="mt-1 text-[13px] leading-snug text-mute">
                {best.reasons.slice(0, 2).join(" · ")}
              </p>
            ) : null}
          </div>
        </div>

        <dl className="mt-4 px-5">
          <Row label="Houle">
            {num(best.wave_height_m)} m · {num(best.wave_period_s, 0)} s ·{" "}
            {compass(best.wave_direction_deg)}
            {best.wave_direction_deg !== null ? (
              <span className="text-mute">
                {" "}
                {Math.round(best.wave_direction_deg)}°
              </span>
            ) : null}
          </Row>
          <Row label="Vent">
            {compass(best.wind_direction_deg)} {num(best.wind_speed_kt, 0)} kt
            {best.wind_gust_kt !== null ? (
              <span className="text-mute">
                {" "}
                · raf. {num(best.wind_gust_kt, 0)}
              </span>
            ) : null}
            {side ? <span className="text-ink-2"> · {side}</span> : null}
          </Row>
          <Row label="Marée">
            {tideLabel(best.tide_rising)}
            {highTide ? (
              <span className="text-mute">
                {" "}
                · PM {localHour(highTide)} h
              </span>
            ) : null}
            {best.tide_range_m !== null ? (
              <span className="text-mute">
                {" "}
                · marnage {num(best.tide_range_m)} m
              </span>
            ) : null}
          </Row>
          <Row label="Eau">{num(best.water_temperature_c, 0)} °C</Row>
        </dl>

        <div className="border-t border-line px-5 pt-3">
          <SlotBand
            slots={slots}
            day={now}
            bestTs={best.ts}
            label="Les huit créneaux d'aujourd'hui"
          />
        </div>

        {/* Deux lignes qui évitent d'ouvrir l'écran Mer neuf fois sur dix. */}
        <footer className="mt-4 border-t border-line bg-soft px-5 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-mute">
            {fullDayLabel(tomorrow.toISOString())}
          </p>
          {nextDay ? (
            <p className="tabular mt-1 text-[14px] leading-snug text-ink-2">
              <span
                className={`mr-2 inline-block rounded-chip px-1.5 py-0.5 text-[13px] font-semibold ${scoreClass(
                  nextDay.level,
                )}`}
              >
                {num(nextDay.score, 1)}
              </span>
              à {localHour(nextDay.ts)} h · {nextDay.line}
            </p>
          ) : (
            <p className="mt-1 text-[14px] text-mute">Pas encore de prévision.</p>
          )}
        </footer>
      </article>

      <Link
        href={`/mer?spot=${spot.slug}`}
        className="mt-3 flex min-h-touch items-center justify-center rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
      >
        Les cinq jours, et les autres spots
      </Link>
    </section>
  );
}
