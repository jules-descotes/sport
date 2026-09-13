"use client";

import { useEffect, useRef } from "react";

import { IconStar } from "@/components/ui/Icons";
import { switcherEntries } from "@/lib/spot-switcher";
import type { Spot, SpotHit } from "@/lib/types";

/**
 * **Passer d'un spot maison à l'autre, en un tap** (13/09).
 *
 * L'écran Surf ouvrait sur le favori principal et n'offrait qu'une loupe :
 * changer de spot demandait d'ouvrir le sélecteur, de taper, de choisir. C'est
 * le bon geste pour aller chercher un spot du catalogue une fois par an, et
 * trois de trop pour l'aller-retour entre deux spots maison un matin de doute
 * — qui est **le** geste de cet écran.
 *
 * Des pastilles, pas un menu déroulant : un menu cache ses options jusqu'à ce
 * qu'on le touche, et on ne compare pas ce qu'on ne voit pas. À vingt favoris
 * au maximum, la barre défile ; à deux ou trois, elle tient d'un coup d'œil.
 *
 * La loupe de l'en-tête ne bouge pas et n'est pas doublée ici : les pastilles
 * servent les spots maison, la loupe sert les quatre mille cinq cents autres.
 * Une seconde loupe en fin de barre serait hors écran neuf fois sur dix, au
 * bout d'une liste qui défile — un bouton qu'on ne trouve qu'en cherchant.
 */
export function SpotSwitcher({
  favorites,
  current,
  homeSpotId,
  onSelect,
}: {
  favorites: readonly SpotHit[];
  current: Pick<Spot, "id" | "slug" | "name"> | null | undefined;
  homeSpotId: number | null;
  onSelect: (slug: string) => void;
}) {
  const strip = useRef<HTMLDivElement>(null);
  const entries = switcherEntries(favorites, current, homeSpotId);
  const activeId = entries.find((entry) => entry.active)?.id ?? null;

  /**
   * Ramène la pastille active sous les yeux.
   *
   * On calcule le `scrollLeft` de la barre à la main plutôt que d'appeler
   * `scrollIntoView` : celui-ci fait remonter **tous** les conteneurs
   * défilants, page comprise, et le tableau horaire sauterait à chaque
   * changement de spot. Ici, seule la barre bouge.
   */
  useEffect(() => {
    const bar = strip.current;
    const chip = bar?.querySelector<HTMLElement>("[data-active='true']");
    if (!bar || !chip) return;

    const centred = chip.offsetLeft - (bar.clientWidth - chip.offsetWidth) / 2;
    bar.scrollTo({ left: Math.max(0, centred), behavior: "instant" });
  }, [activeId]);

  if (entries.length === 0) return null;

  return (
    <nav aria-label="Spots maison" className="pb-3">
      <div
        ref={strip}
        className="flex gap-2 overflow-x-auto px-5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {entries.map((entry) => (
          <button
            key={entry.id}
            type="button"
            data-active={entry.active}
            aria-current={entry.active ? "page" : undefined}
            onClick={() => onSelect(entry.slug)}
            className={`flex min-h-touch shrink-0 items-center gap-1.5 rounded-pill border px-4 text-[14px] font-semibold ${
              entry.active
                ? "border-ink bg-ink text-bg"
                : "border-line bg-card text-ink-2"
            }`}
          >
            {entry.principal ? (
              <IconStar
                className={`h-3.5 w-3.5 ${entry.active ? "" : "text-accent"}`}
                filled
              />
            ) : null}
            {entry.name}
            {/* Un spot de passage se dit tel quel : sans ce point, on croirait
                que le catalogue vient d'entrer dans les favoris. */}
            {entry.visiting ? (
              <span
                className={`text-[11px] font-normal ${
                  entry.active ? "opacity-70" : "text-mute"
                }`}
              >
                · de passage
              </span>
            ) : null}
          </button>
        ))}
      </div>
    </nav>
  );
}
