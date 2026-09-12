import { ScreenHeader } from "@/components/shell/ScreenHeader";

export default function SurfPage() {
  return (
    <>
      <ScreenHeader
        title="Surf"
        subtitle="Je vais à l'eau, oui ou non, et où ?"
      />
      <section className="px-5">
        <p className="rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          Spots, prévisions et recommandation du jour arrivent au lot 1.
        </p>
      </section>
    </>
  );
}
