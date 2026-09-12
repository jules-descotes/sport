/**
 * Une flèche de direction, en SVG, orientée.
 *
 * **La convention est celle des bulletins : une direction météo est une
 * provenance.** Une houle « 290° » vient du nord-ouest ; elle va donc vers le
 * sud-est. La flèche est dessinée dans le sens du **déplacement**, parce que
 * c'est la lecture instinctive — on voit d'où ça arrive en regardant d'où
 * part la flèche, comme sur une carte de vent.
 *
 * Le SVG de base pointe vers le **haut** (le nord). Une rotation de
 * `direction` degrés le ferait pointer vers le secteur de provenance ; on
 * ajoute donc 180° pour qu'il pointe vers là où ça va.
 *
 * Taille minimale 16 px (règle C.4 du 13/09) : à bout de bras, au soleil, une
 * flèche de 12 px ne se lit pas. Pas de gris clair non plus — `currentColor`,
 * et l'appelant fournit une encre franche.
 */
interface DirectionArrowProps {
  /** Provenance en degrés, convention météo. `null` = rien à dessiner. */
  direction: number | null | undefined;
  /** Côté du carré, en pixels. Jamais en dessous de 16. */
  size?: number;
  className?: string;
  /** Nom accessible — « houle de nord-ouest ». Sans lui, la flèche est muette. */
  label?: string;
}

export function DirectionArrow({
  direction,
  size = 18,
  className,
  label,
}: DirectionArrowProps) {
  if (direction === null || direction === undefined) {
    return (
      <span
        aria-hidden
        className={className}
        style={{ display: "inline-block", width: size, textAlign: "center" }}
      >
        —
      </span>
    );
  }

  const side = Math.max(16, size);
  // +180° : de la provenance vers le déplacement.
  const rotation = (direction + 180) % 360;

  return (
    <svg
      viewBox="0 0 24 24"
      width={side}
      height={side}
      className={className}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      style={{ transform: `rotate(${rotation}deg)`, display: "block" }}
    >
      {/* Hampe et pointe pleine : une flèche en trait fin disparaît au soleil.
          La pointe est large pour rester lisible à 16 px. */}
      <path
        d="M12 3.2 18.4 13H14v7.4h-4V13H5.6z"
        fill="currentColor"
        stroke="none"
      />
    </svg>
  );
}
