/**
 * Icônes en trait, épaisseur 1,75 px, jamais d'emoji (cf. CLAUDE.md).
 * Dessinées sur une grille 24 : un seul jeu, une seule graisse.
 */
interface IconProps {
  className?: string;
}

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

/** Surf — une houle qui déferle. */
export function IconWave({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M2 16.5c2 0 2.5-2 4.5-2s2.5 2 4.5 2 2.5-2 4.5-2 2.5 2 4.5 2" />
      <path d="M4.5 11.5c1.6-3.6 4.6-5.5 8-5.5 2.6 0 4.6 1.1 5.8 2.6" />
      <path d="M18.3 8.6 15 9.4" />
    </svg>
  );
}

/** Jour — le soleil sur l'horizon : la journée en cours. */
export function IconDay({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="12.5" r="3.6" />
      <path d="M12 4v2M12 19v2M4.9 5.4l1.4 1.4M17.7 18.2l1.4 1.4M3 12.5h2M19 12.5h2M4.9 19.6l1.4-1.4M17.7 6.8l1.4-1.4" />
    </svg>
  );
}

/** Corps — silhouette : objectifs, formules, composition. */
export function IconBody({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="5.2" r="2.4" />
      <path d="M12 7.6v7M12 14.6 8.5 20M12 14.6 15.5 20M7.5 10h9" />
    </svg>
  );
}

/** Recherche. */
export function IconSearch({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="11" cy="11" r="6" />
      <path d="m15.5 15.5 4 4" />
    </svg>
  );
}

/** Training — haltère. */
export function IconDumbbell({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 9v6M7 7.5v9M17 7.5v9M20 9v6" />
      <path d="M7 12h10" />
    </svg>
  );
}

/** Nutrition — assiette et couvert. */
export function IconPlate({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="11" cy="12" r="7" />
      <circle cx="11" cy="12" r="3.2" />
      <path d="M20 4v16" />
    </svg>
  );
}

/** Stats — courbe de progression. */
export function IconChart({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 4v15.5h16" />
      <path d="M7.5 15l3.5-4.5 3 2.5L20 7" />
    </svg>
  );
}

/** Déconnexion. */
export function IconLogout({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M14 4h4.5a1.5 1.5 0 0 1 1.5 1.5v13a1.5 1.5 0 0 1-1.5 1.5H14" />
      <path d="M9 8.5 5 12l4 3.5" />
      <path d="M5 12h10" />
    </svg>
  );
}

/** Favori — l'étoile pleine signale un spot maison, donc ingéré en planifié. */
export function IconStar({
  className,
  filled = false,
}: IconProps & { filled?: boolean }) {
  return (
    <svg {...base} className={className} fill={filled ? "currentColor" : "none"}>
      <path d="m12 4 2.4 4.9 5.4.8-3.9 3.8.9 5.4-4.8-2.6-4.8 2.6.9-5.4L4.2 9.7l5.4-.8z" />
    </svg>
  );
}

/** Masquer un spot — œil barré. */
export function IconEyeOff({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 12s3.2-5.5 8-5.5c1.3 0 2.5.4 3.5 1" />
      <path d="M19.2 9.2c.5.6.8 1.2.8 1.2v.1s-3.2 5.5-8 5.5c-1 0-2-.2-2.8-.6" />
      <circle cx="12" cy="11.5" r="2.4" />
      <path d="m4.5 19.5 15-15" />
    </svg>
  );
}

/** Carte — épingle de position. */
export function IconPin({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 21s6.5-6.1 6.5-10.5a6.5 6.5 0 0 0-13 0C5.5 14.9 12 21 12 21Z" />
      <circle cx="12" cy="10.5" r="2.4" />
    </svg>
  );
}

/** Comparateur — grille heures × spots. */
export function IconGrid({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M4 10h16M4 15h16M10 4v16" />
    </svg>
  );
}

/** Webcam. */
export function IconCamera({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 8.5h10.5a1.5 1.5 0 0 1 1.5 1.5v5a1.5 1.5 0 0 1-1.5 1.5H4z" />
      <path d="m16 12.5 4-2.5v7l-4-2.5z" />
    </svg>
  );
}

/** Profil. */
export function IconUser({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 20c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5" />
    </svg>
  );
}

/** Retour. */
export function IconBack({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="m14 5-7 7 7 7" />
    </svg>
  );
}

/** Localisation en cours / recentrer la carte. */
export function IconCrosshair({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="12" r="6.5" />
      <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" />
    </svg>
  );
}

/** Plus — ajouter un spot. */
export function IconPlus({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

/** Planche de surf — le matos. */
export function IconBoard({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 2.5c3.6 3 5.5 6.7 5.5 10.2 0 4.2-2.6 8.8-5.5 8.8s-5.5-4.6-5.5-8.8c0-3.5 1.9-7.2 5.5-10.2Z" />
      <path d="M12 7v10" />
    </svg>
  );
}

/** Horloge — l'heure d'une session. */
export function IconClock({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}

/** Coche — enregistré. */
export function IconCheck({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="m5 12.5 4.5 4.5L19 7" />
    </svg>
  );
}

/** Chevron — déplier une section repliée. */
export function IconChevronDown({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="m6 9.5 6 6 6-6" />
    </svg>
  );
}

/** Chevron de ligne de liste — ouvrir le détail. */
export function IconChevronRight({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="m9.5 5 6.5 7-6.5 7" />
    </svg>
  );
}

/** Corbeille — supprimer. */
export function IconTrash({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4.5 7h15M9.5 7V5.5A1.5 1.5 0 0 1 11 4h2a1.5 1.5 0 0 1 1.5 1.5V7" />
      <path d="M6.5 7v12a1.5 1.5 0 0 0 1.5 1.5h8a1.5 1.5 0 0 0 1.5-1.5V7" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  );
}

/** Moins — le pas négatif du compteur de vagues. */
export function IconMinus({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M5 12h14" />
    </svg>
  );
}

/** Nuage barré — en attente d'envoi, le réseau manque. */
export function IconCloudOff({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M7.5 18.5h9a3.5 3.5 0 0 0 1.1-6.8 5.5 5.5 0 0 0-7.7-4.4" />
      <path d="M7.5 18.5a3.5 3.5 0 0 1-.5-7 5.5 5.5 0 0 1 .6-1.9" />
      <path d="m4 4 16 16" />
    </svg>
  );
}

/** Clé — les jetons d'API du raccourci iPhone. */
export function IconKey({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="8" cy="8" r="3.5" />
      <path d="m10.5 10.5 8 8M16 16l-2 2M19 13l-2.5 2.5" />
    </svg>
  );
}

/** Carnet — l'historique des sessions. */
export function IconLog({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M6 3.5h11A1.5 1.5 0 0 1 18.5 5v15.5H6A1.5 1.5 0 0 1 4.5 19V5A1.5 1.5 0 0 1 6 3.5Z" />
      <path d="M8 8h7M8 12h7M8 16h4" />
    </svg>
  );
}

/** Crayon — modifier une session déjà notée. */
export function IconPencil({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4.5 19.5h3.2L18.4 8.8a1.7 1.7 0 0 0 0-2.4l-.8-.8a1.7 1.7 0 0 0-2.4 0L4.5 16.3z" />
      <path d="m14.5 6.8 2.7 2.7" />
    </svg>
  );
}

/** Filtre — l'historique des sessions par spot, mois ou note. */
export function IconFilter({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 6h16l-6 7v5.5l-4 2V13z" />
    </svg>
  );
}

/** Restaurer — sortir une session de la corbeille. */
export function IconRestore({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4.5 12a7.5 7.5 0 1 0 2.4-5.5" />
      <path d="M4 4v4h4" />
    </svg>
  );
}

/** Rafraîchir — la flèche qui reboucle. Même dessin qu'IconRestore, inversé :
 *  l'une ramène une session, l'autre relance une requête. */
export function IconRefresh({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M19.5 12a7.5 7.5 0 1 1-2.4-5.5" />
      <path d="M20 4v4h-4" />
    </svg>
  );
}

/** Lune — la marée, et le coefficient qui va avec. */
export function IconMoon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />
    </svg>
  );
}

/** Réglages — les critères d'un spot favori. */
export function IconSliders({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="10" cy="17" r="2" />
    </svg>
  );
}

/** Poignée de déplacement — l'ordre des favoris. */
export function IconDrag({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M9 6h.01M9 12h.01M9 18h.01M15 6h.01M15 12h.01M15 18h.01" />
    </svg>
  );
}

/** Flamme — une série de jours consécutifs, sans jugement. */
export function IconFlame({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 3c3 3.5 4.5 6 4.5 8.5a4.5 4.5 0 0 1-9 0C7.5 9 9 6.5 12 3z" />
      <path d="M12 21a3 3 0 0 0 3-3c0-1.5-1-2.5-3-4.5-2 2-3 3-3 4.5a3 3 0 0 0 3 3z" />
    </svg>
  );
}

/** Code-barres — le scan d'un produit au journal de nutrition. */
export function IconBarcode({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 6v12M7.5 6v12M11 6v8M14.5 6v12M18 6v12M20.5 6v8" />
    </svg>
  );
}

/** Balance — la pesée hebdomadaire. */
export function IconScale({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="3" />
      <path d="M8 10.5a4 4 0 0 1 8 0" />
      <path d="M12 10.5 13.6 8" />
    </svg>
  );
}

/** Panier — la liste de courses du menu de la semaine. */
export function IconBasket({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M3.5 9h17l-1.6 9.2a2 2 0 0 1-2 1.8H7.1a2 2 0 0 1-2-1.8z" />
      <path d="M8.5 9 11 4M15.5 9 13 4" />
    </svg>
  );
}

/** Verre d'eau — une habitude courante. */
export function IconWater({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 3.5c3.5 4 5.5 6.6 5.5 9.2a5.5 5.5 0 0 1-11 0c0-2.6 2-5.2 5.5-9.2z" />
    </svg>
  );
}

/** Sommeil. */
export function IconSleep({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />
      <path d="M14 4h4l-4 4h4" />
    </svg>
  );
}

/** Livre — lire, méditer, tenir un carnet. */
export function IconBook({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v15H5.5A1.5 1.5 0 0 1 4 17.5z" />
      <path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H13v15h5.5a1.5 1.5 0 0 0 1.5-1.5z" />
    </svg>
  );
}

/** Feuille — le végétal, ou ce qu'on veut en faire. */
export function IconLeaf({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 20c0-8 5-13 16-13 0 9-5 13-11 13-2.5 0-5-1-5-1z" />
      <path d="M8.5 15.5 19 7" />
    </svg>
  );
}

/** Cœur. */
export function IconHeart({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 20s-7-4.4-7-9a3.8 3.8 0 0 1 7-2.1A3.8 3.8 0 0 1 19 11c0 4.6-7 9-7 9z" />
    </svg>
  );
}

/** Soleil — le matin, la lumière, ce qu'on fait tôt. */
export function IconSun({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4" />
    </svg>
  );
}

/** Porte ouverte, flèche vers l'extérieur — « je ne suis pas chez moi ». */
export function IconAway({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M14 4.5H6.5A1.5 1.5 0 0 0 5 6v12a1.5 1.5 0 0 0 1.5 1.5H14" />
      <path d="M17.5 12H10M15 8.5l3.5 3.5-3.5 3.5" />
    </svg>
  );
}

/** Deux flèches qui se croisent — échanger deux créneaux. */
export function IconSwap({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 8h13M13.5 4.5 17 8l-3.5 3.5" />
      <path d="M20 16H7M10.5 12.5 7 16l3.5 3.5" />
    </svg>
  );
}

/** Trois points — les autres gestes d'une ligne. */
export function IconMore({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="5.5" cy="12" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="18.5" cy="12" r="1.1" fill="currentColor" stroke="none" />
    </svg>
  );
}
