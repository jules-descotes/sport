"""Quarante recettes simples — le vivier du menu de la semaine.

Écrites ici, en français, comme les consignes d'exercices du lot 4 et pour la
même raison : **elles nous appartiennent**. Aucune n'est recopiée d'un site de
cuisine ; ce sont des assemblages courants, décrits en une ou deux phrases, et
c'est exactement ce qu'il faut pour un menu qu'on suit vraiment.

Quatre principes, et ils viennent de l'usage :

1. **Rien au-dessus de vingt-cinq minutes.** Une recette de quarante minutes ne
   se fait pas le mardi soir après deux heures d'eau, et une recette qu'on ne
   fait pas fausse le menu de la semaine.
2. **Des ingrédients qu'on a.** Pas de liste de courses à rallonge pour un
   dîner : c'est le générateur qui agrège les courses, et il ne peut rien
   contre une recette à onze ingrédients.
3. **Les étiquettes servent l'algorithme**, pas la décoration : `rapide`,
   `veggie`, `proteine`, `post-surf`. Le générateur choisit sous contrainte de
   macros et de variété à partir d'elles.
4. **Les quantités sont en grammes**, et les valeurs nutritionnelles sont
   calculées au semis depuis Ciqual — jamais saisies. Une recette saisie « à
   450 kcal » serait une estimation qu'on prendrait ensuite pour une mesure.

`ciqual_query` est le nom cherché dans la table importée. Tant que Ciqual n'est
pas importé, les recettes existent sans valeurs nutritionnelles : elles restent
lisibles, et le semis les complétera au prochain passage.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ingredient:
    label: str
    quantity_g: float
    # Le nom cherché dans Ciqual. Volontairement générique : « riz blanc cuit »
    # trouve une ligne, « riz thaï demi-complet bio » n'en trouve aucune.
    ciqual_query: str


@dataclass(frozen=True)
class RecipeSpec:
    slug: str
    name: str
    meals: tuple[str, ...]
    tags: tuple[str, ...]
    prep_min: int
    steps: str
    ingredients: tuple[Ingredient, ...]
    servings: int = 1


def _i(label: str, grams: float, query: str) -> Ingredient:
    return Ingredient(label=label, quantity_g=grams, ciqual_query=query)


# ── Petits déjeuners ───────────────────────────────────────────────────────

BREAKFASTS: tuple[RecipeSpec, ...] = (
    RecipeSpec(
        slug="porridge-avoine-banane",
        name="Porridge avoine banane",
        meals=("breakfast",),
        tags=("rapide", "veggie"),
        prep_min=8,
        steps="Flocons dans le lait, cinq minutes à feu doux, banane écrasée dessus.",
        ingredients=(
            _i("Flocons d'avoine", 70, "flocons d'avoine"),
            _i("Lait demi-écrémé", 250, "lait demi-ecreme"),
            _i("Banane", 120, "banane"),
            _i("Beurre de cacahuète", 15, "beurre de cacahuete"),
        ),
    ),
    RecipeSpec(
        slug="skyr-fruits-rouges",
        name="Skyr, fruits rouges, amandes",
        meals=("breakfast", "snack"),
        tags=("rapide", "proteine", "veggie"),
        prep_min=3,
        steps="Rien à cuire. Skyr dans un bol, fruits par-dessus, amandes concassées.",
        ingredients=(
            _i("Skyr nature", 200, "yaourt nature"),
            _i("Fruits rouges surgelés", 120, "framboise"),
            _i("Amandes", 25, "amande"),
            _i("Miel", 10, "miel"),
        ),
    ),
    RecipeSpec(
        slug="oeufs-brouilles-pain-complet",
        name="Œufs brouillés, pain complet",
        meals=("breakfast",),
        tags=("proteine", "rapide"),
        prep_min=10,
        steps="Trois œufs battus, feu doux, on remue sans arrêt. Pain grillé à côté.",
        ingredients=(
            _i("Œufs", 165, "oeuf"),
            _i("Pain complet", 80, "pain complet"),
            _i("Beurre", 10, "beurre"),
        ),
    ),
    RecipeSpec(
        slug="tartines-avocat-oeuf",
        name="Tartines avocat œuf poché",
        meals=("breakfast", "lunch"),
        tags=("veggie", "rapide"),
        prep_min=12,
        steps="Avocat écrasé au citron sur le pain, œuf poché trois minutes dessus.",
        ingredients=(
            _i("Pain complet", 80, "pain complet"),
            _i("Avocat", 100, "avocat"),
            _i("Œufs", 110, "oeuf"),
        ),
    ),
    RecipeSpec(
        slug="smoothie-post-surf",
        name="Smoothie post-surf",
        meals=("breakfast", "snack"),
        tags=("post-surf", "rapide", "proteine"),
        prep_min=4,
        steps="Tout au blender. Se boit dans la voiture, ce qui est le but.",
        ingredients=(
            _i("Banane", 120, "banane"),
            _i("Lait", 250, "lait demi-ecreme"),
            _i("Flocons d'avoine", 40, "flocons d'avoine"),
            _i("Beurre de cacahuète", 20, "beurre de cacahuete"),
        ),
    ),
    RecipeSpec(
        slug="pain-perdu-proteine",
        name="Pain perdu protéiné",
        meals=("breakfast",),
        tags=("proteine",),
        prep_min=12,
        steps="Pain trempé dans œufs et lait, poêle antiadhésive, deux minutes par face.",
        ingredients=(
            _i("Pain complet", 90, "pain complet"),
            _i("Œufs", 110, "oeuf"),
            _i("Lait", 120, "lait demi-ecreme"),
            _i("Cannelle", 2, "cannelle"),
        ),
    ),
    RecipeSpec(
        slug="muesli-fromage-blanc",
        name="Muesli, fromage blanc",
        meals=("breakfast", "snack"),
        tags=("rapide", "veggie"),
        prep_min=3,
        steps="Muesli sur le fromage blanc, pomme coupée dessus.",
        ingredients=(
            _i("Muesli", 70, "muesli"),
            _i("Fromage blanc", 200, "fromage blanc"),
            _i("Pomme", 150, "pomme"),
        ),
    ),
    RecipeSpec(
        slug="omelette-feta-epinards",
        name="Omelette feta épinards",
        meals=("breakfast", "dinner"),
        tags=("proteine", "veggie", "rapide"),
        prep_min=10,
        steps="Épinards tombés à la poêle, œufs battus dessus, feta émiettée, on plie.",
        ingredients=(
            _i("Œufs", 165, "oeuf"),
            _i("Épinards", 150, "epinard"),
            _i("Feta", 50, "feta"),
            _i("Huile d'olive", 8, "huile d'olive"),
        ),
    ),
)

# ── Déjeuners ──────────────────────────────────────────────────────────────

LUNCHES: tuple[RecipeSpec, ...] = (
    RecipeSpec(
        slug="riz-poulet-brocoli",
        name="Riz, poulet, brocoli",
        meals=("lunch", "dinner"),
        tags=("proteine", "post-surf"),
        prep_min=20,
        steps="Riz à l'eau, poulet à la poêle, brocoli vapeur huit minutes.",
        ingredients=(
            _i("Riz blanc cuit", 220, "riz blanc cuit"),
            _i("Blanc de poulet", 160, "poulet blanc"),
            _i("Brocoli", 180, "brocoli"),
            _i("Huile d'olive", 10, "huile d'olive"),
        ),
    ),
    RecipeSpec(
        slug="pates-thon-tomate",
        name="Pâtes thon tomate",
        meals=("lunch", "dinner"),
        tags=("rapide", "post-surf"),
        prep_min=15,
        steps="Pâtes, thon égoutté, coulis chaud, un tour de poivre.",
        ingredients=(
            _i("Pâtes cuites", 250, "pates cuites"),
            _i("Thon au naturel", 120, "thon au naturel"),
            _i("Coulis de tomate", 150, "purée de tomate"),
            _i("Huile d'olive", 10, "huile d'olive"),
        ),
    ),
    RecipeSpec(
        slug="buddha-bowl-pois-chiches",
        name="Bowl pois chiches patate douce",
        meals=("lunch",),
        tags=("veggie", "proteine"),
        prep_min=25,
        steps="Patate douce au four vingt minutes, pois chiches rincés, crudités, tahini.",
        ingredients=(
            _i("Patate douce", 200, "patate douce"),
            _i("Pois chiches cuits", 150, "pois chiche cuit"),
            _i("Carotte râpée", 80, "carotte"),
            _i("Tahini", 20, "puree de sesame"),
        ),
    ),
    RecipeSpec(
        slug="salade-quinoa-feta",
        name="Salade quinoa feta concombre",
        meals=("lunch",),
        tags=("veggie", "rapide"),
        prep_min=15,
        steps="Quinoa froid, concombre en dés, feta, menthe, citron.",
        ingredients=(
            _i("Quinoa cuit", 200, "quinoa cuit"),
            _i("Feta", 60, "feta"),
            _i("Concombre", 150, "concombre"),
            _i("Huile d'olive", 12, "huile d'olive"),
        ),
    ),
    RecipeSpec(
        slug="wrap-poulet-crudites",
        name="Wrap poulet crudités",
        meals=("lunch",),
        tags=("rapide", "proteine"),
        prep_min=10,
        steps="Galette, poulet froid, salade, tomate, une cuillère de fromage blanc.",
        ingredients=(
            _i("Galette de blé", 70, "galette de ble"),
            _i("Blanc de poulet", 130, "poulet blanc"),
            _i("Tomate", 100, "tomate"),
            _i("Fromage blanc", 40, "fromage blanc"),
        ),
    ),
    RecipeSpec(
        slug="riz-saumon-avocat",
        name="Riz, saumon, avocat",
        meals=("lunch", "dinner"),
        tags=("proteine", "post-surf"),
        prep_min=18,
        steps="Riz tiède, pavé de saumon poêlé peau croustillante, avocat en lamelles.",
        ingredients=(
            _i("Riz blanc cuit", 200, "riz blanc cuit"),
            _i("Saumon", 140, "saumon"),
            _i("Avocat", 80, "avocat"),
            _i("Sauce soja", 10, "sauce soja"),
        ),
    ),
    RecipeSpec(
        slug="lentilles-oeuf-mollet",
        name="Lentilles, œuf mollet",
        meals=("lunch", "dinner"),
        tags=("veggie", "proteine"),
        prep_min=22,
        steps="Lentilles avec une carotte et un oignon, œuf six minutes, vinaigrette.",
        ingredients=(
            _i("Lentilles cuites", 220, "lentille cuite"),
            _i("Œufs", 110, "oeuf"),
            _i("Carotte", 80, "carotte"),
            _i("Huile d'olive", 10, "huile d'olive"),
        ),
    ),
    RecipeSpec(
        slug="taboule-pois-chiches",
        name="Taboulé pois chiches",
        meals=("lunch",),
        tags=("veggie", "rapide"),
        prep_min=12,
        steps="Semoule gonflée à l'eau froide, pois chiches, tomate, citron, menthe.",
        ingredients=(
            _i("Semoule cuite", 200, "semoule cuite"),
            _i("Pois chiches cuits", 130, "pois chiche cuit"),
            _i("Tomate", 120, "tomate"),
            _i("Huile d'olive", 12, "huile d'olive"),
        ),
    ),
    RecipeSpec(
        slug="poke-bowl-thon",
        name="Poke bowl thon",
        meals=("lunch",),
        tags=("proteine", "rapide", "post-surf"),
        prep_min=15,
        steps="Riz vinaigré, thon en dés mariné soja-sésame, edamame, concombre.",
        ingredients=(
            _i("Riz blanc cuit", 200, "riz blanc cuit"),
            _i("Thon", 130, "thon"),
            _i("Edamame", 80, "feve de soja"),
            _i("Concombre", 100, "concombre"),
        ),
    ),
    RecipeSpec(
        slug="salade-poulet-patate",
        name="Salade poulet pommes de terre",
        meals=("lunch",),
        tags=("proteine", "post-surf"),
        prep_min=22,
        steps="Pommes de terre tièdes, poulet, haricots verts, moutarde et huile.",
        ingredients=(
            _i("Pommes de terre cuites", 250, "pomme de terre cuite"),
            _i("Blanc de poulet", 140, "poulet blanc"),
            _i("Haricots verts", 120, "haricot vert"),
            _i("Huile d'olive", 12, "huile d'olive"),
        ),
    ),
    RecipeSpec(
        slug="sandwich-thon-crudites",
        name="Sandwich thon crudités",
        meals=("lunch",),
        tags=("rapide",),
        prep_min=8,
        steps="Baguette, thon, salade, tomate, un filet d'huile. Se mange debout.",
        ingredients=(
            _i("Pain baguette", 120, "pain baguette"),
            _i("Thon au naturel", 120, "thon au naturel"),
            _i("Tomate", 80, "tomate"),
            _i("Huile d'olive", 8, "huile d'olive"),
        ),
    ),
    RecipeSpec(
        slug="chili-sin-carne",
        name="Chili sin carne",
        meals=("lunch", "dinner"),
        tags=("veggie", "proteine"),
        prep_min=25,
        steps="Haricots rouges, tomate, poivron, cumin et paprika. Meilleur réchauffé.",
        ingredients=(
            _i("Haricots rouges cuits", 220, "haricot rouge cuit"),
            _i("Tomate concassée", 200, "purée de tomate"),
            _i("Poivron", 120, "poivron"),
            _i("Riz blanc cuit", 150, "riz blanc cuit"),
        ),
    ),
)

# ── Dîners ─────────────────────────────────────────────────────────────────

DINNERS: tuple[RecipeSpec, ...] = (
    RecipeSpec(
        slug="saumon-patate-douce",
        name="Saumon, patate douce, épinards",
        meals=("dinner",),
        tags=("proteine", "post-surf"),
        prep_min=25,
        steps="Patate douce au four, saumon dix minutes à côté, épinards à la poêle.",
        ingredients=(
            _i("Saumon", 150, "saumon"),
            _i("Patate douce", 220, "patate douce"),
            _i("Épinards", 150, "epinard"),
            _i("Huile d'olive", 10, "huile d'olive"),
        ),
    ),
    RecipeSpec(
        slug="omelette-pommes-de-terre",
        name="Omelette pommes de terre",
        meals=("dinner",),
        tags=("rapide", "veggie"),
        prep_min=18,
        steps="Pommes de terre en rondelles dorées, œufs par-dessus, couvercle.",
        ingredients=(
            _i("Œufs", 165, "oeuf"),
            _i("Pommes de terre cuites", 220, "pomme de terre cuite"),
            _i("Oignon", 60, "oignon"),
            _i("Huile d'olive", 12, "huile d'olive"),
        ),
    ),
    RecipeSpec(
        slug="soupe-legumes-lentilles",
        name="Soupe légumes lentilles",
        meals=("dinner",),
        tags=("veggie",),
        prep_min=25,
        steps="Poireau, carotte, lentilles corail, vingt minutes, on mixe à moitié.",
        ingredients=(
            _i("Lentilles corail cuites", 180, "lentille cuite"),
            _i("Carotte", 150, "carotte"),
            _i("Poireau", 120, "poireau"),
            _i("Pain complet", 60, "pain complet"),
        ),
    ),
    RecipeSpec(
        slug="pates-pesto-poulet",
        name="Pâtes pesto poulet",
        meals=("dinner",),
        tags=("rapide", "proteine"),
        prep_min=15,
        steps="Pâtes, poulet coupé, pesto hors du feu pour qu'il reste vert.",
        ingredients=(
            _i("Pâtes cuites", 250, "pates cuites"),
            _i("Blanc de poulet", 140, "poulet blanc"),
            _i("Pesto", 30, "pesto"),
            _i("Parmesan", 15, "parmesan"),
        ),
    ),
    RecipeSpec(
        slug="curry-legumes-pois-chiches",
        name="Curry légumes pois chiches",
        meals=("dinner",),
        tags=("veggie",),
        prep_min=25,
        steps="Oignon, curry, lait de coco, légumes et pois chiches. Riz à côté.",
        ingredients=(
            _i("Pois chiches cuits", 180, "pois chiche cuit"),
            _i("Lait de coco", 120, "lait de coco"),
            _i("Courgette", 150, "courgette"),
            _i("Riz blanc cuit", 180, "riz blanc cuit"),
        ),
    ),
    RecipeSpec(
        slug="cabillaud-riz-courgettes",
        name="Cabillaud, riz, courgettes",
        meals=("dinner",),
        tags=("proteine",),
        prep_min=20,
        steps="Cabillaud vapeur ou papillote, riz, courgettes poêlées à l'ail.",
        ingredients=(
            _i("Cabillaud", 170, "cabillaud"),
            _i("Riz blanc cuit", 200, "riz blanc cuit"),
            _i("Courgette", 180, "courgette"),
            _i("Huile d'olive", 10, "huile d'olive"),
        ),
    ),
    RecipeSpec(
        slug="steak-hache-haricots",
        name="Steak haché, haricots verts",
        meals=("dinner",),
        tags=("proteine", "rapide", "post-surf"),
        prep_min=15,
        steps="Steak saignant, haricots verts à la poêle avec de l'ail, pommes vapeur.",
        ingredients=(
            _i("Steak haché 5 %", 150, "steak hache"),
            _i("Haricots verts", 200, "haricot vert"),
            _i("Pommes de terre cuites", 200, "pomme de terre cuite"),
        ),
    ),
    RecipeSpec(
        slug="gratin-courgettes-chevre",
        name="Gratin courgettes chèvre",
        meals=("dinner",),
        tags=("veggie",),
        prep_min=25,
        steps="Courgettes en rondelles, chèvre, un œuf battu, vingt minutes au four.",
        ingredients=(
            _i("Courgette", 300, "courgette"),
            _i("Fromage de chèvre", 80, "fromage de chevre"),
            _i("Œufs", 110, "oeuf"),
            _i("Pain complet", 60, "pain complet"),
        ),
    ),
    RecipeSpec(
        slug="wok-boeuf-nouilles",
        name="Wok bœuf nouilles",
        meals=("dinner",),
        tags=("proteine", "post-surf"),
        prep_min=20,
        steps="Bœuf saisi très chaud, légumes croquants, nouilles, soja en fin.",
        ingredients=(
            _i("Bœuf", 150, "boeuf"),
            _i("Nouilles cuites", 220, "pates cuites"),
            _i("Poivron", 120, "poivron"),
            _i("Sauce soja", 15, "sauce soja"),
        ),
    ),
    RecipeSpec(
        slug="tortilla-haricots-noirs",
        name="Tortilla haricots noirs",
        meals=("dinner",),
        tags=("veggie", "rapide"),
        prep_min=15,
        steps="Haricots écrasés au cumin dans la galette, avocat, citron vert.",
        ingredients=(
            _i("Galette de blé", 90, "galette de ble"),
            _i("Haricots rouges cuits", 180, "haricot rouge cuit"),
            _i("Avocat", 80, "avocat"),
            _i("Tomate", 80, "tomate"),
        ),
    ),
    RecipeSpec(
        slug="poulet-roti-legumes",
        name="Poulet rôti légumes du four",
        meals=("dinner",),
        tags=("proteine",),
        prep_min=25,
        steps="Cuisse de poulet et légumes sur la même plaque, herbes, vingt-cinq minutes.",
        ingredients=(
            _i("Cuisse de poulet", 180, "poulet cuisse"),
            _i("Pommes de terre cuites", 220, "pomme de terre cuite"),
            _i("Carotte", 120, "carotte"),
            _i("Huile d'olive", 12, "huile d'olive"),
        ),
    ),
    RecipeSpec(
        slug="risotto-champignons",
        name="Risotto champignons",
        meals=("dinner",),
        tags=("veggie",),
        prep_min=25,
        steps="Riz nacré, bouillon louche par louche, champignons poêlés à part.",
        ingredients=(
            _i("Riz blanc cuit", 230, "riz blanc cuit"),
            _i("Champignons de Paris", 180, "champignon de paris"),
            _i("Parmesan", 25, "parmesan"),
            _i("Huile d'olive", 10, "huile d'olive"),
        ),
    ),
)

# ── En-cas ─────────────────────────────────────────────────────────────────

SNACKS: tuple[RecipeSpec, ...] = (
    RecipeSpec(
        slug="banane-amandes",
        name="Banane et amandes",
        meals=("snack",),
        tags=("rapide", "veggie", "post-surf"),
        prep_min=1,
        steps="Rien à faire. Tient dans la poche du sac.",
        ingredients=(
            _i("Banane", 120, "banane"),
            _i("Amandes", 30, "amande"),
        ),
    ),
    RecipeSpec(
        slug="fromage-blanc-miel",
        name="Fromage blanc miel noix",
        meals=("snack",),
        tags=("proteine", "rapide", "veggie"),
        prep_min=2,
        steps="Fromage blanc, une cuillère de miel, des noix cassées dessus.",
        ingredients=(
            _i("Fromage blanc", 250, "fromage blanc"),
            _i("Miel", 15, "miel"),
            _i("Noix", 25, "noix"),
        ),
    ),
    RecipeSpec(
        slug="tartine-beurre-cacahuete",
        name="Tartine beurre de cacahuète",
        meals=("snack",),
        tags=("rapide", "post-surf"),
        prep_min=2,
        steps="Pain complet, beurre de cacahuète, banane en rondelles.",
        ingredients=(
            _i("Pain complet", 60, "pain complet"),
            _i("Beurre de cacahuète", 25, "beurre de cacahuete"),
            _i("Banane", 80, "banane"),
        ),
    ),
    RecipeSpec(
        slug="oeufs-durs-tomates",
        name="Œufs durs, tomates cerises",
        meals=("snack",),
        tags=("proteine", "rapide"),
        prep_min=10,
        steps="Neuf minutes dans l'eau bouillante, sel, tomates à côté.",
        ingredients=(
            _i("Œufs", 110, "oeuf"),
            _i("Tomate", 120, "tomate"),
        ),
    ),
    RecipeSpec(
        slug="houmous-crudites",
        name="Houmous et crudités",
        meals=("snack",),
        tags=("veggie", "rapide"),
        prep_min=5,
        steps="Pois chiches mixés au tahini et citron, carottes et concombre en bâtonnets.",
        ingredients=(
            _i("Pois chiches cuits", 120, "pois chiche cuit"),
            _i("Tahini", 15, "puree de sesame"),
            _i("Carotte", 100, "carotte"),
            _i("Concombre", 100, "concombre"),
        ),
    ),
    RecipeSpec(
        slug="compote-flocons",
        name="Compote et flocons",
        meals=("snack",),
        tags=("rapide", "veggie", "post-surf"),
        prep_min=2,
        steps="Compote sans sucre ajouté, flocons d'avoine crus dedans.",
        ingredients=(
            _i("Compote de pomme", 200, "compote de pomme"),
            _i("Flocons d'avoine", 40, "flocons d'avoine"),
        ),
    ),
    RecipeSpec(
        slug="pain-fromage-noix",
        name="Pain, fromage, noix",
        meals=("snack",),
        tags=("rapide",),
        prep_min=3,
        steps="Une tranche de pain, du comté, quelques noix.",
        ingredients=(
            _i("Pain complet", 60, "pain complet"),
            _i("Comté", 40, "comte"),
            _i("Noix", 20, "noix"),
        ),
    ),
)


ALL_RECIPES: tuple[RecipeSpec, ...] = (
    *BREAKFASTS,
    *LUNCHES,
    *DINNERS,
    *SNACKS,
)


def by_meal(meal: str) -> list[RecipeSpec]:
    return [recipe for recipe in ALL_RECIPES if meal in recipe.meals]
