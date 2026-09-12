import { ScreenHeader } from "@/components/shell/ScreenHeader";

export const metadata = { title: "Nutrition" };

export default function NutritionPage() {
  return (
    <>
      <ScreenHeader title="Nutrition" subtitle="Menu de la semaine et journal." />
      <section className="px-5">
        <p className="rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          Journal alimentaire et cible calorique arrivent au lot 5.
        </p>
      </section>
    </>
  );
}
