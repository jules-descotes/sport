import { ScreenHeader } from "@/components/shell/ScreenHeader";

export const metadata = { title: "Nutrition" };

/**
 * **Nutrition** — coquille, lot 5.
 *
 * Sobre, et volontairement : pas de bouton mort, pas de jauge à zéro, pas de
 * fausse promesse. Une ligne qui dit ce qui viendra et quand. Un onglet vide
 * qui feint d'être plein coûte plus cher qu'un onglet vide qui l'assume — on
 * le tape une fois, on ne le retape jamais.
 */
export default function NutritionPage() {
  return (
    <main className="pb-6">
      <ScreenHeader
        title="Nutrition"
        subtitle="Cible calorique, journal, menu de la semaine."
      />

      <section className="px-5">
        <p className="rounded-card border border-dashed border-line bg-soft px-5 py-5 text-[14px] leading-snug text-ink-2">
          Arrive au lot 5 : table Ciqual 2025 de l&apos;ANSES, journal des
          repas, et une cible calorique recalculée à partir des sessions à
          l&apos;eau et de l&apos;évolution réelle du poids — jamais saisie à la
          main.
        </p>
      </section>
    </main>
  );
}
