"use client";

import { num } from "@/lib/format";
import type { Calibration, CalibrationBucket } from "@/lib/types";

/**
 * Ce que trente jours de mesures disent du modèle, par délai de prévision.
 *
 * **Thin marks, une seule teinte, jamais de rouge.** Ce n'est pas un bulletin
 * de notes : un modèle de vagues qui se trompe de 8 % à 24 h fait son travail.
 * La barre dit une amplitude et un sens, rien de plus — et elle part du centre
 * parce qu'un biais a un signe.
 *
 * Une tranche sans assez de paires affiche son compte et pas un chiffre. Un
 * biais calculé sur huit mesures se lirait comme un réglage fin là où il n'y a
 * que du bruit, et c'est précisément ce qu'on écrit quand on démarre.
 *
 * Le sens du biais n'est **pas** recalculé ici : les phrases viennent du
 * serveur. Écrire « sous-estime » à deux endroits finirait un jour par en
 * inverser un seul des deux.
 */

interface CalibrationCardProps {
  calibration: Calibration;
  /** Unité affichée à côté du biais — « m » pour la hauteur, « s » pour la période. */
  unit?: string;
  /** Quelle grandeur montrer. La hauteur par défaut : c'est celle qu'on lit. */
  quantity?: "hm0" | "period";
  className?: string;
}

/** Largeur de la barre, en % de la demi-largeur. Plafonnée à 100. */
function barWidth(bucket: CalibrationBucket): number {
  if (bucket.bias_pct === null) return 0;
  // 25 % d'écart remplit la barre. Au-delà, ce n'est plus une nuance.
  return Math.min(100, Math.abs(bucket.bias_pct) * 4);
}

function BucketRow({
  bucket,
  unit,
}: {
  bucket: CalibrationBucket;
  unit: string;
}) {
  const width = barWidth(bucket);
  const positive = (bucket.bias ?? 0) > 0;

  return (
    <li className="flex items-center gap-3 py-1.5">
      <span className="w-16 shrink-0 text-xs tabular-nums text-mute">
        {bucket.bucket}
      </span>

      <span className="relative h-1.5 flex-1 rounded-pill bg-soft">
        {/* Le zéro est matérialisé : sans lui, une barre courte à droite et
            une barre courte à gauche se ressemblent trop. */}
        <span className="absolute inset-y-[-3px] left-1/2 w-px bg-line" />
        {bucket.bias !== null ? (
          <span
            className="absolute inset-y-0 rounded-pill bg-accent/70"
            style={
              positive
                ? { left: "50%", width: `${width / 2}%` }
                : { right: "50%", width: `${width / 2}%` }
            }
          />
        ) : null}
      </span>

      <span className="w-24 shrink-0 text-right text-xs tabular-nums text-ink-2">
        {bucket.bias === null ? (
          <span className="text-mute">
            {bucket.pairs} mesure{bucket.pairs > 1 ? "s" : ""}
          </span>
        ) : (
          <>
            {bucket.bias > 0 ? "+" : ""}
            {num(bucket.bias, 2)} {unit}
          </>
        )}
      </span>
    </li>
  );
}

export function CalibrationCard({
  calibration,
  unit = "m",
  quantity = "hm0",
  className,
}: CalibrationCardProps) {
  const buckets =
    quantity === "period" ? calibration.period : calibration.hm0;
  const usable = buckets.some((bucket) => bucket.bias !== null);

  return (
    <section
      className={`rounded-card border border-line bg-card p-4 ${className ?? ""}`}
      aria-label="Écart entre prévision et mesure"
    >
      <header>
        <h2 className="font-display text-base font-semibold uppercase tracking-wide text-ink">
          Prévu contre mesuré
        </h2>
        <p className="mt-0.5 text-xs text-mute">
          {calibration.station_id
            ? `bouée ${calibration.station_id} · `
            : ""}
          {calibration.window_days} derniers jours · {calibration.pairs}{" "}
          comparaison{calibration.pairs > 1 ? "s" : ""}
        </p>
      </header>

      {usable ? (
        <>
          <ul className="mt-3">
            {buckets.map((bucket) => (
              <BucketRow key={bucket.bucket} bucket={bucket} unit={unit} />
            ))}
          </ul>
          {calibration.sentences.length > 0 ? (
            <p className="mt-2 border-t border-line pt-2 text-sm text-ink-2">
              {calibration.sentences[0]}
            </p>
          ) : null}
          <p className="mt-2 text-xs text-mute">
            Positif = le modèle annonce moins que ce que la bouée mesure. Rien
            n&apos;est corrigé : on mesure d&apos;abord.
          </p>
        </>
      ) : (
        <p className="mt-3 text-sm text-mute">
          Pas encore assez de mesures pour dire quoi que ce soit. La bouée
          alimente la comparaison heure par heure ; laisse-lui quelques jours.
        </p>
      )}
    </section>
  );
}
