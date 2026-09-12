import { ScreenHeader } from "@/components/shell/ScreenHeader";

export const metadata = { title: "Training" };

export default function TrainingPage() {
  return (
    <>
      <ScreenHeader title="Training" subtitle="Mobilité, renfo, gainage." />
      <section className="px-5">
        <p className="rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          Exercices, programmes et mode séance arrivent au lot 4.
        </p>
      </section>
    </>
  );
}
