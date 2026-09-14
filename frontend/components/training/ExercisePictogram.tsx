import type { ReactNode } from "react";

/**
 * **Trois mouvements que personne n'a photographiés sous licence libre.**
 *
 * Rotation thoracique, passage de bâton et pop-up à sec n'existent dans aucune
 * base ouverte — cherché le 13/09, recherché le 14/09 sur Wikimedia Commons.
 * Et une image approchante est pire que pas d'image : la première version de
 * la règle d'emprunt avait donné au pop-up un « développé épaules à la
 * poulie ». On les dessine donc, plutôt que de les rapprocher de quelque
 * chose.
 *
 * **Pourquoi en ligne dans le code et non des fichiers `.svg`.** Le thème du
 * site bascule sur `@media (min-width: 1024px)` — clair sur téléphone, sombre
 * sur bureau — en redéfinissant `--sport-ink` et `--sport-accent`. Un SVG
 * chargé dans une balise `img` est un document isolé : ses propres media
 * queries se mesurent à la taille de l'image, pas à celle de la page, et il ne
 * peut donc pas suivre. En ligne, il hérite des variables et bascule avec le
 * reste. C'est aussi une requête réseau de moins sur un écran qu'on ouvre les
 * mains mouillées.
 *
 * **La grammaire est la même pour les trois**, et c'est ce qui les rend
 * lisibles d'un coup d'œil : deux poses côte à côte, départ à gauche, arrivée
 * à droite, une flèche entre les deux ; silhouette en trait de 1,75 px couleur
 * `ink` ; **un seul segment en accent**, celui qui bouge, et le même dans les
 * deux poses — c'est son déplacement qu'on lit, pas la pose.
 */

const STROKE = 1.75;
const INK = "var(--sport-ink)";
const ACCENT = "var(--sport-accent)";
const LINE = "var(--sport-line)";

/** Le sol : un repère discret, sans lui les poses allongées flottent. */
function Ground({ from, to }: { from: number; to: number }) {
  return (
    <line
      x1={from}
      y1={82}
      x2={to}
      y2={82}
      stroke={LINE}
      strokeWidth={STROKE}
      strokeLinecap="round"
    />
  );
}

/** Départ → arrivée. La flèche est le seul élément qui n'est pas un corps. */
function Arrow({ y }: { y: number }) {
  return (
    <g stroke={LINE} strokeWidth={STROKE} strokeLinecap="round" fill="none">
      <line x1={57} y1={y} x2={71} y2={y} />
      <polyline points={`66,${y - 4} 71,${y} 66,${y + 4}`} strokeLinejoin="round" />
    </g>
  );
}

function Frame({ label, children }: { label: string; children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 128 128"
      role="img"
      aria-label={label}
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={STROKE}
      // Le fond reste transparent : le pictogramme se pose sur la carte, la
      // carte porte déjà sa couleur et sa bordure.
      className="h-full w-full"
    >
      {children}
    </svg>
  );
}

/** Le corps : tout ce qui ne bouge pas dans le mouvement décrit. */
function Body({ children }: { children: ReactNode }) {
  return <g stroke={INK}>{children}</g>;
}

/** Le segment qui bouge, et lui seul. */
function Moving({ children }: { children: ReactNode }) {
  return (
    <g stroke={ACCENT} strokeWidth={STROKE + 0.75}>
      {children}
    </g>
  );
}

/**
 * **Rotation thoracique.** À quatre pattes, main derrière la tête : le coude
 * part sous le corps et s'ouvre vers le plafond. Le bassin ne bouge pas — il
 * est donc dessiné à l'identique dans les deux poses, et c'est ce qui fait
 * voir que seule la rotation change.
 */
function RotationThoracique() {
  return (
    <Frame label="Rotation thoracique : le coude s'ouvre du sol vers le plafond">
      <Ground from={6} to={54} />
      <Ground from={74} to={122} />
      <Arrow y={60} />

      {/* Départ : coude rentré sous le corps */}
      <Body>
        <circle cx={13} cy={56} r={5} />
        <path d="M18 58 L44 63" />
        <path d="M20 60 L18 81" />
        <path d="M44 63 L42 81" />
        <path d="M42 81 L52 79" />
      </Body>
      <Moving>
        {/* Coude bas, avant-bras passé **sous** le corps : c'est le geste que
            l'anglais appelle « thread the needle », et le replier vers la tête
            en dessinait un éclair illisible. */}
        <path d="M20 59 L27 71 L39 69" />
      </Moving>

      {/* Arrivée : coude ouvert vers le plafond */}
      <Body>
        <circle cx={81} cy={56} r={5} />
        <path d="M86 58 L112 63" />
        <path d="M88 60 L86 81" />
        <path d="M112 63 L110 81" />
        <path d="M110 81 L120 79" />
      </Body>
      <Moving>
        {/* Coude au plafond, main restée derrière la tête. */}
        <path d="M88 59 L98 48 L88 43" />
      </Moving>
    </Frame>
  );
}

/**
 * **Passage de bâton.** Debout, prise large : le bâton passe de devant les
 * cuisses à derrière la tête, bras tendus. L'accent est sur le bâton : c'est
 * lui qu'on suit du regard, et sa trajectoire dit tout du mouvement.
 */
function PassageDeBaton() {
  return (
    <Frame label="Passage de bâton : le bâton passe de devant les cuisses à derrière la tête">
      <Ground from={6} to={54} />
      <Ground from={74} to={122} />
      <Arrow y={64} />

      {/* Départ : bâton devant, bras vers le bas */}
      <Body>
        <circle cx={30} cy={20} r={6} />
        <path d="M30 26 L30 56" />
        <path d="M30 56 L23 81" />
        <path d="M30 56 L37 81" />
        <path d="M30 32 L17 52" />
        <path d="M30 32 L43 52" />
      </Body>
      <Moving>
        <path d="M13 52 L47 52" />
      </Moving>

      {/* Arrivée : bâton au-dessus, bras tendus */}
      <Body>
        <circle cx={94} cy={20} r={6} />
        <path d="M94 26 L94 56" />
        <path d="M94 56 L87 81" />
        <path d="M94 56 L101 81" />
        <path d="M94 32 L81 11" />
        <path d="M94 32 L107 11" />
      </Body>
      <Moving>
        <path d="M77 11 L111 11" />
      </Moving>
    </Frame>
  );
}

/**
 * **Pop-up à sec.** À plat ventre comme sur la planche, puis les pieds passent
 * sous le corps d'un coup, en position de surf. L'accent est sur les jambes :
 * ce sont elles qui voyagent, et c'est le seul point sur lequel le geste se
 * rate.
 */
function PopUp() {
  return (
    <Frame label="Pop-up à sec : à plat ventre, les pieds passent sous le corps en position de surf">
      <Ground from={6} to={54} />
      <Ground from={74} to={122} />
      <Arrow y={58} />

      {/* Départ : à plat ventre. Le corps est **horizontal**, au ras du sol —
          un tronc incliné se lit comme un buste qui se redresse, c'est-à-dire
          comme la fin du mouvement et non son début. */}
      <Body>
        <circle cx={12} cy={69} r={5} />
        <path d="M17 71 L40 74" />
        <path d="M20 72 L25 81" />
      </Body>
      <Moving>
        <path d="M40 74 L54 79" />
      </Moving>

      {/* Arrivée : position de surf, de profil. Genoux fléchis, appuis
          larges, buste bas — c'est l'écart des pieds qui dit le pop-up. */}
      <Body>
        <circle cx={96} cy={43} r={5} />
        <path d="M95 48 L93 61" />
        <path d="M94 51 L82 47" />
        <path d="M94 51 L107 55" />
      </Body>
      <Moving>
        <path d="M93 61 L105 68 L107 80" />
        <path d="M93 61 L83 69 L81 80" />
      </Moving>
    </Frame>
  );
}

/**
 * Les trois, par la clé portée dans `image_url`.
 *
 * Le préfixe `pictogram:` n'est pas une URL et ne doit jamais partir dans une
 * balise `img` : c'est une valeur reconnue par `ExerciseImage`, et par lui
 * seul. Il occupe `image_url` parce que c'est ce champ qui décide qu'un
 * exercice est proposable (`Exercise.is_eligible`) — un pictogramme dessiné
 * ici vaut une image, et l'exercice redevient donc éligible.
 */
export const PICTOGRAM_PREFIX = "pictogram:";

const PICTOGRAMS: Record<string, () => ReactNode> = {
  "rotation-thoracique": RotationThoracique,
  "passage-de-baton": PassageDeBaton,
  "pop-up": PopUp,
};

/** La clé si l'URL en est une, `null` sinon. */
export function pictogramKey(imageUrl: string | null | undefined): string | null {
  if (!imageUrl || !imageUrl.startsWith(PICTOGRAM_PREFIX)) return null;
  const key = imageUrl.slice(PICTOGRAM_PREFIX.length);
  return key in PICTOGRAMS ? key : null;
}

export function ExercisePictogram({ name }: { name: string }) {
  const Draw = PICTOGRAMS[name];
  if (!Draw) return null;
  return <Draw />;
}
