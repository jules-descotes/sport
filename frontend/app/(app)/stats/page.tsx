import { ScreenHeader } from "@/components/shell/ScreenHeader";

export const metadata = { title: "Stats" };

export default function StatsPage() {
  return (
    <>
      <ScreenHeader title="Stats" subtitle="Conditions, notes, corrélations." />
      <section className="px-5">
        <p className="rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          Les corrélations conditions / note arrivent au lot 6.
        </p>
      </section>
    </>
  );
}
