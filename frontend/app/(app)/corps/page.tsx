import { ScreenHeader } from "@/components/shell/ScreenHeader";

export const metadata = { title: "Corps" };

/**
 * **Corps** — objectifs mesurés, formules, composition.
 *
 * Coquille du lot 1 ter : les trois jauges sont vides et le disent. Le contenu
 * arrive au lot 4 — objectifs mesurés (`objectives`, `objective_measurements`),
 * cinq formules, mode séance plein écran.
 *
 * Cet écran existe **dès maintenant** et non au lot 4, et c'est le point de la
 * décision du 12/09 au soir : le training et la nutrition entrent par une porte
 * qui existe déjà, au lieu de deux onglets affichant « arrive au lot 4 ».
 *
 * Les objectifs affichés sont ceux de `docs/DESIGN-EXPLORATION.md` §3 — ils
 * disent ce que l'écran mesurera, pas ce qu'il mesure : aucune valeur n'est
 * inventée, les jauges sont vides et la mention « à définir » est portée par
 * chacune.
 */

const OBJECTIVES = [
  {
    name: "Assouplissement",
    measure: "distance mains-sol, jambes tendues",
    unit: "cm",
  },
  { name: "Mobilité", measure: "rotation thoracique", unit: "°" },
  { name: "Gainage", measure: "durée tenue", unit: "min" },
] as const;

function Gauge({
  name,
  measure,
  unit,
}: {
  name: string;
  measure: string;
  unit: string;
}) {
  return (
    <article className="rounded-card border border-line bg-card px-5 py-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-display text-[22px] leading-none font-semibold uppercase text-ink">
          {name}
        </h2>
        <p className="tabular shrink-0 font-display text-[22px] leading-none font-semibold text-mute">
          — {unit}
        </p>
      </div>
      <p className="mt-1.5 text-[13px] text-mute">{measure}</p>

      {/* Jauge vide : une barre à zéro, pas une barre grise à moitié pleine —
          un remplissage inventé se lirait comme une mesure. */}
      <div
        className="mt-3 h-2.5 overflow-hidden rounded-pill border border-line bg-soft"
        role="img"
        aria-label={`${name} : à définir`}
      />
      <p className="mt-2 text-[12px] text-mute">À définir</p>
    </article>
  );
}

export default function CorpsPage() {
  return (
    <main className="pb-6">
      <ScreenHeader
        title="Corps"
        subtitle="Objectifs mesurés, formules, composition."
      />

      <section className="flex flex-col gap-3 px-5" aria-label="Objectifs">
        {OBJECTIVES.map((objective) => (
          <Gauge key={objective.name} {...objective} />
        ))}
      </section>

      <section className="px-5 pt-6">
        <p className="rounded-card border border-dashed border-line bg-soft px-5 py-5 text-[14px] leading-snug text-ink-2">
          Un objectif se mesure ou n&apos;existe pas : chaque jauge prendra un
          point de départ, une valeur courante et une cible, plus un rappel de
          mesure toutes les deux ou trois semaines. Les cinq formules
          d&apos;entraînement et le mode séance arrivent avec, au lot 4.
        </p>
      </section>
    </main>
  );
}
