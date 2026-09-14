"""Comment un ingrédient **s'achète** — à la pièce, au volume, ou au poids.

La base parle en grammes et elle a raison : Ciqual donne des valeurs pour
100 g, et une recette qui pèserait ses œufs « à l'unité » ne pourrait plus
calculer ses macros. Mais **on ne fait pas ses courses en grammes**. Personne
n'a jamais demandé 165 g d'œufs à la caisse : on prend trois œufs, un avocat,
un concombre, une brique de lait.

D'où ce module, et une seule règle : le gramme reste la grandeur stockée, la
pièce n'est qu'une **conversion d'affichage** — exactement comme un 6'2 de
planche qui vit en base à 1,88 m (cf. CLAUDE.md, « aucune unité composite »).

Trois unités, et pas une de plus :

- **`piece`** — ce qui se compte. Œufs, bananes, avocats, courgettes. La masse
  unitaire est une **moyenne assumée**, pas une mesure : un œuf moyen sans
  coquille fait 55 g, une banane épluchée 120 g. C'est faux à dix pour cent, et
  c'est sans importance : on arrondit **au-dessus**, parce qu'on ne met pas 2,7
  œufs dans un panier.
- **`ml`** — ce qui se verse. Du lait affiché « 1,8 kg » se lit mal ; « 1,8 L »
  se lit tout seul. La densité est dans la table, parce que l'huile ne pèse pas
  comme l'eau.
- **`g`** — tout le reste, et c'est le défaut. Le riz, le poulet, le fromage
  s'achètent au poids, et les afficher autrement serait du zèle.

Un ingrédient absent de la table reste en grammes. **L'absence n'est pas un
bug** : c'est le comportement correct pour les trois quarts des lignes.
"""
from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Piece:
    """Ce qui se compte. `grams` est la masse moyenne d'**une** pièce."""

    grams: float
    singular: str
    plural: str


@dataclass(frozen=True)
class Liquid:
    """Ce qui se verse. `density` en grammes par millilitre."""

    density: float = 1.0


def unit_key(label: str) -> str:
    """La clé de la table : minuscules, sans accents, **sans ligature**.

    `NFD` ne décompose pas « œ » — c'est un caractère à part entière, pas un
    « o » avec un accent (seul `NFKD` le casserait, en cassant autre chose au
    passage). Sans la substitution explicite, « Œufs » ne trouverait jamais
    « oeufs », et les œufs sont l'ingrédient le plus fréquent du catalogue.

    Le pluriel n'est **pas** traité ici : voir `_lookup`. Retirer un `s` final
    au passage ferait d'« ananas » un « anana », et la règle qui protège les
    pluriels français casse les mots qui finissent en `s` au singulier. Deux
    recherches valent mieux qu'une fausse normalisation.
    """
    stripped = "".join(
        char
        for char in unicodedata.normalize("NFD", label)
        if unicodedata.category(char) != "Mn"
    )
    key = " ".join(stripped.lower().split())
    return key.replace("œ", "oe").replace("æ", "ae")


def _lookup(table: dict, label: str):
    """Le libellé tel quel, puis sans son `s` final. Jamais l'inverse.

    Le catalogue écrit « Œufs » au pluriel et « Carotte » au singulier ; la
    table est au singulier. Chercher d'abord la forme exacte laisse la porte
    ouverte à une entrée volontairement au pluriel (« pommes de terre »), et
    « ananas » ne devient jamais « anana ».
    """
    key = unit_key(label)
    found = table.get(key)
    if found is not None:
        return found
    if len(key) > 3 and key.endswith("s"):
        return table.get(key[:-1])
    return None


# Masses moyennes, en grammes, **net** — un œuf sans sa coquille, une banane
# épluchée : c'est ce que la recette met dans la casserole, donc ce que la base
# a stocké. Les valeurs sont rondes à dessein ; les affiner donnerait une
# fausse impression de mesure.
PIECES: dict[str, Piece] = {
    "oeuf": Piece(55, "œuf", "œufs"),
    "banane": Piece(120, "banane", "bananes"),
    "avocat": Piece(120, "avocat", "avocats"),
    "tomate": Piece(120, "tomate", "tomates"),
    "courgette": Piece(200, "courgette", "courgettes"),
    "poivron": Piece(150, "poivron", "poivrons"),
    "carotte": Piece(80, "carotte", "carottes"),
    # Le catalogue a une ligne « Carotte râpée » : c'est la même chose dans le
    # caddie, et sans entrée explicite elle repartirait en grammes.
    "carotte rapee": Piece(80, "carotte", "carottes"),
    "oignon": Piece(100, "oignon", "oignons"),
    "poireau": Piece(150, "poireau", "poireaux"),
    "patate douce": Piece(220, "patate douce", "patates douces"),
    "pomme": Piece(150, "pomme", "pommes"),
    # Un concombre entier, pas la rondelle : on en achète un, jamais 150 g.
    "concombre": Piece(300, "concombre", "concombres"),
    "brocoli": Piece(400, "brocoli", "brocolis"),
    "galette de ble": Piece(60, "galette", "galettes"),
    "pain baguette": Piece(250, "baguette", "baguettes"),
    "cuisse de poulet": Piece(180, "cuisse", "cuisses"),
}

# Densités en g/ml. Le lait est à 1,03 et l'huile à 0,92 : l'écart est réel, il
# ne change rien au caddie, et l'écrire coûte une ligne.
LIQUIDS: dict[str, Liquid] = {
    "lait": Liquid(1.03),
    "lait demi-ecreme": Liquid(1.03),
    "lait entier": Liquid(1.03),
    "lait de coco": Liquid(1.0),
    "huile d'olive": Liquid(0.92),
    "sauce soja": Liquid(1.2),
    "coulis de tomate": Liquid(1.05),
}


@dataclass(frozen=True)
class Quantity:
    """Une quantité prête à lire au supermarché.

    `quantity_g` reste là, toujours : c'est la grandeur vraie, celle qui a servi
    à agréger. Le reste est de l'affichage, et on ne remplace jamais la mesure
    par son affichage.
    """

    quantity_g: float
    unit: str  # "g" | "piece" | "ml"
    quantity: float
    # « œufs », « bananes ». Nul pour les grammes et les millilitres, dont
    # l'unité se suffit à elle-même.
    unit_label: Optional[str] = None


def to_shopping_unit(label: str, quantity_g: float) -> Quantity:
    """La quantité d'une ligne de courses, dans l'unité où on l'achète.

    Les pièces sont arrondies **au-dessus**, et jamais à zéro : deux virgule
    sept œufs font trois œufs, et cinq grammes d'ail font une gousse. Arrondir
    au plus proche ferait manquer un ingrédient une fois sur deux, ce qui est
    la seule façon pour une liste de courses d'être vraiment inutile.
    """
    piece = _lookup(PIECES, label)
    if piece is not None and piece.grams > 0:
        count = max(1, math.ceil(quantity_g / piece.grams - 1e-9))
        return Quantity(
            quantity_g=quantity_g,
            unit="piece",
            quantity=float(count),
            unit_label=piece.singular if count == 1 else piece.plural,
        )

    liquid = _lookup(LIQUIDS, label)
    if liquid is not None and liquid.density > 0:
        millilitres = quantity_g / liquid.density
        # Au décilitre près au-dessus d'un litre, aux dix millilitres en
        # dessous : on n'achète pas 1 237 ml de lait.
        step = 100.0 if millilitres >= 1000 else 10.0
        rounded = max(step, math.ceil(millilitres / step - 1e-9) * step)
        return Quantity(quantity_g=quantity_g, unit="ml", quantity=rounded)

    return Quantity(quantity_g=quantity_g, unit="g", quantity=round(quantity_g, 1))
