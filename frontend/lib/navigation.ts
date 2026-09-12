/**
 * La barre basse — **cinq entrées, et jamais une sixième**.
 *
 * Décidé le 13/09 après la première utilisation en ligne (cf. `PROJET.md` §1,
 * règle 3). Elle remplace les trois destinations Jour / Mer / Corps du 12/09 :
 *
 * - **Mer** devient **Surf**, et absorbe l'historique des sessions et le matos —
 *   tout ce qui touche à l'eau entre par la même porte ;
 * - **Corps** éclate en **Training** et **Nutrition**, qui étaient déjà deux
 *   sujets distincts sous un seul mot ;
 * - **Profil** sort du menu caché : il n'était atteignable que par une icône
 *   en haut de Jour, et un réglage qu'on ne trouve pas n'existe pas.
 *
 * La liste vit dans un module à part et non dans le composant : c'est la seule
 * façon de la tester sans monter React, et la règle « cinq entrées » mérite un
 * test qui échoue le jour où quelqu'un en ajoute une sixième.
 */

export type TabIcon = "day" | "wave" | "dumbbell" | "plate" | "user";

export interface Tab {
  href: string;
  label: string;
  icon: TabIcon;
}

export const TABS: readonly Tab[] = [
  { href: "/", label: "Jour", icon: "day" },
  { href: "/surf", label: "Surf", icon: "wave" },
  { href: "/training", label: "Training", icon: "dumbbell" },
  { href: "/nutrition", label: "Nutrition", icon: "plate" },
  { href: "/profil", label: "Profil", icon: "user" },
] as const;

/**
 * Les anciennes destinations et leur remplaçante.
 *
 * Elles restent servies, en redirection : un lien « Mer » mis en favori sur
 * l'écran d'accueil du téléphone, ou une page laissée ouverte, ne doit pas
 * tomber sur un 404 le lendemain d'un déploiement.
 */
export const MOVED_ROUTES: Readonly<Record<string, string>> = {
  "/mer": "/surf",
  "/corps": "/training",
  "/sessions": "/surf/sessions",
  "/profil/matos": "/surf/matos",
} as const;

/** L'onglet actif pour un chemin donné. `/` n'est actif que sur lui-même. */
export function activeTab(pathname: string): string | null {
  for (const tab of TABS) {
    if (tab.href === "/") continue;
    if (pathname === tab.href || pathname.startsWith(`${tab.href}/`)) {
      return tab.href;
    }
  }
  return pathname === "/" ? "/" : null;
}
