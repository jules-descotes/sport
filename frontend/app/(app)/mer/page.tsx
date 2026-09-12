import { redirect } from "next/navigation";

/**
 * « Mer » est devenue « Surf » le 13/09 (cf. `lib/navigation.ts`).
 *
 * La route reste servie, en redirection permanente : un raccourci mis sur
 * l'écran d'accueil du téléphone, ou un onglet resté ouvert, ne doit pas
 * tomber sur un 404 le lendemain d'un déploiement.
 */
export default function MerPage() {
  redirect("/surf");
}
