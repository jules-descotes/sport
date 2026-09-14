# CANDHIS — ce que dit l'API, et ce qu'elle ne dit pas

> Référence pour le lot 1 bis. Relevé le 2026-09-14 dans
> `https://candhis.cerema.fr/doc/04_Candhis_API_v1_Utilisateur.pdf`
> (« API PHP REST de Candhis (v1) — Documentation utilisateur »,
> Cerema REM-D2PN/PN/ALG, **octobre 2024**), complété par la liste publique des
> campagnes et par le jeu data.gouv des houlographes.
>
> **Écrit avant le code, et c'est volontaire.** La leçon de `sport=surfing` :
> on vérifie la donnée avant de s'y fier. Tout ce qui suit a été lu dans la
> documentation ; ce qui n'y est pas est signalé comme tel, jamais comblé par
> une supposition silencieuse.

## 1. Accès

| | |
|---|---|
| Base | `https://candhis.cerema.fr/API/v1/` |
| Méthode | `GET` **uniquement** — toutes les autres sont bloquées |
| Authentification | en-tête `Authorization`, valeur = le jeton nu |
| Forme du jeton | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` (un UUID) |
| Encodage | JSON, UTF-8 |

L'en-tête porte le jeton **tel quel**, sans le préfixe `Bearer`. L'exemple de
la documentation est sans ambiguïté :

```
curl -X GET -H "Authorization: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
  https://candhis.cerema.fr/API/v1/getCampListe.php?type=2
```

Le jeton se demande à l'équipe Candhis en déclarant son nom, son domaine
d'activité et le type de sa structure. Le nôtre est posé en variable Railway
`CANDHIS_API_KEY`, **jamais dans le dépôt ni dans un fichier** (cf. CLAUDE.md,
décidé le 15/09).

## 2. Enveloppe de réponse

Toutes les fonctions renvoient le même tableau JSON :

| Clé | Contenu |
|---|---|
| `apiVer` | n° de version de l'API — `1.xx` pour la v1 |
| `success` | `True` ou `False` |
| `message` | message de retour, spécifique à chaque fonctionnalité |
| `nbLig` | nombre de lignes de `results` |
| `entete` | **en-têtes de colonnes** de `results` |
| `results` | tableau de valeurs |

> ⚠️ **`success` se lit toujours, le code HTTP ne suffit pas.** Un échec
> *métier* — pas de données pour cette campagne, valeur de paramètre non
> reconnue — répond **HTTP 200** avec `success: False`, `nbLig: 0` et
> `entete`/`results` à `Null`. Seuls les échecs *protocolaires* portent un
> code 4xx. Un client qui se contenterait de `raise_for_status()` prendrait
> « aucune donnée » pour un succès et écrirait une passe vide sans un mot.

| `success` | Code HTTP | Cas |
|---|---|---|
| `True` | 200 | appel valide |
| `False` | 200 | aucune donnée, valeur de paramètre non reconnue |
| `False` | 400 | paramètre en doublon, non autorisé, requête incomplète ou valeur incorrecte |
| `False` | 401 | utilisateur non authentifié |
| `False` | 404 | ressource non trouvée |
| `False` | 405 | méthode non autorisée |
| `False` | 423 | ressource verrouillée (**IP bannie**) |
| `False` | 429 | quota de requêtes quotidiennes atteint |

Le 423 mérite d'être lu deux fois : une IP peut être bannie. C'est exactement
ce qui est arrivé à l'IP de sortie Railway sur Overpass le 12/09. D'où le
compteur de quota persisté et le plafond dur — on n'attend pas de se faire
bannir pour se limiter.

**`entete` est l'en-tête de `results`, et il change selon la campagne.** Ce
n'est pas un JSON à clés : c'est un tableau de colonnes et un tableau de
lignes. La correspondance nom → valeur se reconstruit à chaque réponse, et
c'est pour ça que le client ne peut pas se contenter d'un index de colonne.

## 3. Quota

La documentation décrit le code 429 (« Quota requêtes quotidiennes atteint »)
mais **ne publie aucun chiffre**. Le nôtre vient de l'attribution du jeton :
**150 requêtes par jour** (cf. CLAUDE.md, décidé le 15/09).

On s'arrête à **140** — un compteur persisté en base (`api_quota`), par
fournisseur et par jour UTC. La marge de dix n'est pas de la pudeur : le
compteur est le nôtre, celui du Cerema est le sien, et deux compteurs ne
tombent jamais exactement d'accord sur le fuseau d'une journée.

## 4. Fonctionnalités

| Fonction | Ce qu'elle rend |
|---|---|
| `getCampListe.php` | liste des campagnes |
| `getCampInfos.php` | informations sur une campagne |
| `getCampDispo.php` | disponibilité des données d'une campagne |
| `getCampZone.php` | liste des campagnes d'une zone |
| `getCampTD.php` | données **temps différé** d'une campagne |
| `getCampTR.php` | données **temps réel** d'une campagne |
| `getCampListeTR.php` | **dernière** donnée temps réel d'une liste de campagnes |

### 4.1 `getCampListe.php?type=i`

`type` est **optionnel** (1 caractère numérique) :

| `type` | Houlographe |
|---|---|
| `0` | non directionnel **H13** |
| `1` | directionnel **Hm0** |
| `2` | directionnel **H13** |

`entete` : `["Code campagne", "Nom", "Actif", "Type données TR"]`.

```json
["02911", "Les Pierres Noires", "1", "TR directionnel H13"]
```

C'est le seul endroit qui donne **`Actif`**. C'est donc lui qui décide quelle
bouée est vivante, et non une liste écrite à la main ici.

### 4.2 `getCampInfos.php?camp=ccccc`

`camp` obligatoire, 5 caractères alphanumériques.

`entete` : `["Nom", "Latitude", "Longitude", "Profondeur", "Directionnel", "Capteur"]`.

```json
["Les Pierres Noires", "48.2903328", "-4.9683332", "60.000", "1", "Houlographe Datawell DWR MkIII 90"]
```

Latitude et longitude sont ici en **degrés décimaux**, en chaînes de
caractères. (Le jeu data.gouv, lui, les écrit en degrés-minutes — voir §7.)

### 4.3 `getCampDispo.php?camp=ccccc`

`entete` : `["Année", "Mois", "Nombre mesures"]`. Sert à savoir où chercher
avant de dépenser une requête de données sur un mois vide.

### 4.4 `getCampZone.php?zone=Zxx`

| Zone | |
|---|---|
| `Z01` | France métropolitaine |
| `Z02` | Nord Atlantique — Manche Ouest |
| `Z03` | Manche — Mer du Nord |
| `Z04` | Méditerranée |
| `Z05` | Outre-Mer Océan Atlantique (Antilles, Guyane, Saint-Pierre-et-Miquelon) |
| `Z06` | Outre-Mer Océan Indien (La Réunion, Mayotte) |
| `Z07` | **Golfe de Gascogne** |

> ⚠️ **`results` n'a pas la même forme ici.** `entete` vaut `["N° campagne"]`
> et `results` est une liste **plate de chaînes** — `["02201", …, "05610"]` —
> et non une liste de lignes. Un client qui déroulerait chaque ligne comme un
> tableau lirait les caractères un par un.

### 4.5 `getCampTD.php` — temps différé

`?camp=ccccc&dateDeb=AAAA-MM-JJ&dateFin=AAAA-MM-JJ`

Colonnes (directionnel) : `DateHeure`, `H13D`, `H110D`, `HMAXD`, `HSIGMA`,
`HRMSD`, `H2%D`, `TH13D`, `TH110D`, `TAVGD`, `THMAXD`, `TMAXD`, `ETAMAX`,
`ETAMIN`, `SZ13D`, `SZMAXD`, `TSZMAXD`, `NBRE_VAG`, `SKEW`, `KURT`, `RHH`,
**`HM0`**, **`TP`**, **`T02`**, `TE`, `EPS2`, `KAPA`, **`THETAP`**,
`THETAM`, **`SIGMAP`**, `SIGMAM`, `QUALITE`, `NBSYS`, puis les quatre
partitions `…_S1` à `…_S4`, et `QUALITE`.

`DateHeure` y est au format `AAAA-MM-JJ HH:MM:SS`.

Le temps différé est la donnée **validée**, mais elle arrive avec des mois de
retard. On ne l'utilise pas au lot 1 bis : le volet `observed` d'une session et
la calibration ont besoin de ce qui existe le jour même.

### 4.6 `getCampTR.php` — temps réel *(c'est celui qu'on utilise)*

`?camp=ccccc&dateDeb=AAAA-MM-JJ[&dateFin=AAAA-MM-JJ]`

- `camp` et `dateDeb` **obligatoires**, `dateFin` optionnel.
- **L'intervalle maximum est de 12 mois.** Au-delà, la date de fin est
  corrigée d'office et `message` le dit.
- Sans `dateFin`, elle vaut `dateDeb + 12 mois`. Un appel qui l'oublie ne
  ramène donc pas « aujourd'hui » : il ramène une année.
- `FT` existe, réservé Cerema, non implémenté.

> ⚠️ **Les dates sont des jours, pas des instants.** Il n'existe aucun moyen de
> demander « les trois dernières heures » : la granularité de l'API est la
> journée. Une fenêtre de 3 h est donc un filtre **côté client** sur une
> requête d'un ou deux jours. C'est ce que fait le job horaire.

**`entete` change selon le type de houlographe** — c'est le point qui rend un
index de colonne codé en dur impossible :

*TR directionnel H13*
```
["Date", "H1/3 (m)", "Hmax (m)", "TH1/3 (s)", "Dir. au pic (°)", "Etal. au pic (°)", "Temp. mer (°C)"]
["2022-03-26 00:00", "1.1000", "1.9000", "11.6000", "260.0000", "19.0000", "10.4000"]
```

*TR non directionnel H13*
```
["Date", "H1/3 (m)", "Hmax (m)", "TH1/3 (s)", "T. au pic (s)", "Temp. mer (°C)"]
["2022-03-12 15:30", "2.2000", "3.5000", "11.0000", "16.7000", "999.9999"]
```

*TR directionnel Hm0*
```
["Date", "Hm0 (m)", "Hmax (m)", "T02 (s)", "Dir. au pic (°)", "Temp. mer (°C)"]
["2021-08-25 06:56", "0.8000", "999.9999", "3.2000", "46.0000", "999.9999"]
```

Trois choses s'y lisent, et elles commandent tout le client :

1. **`999.9999` est la valeur manquante.** Elle apparaît sur `Hmax` et sur
   `Temp. mer` dans les exemples *de la documentation elle-même*. La prendre au
   premier degré donnerait une mer à 1 000 °C et une vague de 1 km. Toute
   valeur ≥ 999 est lue comme absente.
2. **Les libellés sont des intitulés humains**, avec des unités, des accents et
   des espaces dont on ne peut pas jurer au caractère près (ils viennent d'un
   PDF). Le client les apparie donc sur une forme **normalisée** — minuscules,
   sans accents, sans espaces — et jamais sur un index de colonne.
3. **Le pas de temps n'est pas garanti régulier.** 48 lignes sur une journée
   dans le premier exemple, soit 30 min ; mais le troisième est horodaté
   `06:56`, qui n'est aligné sur rien. On ne déduit donc pas l'heure d'un
   rang : on lit la colonne `Date`.

Selon le type, **la période disponible n'est pas la même grandeur** : `TH1/3`
(période des H1/3) pour les H13, `T02` (période moyenne) pour les Hm0, et
`T. au pic` pour les non directionnels. Elles ne se rangent pas dans la même
colonne de `observations` — voir §6.

### 4.7 `getCampListeTR.php?type=i[&camp=c1,c2,…]`

« Seule la dernière donnée horaire disponible est récupérée. » Même forme que
`getCampTR.php`, avec une colonne **`Campagne`** en tête. Sans `camp`, toutes
les campagnes du `type` ; avec, celles qui ne sont pas du bon `type` sont
ignorées **en silence**.

Un appel pour N bouées : c'est l'endpoint le moins cher qui existe ici. On ne
s'en sert pas pour le job horaire — il ne rend qu'un point, donc il ne
rattrape aucun trou après un redémarrage — mais c'est lui qu'il faudra prendre
le jour où on suivra plusieurs bouées.

## 5. Le fuseau horaire n'est pas documenté

**La documentation de l'API ne dit nulle part dans quel fuseau sont les
horodatages.** Ni `04_Candhis_API_v1_Utilisateur.pdf`, ni les conditions
d'utilisation. C'est le seul trou important de ce relevé, et il n'est pas
comblé ici par une supposition déguisée en fait.

Ce qui est fait à la place :

- les horodatages sont interprétés selon `CANDHIS_TZ`, **par défaut `UTC`** —
  la convention des archives océanographiques, et celle du reste de la base
  (cf. CLAUDE.md : « dates et heures en UTC en base ») ;
- la variable existe précisément pour corriger sans redéployer si la mesure
  dit le contraire ;
- **la table de calibration le dira toute seule.** Un décalage d'une ou deux
  heures entre la bouée et la prévision ne se cache pas : il apparaît comme un
  biais qui change de signe avec la marée et comme une erreur minimale à
  délai nul. Si le biais à 0–6 h ne s'annule pas alors que la bouée est à 4 km,
  regarder le fuseau **avant** de conclure quoi que ce soit sur le modèle.

## 6. Ce qu'on en range dans `observations`

`observations` existe depuis le lot 1, créée vide. Elle porte déjà `hm0_m`,
`peak_period_s`, `mean_period_s`, `wave_direction_deg` et
`water_temperature_c`. Le lot 1 bis y ajoute l'étalement, les valeurs brutes et
la version du format.

| Colonne | TR directionnel Hm0 | TR directionnel H13 | TR non directionnel H13 |
|---|---|---|---|
| `hm0_m` | `Hm0 (m)` | `H1/3 (m)` | `H1/3 (m)` |
| `wave_height_max_m` | `Hmax (m)` | `Hmax (m)` | `Hmax (m)` |
| `mean_period_s` | `T02 (s)` | — | — |
| `peak_period_s` | — | `TH1/3 (s)` | **`T. au pic (s)`**, sinon `TH1/3 (s)` |
| `wave_direction_deg` | `Dir. au pic (°)` | `Dir. au pic (°)` | — |
| `directional_spread_deg` | — | `Etal. au pic (°)` | — |
| `water_temperature_c` | `Temp. mer (°C)` | `Temp. mer (°C)` | `Temp. mer (°C)` |

> `H1/3` et `Hm0` ne sont pas la même grandeur — l'une est la moyenne du tiers
> supérieur des vagues, l'autre se déduit du moment d'ordre zéro du spectre.
> Elles sont très proches en mer du vent et la littérature les échange
> couramment. On les range donc dans la **même** colonne `hm0_m`, et `raw`
> garde le libellé d'origine : le jour où l'écart comptera, il sera encore là.

> ⚠️ **Le houlographe non directionnel publie `TH1/3` *et* `T. au pic` sur la
> même ligne** — 11,0 s et 16,7 s dans l'exemple du Cerema. Ce sont deux
> grandeurs différentes, et prendre la première venue retiendrait 11 s là où la
> période de pic vaut 16,7 s : cinq secondes d'écart sur la grandeur qui décide
> si une houle est exploitable. `T. au pic` l'emporte donc toujours, où qu'elle
> soit dans l'en-tête, et `TH1/3` n'est qu'un **repli**.
>
> Ce repli n'est pas de la commodité : les houlographes H13 directionnels —
> dont **les deux de la côte basque** — ne publient que `TH1/3`. Sans lui, la
> bouée maison n'aurait aucune période, et la calibration des périodes n'aurait
> jamais rien à comparer.
>
> *(Cette ligne du tableau était fausse dans la première version de ce
> document : elle donnait au non directionnel `T. au pic` seul. C'est un test
> qui l'a relevée, pas une relecture.)*

`raw` (JSONB) garde **la ligne entière appariée à son en-tête**, telle que
l'API l'a rendue. C'est ce qui permettra de récupérer une colonne qu'on n'a pas
su lire aujourd'hui sans redemander douze mois d'archive.

`format_version` porte le type de houlographe reconnu
(`tr-directionnel-hm0`, `tr-directionnel-h13`, `tr-non-directionnel-h13`) :
le même principe que `model_version` sur `forecasts`. Le jour où le Cerema
ajoute une colonne, l'historique dit dans quelle grammaire il a été écrit.

## 7. Les stations, et celle qu'on suit

La liste publique des campagnes et le jeu data.gouv **« Stations de mesure de
Candhis »** (`candhis_houlographes_202412.gpkg`, 118 houlographes) donnent les
positions. Sur la côte basco-landaise :

| Code | Nom | Latitude | Longitude | Temps réel |
|---|---|---|---|---|
| `03302` | Cap Ferret | 44,65250 | −1,44667 | oui |
| `03303` | Cap Ferret | 44,65250 | −1,44667 | — |
| `06401` | Bayonne | 43,54667 | −1,54333 | — |
| `06402` | **Anglet** | 43,53217 | −1,61500 | **oui** |
| `06403` | **Saint-Jean-de-Luz** | 43,40833 | −1,68167 | **oui** |

> Le GPKG écrit les coordonnées en degrés-minutes (`43°31,930'N`) dans ses
> colonnes texte, et en degrés décimaux dans la géométrie. Les valeurs
> ci-dessus viennent de la **géométrie**.

**La station maison n'est pas écrite en dur.** Elle est choisie à l'exécution :
la station **active**, en temps réel, la plus proche du spot favori principal,
à moins de 30 km. Avec le catalogue actuel, un favori dans les Landes ou à
Anglet retient **06402 Anglet**, un favori à Guéthary ou Ciboure retient
**06403 Saint-Jean-de-Luz**. Ces deux lignes décrivent l'état du réseau au
14/09 — elles ne le décident pas : `Actif` vient de `getCampListe.php`, et une
bouée part en carénage sans nous prévenir.

## 8. Conditions d'utilisation

Les données sont diffusées par le Cerema sous les conditions de
`https://candhis.cerema.fr/doc/01_Utilisation.fr.pdf`. Usage strictement
personnel et non commercial ici, comme Open-Meteo et Open Food Facts. On ne
réhéberge rien et on ne rediffuse rien.
