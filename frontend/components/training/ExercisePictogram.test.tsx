// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ExerciseCredit,
  ExerciseImage,
} from "@/components/training/ExerciseImage";
import {
  PICTOGRAM_PREFIX,
  pictogramKey,
} from "@/components/training/ExercisePictogram";
import type { Exercise } from "@/lib/types";

/**
 * **Les pictogrammes maison, et le fil qui les relie au reste.**
 *
 * `image_url` porte une clé `pictogram:…` et non une URL. C'est un choix, et
 * il a un coût : si quoi que ce soit envoyait cette valeur dans un `src`, le
 * navigateur afficherait une image cassée, en silence, sur l'écran qu'on
 * regarde les mains au sol. Ces tests tiennent les deux bouts — la clé est
 * reconnue là où il faut, et elle ne part jamais dans une balise `img`.
 *
 * Et l'attribution : les photos de Commons sont en CC BY et CC BY-SA, qui
 * demandent de **nommer l'auteur**. Un test l'exige, parce qu'une attribution
 * qui disparaît d'une retouche de mise en page ne se voit pas, et qu'elle est
 * la condition du droit d'afficher la photo.
 */

function exercise(overrides: Partial<Exercise> = {}): Exercise {
  return {
    id: 1,
    slug: "rotation-thoracique",
    name: "Thoracic rotation",
    name_fr: "Rotation thoracique",
    description_fr: null,
    category: "mobility",
    muscle_group: "dos",
    instructions: null,
    image_url: null,
    images: [],
    source: "builtin",
    license: null,
    source_url: null,
    image_author: null,
    group_key: "dos",
    pattern: "mobilite",
    equipment: "aucun",
    difficulty: 2,
    effort_kind: "temps",
    unilateral: true,
    ...overrides,
  } as Exercise;
}

describe("pictogramKey", () => {
  it("reconnaît les trois pictogrammes dessinés", () => {
    for (const key of ["rotation-thoracique", "passage-de-baton", "pop-up"]) {
      expect(pictogramKey(`${PICTOGRAM_PREFIX}${key}`)).toBe(key);
    }
  });

  it("rend null sur une vraie URL — sinon une photo passerait pour un dessin", () => {
    expect(pictogramKey("/exercises/cobra.jpg")).toBeNull();
    expect(pictogramKey("https://wger.de/media/x.png")).toBeNull();
  });

  it("rend null sur une clé inconnue plutôt que de rendre un cadre vide", () => {
    // Le cas qui arrive pour de vrai : un pictogramme retiré du code alors
    // qu'une ligne en base le désigne encore. On retombe alors sur le
    // pictogramme de groupe, qui est un repli honnête.
    expect(pictogramKey(`${PICTOGRAM_PREFIX}saut-perilleux`)).toBeNull();
  });

  it("rend null sur vide", () => {
    expect(pictogramKey(null)).toBeNull();
    expect(pictogramKey("")).toBeNull();
  });
});

describe("ExerciseImage", () => {
  it("dessine le pictogramme et n'émet aucune balise img", () => {
    const { container } = render(
      <ExerciseImage
        exercise={exercise({ image_url: `${PICTOGRAM_PREFIX}pop-up` })}
      />,
    );

    expect(container.querySelector("svg")).not.toBeNull();
    // Le point qui compte : la clé ne part jamais dans un `src`.
    expect(container.querySelector("img")).toBeNull();
  });

  it("garde la balise img pour une vraie photo", () => {
    const { container } = render(
      <ExerciseImage exercise={exercise({ image_url: "/exercises/cobra.jpg" })} />,
    );

    expect(container.querySelector("img")?.getAttribute("src")).toBe(
      "/exercises/cobra.jpg",
    );
  });

  it("décrit le mouvement pour les lecteurs d'écran", () => {
    render(
      <ExerciseImage
        exercise={exercise({
          image_url: `${PICTOGRAM_PREFIX}rotation-thoracique`,
        })}
      />,
    );

    expect(
      screen.getByRole("img", { name: /coude s'ouvre du sol vers le plafond/ }),
    ).toBeTruthy();
  });
});

describe("ExerciseCredit", () => {
  it("nomme l'auteur d'une photo CC BY — c'est la licence qui l'exige", () => {
    render(
      <ExerciseCredit
        exercise={exercise({
          image_url: "/exercises/cobra.jpg",
          source: "wikimedia-commons",
          license: "CC BY 3.0",
          image_author: "Kennguru",
          source_url: "https://commons.wikimedia.org/wiki/File:X.jpg",
        })}
      />,
    );

    const credit = screen.getByRole("link");
    expect(credit.textContent).toContain("Kennguru");
    expect(credit.textContent).toContain("CC BY 3.0");
  });

  it("dit qu'un pictogramme est de nous, sans inventer d'auteur", () => {
    const { container } = render(
      <ExerciseCredit
        exercise={exercise({
          image_url: `${PICTOGRAM_PREFIX}pop-up`,
          source: "sport",
          license: "personnelle",
        })}
      />,
    );

    expect(container.textContent).toContain("Sport");
    expect(container.querySelector("a")).toBeNull();
  });

  it("ne perd pas l'origine quand l'auteur est inconnu", () => {
    // wger publie au nom du projet : pas de personne à nommer, mais la
    // licence reste due.
    const { container } = render(
      <ExerciseCredit
        exercise={exercise({
          image_url: "https://wger.de/media/x.png",
          source: "wger",
          license: "CC BY-SA 4.0",
        })}
      />,
    );

    expect(container.textContent).toContain("wger.de");
    expect(container.textContent).toContain("CC BY-SA 4.0");
  });

  it("ne dit rien quand il n'y a pas d'image", () => {
    const { container } = render(<ExerciseCredit exercise={exercise()} />);
    expect(container.textContent).toBe("");
  });
});
