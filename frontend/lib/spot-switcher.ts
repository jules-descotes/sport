import type { Spot, SpotHit } from "@/lib/types";

/**
 * La barre de passage d'un spot maison à l'autre, sur l'écran Surf.
 *
 * Surf n'avait qu'une loupe : changer de spot voulait dire ouvrir le
 * sélecteur, taper trois lettres, choisir. Un geste juste pour aller chercher
 * un spot du catalogue ; trois de trop pour faire l'aller-retour entre La
 * Gravière et Parlementia un matin de doute, ce qui est **le** geste de
 * l'écran.
 *
 * La liste des pastilles est calculée ici plutôt que dans le composant, pour
 * une raison précise : elle a deux cas limites qui ne se voient pas à l'œil
 * sur la maquette, et qui feraient l'un une pastille absente, l'autre une
 * pastille en double.
 */

export interface SwitcherEntry {
  id: number;
  slug: string;
  name: string;
  /** Le spot affiché en ce moment. */
  active: boolean;
  /** Le favori principal (`profiles.home_spot_id`) — celui de l'écran Jour. */
  principal: boolean;
  /** Vrai pour un spot ouvert de passage, qui n'est pas dans les favoris. */
  visiting: boolean;
}

/**
 * Les pastilles à afficher, dans l'ordre.
 *
 * Les favoris viennent dans **l'ordre choisi par Jules** (Profil → Favoris) :
 * c'est le même ordre qui départage les annonces de Jour, et deux ordres
 * différents pour la même liste se paieraient en hésitation à chaque fois.
 *
 * Deux cas limites, et c'est pour eux que cette fonction existe :
 *
 * 1. **Le spot ouvert n'est pas un favori.** On vient de le chercher dans le
 *    catalogue. Il prend la première pastille, marquée `visiting` : sans elle,
 *    la barre montrerait cinq spots dont aucun n'est celui qu'on lit, et le
 *    retour se ferait par le bouton du navigateur.
 * 2. **Il est un favori.** Alors il ne prend pas de pastille en plus — il est
 *    déjà dans la liste, simplement `active`.
 *
 * Renvoie une liste vide quand il n'y a rien à choisir : un seul favori et
 * c'est lui qu'on regarde. Une barre à une pastille, qui plus est celle de la
 * page en cours, occupe de la hauteur sans offrir un seul geste.
 */
export function switcherEntries(
  favorites: readonly SpotHit[],
  current: Pick<Spot, "id" | "slug" | "name"> | null | undefined,
  homeSpotId: number | null,
): SwitcherEntry[] {
  const entries: SwitcherEntry[] = favorites.map((spot) => ({
    id: spot.id,
    slug: spot.slug,
    name: spot.name,
    active: current?.id === spot.id,
    principal: spot.id === homeSpotId,
    visiting: false,
  }));

  if (current && !favorites.some((spot) => spot.id === current.id)) {
    entries.unshift({
      id: current.id,
      slug: current.slug,
      name: current.name,
      active: true,
      principal: current.id === homeSpotId,
      visiting: true,
    });
  }

  return entries.length > 1 ? entries : [];
}
