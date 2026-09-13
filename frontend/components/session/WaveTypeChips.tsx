import {
  WAVE_LENGTH_LABELS,
  WAVE_SHAPE_LABELS,
  WAVE_SIZE_LABELS,
} from "@/lib/types";
import type { WaveType } from "@/lib/types";

/**
 * Le type de vagues, en toutes lettres.
 *
 * Trois pastilles au plus, dans l'ordre où on les décrit : taille, longueur,
 * forme. Rien du tout quand rien n'a été dit — et surtout pas « moyennes » par
 * défaut : **une absence de réponse n'est pas une réponse moyenne**, c'est
 * toute la raison pour laquelle ces colonnes sont nullables.
 */

export function waveTypeLabels(value: WaveType): string[] {
  const labels: string[] = [];
  if (value.wave_size) labels.push(WAVE_SIZE_LABELS[value.wave_size]);
  if (value.wave_length) labels.push(WAVE_LENGTH_LABELS[value.wave_length]);
  if (value.wave_shape) labels.push(WAVE_SHAPE_LABELS[value.wave_shape]);
  return labels;
}

export function WaveTypeChips({
  value,
  className = "",
}: {
  value: WaveType;
  className?: string;
}) {
  const labels = waveTypeLabels(value);
  if (labels.length === 0) return null;

  return (
    <ul className={`flex flex-wrap gap-2 ${className}`} aria-label="Type de vagues">
      {labels.map((label) => (
        <li
          key={label}
          className="rounded-pill border border-line bg-soft px-3 py-1 text-[13px] font-semibold text-ink-2"
        >
          {label}
        </li>
      ))}
    </ul>
  );
}
