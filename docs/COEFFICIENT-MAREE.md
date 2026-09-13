# Coefficient de marée — calcul, et écart mesuré contre le SHOM

> Décidé le 13/09. Rejouable : `python -m scripts.check_tide_coefficient --days 5 --shom …`
> Code : `app/services/tide_coefficient.py` · Tests : `tests/test_tide_coefficient.py`

## Ce qu'on calcule

Le coefficient de marée est **national par définition** : le SHOM le calcule au
port de référence de **Brest**, et il vaut de Dunkerque à Hendaye. Ce n'est pas
une approximation qu'on s'autorise pour la côte basque, c'est la définition.

```
C = (H_PM − N0) / U × 100
```

| Terme | Ce qu'on met dedans |
|---|---|
| `H_PM` | Hauteur de la pleine mer, à Brest, lue sur `sea_level_height_msl` d'Open-Meteo |
| `N0` | Niveau moyen du **modèle**, mesuré sur 30 jours glissants |
| `U` | Unité de hauteur de Brest : **3,05 m**. Constante SHOM |

Deux détails de méthode font toute la précision, et ils ne sont pas
optionnels :

**1. Le niveau moyen est mesuré, pas supposé.** Open-Meteo annonce un niveau
*relatif au niveau moyen de la mer*, donc `N0` devrait valoir zéro. Il vaut en
réalité **−0,39 m** à Brest sur la fenêtre du 14/08 au 18/09/2026. Poser `N0 = 0`
ajouterait **13 points** à tous les coefficients, en permanence. C'est le plus
gros terme d'erreur du calcul, et il est invisible tant qu'on ne le cherche pas.

**2. Le sommet est interpolé, pas échantillonné.** Une marée a une période de
12 h 25 : l'échantillon horaire tombe presque toujours à côté du sommet, jusqu'à
une demi-heure avant ou après. Sur une sinusoïde, une demi-heure coûte 3 % de
hauteur, soit **trois points de coefficient**, systématiquement en moins. Une
parabole sur trois points récupère le sommet et son heure.

## Mesure du 13/09/2026 — dix pleines mers

Référence : annuaire SHOM pour Brest, via [maree.info](https://maree.info/82/calendrier)
et [Météo Consult Marine](https://marine.meteoconsult.fr/meteo-marine/horaires-des-marees/brest-4/septembre-2026),
qui concordent exactement.

Niveau moyen du modèle sur 851 h : **−0,391 m**

| Pleine mer (UTC) | Hauteur | Nous | SHOM | Écart |
|---|---|---|---|---|
| 2026-09-13 16:39 | 2,502 m | 95 | 97 | −2 |
| 2026-09-14 04:56 | 2,271 m | 87 | 93 | **−6** |
| 2026-09-14 17:12 | 2,267 m | 87 | 89 | −2 |
| 2026-09-15 05:29 | 2,040 m | 80 | 83 | −3 |
| 2026-09-15 17:46 | 1,845 m | 73 | 77 | −4 |
| 2026-09-16 06:03 | 1,631 m | 66 | 70 | −4 |
| 2026-09-16 18:23 | 1,438 m | 60 | 63 | −3 |
| 2026-09-17 06:41 | 1,403 m | 59 | 56 | +3 |
| 2026-09-17 19:02 | 1,090 m | 49 | 49 | 0 |
| 2026-09-18 07:26 | 0,973 m | 45 | 41 | +4 |

- **Biais moyen : −1,7 point.**
- **Écart maximal : 6 points.**
- Droite d'ajustement : `SHOM = 1,120 × nous − 6,7`

## Verdict : le coefficient s'affiche avec « ≈ »

L'écart maximal mesuré (6 points) dépasse la tolérance de 5 points fixée le
13/09. Le coefficient est donc rendu **précédé d'un « ≈ »** partout où il
apparaît — tableau horaire, détail de créneau, détail de session. C'est
`MEASURED_MAX_GAP` dans `tide_coefficient.py` qui porte cette décision, et il
suffit de le mettre à jour après une nouvelle campagne de mesure pour que le
signe disparaisse.

Un chiffre approximatif annoncé comme exact est pire qu'un chiffre absent :
celui-ci, on sait qu'on ne peut pas s'y fier au point près, et on peut quand
même s'en servir pour distinguer une vive-eau d'une morte-eau — ce qui est
l'usage réel.

## Ce que dit la forme de l'erreur

L'écart n'est pas du bruit : il est **négatif en vive-eau et positif en
morte-eau**. La pente de 1,12 dit que le modèle d'Open-Meteo **comprime le
balancement vive-eau / morte-eau** d'environ 12 %. C'est un défaut de
résolution du modèle de marée, et non un décalage de datum — les deux ne se
corrigent pas de la même façon, d'où la droite d'ajustement dans la sortie du
script.

Le point à −6 (matin du 14/09) est l'**inégalité diurne** : le SHOM sépare les
deux marées du jour de 4 points (93 puis 89), le modèle les rend quasi égales
(2,271 m et 2,267 m). Un modèle à maille grossière lisse cette asymétrie.

**On ne corrige pas.** Appliquer `SHOM = 1,120 × nous − 6,7` collerait à dix
points, sur cinq jours, sur une seule phase lunaire — c'est du surajustement,
et la correction serait fausse le jour où Open-Meteo recalibre son modèle. La
règle du projet vaut ici comme ailleurs : on mesure, on consigne, on affiche ce
qu'on sait avec la réserve qui va avec. Le jour où une campagne couvrira
plusieurs lunaisons et confirmera la pente, la correction se posera — avec sa
date, comme `FORECAST_MODEL_VERSION`.

## Écart de temps, noté au passage

Les heures de pleine mer du modèle sont **en avance de 24 à 42 minutes** sur
l'annuaire, avec un écart qui décroît régulièrement le long de la période. Ça
ne touche pas le coefficient (c'est une hauteur, pas une heure), mais ça
concerne l'affichage de la marée sur le tableau horaire : la courbe du niveau
marin est en avance d'une demi-heure environ. À garder en tête avant de caler
une session sur l'étale à la minute près.

## Quand rejouer cette mesure

- Après un changement de version d'Open-Meteo ou de son modèle de marée ;
- Si un coefficient affiché paraît franchement faux à l'usage ;
- Au moins une fois par an, à l'équinoxe, où l'amplitude est maximale et où
  l'erreur de pente est donc la plus visible.

```
python -m scripts.check_tide_coefficient --days 5 \
  --shom 2026-09-14=93/89,2026-09-15=83/77
```

Le script sort en code 1 au-delà de la tolérance : il est utilisable tel quel
dans une vérification automatique le jour où on en voudra une.
