# Exploration ergonomique — architecture retenue et variantes UI

> Document de comparaison. Les maquettes vivent dans le canvas
> « Sport — exploration ergonomique ».
> Rien n'est décidé ici. Ce document sert à trancher.

## 1. Ce qui est retenu

**L'accueil est la journée, pas les domaines.** Ce qu'il y a à faire ou à noter
aujourd'hui, dans l'ordre où ça se vit : la fenêtre de mer, la séance, les
repas, la pesée. Les modules ne sont plus des onglets, ce sont les ingrédients
du jour — et c'est ce qui rend visible le lien entre eux : la cible calorique
monte parce qu'il y a eu 1 h 43 à l'eau, la séance de mobilité est proposée
parce qu'il y a eu trois jours de surf d'affilée.

**Trois destinations, et trois seulement :**

| | Contenu |
|---|---|
| **Jour** | la journée en cours, tous domaines mêlés |
| **Mer** | la prévision côte basque, 5 jours, toutes les 3 h |
| **Corps** | objectifs, formules d'entraînement, table et composition |

> **IMPORTANT** — Plus de barre à quatre onglets dont deux affichent « arrive au
> lot 4 ». Le training et la nutrition entrent par la porte « Corps », qui
> existe dès le premier jour.

---

## 2. La fenêtre du jour, enrichie

Le bloc de mer de l'accueil n'est plus un verdict, c'est un vrai tableau de
bord. Il affiche, sans défilement :

- la **note** du meilleur créneau et **l'heure** de ce créneau (09 – 11 h) ;
- **houle** en mètres, **période** en secondes, **direction** en lettres et en
  degrés ;
- **vent** moyen, **rafales**, et s'il est de terre ou de mer ;
- **marée** : sens, heure de pleine mer, coefficient ;
- **température de l'eau** ;
- les **huit créneaux de la journée** en une bande, le meilleur en accent ;
- un **aperçu de demain** en pied de bloc.

Onze informations dans un bloc qui se lit en deux secondes parce qu'une seule
est en grand. C'est ce que la version précédente ne faisait pas.

---

## 3. Le training — objectifs et formules

C'est la partie qui manquait. Elle repose sur deux objets.

**Trois objectifs mesurables**, chacun avec un point de départ, une valeur
courante et une cible — pas des intentions, des nombres :

| Objectif | Mesure | Départ | Aujourd'hui | Cible |
|---|---|---|---|---|
| Assouplissement | distance mains-sol, jambes tendues | −14 cm | −6 cm | 0 cm |
| Mobilité | rotation thoracique | 24° | 32° | 45° |
| Abdominaux | gainage tenu | 1:20 | 2:10 | 3:00 |

**Cinq formules**, chacune servant un ou deux objectifs :

| Formule | Durée | Fréquence | Sert |
|---|---|---|---|
| Réveil | 8 min | tous les matins | mobilité, entretien |
| Post-surf | 12 min | après chaque session | mobilité, épaules et hanches |
| Abdos | 15 min | 3 × / semaine | gainage |
| Souplesse longue | 25 min | 2 × / semaine | assouplissement |
| Renfo surf | 28 min | 2 × / semaine | force, épaules et jambes |

L'écran « Corps » montre les trois jauges, les cinq formules avec leur
avancement de la semaine (3 / 4, 5 / 7, 1 / 2…), et la prochaine séance. La
proposition du jour vient de là : la formule choisie est celle qui sert
l'objectif le plus en retard.

> **À DÉCIDER** — `PROJET.md` §5 prévoit `exercises`, `programs`, `workouts`,
> mais **pas d'objectifs mesurés**. Il faut une table de plus — une mesure
> datée par objectif — et un rappel de mesure toutes les deux ou trois semaines.
> Coût : négligeable ; effet : c'est ce qui transforme le training en suivi.

---

## 4. Les cinq variantes

Même architecture, même contenu, cinq écritures. Trois écrans chacune : accueil,
corps, prévisions.

| | **V1 Cartes** | **V2 Liste dense** | **V3 La marée** | **V4 Plein cadre** | **V5 Le cadran** |
|---|---|---|---|---|---|
| Registre | classique | classique | originale | originale | originale |
| Principe | une carte par sujet | une colonne, filets fins, valeurs à droite | la courbe de marée porte la journée | trois bandes pleine largeur, un chiffre énorme chacune | la journée est un cadran de 24 h |
| Info par écran | moyenne | **la plus forte** | moyenne | **la plus faible** | forte |
| Lecture au soleil, à bout de bras | correcte | difficile | correcte | **la meilleure** | bonne |
| Lecture de la grille 5 jours | bonne (liste verticale) | **excellente** (matrice entière) | belle mais approximative | claire mais 5 écrans | originale, moins précise |
| Personnalité | aucune | austère | **forte, et issue du sujet** | forte | **la plus mémorable** |
| Ce qu'elle sacrifie | se confond avec n'importe quelle app | tout a le même poids | la mise en page bouge avec la marée | il faut défiler pour tout voir | un cadran s'apprend une fois |
| Risque | oubliable | fatigue visuelle | jolie mais instable | pauvre en information | gadget si mal exécuté |

---

## 5. Recommandation

**Un hybride, pas une variante :**

- **V4 Plein cadre pour l'accueil et pour « Corps ».** C'est le seul traitement
  qui respecte vraiment la règle §1.9 de `PROJET.md` — *une seule information par
  écran sur les parcours quotidiens* — et la règle de lecture au soleil. Sur
  l'écran corps, le fait que l'objectif en retard passe en orange plein dit tout
  sans une ligne de texte.
- **V2 Liste dense pour « Mer ».** `PROJET.md` §1.9 prévoit déjà **une seule vue
  dense**. C'était le tableau multi-spots ; c'est maintenant la grille 5 jours ×
  8 créneaux, et la matrice de V2 la fait tenir en entier sur un écran, sans
  défilement ni pagination par jour.

Ce que je garderais des autres :

1. **De V5 — l'arc de journée.** Si la bande de huit barres de V4 se révèle trop
   grossière pour repérer où tombe la bonne fenêtre, l'anneau de 24 h le dit
   mieux, et il tient dans un coin de bloc.
2. **De V3 — le segment de marée épais.** Marquer la fenêtre de surf *sur* la
   courbe de marée, plutôt qu'à côté, est la seule façon de montrer en un trait
   que la bonne fenêtre est une histoire de marée autant que de houle.
3. **De V1 — le pied de bloc « demain ».** Deux lignes qui évitent d'ouvrir
   l'écran Mer neuf fois sur dix.

---

## 6. Ce que ça change dans ce qui est codé

**Reste utile tel quel** : auth, PWA, `forecasts` et l'ingestion Open-Meteo /
MFWAM, `services/scoring.py`, `services/sun.py`, le backfill d'archive,
`daily_log`, `POST /sessions`, le modèle `surf_sessions` avec ses deux notes et
son `conditions_snapshot`.

**Sort du produit** — conséquence de « une seule côte » : le catalogue mondial
OSM et `import_osm_spots.py`, l'orientation de côte calculée, les trois niveaux
d'ingestion, le rayon, les favoris, les spots masqués, `GET /spots/nearby`,
`POST /spots/position`, la carte et le comparateur multi-spots. La table `spots`
reste, réduite à une liste de lieux pour étiqueter une session.

> **IMPORTANT** — Il reste une tâche du lot 1 : lancer
> `python -m scripts.import_osm_spots` en production, monde entier. **Ne la lance
> pas.** Elle n'a plus d'objet.

**Reste à écrire, et remonte en priorité** : le training (lot 4) et la nutrition
(lot 5). Dans cette architecture, l'accueil les affiche dès le premier jour — un
accueil « ta journée » avec deux blocs vides serait pire que quatre onglets.

---

## 7. À décider

1. **Ordre des lots.** Proposition : **lot 2 (session) → lot 4 (training) →
   lot 5 (nutrition) → lot 3 (reco) → lot 6 (stats)**.
2. **Table de mesures d'objectifs** (§3) — à ajouter au modèle de données.
3. **La règle « aucune vue qui n'existe qu'en desktop »** (`PROJET.md` §1, règle
   n° 2). Proposition de reformulation : *« aucun parcours quotidien qui n'existe
   qu'en desktop »*.
4. **Historiser les runs de prévision.** `UniqueConstraint(spot_id, ts, source)`
   + `ON CONFLICT DO UPDATE` font que la passe du matin écrase la prévision émise
   la veille au soir. Sans un `run_ts` dans la clé, ni l'écart « depuis hier
   soir » ni la calibration prévision ↔ mesure de §7.3 ne sont possibles, et
   chaque jour d'ingestion sans lui est perdu définitivement. ~0,5 j + une
   migration.
