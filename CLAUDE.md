# Sport — Contexte projet et conventions

> Cadrage fonctionnel, backlog et décisions : `PROJET.md`. Ce fichier = conventions de code et état d'avancement.

## Identité
- Nom : Sport (provisoire)
- Concept : suivi perso surf / training / nutrition, mobile-first, un seul utilisateur
- Site : https://sport.atelier-okomi.fr *(à créer)*
- API : https://api-sport.atelier-okomi.fr *(à créer)*
- Maquettes : canvas « Sport — exploration ergonomique » — https://claude.ai/code/artifact/1098d9c7-5942-4ba4-b84d-1311fa851b6e

## Stack technique
- Back-end : FastAPI (Python 3.12), SQLAlchemy async, PostgreSQL (prod) / SQLite (tests)
- Front-end : Next.js 16 App Router, TypeScript, Tailwind 4, **PWA installable**
- Données : TanStack Query, Zustand, Zod, react-hook-form
- Auth : JWT (`python-jose` + `bcrypt`), cookie httpOnly
- Emails : Resend (domaine atelier-okomi.fr déjà vérifié)
- Stockage images : Cloudflare R2, bucket dédié `sport-media`
- Jobs planifiés : APScheduler dans le process FastAPI
- Erreurs : Sentry
- Tests : pytest + pytest-asyncio

Stack **volontairement identique à `atelier-okomi`**, moins Stripe / SEO / admin, plus PWA et hors-ligne.

## Infrastructure production
- Back : Railway (service dédié, Dockerfile) → api-sport.atelier-okomi.fr
- Front : Vercel (projet dédié) → sport.atelier-okomi.fr
- BDD : PostgreSQL sur Railway — **instance dédiée**, jamais celle d'Okomi
- Domaine : atelier-okomi.fr (OVH) — 2 CNAME à créer : `sport`, `api-sport`
- Repo GitHub : jules-descotes/sport *(à créer)*
- CI : GitHub Actions, `ci.yml` copié d'Okomi (tests pytest + build front)
- CD : **intégrations natives Railway et Vercel** sur push `main` — pas de workflow de déploiement maison

> ⚠️ Ne PAS copier `deploy.yml` d'Okomi : ses jobs de déploiement sont des `echo` factices. Seul `ci.yml` est utile.

## Structure du projet
- `/` → back-end FastAPI
- `/frontend` → front-end Next.js
- `/tests` → tests pytest
- `/alembic` → migrations

## Commandes utiles
- Back seul : `python run.py` (port 8000)
- Front seul : `cd frontend && npm run dev` (port 3000)
- Tests : `pytest tests/ -v`
- API docs local : http://localhost:8000/docs
- Import OSM : `python -m scripts.import_osm_spots [--bbox min_lat,min_lon,max_lat,max_lon] [--dry-run]`

> Contrairement à Okomi, **`frontend/.env.local` pointe vers le back LOCAL** (`http://localhost:8000/api/v1`). Le dev local tape le local.

## Conventions code
- Commits en anglais, préfixe `feat/fix/chore/test/perf`
- Push direct sur `main` (repo solo, pas de PR)
- Slugs en kebab-case
- **Une migration = une transaction `engine.begin()`** — ne jamais les regrouper
- **Routes FastAPI fixes définies AVANT les routes paramétrées** (`/spots/nearby` avant `/spots/{id}`), sinon 422
- Un fichier de modèle par agrégat, importé dans `main.py` pour l'enregistrement des métadonnées
- Dates et heures **en UTC en base**, converties à l'affichage. Les marées et les créneaux de surf sont en heure locale pour l'utilisateur — la conversion est côté front, jamais en base.
- Unités en base : mètres, secondes, degrés, nœuds, kilocalories. Aucune unité composite.

## Règles produit non négociables
1. **Mobile d'abord** — on dessine le 390 px, le desktop suit. Barre de navigation basse à **trois destinations : Jour / Mer / Corps** (plus de Surf / Training / Nutrition / Stats). Cibles ≥ 44 px, police ≥ 14 px.
2. **Zéro saisie clavier pendant l'effort** — boutons, curseurs, molettes. Le clavier ne sert qu'aux notes libres optionnelles.
3. **Hors-ligne réel** — enregistrer une session sans réseau, file IndexedDB synchronisée au retour.
4. **Écran d'accueil « Jour » = la journée dans l'ordre où elle se vit** : bloc de mer enrichi (une seule info en grand), séance proposée, repas, pesée. Rendu plein cadre (V4) pour Jour et Corps, liste dense (V2) pour Mer. Référence : `docs/DESIGN-EXPLORATION.md` et le canvas « Sport — exploration ergonomique ».
5. **Ingestion météo idempotente et historisée** — clé `(spot_id, ts, source, run_ts)`, `ON CONFLICT DO NOTHING`. Une passe n'écrase **jamais** une prévision antérieure ; la « dernière prévision » est le `run_ts` max. Le service Railway redémarre, le job repart.
6. **Deux notes par session** : qualité des conditions, et ressenti perso. Jamais une seule.
7. **`conditions_snapshot` figé** à l'enregistrement de chaque session, sous forme de **fenêtre T−2 h / T−1 h / T0**, en deux volets `forecast` et `observed`. C'est la donnée d'apprentissage, et elle porte les tendances.
8. **`discipline` sur la session et sur le matos** (surf / foil / longboard).
9. **`forecasts` et `observations` sont deux tables distinctes.** Prévision et mesure ne sont pas la même grandeur — ne jamais les mélanger dans un même vecteur de features.
10. **Une feature active pour dix sessions notées, au maximum.** On stocke large (registre §7.4 du PROJET.md), on modélise étroit, on élargit au fil des sessions. Volume de référence : **~20 jours de surf par mois, ~240 sessions par an**, 20 à 50 par spot — les 20 features du registre sont légitimes dès la fin de la première saison.
10 bis. **Le risque du projet est la friction de saisie, pas la rareté des données.** 240 sessions par an : tout écran de saisie qui dépasse 15 secondes tue le jeu de données. Le chemin rapide (`POST /sessions/quick`, raccourci iPhone, pré-remplissage par géoloc) est prioritaire sur la richesse du formulaire.
11. **Toute variable d'entraînement doit être disponible au moment de la prédiction.** Le modèle moyen terme n'a droit qu'aux prévisions ; seul le modèle dernière minute a droit aux mesures de bouée.
12. **`daily_log` alimenté tous les jours**, y compris les jours sans session. Sans labels négatifs, le modèle n'apprend que la moitié haute de la distribution.

## Points de vigilance
- **Un seul hôte, déclaré partout.** `sport.atelier-okomi.fr` sans `www`, cohérent dans `SITE_URL`, `NEXT_PUBLIC_SITE_URL`, le manifest PWA et le cookie de session. Okomi a un désalignement apex/www non résolu — ne pas le reproduire.
- **Open-Meteo est gratuit en usage non commercial.** Si le projet devient commercial un jour, la source change.
- **Ne jamais changer de source ni de modèle de vagues en cours de route.** Modèle retenu : MFWAM via Open-Meteo. `forecasts` porte la source ET la version du modèle — les modèles de vagues sont recalibrés tous les ans ou deux, et un biais qui change casse tout l'historique d'apprentissage.
- **`sport=surfing` d'OSM ne désigne pas des spots, mais des commerces.** Vérifié sur le terrain le 12/09 : sur la côte basco-landaise, les **68 objets** `sport=surfing` sont *tous* des magasins, des écoles ou des clubs — pas un seul spot. Idem à Santa Cruz (13/13) et sur la Gold Coast (12/13). Les vrais spots sont dans les **`natural=beach` nommées** (Plage de la Gravière, Les Culs Nus, Parlementia, Pavillon Royal…) et dans `natural=reef`. L'import ratisse donc les trois, écarte tout objet portant `shop`, `club`, `amenity`, `office`, `tourism`, `craft`, `building` ou `leisure`, et **rejette tout candidat à plus de 5 km du trait de côte** (plages de lac, vagues de rivière).
- **Ne pas ré-héberger les flux de webcams** : iframe ou lien sortant uniquement.
- **Aucune donnée CAFPI ici.** Projet strictement perso, sur le temps perso.
- Le back Railway peut redémarrer à froid : prévoir un `/health` (comme Okomi) et un état de chargement propre côté front.

## Design tokens (v1, issus du canvas de design — ajustables)
Direction : instrument de bord marin, Atlantique en hiver. Mobile en mode clair, desktop en mode sombre. Un seul accent chaud, réservé à l'action principale et aux scores 4-5.

```
# Typo
font-display : "Barlow Condensed" (500/600/700) — gros chiffres, titres, tabular-nums
font-body    : "IBM Plex Sans" (400/500/600)
# Clair (mobile)
bg #EEF2F4 · card #FFFFFF · soft #F6F8F9 · line #D8E0E5 · sand #E8E1D6
ink #10202B · ink-2 #46596A · mute #62737F · accent #D97A2B (texte sur accent #FFFFFF)
# Sombre (desktop)
bg #0D171E · card #13222B · card-2 #182A34 · line #22343F
ink #E7EDF0 · ink-2 #A7B6BF · mute #7F92A0 · accent #E48A3A (texte sur accent #10202B)
# Échelle de score 1→5 (fil rouge, identique partout)
clair  : #CDD5DA #A9BFCB #6C9AB2 #E6A05A #D97A2B   (texte ink sur tous les paliers)
sombre : #2B3A45 #3E5A6C #5C8FAB #C98A48 #E48A3A   (texte ink clair sur 1-3, ink sombre sur 4-5)
# Séquentiel (heatmaps d'analyse, magnitude)
#E3ECF1 #B9CFDC #86AEC4 #5A8FAB #3A7191 #245572
# Rayons : chip 8 · cellule 10 · bouton 14 · carte 16 · pilule 999
# Espacements : 4 8 12 16 20 24 32 48
# Règles : cibles ≥ 44 px · corps ≥ 14 px, libellés ≥ 12 px · pas d'ombre portée (bordure `line`) · icônes en trait 1,75 px, jamais d'emoji
```

**Canvas de design** — « Sport — exploration ergonomique » : https://claude.ai/code/artifact/1098d9c7-5942-4ba4-b84d-1311fa851b6e
Privé. Une session Claude disposant de l'outil Artifact peut le relire par cette URL ; il contient
cinq traitements UI de la même architecture (Cartes, Liste dense, La marée, Plein cadre, Le cadran),
trois écrans chacun. Retenus : **plein cadre (V4)** pour Jour et Corps, **liste dense (V2)** pour Mer.

Écrans de référence (maquettes) : **Jour** — bloc de mer enrichi (note et heure du meilleur créneau,
houle, période, direction, vent et rafales, marée et coefficient, eau, les huit créneaux, aperçu de
demain), séance proposée, repas, pesée · **Corps** — trois objectifs mesurés et cinq formules ·
**Mer** — matrice 5 jours × 8 créneaux · sortie de l'eau · séance en cours (plein écran, timer géant) ;
desktop : semaine et analyse.

## Variables d'environnement — Railway (back)
```
APP_NAME=Sport
DEBUG=False
DATABASE_URL=postgresql+asyncpg://...
SECRET_KEY=...
SITE_URL=https://sport.atelier-okomi.fr
STORAGE_BACKEND=r2
R2_ACCOUNT_ID= / R2_ACCESS_KEY_ID= / R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=sport-media
R2_PUBLIC_URL=
RESEND_API_KEY=
EMAILS_FROM=bonjour@atelier-okomi.fr
SENTRY_DSN=
WINDY_WEBCAMS_API_KEY=          # clé Webcams API (≠ Point Forecast)
TIDES_API_KEY=
FORECAST_INGEST_INTERVAL_HOURS=3
```

### À ajouter sur Railway au lot 1
Toutes ces variables ont une valeur par défaut dans `config.py` : l'application
démarre sans elles. Les deux premières méritent d'être **posées explicitement**,
parce qu'elles décident de la cohérence de l'historique d'apprentissage ; les
autres ne servent qu'à corriger un incident sans redéployer.

```
FORECAST_WAVE_MODEL=meteofrance_wave   # à poser explicitement — ne JAMAIS changer
FORECAST_MODEL_VERSION=mfwam-2025      # à poser explicitement — bump à la main
                                       # le jour où Météo-France recalibre MFWAM
FORECAST_CACHE_HOURS=3                 # cache des spots « potentiels »
FORECAST_CALL_CAP=600                  # plafond dur par passe d'ingestion
FORECAST_ON_DEMAND_TIMEOUT_S=5         # au-delà : on sert la base, on complète derrière
OVERPASS_URL=https://overpass-api.de/api/interpreter
OPENMETEO_MARINE_URL=https://marine-api.open-meteo.com/v1/marine
OPENMETEO_FORECAST_URL=https://api.open-meteo.com/v1/forecast
OPENMETEO_ARCHIVE_URL=https://historical-forecast-api.open-meteo.com/v1/forecast
```

Aucune clé d'API n'est nécessaire : Open-Meteo et Overpass sont gratuits et sans
authentification en usage non commercial. `WINDY_WEBCAMS_API_KEY` reste vide —
les webcams sont saisies à la main par URL sur la fiche spot au lot 1.

## Variables d'environnement — Vercel (front)
```
NEXT_PUBLIC_API_URL=https://api-sport.atelier-okomi.fr/api/v1
NEXT_PUBLIC_SITE_URL=https://sport.atelier-okomi.fr
NEXT_PUBLIC_APP_NAME=Sport
```

## État d'avancement
- [x] Lot 0 — repo, infra, auth, coquille PWA — **code terminé le 2026-09-12**, mise en ligne à faire
- [x] Lot 1 — spots, ingestion météo, écran d'accueil, webcams — **code terminé le 2026-09-12**, import OSM à lancer en production
- [ ] Lot 2 — log de session, matos, notation, hors-ligne
- [ ] Lot 3 — reco (règles puis plus proche voisin)
- [ ] Lot 4 — training
- [ ] Lot 5 — nutrition
- [ ] Lot 6 — stats

### Lot 0 — ce qui est livré (2026-09-12)
- Dépôt git sur `main`, remote `jules-descotes/sport`, `.gitignore` + `.gitattributes` (LF)
- Back : `/health`, `/api/v1/auth/login`, `/logout`, `/me`, `/me/profile`. Utilisateur
  unique créé au démarrage depuis `ADMIN_EMAIL` / `ADMIN_PASSWORD`, pas d'inscription publique
- JWT en cookie httpOnly (`SameSite=Lax`, `Secure` hors debug), en-tête Bearer accepté en
  secours pour `/docs` et le raccourci iPhone du lot 2
- `config.py` convertit `postgresql://` (format Railway) en `postgresql+asyncpg://`
- Modèles `users` et `profiles`, Alembic initialisé, migration `0001` appliquée
- APScheduler câblé, job `forecast_ingest` toutes les `FORECAST_INGEST_INTERVAL_HOURS` heures
  (coquille vide, contenu au lot 1)
- Front Next.js 16 : `/login`, coquille `(app)` avec barre basse 4 onglets, jetons de design
  en thème Tailwind (clair en mobile, sombre au-dessus de 1024 px)
- PWA : manifest, icônes 192/512/maskable, apple-touch-icon, service worker minimal
  (coquille en cache + repli `offline.html`, jamais l'API)
- 10 tests pytest verts, `npm run lint` et `npm run build` propres, CI GitHub Actions

### Lot 0 — ce qui reste (hors code, à faire à la main)
- [x] Créer le dépôt GitHub `jules-descotes/sport` et pousser
- [ ] Railway : service back (Dockerfile) + Postgres dédié, variables d'environnement
- [ ] Vercel : projet front sur `/frontend`, variables `NEXT_PUBLIC_*`
- [ ] OVH : CNAME `sport` et `api-sport` sur `atelier-okomi.fr`
- [ ] Installer la PWA sur le téléphone et vérifier le plein écran iOS

### Lot 1 — ce qui est livré (2026-09-12)
**Catalogue**
- `scripts/import_osm_spots.py` — Overpass mondial, rejouable tous les mois,
  idempotent sur la clé `(osm_type, osm_id)`, **ne touche jamais aux spots
  `source='user'`**. Options `--bbox`, `--skip-coastline`, `--dry-run`
- Orientation de côte **calculée** : cap du segment `natural=coastline` le plus
  proche, lissé sur 500 m ; la convention OSM « terre à gauche, mer à droite »
  donne `onshore_dir_deg` = cap + 90°. Jamais calculée à la volée dans l'API
- `spots.tier` (`home` / `potential` / `catalog`) recalculé à chaque connexion,
  changement de favoris et changement de position (> 5 km). Favoris plafonnés à 20
- `spot_preferences` : rayon, favoris, masqués, domicile, dernière position
- `POST /spots`, `GET /spots/nearby`, `GET|PATCH /spots/{ref}`,
  `POST /spots/{ref}/favorite`, `/hide`, `GET|PUT /spots/preferences`,
  `POST /spots/position`. Routes fixes déclarées avant les paramétrées

**Ingestion**
- `forecast_ingest` planifié : **spots `home` uniquement**
- À la demande sur `/recommend` et `/spots/{ref}/forecast` si le cache dépasse
  3 h ; au-delà de 5 s, la réponse part de la base et le reste se complète dans
  une tâche détachée (`refreshing` dans la réponse)
- `ON CONFLICT (spot_id, ts, source) DO UPDATE`, plafond dur 600 appels par
  passe, backoff exponentiel sur 429 en respectant `Retry-After`
- Trois appels par spot : houle MFWAM, puis niveau de la mer et température
  d'eau (hors modèle de vagues), puis vent en nœuds
- **Backfill** à la création d'une session, y compris rétroactive et sur un spot
  jamais ingéré : archive Open-Meteo sur T−2 h → T0 → volet `observed`. Un échec
  d'archive n'empêche jamais l'enregistrement
- `observations` créée **vide** (CANDHIS au lot 1 bis), `daily_log` + endpoints

**Score et reco**
- `services/scoring.py` — règles génériques, sans aucune fenêtre par spot.
  Taille et vent sont des **facteurs**, pas des termes : un jour à plat ou un
  coup de vent onshore écrase la note au lieu de se faire compenser
- `GET /recommend` sert l'accueil **et** le comparateur en un appel : verdict
  OUI / NON / PEUT-ÊTRE sur la prochaine fenêtre de jour, meilleur créneau,
  grille heures × spots sur 5 jours, phrase en français
- Lever et coucher du soleil calculés localement (`services/sun.py`) : pas
  d'appel supplémentaire, et les créneaux de nuit sont écartés

**Front**
- Accueil « verdict en très grand », swipe `daily_log`, comparateur heures ×
  spots, fiche spot (webcam, courbe de houle et niveau de la mer en SVG à la
  main, favori / masquer), carte avec ajout par appui long, profil (domicile +
  rayon). Géoloc avec repli sur le domicile
- `TileMap` écrit à la main plutôt qu'une librairie de cartographie, attribution
  ODbL affichée en permanence
- **170 tests pytest verts**, `npm run lint` et `npm run build` propres

**Vérifié en conditions réelles le 12/09** : Open-Meteo (prévision et archive),
Overpass (70 spots importés sur la côte basco-landaise, orientations correctes —
Parlementia NO, Ciboure N dans sa baie), rejeu de l'import idempotent,
`/recommend` et session rétroactive de bout en bout.

### Lot 1 — ce qui reste (hors code)
- [ ] Lancer `python -m scripts.import_osm_spots` en production (monde entier,
      compter plusieurs heures — Overpass est bénévole et renvoie des 429)
- [ ] Valider `sea_level_height_msl` contre l'annuaire SHOM sur quelques marées
- [ ] Saisir les URL de webcams des spots maison (`PATCH /spots/{ref}`)
- [ ] Relancer l'import tous les mois (à la main, ou cron Railway plus tard)

### Décidé le 12/09 pour le lot 1 (cf. PROJET.md §11)
- Spots : **catalogue mondial OpenStreetMap** (`sport=surfing`, Overpass), affichage filtré par **géolocalisation en direct + rayon du profil**, ajout manuel depuis la carte. Jamais de scraping de sites de prévi.
- **Ingestion à trois niveaux, jamais « tous les spots tout le temps »** : spots maison (favoris, ≤ 20) en planifié toutes les 3 h ; spots potentiels (rayon + position courante) **à la demande à l'ouverture de l'app**, cache 3 h ; le reste du catalogue jamais. Plafond dur 600 appels par passe, backoff sur 429.
- **Backfill à l'enregistrement d'une session** : archive Open-Meteo sur T−2 h → T0 pour remplir `observed`, quel que soit le spot. Le modèle de goût s'entraîne sur `observed`.
- Orientation de la côte **calculée** depuis le trait de côte OSM, pas saisie.
- Discipline : **surf seul à l'écran** en V1, colonne conservée.
- Marées : **Open-Meteo `sea_level_height_msl`**, à valider contre l'annuaire SHOM.
- CANDHIS : jeton pas encore reçu → lot 1 bis.

### Décidé le 12/09 (soir) après l'exploration design
- **Trois destinations Jour / Mer / Corps**, hybride plein cadre + liste dense. Objectifs mesurés (`objectives`, `objective_measurements`) et formules pour le training.
- **Une seule prévision par défaut : celle du spot favori du profil**, affichée sur Jour. **Mer** est un explorateur : la même grille pour n'importe quel autre spot du catalogue, par recherche, favoris ou position, ingérée à la demande. La section « Sort du produit » de `docs/DESIGN-EXPLORATION.md` n'est appliquée **qu'à l'écran** : catalogue OSM, tiers d'ingestion et `spots/nearby` restent en place et alimentent Mer ; la carte et le comparateur multi-spots disparaissent de la navigation.
- **`run_ts`** dans la clé de `forecasts`, en premier dans le lot 1 ter.
- Ordre des lots : **1 ter → 2 → 4 → 5 → 3 → 6**.
- `OVERPASS_URL` : poser en variable Railway l'instance qui a fonctionné (overpass-api.de bannit l'IP de sortie Railway). `railway.json` est déprécié au profit de `.railway/railway.ts` — migration avant le 2026-12-01.
