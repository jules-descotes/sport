# Projet — Site perso de suivi sportif

> Document de cadrage. Lu en début de session, avant toute action.
> Conventions de code et état d'avancement : `CLAUDE.md`.

## Identité

- **Nom de travail** : Sport (nom définitif à trancher)
- **Quoi** : site perso de suivi surf / training / nutrition, utilisable une main sur la plage
- **Pour qui** : Jules, seul dans un premier temps
- **URL cible** : `https://sport.atelier-okomi.fr` (front) + `https://api-sport.atelier-okomi.fr` (back)

## Périmètre demandé

**Global** — profil · connexion · stats
**Surf** — données météo de la côte · enregistrement de session + matos · notation · reco « plus proche voisin » · webcams des spots
**Training quotidien** — étirement / assouplissement · renfo surf · objectif composition corporelle
**Nutrition** — menu de la semaine · calories cibles selon l'entraînement

---

## 1. Contrainte n°1 — mobile

Le site est **utilisé sur téléphone, debout, souvent mouillé, parfois sans réseau**. C'est la contrainte qui prime sur tout le reste, y compris sur l'élégance du code.

**Règles non négociables :**

1. **PWA installable** — manifest + service worker, ajout à l'écran d'accueil iOS, plein écran sans barre Safari. Pas d'app native, pas de store.
2. **Mobile-first strict** — on dessine l'écran 390 px d'abord, le desktop est un bonus. Aucune vue qui n'existe qu'en desktop.
3. **Navigation par barre basse fixe** (4 onglets : Surf · Training · Nutrition · Stats). Zone du pouce. Pas de menu hamburger sur les parcours quotidiens.
4. **Cibles tactiles ≥ 44 px**, espacées. Aucun contrôle à moins de 16 px d'un bord.
5. **Zéro saisie clavier pendant l'effort** — la notation d'une session et le suivi d'une série se font en boutons, curseurs et molettes. Le clavier n'apparaît que pour les notes libres, optionnelles.
6. **Mode hors-ligne réel** — on doit pouvoir enregistrer une session sans réseau sur le parking de la plage. File d'attente locale (IndexedDB) synchronisée au retour du réseau.
7. **Lecture au soleil** — contrastes forts, pas de gris clair sur blanc, taille de police ≥ 16 px (évite aussi le zoom auto iOS sur les champs).
8. **Budget performance** : premier rendu utile < 2 s en 4G. Images en `next/image`, pas de librairie de graphes lourde.
9. **Une seule information par écran** sur les parcours quotidiens. Le tableau multi-spots est la seule vue dense, et elle scrolle horizontalement.

> **IMPORTANT** — Le premier écran de l'app doit répondre à une seule question : **« je vais à l'eau, oui ou non, et où ? »**. Tout le reste est à un tap de distance. Si cet écran demande plus de deux secondes de lecture, c'est raté.

---

## 2. Stack — alignée sur Atelier Okomi

On copie la stack du projet `atelier-okomi`, volontairement, pour ne rien réapprendre et réutiliser les workflows.

| Couche | Choix | Identique à Okomi |
|---|---|---|
| Back | FastAPI (Python 3.12), SQLAlchemy async, Pydantic Settings | oui |
| Base | PostgreSQL sur Railway (**instance dédiée**) / SQLite pour les tests | oui |
| Migrations | Alembic | oui |
| Front | Next.js 16 App Router, TypeScript, Tailwind 4 | oui |
| État / données | TanStack Query + Zustand, Zod, react-hook-form | oui |
| Auth | JWT maison (`python-jose` + `bcrypt`), cookie httpOnly | oui |
| Fichiers | Cloudflare R2 (photos de session) | oui, bucket dédié |
| Emails | Resend | oui |
| Jobs planifiés | **APScheduler dans le process FastAPI** | oui |
| Erreurs | Sentry | oui |
| Conteneur | Dockerfile `python:3.12-slim` + `run.py` / uvicorn | oui |
| Tests | pytest + pytest-asyncio | oui |

**Ce qui change par rapport à Okomi** : pas de Stripe, pas de SEO, pas d'admin. En échange : PWA, hors-ligne, et un job d'ingestion météo.

> **IMPORTANT** — L'ingestion météo tourne via **APScheduler dans le conteneur Railway**, comme le nettoyage des paniers abandonnés chez Okomi. Pas besoin de cron externe ni de service supplémentaire. Attention : si le service Railway redémarre, le job repart de zéro — l'ingestion doit être **idempotente** (`ON CONFLICT DO UPDATE` sur `(spot_id, ts, source)`).

---

## 3. Déploiement — réutilisation de l'existant

**Décision : repo séparé, même infrastructure.**

| Élément | Réutilisé | Nouveau |
|---|---|---|
| Domaine `atelier-okomi.fr` (OVH) | oui | 2 enregistrements DNS : `sport` et `api-sport` |
| Compte Railway | oui | 1 service (back) + 1 Postgres dédié |
| Compte Vercel | oui | 1 projet (front) |
| Compte Cloudflare R2 | oui | 1 bucket `sport-media` |
| Compte Resend | oui | rien (domaine déjà vérifié) |
| Workflows GitHub Actions | copiés depuis `atelier-okomi/.github/workflows/` | adaptés |
| Repo GitHub | non | `jules-descotes/sport` |

**Pourquoi pas dans le repo Okomi** : c'est une boutique en production avec Stripe en mode LIVE et 17 articles SEO. Un projet perso dans le même repo couple les déploiements, pollue le sitemap et fait qu'un bug de surf peut casser un paiement. Le coût de la séparation est de deux enregistrements DNS.

> **IMPORTANT — le CI/CD d'Okomi n'est pas ce qu'on croit.** `.github/workflows/deploy.yml` contient des jobs de déploiement **factices** (`echo "Railway deploy via CLI"`), et `ci.yml` est documenté comme désactivé. Le déploiement réel passe par les **intégrations GitHub natives de Railway et Vercel** (auto-deploy sur push `main`). Donc : on copie `ci.yml` pour les tests, on branche Railway et Vercel sur le repo, et on ne copie **pas** `deploy.yml`.

**Pièges hérités d'Okomi, à ne pas reproduire :**
- Le couple apex / `www` est mal aligné chez Okomi. Ici, choisir **un seul** hôte (`sport.atelier-okomi.fr`, sans `www`) et le déclarer partout : `SITE_URL`, `NEXT_PUBLIC_SITE_URL`, manifest PWA, cookie de session.
- `frontend/.env.local` d'Okomi pointe vers l'API **de production**. Ici, `.env.local` pointe vers `http://localhost:8000/api/v1`. Le dev local tape le local.

> **À DÉCIDER** — `sport.atelier-okomi.fr` est gratuit et immédiat, mais accroche un projet perso à une marque de boutique. Un domaine dédié coûte ~12 €/an. On part sur le sous-domaine, quitte à basculer plus tard (aucune dette : c'est une variable d'environnement).

---

## 4. Structure du repo

```
/                        back-end FastAPI (miroir d'Okomi)
  app/
    api/routes/          auth · profile · spots · forecasts · sessions · gear
                         exercises · programs · workouts · foods · meals · stats · recommend
    core/                config.py · security.py
    db/                  database.py
    models/              un fichier par agrégat
    schemas/             Pydantic
    services/            forecast_ingest · recommender · nutrition · scheduler
  alembic/
  tests/
  Dockerfile  railway.json  run.py  requirements.txt
/frontend                Next.js 16
  app/
    (app)/               page.tsx (accueil « je vais à l'eau ? »)
      surf/              spots/[slug] · sessions · sessions/new · matos
      training/          seance/[id] · exercices
      nutrition/         menu · journal
      stats/  profil/
    (auth)/login
  components/            ui/ · surf/ · training/ · nutrition/ · shell/ (BottomNav…)
  lib/                   api.ts · offline-queue.ts · store/
  public/                manifest.json · icônes PWA
/.github/workflows/ci.yml
CLAUDE.md  PROJET.md
```

---

## 5. Modèle de données

**Global** — `users` · `profiles` (taille, poids, niveau, disciplines) · `body_metrics` (date, poids, tour de taille, photo R2)

**Surf**
- `spots` — slug, nom, lat/lon, type (beach/reef/point), orientation de la plage, fenêtres idéales (houle min/max, période min, secteur de vent offshore, marée), niveau requis, URL webcam
- `forecasts` — spot_id, ts, hauteur/période/direction de houle, composantes de swell, vent moyen et rafale, température de l'eau, **source + version du modèle**. **Contrainte unique `(spot_id, ts, source)`**
- `observations` — mesures réelles (bouée CANDHIS, station de vent) : station_id, ts, Hm0, Tp, T02, direction, vent. Table **distincte** de `forecasts` : ce n'est pas la même grandeur, on ne les mélange jamais dans un même vecteur
- `tides` — spot_id, ts, hauteur, pleine/basse mer, marnage du jour
- `gear` — planches et combis : type, longueur, volume, discipline, date d'achat
- `surf_sessions` — spot_id, début, durée, **discipline**, gear utilisé, **note conditions**, **note perso**, nb de vagues, monde à l'eau, notes libres, `conditions_snapshot` (JSONB)
- `daily_log` — une ligne par jour : `surfé` / `regardé et renoncé` / `pas regardé`, spot envisagé, raison du renoncement. **Trois secondes de swipe par jour.**

> **IMPORTANT** — `conditions_snapshot` n'est pas un point, c'est une **fenêtre** : T−2 h, T−1 h, T0, en deux volets — `forecast` (ce qui était annoncé la veille) et `observed` (ce qu'ont mesuré la bouée et la station, enrichi a posteriori). C'est la fenêtre qui permet de calculer les **tendances** (houle montante ou descendante, vent qui se lève), et la tendance est un des signaux les plus forts. Sans ce figeage au moment de la session, la reco ne pourra jamais apprendre : c'est la seule décision de modèle irrattrapable après coup.

> **IMPORTANT** — `daily_log` corrige le biais de sélection : sans les jours où Jules a renoncé, le modèle n'apprend que la moitié haute de la distribution et ne sait pas reconnaître un mauvais jour. À 20 jours de surf par mois le déséquilibre est moins violent qu'on pourrait le craindre, mais les ~10 jours restants sont les seuls exemples négatifs disponibles — et ils coûtent un swipe.

> **IMPORTANT** — **Deux notes distinctes** à la saisie : *qualité des conditions* et *comment je me suis senti*. Une note unique mélange la houle et la forme du jour, et le modèle apprend du bruit.

> **IMPORTANT** — Colonne `discipline` sur la session **et** sur le matos. Les conditions idéales en foil sont quasi l'inverse du surf (petit, mou, onshore acceptable). Sans ce champ, les notes se contredisent et le modèle n'apprend rien.

**Training** — `exercises` (nom, groupe, catégorie mobilité/renfo/gainage, consignes, vidéo) · `programs` → `program_days` → `program_items` · `workout_sessions` → `workout_sets`

**Nutrition** — `foods` (import de la table **Ciqual 2025** de l'ANSES) · `recipes` → `recipe_items` · `meal_plans` → `meal_plan_items` · `food_log` · `daily_targets` (calculé, jamais saisi)

---

## 6. Données externes

| Besoin | Source | Coût |
|---|---|---|
| Houle, période, direction, swell — **prévision** | **Open-Meteo Marine API**, modèle **MFWAM (Météo-France)** explicitement sélectionné. Archive MFWAM depuis oct. 2021, ERA5-Ocean depuis 1940 | gratuit, sans clé, usage non commercial |
| Houle — **mesure réelle** | **CANDHIS (Cerema)** — `candhis.cerema.fr/API/v1/`, bouée de la côte basque. Alimente le modèle dernière minute et la calibration | gratuit, **jeton à demander** à candhis@cerema.fr |
| Vent, pluie, température de l'air | Open-Meteo Forecast API | gratuit, sans clé |
| Marées | WorldTides ou table annuelle importée une fois (le SHOM est payant) | **à décider** |
| Webcams | Windy Webcams API v3 pour le catalogue + iframe vers les webcams locales (Biarritz, Anglet, Landes) | clé gratuite |
| Aliments FR | Table Ciqual 2025 (ANSES / data.gouv.fr) | gratuit, import unique |
| Produits au code-barres | Open Food Facts | gratuit, sans clé |
| Exercices | wger (open source) pour amorcer | gratuit |

> **IMPORTANT** — **Pas de scraping.** Tout est en API propre : plus simple, légal, plus fiable. Et l'archive Open-Meteo permet de **reconstituer rétroactivement** les conditions des sessions passées si Jules les saisit.

> **IMPORTANT** — Prévision et mesure sont **deux grandeurs différentes**, stockées dans deux tables. La bouée n'existe pas dans le futur : elle ne peut pas servir au modèle moyen terme. En revanche, le couple (prévision, mesure) s'accumule **toutes les heures dès le jour 1** — soit ~8 700 points par an, sans aller à l'eau. De quoi mesurer l'erreur du fournisseur et afficher une barre d'incertitude sur les recos.

---

## 7. Moteur de reco surf

### 7.1 Double horizon

Deux usages distincts, deux modèles, deux écrans.

| | **Moyen terme — « je m'organise »** | **Dernière minute — « j'y vais ou pas »** |
|---|---|---|
| Horizon | J−5 à J−1 | H−2 à H0 |
| Question | Ça vaut le coup de poser mon vendredi ? | Je prends la voiture maintenant ? |
| Entrées | `forecasts` uniquement | `observations` (bouée + station vent) + webcam + dernière prévi |
| Nature | prédiction | mesure |
| Sortie | note prévue par spot et par créneau, sur 5 jours | verdict immédiat sur 2-3 spots proches |

> **IMPORTANT** — Ces deux modèles ne partagent **pas** leur jeu d'entraînement. Une variable d'entraînement doit être disponible au moment où l'on prédit : le modèle moyen terme n'a droit qu'à des prévisions, le modèle dernière minute a droit aux mesures. Entraîner l'un avec les données de l'autre, c'est du décalage train/serve — l'erreur classique, et elle ne se voit qu'en production.

### 7.2 Volume de données et échelle de modèles

**Hypothèse de volume — c'est elle qui dimensionne tout le reste.** Jules surfe environ **20 jours par mois**, soit ~240 sessions par an, et **20 à 50 sessions par an et par spot**. Ce n'est pas un projet en pénurie de données : dès la première saison, un modèle par spot est atteignable sur les spots principaux.

| Échéance | Sessions notées | Outil | Features actives |
|---|---|---|---|
| Semaines 1-4 | < 40 | règles expertes | — |
| Mois 2-4 | 40 → 150 | **régression ridge** sur features construites, tous spots poolés | 6 à 12 |
| Mois 5-12 | 150 → 250 | ridge + **plus proche voisin**, KNN par spot sur les spots principaux | 12 à 20 |
| Année 2+ | > 500 | **gradient boosting** (LightGBM) sur features brutes | toutes |

> **IMPORTANT** — Règle de dimensionnement : **une feature active pour dix sessions notées**, au maximum. À ce rythme, les 20 features du registre §7.4 sont légitimes **dès la fin de la première saison** — il n'y a pas de raison de s'auto-limiter longtemps. Le registre liste ce qu'on **stocke** ; la colonne « v1 » ce qu'on **donne au modèle** au démarrage. On élargit au fil des sessions, pas au fil des idées.

> **IMPORTANT** — **Le gradient boosting de l'année 2 est la cible réelle.** Un arbre apprend seul les interactions direction × spot, marée × spot, houle × période — exactement ce qu'on encode à la main en phase 1 faute de volume. À ce moment-là, les features dérivées (10, 11) deviennent inutiles et les brutes suffisent.

> **IMPORTANT** — **Le risque de ce projet n'est pas la rareté des données, c'est la friction de saisie.** 240 sessions par an, c'est 240 formulaires. À 90 secondes pièce, 6 heures de saisie par an et un abandon au bout de trois mois. À 15 secondes, l'historique existe. **Le chemin de saisie rapide n'est pas un confort, c'est ce qui décide si le modèle aura des données** — d'où le `POST /sessions/quick` et le raccourci iPhone dès le lot 2 (§8).

**Le plus proche voisin sert surtout à expliquer.** Même quand la régression fait le classement, on cherche la session passée la plus proche pour produire la phrase — c'est ce qui rend la reco crédible, et ça dit aussi quelle planche prendre.

**Implémentation** — extension `pgvector` sur le Postgres Railway si disponible (opérateur `<->`, une requête SQL, zéro serveur ML). Sinon un calcul de distance en SQL pur ou en NumPy dans le service est instantané à cette échelle. Ne pas sur-concevoir.

**Sortie attendue :**
> Demain 8 h 30 — **Les Cavaliers, 4,2/5** · houle 1,4 m / 12 s / NO, vent E 8 kt, marée montante
> *Proche de ta session du 12/10/25 notée 5/5 — tu étais en 6'2.*

### 7.3 Cohérence des sources

- **Ne jamais changer de source ou de modèle en cours de route.** Un biais systématique constant s'annule dans l'apprentissage ; un biais qui change casse tout l'historique.
- Stocker **la source et la version du modèle** sur chaque ligne de `forecasts`. Les modèles de vagues sont recalibrés tous les ans ou deux.
- En cas de bascule nécessaire, **ingérer les deux sources en parallèle** plusieurs mois avant de couper.
- Modèle retenu : **MFWAM (Météo-France)** via Open-Meteo plutôt que le modèle global par défaut — meilleure résolution côtière sur le Golfe de Gascogne.

### 7.4 Registre des features

Liste vivante. Tout ce qui est ici est **stocké** dès le lot 1 ; seules les lignes marquées v1 entrent dans le modèle au démarrage.

| # | Feature | Source | Dispo à J−1 ? | Dérivée | v1 |
|---|---|---|---|---|---|
| 1 | Hauteur de houle (Hm0) | forecast + bouée | oui | — | ✅ |
| 2 | Direction de houle | forecast + bouée | oui | — | — |
| 3 | Période (Tp et T02) | forecast + bouée | oui | — | — |
| 4 | Vent constant | forecast + station | oui | — | — |
| 5 | Vent en rafale | forecast + station | oui | — | — |
| 6 | Direction du vent | forecast + station | oui | — | — |
| 7 | Moment de la marée | table des marées | **exact** | — | ✅ |
| 8 | Marnage du jour | table des marées | **exact** | — | ✅ |
| 9 | Énergie de la houle (∝ H²T) | calcul | oui | oui | ✅ |
| 10 | **Écart angulaire houle ↔ orientation du spot** | calcul (2 + spot) | oui | oui | ✅ |
| 11 | **Composante offshore du vent, signée** | calcul (4/6 + spot) | oui | oui | ✅ |
| 12 | **Tendance de houle sur 3 h** (montante / descendante) | fenêtre T−2h | oui | oui | — |
| 13 | **Tendance de vent sur 3 h** | fenêtre T−2h | oui | oui | — |
| 14 | Sens de la marée (montante / descendante) | table des marées | exact | oui | — |
| 15 | Cambrure de la houle (H/L) | calcul (1 + 3) | oui | oui | — |
| 16 | Houle secondaire : hauteur + direction | forecast | oui | — | — |
| 17 | Écart angulaire entre houle primaire et secondaire | calcul | oui | oui | — |
| 18 | Température de l'eau | forecast | oui | — | — |
| 19 | Heure relative au lever / coucher du soleil | calcul | exact | oui | — |
| 20 | Jour de semaine + vacances scolaires | calendrier | exact | oui | — |
| 21 | Jours depuis la dernière session | historique | exact | oui | — |

**Notes de conception :**
- **Les directions brutes (2 et 6) sont les features de référence à terme.** À l'intérieur d'un spot donné, une houle de 290° veut toujours dire la même chose : le modèle apprend de lui-même quelles directions marchent où, à partir des seules notes de Jules, sans qu'on lui décrive jamais le spot. C'est la bonne cible, et c'est plus juste qu'une orientation saisie à la main — une orientation de plage ne sait rien du récif de Parlementia, de la fosse de la Gravière ni de l'ombre d'une digue.
- **Les features 10 et 11 sont un *a priori*, pas une vérité.** Leur seul intérêt est la **mutualisation** : « houle alignée = mieux » est une relation unique, apprise sur les 50 sessions de tous les spots confondus. Les directions brutes, elles, demandent une interaction direction × spot — soit un jeu d'apprentissage par spot, donc ~5 sessions par an et par spot, donc 4 à 6 ans avant de dire quoi que ce soit d'utile.
- **Règle de bascule** : on démarre sur 10 et 11 pour que la reco serve dès le premier mois ; **dès qu'un spot atteint ~25 sessions notées, il passe sur sa direction brute** et l'*a priori* est abandonné pour ce spot. Bascule spot par spot, pas globale. Au rythme de Jules, le spot principal bascule en **quelques mois**, pas en années : l'*a priori* n'est qu'un amorçage d'une saison.
- L'orientation de plage dans `spots` ne sert donc **que** aux règles de cold start et au calcul de 10/11. Une valeur approximative suffit, et elle ne doit jamais contraindre le modèle appris.
- Les features **20 et 21 ne prédisent pas la qualité des vagues** : elles prédisent le monde à l'eau et la forme du jour. Elles nourrissent la **note perso**, pas la note conditions.
- **Ajouts à venir** : Jules complète cette liste au fil de l'eau. Toute nouvelle feature se stocke immédiatement, et n'entre dans le modèle que si le volume de sessions le permet.

---

## 8. Backlog

| Lot | Contenu | Effort |
|---|---|---|
| **0** | Repo, Dockerfile + railway.json copiés, Postgres Railway, Vercel, DNS, auth JWT, shell PWA + barre basse, **déployé en ligne** | 1 j |
| **1** | Spots, ingestion Open-Meteo/MFWAM + CANDHIS (APScheduler), **`daily_log` (swipe quotidien)**, écran « je vais à l'eau ? », webcams | 2,5 j |
| **2** | Log de session surf, matos, double notation, **`conditions_snapshot` en fenêtre T−2h**, file hors-ligne, **`POST /sessions/quick` + raccourci iPhone** | 2,5 j |
| **3** | Reco par règles → ridge, **double horizon** (moyen terme / dernière minute), phrase d'explication par plus proche voisin | 1,5 j |
| **4** | Training : exercices, programmes, mode séance plein écran, streak | 2 j |
| **5** | Nutrition : import Ciqual, journal, cible calorique, menu de la semaine | 2 j |
| **6** | Stats et corrélations conditions ↔ note | 1 j |

≈ **12,5 jours de dev effectif**.

> **IMPORTANT** — **Mise en ligne à la fin du lot 0**, pas à la fin du lot 6. Un projet perso qui n'est pas installable sur le téléphone dans la première soirée ne sort jamais. Et l'ingestion démarre au lot 1 : chaque jour d'ingestion est un jour de données pour le modèle, et le `daily_log` commence à accumuler les labels négatifs bien avant que la reco existe.

---

## 9. Idées en plus

**Ce qui fait ouvrir l'app**
- **Notification push la veille au soir** : « demain 7 h, Cavaliers, 4,5/5 ». La PWA gère les push. Feature n°1.
- **Fenêtre horaire optimale** dans la journée, pas une note journalière.
- **Comparateur multi-spots** : tableau heures × spots en couleurs, lecture en 2 secondes.
- Mail récap du dimanche soir via Resend (déjà configuré).

**Surf**
- Pré-remplissage de session par géoloc : > 30 min à moins de 300 m d'un spot → session proposée à valider.
- La reco sort aussi **quelle planche** (déduite du voisin le plus proche).
- Compteur d'usure du matos : sessions et heures par planche.
- Combi conseillée selon la température de l'eau (déjà dans les données Open-Meteo).
- **Mode trip** : évaluer un spot inconnu par similarité avec ceux qu'on connaît.
- Carte de session partageable générée en image.
- Photos de session sur R2.

**Training / nutrition**
- Objectifs hebdo + streak (3 sessions à l'eau, 5 mobilités).
- Mode séance plein écran avec timer, sans clavier.
- Générateur de menu sous contrainte de macros + **liste de courses agrégée** — un algo glouton sur une banque de recettes taggées suffit, pas besoin d'IA.
- Scan de code-barres (Open Food Facts) pour le journal.

**Data**
- Import Strava / Apple Health / Garmin pour la durée réelle et la fréquence cardiaque.
- **Export CSV et connexion Postgres → Power BI** pour les analyses profondes. L'app garde les graphes simples.

---

## 10. Adaptations proposées sur la demande initiale

1. **« Scraping météo » → API.** Open-Meteo couvre tout, gratuitement, avec l'historique en bonus.
2. **« IA plus proche voisin » → règles d'abord, KNN ensuite.** Sinon l'app est inutile jusqu'à la 30ᵉ session.
3. **Ajouter `discipline`** (surf / foil / longboard) partout. Cf. §5.
4. **« Webcam direct » → embed ou lien.** Ne pas ré-héberger les flux : droits et bande passante.
5. **« Objectif six pack » → « composition corporelle ».** Poids + tour de taille + photo mensuelle. Un objectif mesurable tient, un objectif visuel non.
6. **« Calories suivant entraînement » → cible recalibrée.** Mifflin-St Jeor + facteur d'activité + dépense estimée de la séance, **corrigée toutes les 2-3 semaines sur l'évolution réelle du poids**. L'estimation calorique d'une session de surf est très approximative.
7. **« Connexion » → JWT + cookie httpOnly longue durée.** Un seul utilisateur : on se connecte une fois, jamais plus. Pas de flux d'inscription public au départ.
8. **« Stats » = le vrai produit.** La vue qui dira « tes meilleures sessions : houle 1,2–1,8 m, période 11–14 s, marée montante » justifie à elle seule le projet.

---

## 11. À décider avant de coder

- [ ] **Liste des spots** — 8 à 12 max pour démarrer (Anglet, Biarritz, Bidart, Guéthary, Hendaye, Hossegor, Seignosse, Capbreton ?). Seules les coordonnées sont indispensables : l'orientation et les fenêtres idéales ne servent qu'au cold start, une estimation grossière suffit, le modèle apprendra le reste.
- [ ] **Disciplines suivies** : surf seul, ou surf + foil dès le départ ?
- [ ] **Marées** : API payante ou table statique annuelle importée une fois ?
- [ ] **Nom du projet** et confirmation du sous-domaine `sport.atelier-okomi.fr`
- [ ] **Ouverture aux potes** plus tard, oui ou non ? (si oui, `user_id` partout dès la première migration — c'est prévu, mais ça change les écrans)

---

## 12. Première action

Créer le repo, copier `Dockerfile` / `railway.json` / `run.py` / `ci.yml` depuis `atelier-okomi`, brancher Railway et Vercel, poser les deux DNS, et **installer la coquille PWA sur le téléphone le premier soir**. Le reste suit.
