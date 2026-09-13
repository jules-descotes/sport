"use client";

import { useEffect, useState } from "react";

import { IconRefresh } from "@/components/ui/Icons";
import { ageLabel } from "@/lib/forecast-cache";
import { usePullToRefresh } from "@/lib/usePullToRefresh";

/**
 * L'âge de la prévision affichée, et le geste pour la forcer.
 *
 * Sobre par construction : une ligne de douze pixels et un bouton de
 * rafraîchissement. C'est une information de contexte, pas une alerte — une
 * prévision d'il y a une heure quarante est **une bonne prévision**, et
 * l'afficher en rouge donnerait envie de la rafraîchir pour rien.
 *
 * Le bouton existe aussi sur mobile : le « tirer pour rafraîchir » est le geste
 * naturel, mais il n'est découvrable que par hasard, et il ne marche pas quand
 * on a déjà fait défiler l'écran.
 */
interface FreshnessProps {
  cachedAt: number | null;
  isFetching: boolean;
  onRefresh: () => void;
  /** Vrai quand le back complète encore la prévision derrière. */
  refreshing?: boolean;
  className?: string;
}

export function Freshness({
  cachedAt,
  isFetching,
  onRefresh,
  refreshing = false,
  className = "",
}: FreshnessProps) {
  // L'âge se réécrit tout seul : un écran laissé ouvert pendant la séance de
  // photos du matin afficherait sinon « à l'instant » deux heures plus tard.
  const [, tick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => tick((value) => value + 1), 60_000);
    return () => clearInterval(timer);
  }, []);

  const label = isFetching
    ? "mise à jour…"
    : refreshing
      ? "complétée en arrière-plan…"
      : cachedAt === null
        ? ""
        : `prévision reçue ${ageLabel(cachedAt)}`;

  return (
    <div
      className={`flex items-center justify-between gap-3 text-[12px] text-mute ${className}`}
    >
      <span aria-live="polite">{label}</span>
      <button
        type="button"
        onClick={onRefresh}
        disabled={isFetching}
        aria-label="Rafraîchir la prévision"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-pill border border-line bg-card text-ink-2 disabled:opacity-40"
      >
        <IconRefresh className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
      </button>
    </div>
  );
}

/**
 * L'indicateur du geste « tirer pour rafraîchir », en haut de l'écran.
 *
 * Il pousse le contenu vers le bas au lieu de le recouvrir : c'est ce qui rend
 * le geste physique, et ce qui évite de masquer la première ligne — qui est
 * précisément celle qu'on regarde.
 */
export function PullToRefresh({
  onRefresh,
  enabled = true,
}: {
  onRefresh: () => void;
  enabled?: boolean;
}) {
  const pull = usePullToRefresh(onRefresh, enabled);
  if (pull.distance === 0) return null;

  return (
    <div
      aria-hidden
      className="flex items-end justify-center overflow-hidden"
      style={{ height: pull.distance }}
    >
      <span
        className={`flex items-center gap-2 pb-2 text-[12px] font-semibold ${
          pull.armed ? "text-accent" : "text-mute"
        }`}
      >
        <IconRefresh className="h-4 w-4" />
        {pull.armed ? "Lâche pour rafraîchir" : "Tire pour rafraîchir"}
      </span>
    </div>
  );
}
