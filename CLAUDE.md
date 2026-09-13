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
- Tests back : `pytest tests/ -v`
- Tests front (file hors ligne) : `cd frontend && npm run test`
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
1. **Mobile d'abord** — on dessine le 390 px, le desktop suit. Barre de navigation basse à **cinq entrées : Jour / Surf / Training / Nutrition / Profil** (décision du 13/09 ; remplace Jour / Mer / Corps). Les stats vivent dans chaque onglet et sur desktop, pas dans le menu. Cibles ≥ 44 px, police ≥ 14 px.
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
API_TOKEN_EXPIRE_DAYS=365       # jeton Bearer du raccourci iPhone (lot 2)
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
OPENFOODFACTS_URL=https://world.openfoodfacts.org
OPENFOODFACTS_USER_AGENT=Sport/0.1 (perso, non commercial)
OPENMETEO_MARINE_URL=https://marine-api.open-meteo.com/v1/marine
OPENMETEO_FORECAST_URL=https://api.open-meteo.com/v1/forecast
OPENMETEO_ARCHIVE_URL=https://historical-forecast-api.open-meteo.com/v1/forecast
```

Aucune clé d'API n'est nécessaire : Open-Meteo, Overpass et Open Food Facts sont
gratuits et sans authentification en usage non commercial. Le `User-Agent`
d'Open Food Facts est en revanche **exigé** par leurs conditions : une base
bénévole a le droit de savoir qui l'interroge. `WINDY_WEBCAMS_API_KEY` reste vide —
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
- [x] Lot 1 ter — `run_ts`, spot favori, navigation Jour / Mer / Corps — **code terminé le 2026-09-12**
- [x] Lot 2 — log de session, matos, notation, hors-ligne — **code terminé le 2026-09-12**, raccourci iPhone à monter sur le téléphone
- [x] Lot 2 ter — navigation à cinq entrées, HTTPS, tableau horaire, sessions au navigateur — **code terminé et en ligne le 2026-09-13**
- [x] Lot 4 — training : objectifs mesurés, formules, mode séance — **code terminé et en ligne le 2026-09-13**, import d'exercices à lancer en production
- [x] Étape A — desktop 1600 px, cache client des prévisions — **en ligne le 2026-09-13**
- [x] Étape B — coefficient de marée (Brest), énergie dans les sessions — **en ligne le 2026-09-13**
- [x] Étape C — favoris multiples, `spot_rules`, annonces sur Jour — **en ligne le 2026-09-13**
- [x] Étape D — demi-points, segments horaires — **en ligne le 2026-09-13**
- [x] Lot 5 — nutrition : Ciqual, cible recalibrée, journal, menu, pesée — **en ligne le 2026-09-13**, import Ciqual à lancer en production
- [x] Étape F — habitudes quotidiennes, stats de profil — **en ligne le 2026-09-13**
- [ ] Lot 3 — reco (règles puis plus proche voisin)
- [ ] Lot 6 — stats et corrélations conditions ↔ note

### Étapes A → G (13/09) — ce qui est livré

**A. Desktop et cache.** Coquille à 1 600 px, colonnes au-dessus de 1 024 px
sur Jour (mer · ce qu'on fait · ce qu'on note), Training (jauges · formules ·
séance du jour) et Surf (tableau pleine largeur, détail en panneau latéral
collant). La colonne d'heure du tableau horaire passe de 46 à **30 px** sur
desktop : les 46 px sont la cible tactile, au-dessus de 1 024 px le pointeur
est une souris — et ce sont ces 30 px qui font tenir **deux jours entiers**
dans 1 440 px.

Cache client IndexedDB, clé `(spot, run_ts)` comme en base. L'entrée est
injectée dans le cache de TanStack Query avec son `updatedAt` d'origine et
`staleTime` vaut deux heures : c'est la bibliothèque qui tranche, pas un second
état parallèle. Âge affiché en clair, « tirer pour rafraîchir » pour forcer.

**B. Coefficient de marée.** Spot technique `is_reference` sur le marégraphe de
**Brest** — le coefficient est national par définition. Un appel de niveau
marin par passe, pas trois. Deux détails portent toute la précision : le niveau
moyen est **mesuré** (−0,39 m ; le poser à zéro ajouterait 13 points en
permanence) et le sommet de marée est **interpolé** par une parabole (l'échantillon
horaire coûte 3 points, systématiquement en moins).

Validé contre l'annuaire SHOM sur dix pleines mers : biais −1,7, écart maximal
**6 points**, donc affichage avec « ≈ ». Tout est consigné dans
`docs/COEFFICIENT-MAREE.md`, rejouable par `scripts/check_tide_coefficient.py`.

Énergie de houle dans la fenêtre observée du détail de session et en colonne
dans l'historique, calculée **côté serveur** avec la fonction de l'écran Surf.

**C. Favoris multiples et critères.** `spot_rules` par spot : houle min/max,
période min, secteurs de houle et de vent (rose à huit points), vent max,
phases de marée, heures préférées. **Tout champ vide est une absence de
contrainte**, jamais une valeur par défaut.

Deux critères sont *durs* — houle et vent au-dessus du maximum. Un créneau qui
correspond ne peut pas être noté sous 3 ; un créneau qui rate un critère dur ne
peut pas dépasser 2. Ses secteurs **remplacent** l'orientation calculée depuis
le trait de côte, entièrement.

Jour annonce les fenêtres à venir des autres favoris (« Parlementia devrait
marcher — dim. 10 h à 13 h »), trois au maximum. Un spot sans critères n'est
jamais annoncé.

**D. Demi-points et segments.** Échelle de 1 à 5 par pas de 0,5, stockée en
entiers ×2 dans des colonnes **renommées** `_half` — une colonne qui change
d'unité sans changer de nom est une bombe à retardement. Aucun bouton de plus à
l'écran : second tap ou appui long. La couleur interpole en oklab.

Segments horaires optionnels, chacun apparié à **sa** ligne du
`conditions_snapshot` — d'où l'extension de la fenêtre à toute la durée de la
session. La marée du snapshot reste rapportée à l'heure du départ.

**E (lot 5). Nutrition.** Import Ciqual (`--sample` d'abord, colonnes trouvées
par fragments, `traces` = 0 et `-` = inconnu), Open Food Facts au code-barres
avec cache. Cible Mifflin-St Jeor + activité + dépense du jour par MET +
objectif + **terme appris** corrigé par la balance toutes les deux à trois
semaines. Journal figeant ses valeurs à la saisie, menu de la semaine par
glouton reproductible, liste de courses agrégée, pesée à la molette.

**F. Habitudes et stats.** Compteurs libres définis par Jules, un tap pour
ajouter, un appui long pour retirer. Événements **horodatés à la seconde** —
c'est ce qui permettra au lot 6 de les croiser avec le ressenti du lendemain.
Ton strictement neutre : jamais de rouge, jamais de série perdue. Quatre cartes
de statistiques sur le profil, avec de vraies courbes sur desktop.

**G. Tests.** 518 pytest + 65 vitest. Ajoutés au passage : le *stale-while-
revalidate* du cache client testé avec un vrai DOM (stale / revalidate /
force), et la migration 0010 jouée **sur de vraies lignes** dans un
sous-processus Alembic — un 4 doit devenir 8, et une session non notée doit le
rester.

### Étapes A → G — ce qui reste (hors code, à faire à la main)

Dans l'ordre où ça débloque le plus de choses.

- [ ] **Importer la table Ciqual.** Télécharger le CSV de l'ANSES sur
      data.gouv.fr (« Table de composition nutritionnelle Ciqual »), le poser
      en `data/ciqual.csv`, puis depuis le conteneur Railway :
      `python -m scripts.import_ciqual --sample` — **regarder les colonnes** —
      puis `python -m scripts.import_ciqual`. Sans lui, la recherche d'aliment
      est vide et les recettes n'ont pas de macros. Elles se complètent toutes
      seules au premier accès à l'écran Nutrition après l'import.
- [ ] **Compléter le profil nutrition** : année de naissance, taille, sexe,
      objectif (Profil → Nutrition). Sans eux, la cible calorique est une
      estimation — elle le dit, mais elle reste une estimation.
- [ ] **Se peser une première fois** (Nutrition → Me peser). La calibration
      demande **deux** pesées à quatorze jours d'écart : la première ne
      corrige rien, elle amorce.
- [ ] **Poser les critères des spots favoris** (fiche spot → Tes critères).
      Sans eux, aucune annonce ne s'affiche sur Jour — c'est voulu : un spot
      sans critères n'a rien à annoncer.
- [ ] **Définir les premières habitudes** (Profil → Habitudes). Rien n'est
      semé, et c'est délibéré : une habitude proposée par l'app serait une
      leçon de morale.
- [ ] **Vérifier le coefficient de marée à l'usage**, et rejouer
      `python -m scripts.check_tide_coefficient --days 5 --shom …` à
      l'équinoxe. Le « ≈ » disparaîtra le jour où l'écart mesuré passera sous
      cinq points (`MEASURED_MAX_GAP` dans `services/tide_coefficient.py`).
- [ ] **Vérifier le tableau horaire à 1 440 px** : deux jours doivent tenir
      d'un coup, colonne des libellés figée.
- [ ] **Tester le scan de code-barres** sur le téléphone. `BarcodeDetector`
      n'existe pas sur Safari : sur iPhone, c'est la saisie du code à la main —
      c'est prévu, mais ça se vérifie.

Restent des lots précédents : import OSM de la côte française à rejouer
(`OVERPASS_URL` sur une autre instance), import d'exercices, raccourci iOS,
matos réel, URL de webcams, `STORAGE_BACKEND=r2` pour les photos.

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
- [x] Railway : service `sport` (Dockerfile, `PORT=8080`) + Postgres dédié, variables posées dont `FORECAST_WAVE_MODEL` / `FORECAST_MODEL_VERSION`, domaine custom `api-sport` déclaré (cible `voy0nwe9.up.railway.app`) — **en attente du DNS**. `railway ssh --service sport --environment production` fonctionne (le `--environment` est indispensable)
- [x] Vercel : projet front sur `/frontend`, variables `NEXT_PUBLIC_*`, domaine `sport` déclaré — **en attente du DNS**
- [x] OVH : 2 CNAME (`sport` → cible Vercel, `api-sport` → cible Railway) — **faits**. Les deux hôtes répondent en HTTPS et servent l'app ; vérifié le 13/09
- [ ] Installer la PWA sur le téléphone et vérifier le plein écran iOS
- [~] Import OSM en production : **4 568 spots créés** (Portugal → Bretagne) le 12/09 depuis le conteneur Railway ; la **côte française est à rejouer** (`--bbox 43.3,-5.0,49.0,-1.0`) car overpass-api.de a banni l'IP de sortie Railway en cours de route — orientations manquantes et plages de lac à purger. Utiliser une autre instance via `OVERPASS_URL` (private.coffee ou maps.mail.ru)
- [ ] Choisir le **spot favori** dans le profil à la première connexion — sans lui, le job planifié n'ingère rien

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

### Lot 1 ter — ce qui est livré (2026-09-12)
**`run_ts` — fait en premier, avant tout le reste**
- `forecasts.run_ts` (heure d'émission, UTC, **arrondie à l'heure**) entre dans
  la clé unique `(spot_id, ts, source, run_ts)`, et le conflit devient
  `ON CONFLICT DO NOTHING`. Une passe **ajoute** une prévision plus récente,
  elle n'en écrase plus aucune
- L'arrondi à l'heure préserve l'idempotence : le conteneur Railway redémarre,
  la passe repart dans la même heure et retombe sur le même run au lieu de
  dupliquer 120 lignes par spot. `fetched_at` reste exact et ne sert plus qu'au
  cache de trois heures
- Un seul `run_ts` par passe : les vingt spots maison d'un même cycle
  appartiennent au même run, même si la passe dure dix minutes
- `services/forecast_reads.py` — **seul endroit** où est écrite la règle
  « dernière prévision = `run_ts` max par `(spot_id, ts, source)` ». Y passent
  la reco, `/spots/{ref}/forecast` et le `conditions_snapshot`
- `forecast_delta(spot, ts)` — écart entre le dernier run et celui de la veille
  au soir (20 h **locale**, convertie en UTC), directions repliées par le court
  chemin (350° → 10° = +20°)
- Le volet `forecast` d'une session ne lit que les runs **émis avant** le début
  de la session : une passe postérieure est un constat déguisé, et la retenir
  serait du décalage train/serve (§7.1)
- Migration `0003` : `run_ts = fetched_at` sur l'existant — c'est exactement ce
  que `fetched_at` portait jusque-là. Aller-retour vérifié sur SQLite avec des
  données

**Spot favori**
- `profiles.home_spot_id` (migration `0004`). Le tier `home` part de lui, plus
  les favoris secondaires, plafond de 20 inchangé. Un favori à 300 km reste
  `home` : c'est celui qu'on regarde tous les matins
- **Plus aucun chemin n'ingère un spot qu'on n'a pas regardé.** `/recommend`
  rafraîchissait jusqu'à douze spots du rayon à chaque ouverture ; il ne
  rafraîchit plus que le favori, et zéro appel tant qu'aucun favori n'est
  choisi. Seul `/spots/{ref}/forecast` ingère encore — le spot qu'on ouvre
- `GET /spots/search` (nom, préfixes en tête) et `GET /spots/favorites`
  n'ingèrent rien
- Les créneaux portent `daylight`, la position dans la marée, le marnage, la
  composante offshore signée et les raisons de la note. `step_hours=3` sert la
  grille en 40 points au lieu de 120, notes toujours calculées sur **toutes**
  les heures — la marée se lit sur les extrêmes du jour

**Écrans**
- Barre basse **Jour / Mer / Corps**. Carte et comparateur multi-spots sortent
  de la navigation ; `Comparator.tsx` reste dans l'arbre, non routé
- **Jour** (plein cadre) : bloc de mer du favori — note et fenêtre du meilleur
  créneau en grand, houle, vent et rafales avec mention terre / mer, marée
  (sens, PM, marnage), eau, bande des huit créneaux, deux lignes « demain ».
  Puis le swipe `daily_log` et deux emplacements « séance » et « repas »
- **Mer** (liste dense) : sélecteur (recherche, favoris, autour de moi), grille
  5 j × 8 créneaux entière sur un écran, tap = détail du créneau, bouton
  « définir comme favori ». Ouvrir un spot déclenche son ingestion
- **Corps** : trois jauges vides et « à définir », contenu au lot 4
- **Profil** : choix du spot favori par recherche, domicile, rayon
- **218 tests pytest verts**, `npm run lint` et `npm run build` propres

> Le **coefficient de marée** n'est pas affiché : il se calcule par rapport au
> marnage de vive-eau moyen d'un port de référence, que ni Open-Meteo ni nous
> n'avons. Le marnage du jour est affiché à la place — c'est la grandeur qu'on
> a vraiment (feature 8 du registre). Ne pas l'inventer à partir du niveau.

### Lot 1 ter — ce qui reste (hors code)
- [ ] Appliquer les migrations `0003` et `0004` en production (automatique au
      déploiement : `run.py` fait `alembic upgrade head` avant uvicorn)
- [ ] Poser `FORECAST_WAVE_MODEL` et `FORECAST_MODEL_VERSION` sur Railway avant
      la première passe d'ingestion historisée
- [ ] Choisir le spot favori depuis le profil dès la première connexion en
      production — sans lui, le job planifié n'interroge rien

### Lot 2 — ce qui est livré (2026-09-12)

**Le chemin des quinze secondes**
- `POST /sessions/quick` — entrée minimale (`lat`, `lon`, `ended_at` optionnel).
  Le serveur identifie le **spot le plus proche à moins de 2 km**, retombe sur
  le **favori du profil** hors zone, estime le début à **fin − 90 min**, crée la
  session en statut `to_rate`, fige le `conditions_snapshot` et renvoie un lien
  profond `/sessions/{id}/noter`
- **Idempotent sur 10 minutes** : deux déclenchements rapprochés du raccourci
  donnent une seule session (`created: false`). Un `client_uuid` facultatif
  donne en plus une idempotence exacte, indépendante de l'horloge
- `start_estimated` distingue une heure devinée d'une heure relevée. Corriger le
  début d'au moins une heure, ou changer de spot, **refait le snapshot** — le
  garder étiquetterait la session avec les conditions d'un autre endroit
- Le volet `forecast` ne retient que les runs **émis avant le début**. Le volet
  `observed` manquant (parking sans réseau) est **rattrapé à la notation**

**Jeton Bearer révocable**
- `POST|GET /auth/tokens`, `DELETE /auth/tokens/{id}`. JWT `type: "api"` portant
  un `jti` cherché dans `api_tokens` à chaque appel : **un JWT ne se révoque
  pas**, et couper le raccourci d'un téléphone perdu ne doit pas obliger à
  changer `SECRET_KEY` — ce qui déconnecterait aussi le navigateur
- La valeur n'est jamais stockée ni réaffichée. `last_used_at` dit quel jeton ne
  sert plus

**Matos**
- `gear` (type, nom court, **longueur en mètres**, volume, discipline, date
  d'achat, actif) + CRUD. Un 6'2 est une unité composite : la base porte 1,88 m,
  le front affiche `6'2`
- Compteur de sessions et `last_used_at` **calculés**, jamais stockés.
  Supprimer du matos qui a servi est refusé (409) : le lien session ↔ planche
  est de la donnée d'apprentissage. On range, on ne supprime pas

**Écran « Noter la session »** (`/sessions/{id}/noter`, plein cadre)
- Spot en tête, modifiable en un tap (les 5 plus proches) · début / fin en
  molettes de 15 min avec durée affichée · **QUALITÉ DES CONDITIONS** puis
  **MON RESSENTI**, cinq grands boutons chacun, séparés par un filet et un fond
  · planche en pastilles, la dernière utilisée présélectionnée · compteur de
  vagues, pas de 1 au tap et de 5 en appui long · note libre et photo repliées
- **Aucune zone de texte visible sans action explicite.** Un seul bouton
  « Enregistrer », inerte tant que les deux notes ne sont pas posées

**Hors ligne**
- `lib/offline-queue.ts` — file IndexedDB, une entrée par session (re-noter
  remplace), envoi au retour du réseau (`online` + `visibilitychange`),
  indicateur « en attente d'envoi ». Une erreur réseau se retente, un refus de
  l'API se jette — sinon la file rejoue l'échec indéfiniment
- La file vit dans la page, **pas dans le service worker** : ce qu'on met en
  attente est une notation avec sa règle propre, pas une requête à rejouer

**Écrans**
- **Jour** : une session `to_rate` passe **au-dessus du bloc de mer**, plein
  cadre sur accent. Une fois notée, le bloc de mer reprend sa place et la
  session du jour se range en pied avec ses deux notes
- **`/sessions`** : historique en liste dense · **`/sessions/{id}`** : détail
  avec la fenêtre `observed` et le `forecast` d'avant, en deux matrices de trois
  colonnes
- **Profil** : matos, sessions, raccourci iPhone. Le profil est enfin atteignable
  — une icône en haut de Jour, il n'était routé nulle part depuis le lot 1 ter

**Photos** — `POST /sessions/{id}/photo`, R2 en production. Ré-encodage en JPEG
1 600 px : l'EXIF part avec, **GPS compris**.

**Correction au passage** — `UtcDatetime` (`app/schemas/types.py`) recolle UTC
aux datetimes rendus par SQLite. Sans décalage explicite, `new Date(...)` lit
l'heure comme locale : une session de 10 h 30 s'affichait à 8 h 30 en
développement. Invisible en production (asyncpg rend des datetimes conscients),
permanent en local.

**257 tests pytest + 15 tests vitest verts**, `npm run lint` et `npm run build`
propres.

**Vérifié en conditions réelles le 12/09** : chaîne complète jeton → quick POST
en Bearer sans cookie → archive Open-Meteo → notation → historique. La Gravière
reconnue à 206 m, fenêtre T−2 h/T−1 h/T0 remplie (0,62 m / 7,8 s / 310°, vent
8,8 → 17,1 kt, marnage 4,11 m), idempotence confirmée, révocation du jeton
effective sans toucher au cookie, session rétroactive sur Uluwatu — jamais
ingéré, trois mois en arrière — backfillée à 2,08 m / 11,8 s / 191°.

### Lot 2 — ce qui reste (hors code, à faire à la main)
- [ ] Monter le raccourci iOS sur le téléphone : `docs/RACCOURCI-IOS.md`
- [ ] Créer le jeton depuis Profil → Raccourci iPhone, et le coller dans
      l'en-tête `Authorization` du raccourci
- [ ] Saisir le matos réel (planches, combinaisons) depuis Profil → Matos
- [ ] Appliquer la migration `0005` en production (automatique au déploiement)
- [ ] Poser `STORAGE_BACKEND=r2` et les clés R2 sur Railway si on veut les
      photos — sans elles, l'envoi répond 502 et la notation marche quand même

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

### Décidé le 13/09 après première utilisation en ligne
- **Navigation à cinq entrées** : Jour / Surf / Training / Nutrition / Profil. « Mer » → « Surf » ; « Corps » → Training + Nutrition ; Profil visible.
- **Écran Surf = Windguru en plus moderne** : pour le spot choisi, tableau **heure par heure** sur 5 jours — houle (hauteur, période, **énergie ∝ H²·T**, direction en **flèche**), vent (moyen, rafales, direction en flèche, terre/mer), marée, température de l'eau, score — les flèches deviennent des degrés uniquement dans le détail d'un créneau. Sur Jour, résumé **toutes les 3 h**.
- **Sessions** : création manuelle et modification des anciennes **depuis le navigateur**, pas seulement le raccourci.
- **Programmes d'entraînement** : exercices importés depuis des bases **ouvertes** (wger, free-exercise-db) ; les formules sont composées à partir d'eux pour les objectifs du document design. **Aucun scraping de sites commerciaux de programmes** (droits d'auteur, CGU, et la même leçon que `sport=surfing` : vérifier la donnée avant de s'y fier).
- **HTTPS partout** : HSTS, redirection http → https, `upgrade-insecure-requests`, aucune ressource http (webcams comprises).

### Décidé le 13/09 (suite) — retours après deux jours d'usage, à livrer en parallèle du lot 5
- **Notation plus fine** : demi-points sur l'échelle 1-5 (stockés ×2 en entier), et **segments horaires optionnels** (`session_segments` : heure, note conditions, note perso). Chaque segment noté s'aligne sur la ligne horaire de `forecasts` — c'est un point d'apprentissage à part entière.
- **Plusieurs spots favoris**, chacun avec des **critères larges saisis par Jules** (`spot_rules` : houle min/max, période min, secteurs de houle et de vent acceptés, vent max, phase de marée). Quand un créneau des 3 prochains jours correspond, Jour l'annonce (« Parlementia devrait marcher dim. 10 h »). C'est l'*a priori* du §7.4, mais c'est le sien — il prime sur l'orientation calculée.
- **Coefficient de marée** : calculé à partir du niveau marin Open-Meteo **à Brest** (définition SHOM, U = 3,05 m, N0 = niveau moyen), le coefficient étant national par définition. Validé contre l'annuaire SHOM ; affiché « ≈ » si l'écart dépasse 5 points. Au survol dans les prévisions, dans le détail de session.
- **Énergie** affichée dans le détail et l'historique des sessions (même forme et même constante que l'écran Surf).
- **Desktop** : les écrans utilisent la largeur — max 1600 px, multi-colonnes, tableau horaire étendu à 2-3 jours visibles. Fini le contenu centré en colonne étroite.
- **Cache client** des prévisions : affichage immédiat depuis IndexedDB, rafraîchissement seulement si la donnée a plus de 2 h (stale-while-revalidate). Le cache serveur de 3 h reste.
- **Profil** : stats sympas — surf (sessions, heures, note moyenne, spot n°1, série en cours), nutrition (jours dans la cible), training (formules respectées / prévues).
- **Suivi d'habitudes quotidiennes** (`habits`, `habit_events`) : compteurs libres définis par Jules, saisie en un tap depuis Jour, ton neutre — jamais de rouge ni de morale. Servira plus tard à croiser avec le ressenti.
- `OVERPASS_URL` : poser en variable Railway l'instance qui a fonctionné (overpass-api.de bannit l'IP de sortie Railway). `railway.json` est déprécié au profit de `.railway/railway.ts` — migration avant le 2026-12-01.

### Lot 2 ter — ce qui est livré (2026-09-13)

**Navigation à cinq entrées**
- `lib/navigation.ts` — la liste des onglets vit dans un module à part, testé :
  cinq entrées, jamais une sixième. **Jour / Surf / Training / Nutrition /
  Profil**
- « Mer » devient **Surf** et absorbe l'historique des sessions et le matos ;
  « Corps » éclate en **Training** et **Nutrition** ; **Profil** sort du menu
  caché — il n'était atteignable que par une icône en haut de Jour
- Les anciennes routes **redirigent en 308**, elles ne disparaissent pas :
  `/mer`, `/corps`, `/sessions`, `/profil/matos`. Redirections déclarées dans
  `next.config.ts` depuis `MOVED_ROUTES` — une page qui appellerait
  `redirect()` rendrait un 200 de douze kilo-octets qui ne redirige qu'une fois
  React hydraté. Le lien profond du raccourci iPhone (`/sessions/{id}/noter`)
  ne bouge pas — il vit dans les Raccourcis iOS

**HTTPS — ce qui a été trouvé**
- **Aucune ressource `http:` dans le code.** Les seules occurrences sont des
  valeurs par défaut de développement (`localhost:3000`, `localhost:8000`) et
  les `base_url` des tests. Les tuiles de carte étaient déjà en
  `https://tile.openstreetmap.org`, les polices sont auto-hébergées par
  `next/font`, le manifest et les icônes sont relatifs, le service worker ne
  touche à rien d'externe. **S'il reste un avertissement en production, la
  cause est le certificat ou l'URL tapée, pas une ressource de la page.**
- Le seul vrai trou était **l'URL de webcam**, saisie libre et non validée :
  `services/webcams.py` refuse désormais le clair et réécrit en `https:` quand
  le site le sert, avec la raison du refus sinon
- En-têtes sur **les deux côtés** — le front (`next.config.ts`) et l'API
  (`core/security_headers.py`), parce que c'est l'API qui pose le cookie de
  session : HSTS un an `includeSubDomains`, CSP avec
  `upgrade-insecure-requests` et `frame-src` limitée aux hôtes de webcam
  (`lib/webcam-hosts.ts`, **source unique** partagée avec le composant),
  `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy
  geolocation=(self)`, `frame-ancestors 'none'`
- CSP de l'API : `default-src 'none'` — une API ne rend que du JSON. `/docs` a
  sa politique à part (Swagger charge ses scripts depuis jsDelivr)
- Redirection http → https **explicite** des deux côtés, lue sur
  `x-forwarded-proto` : Railway et Vercel terminent le TLS en amont, se fier au
  schéma interne donnerait une boucle infinie. **308 et pas 301** — un 301
  transformerait le POST du raccourci iPhone en GET
- Un hôte de webcam hors allowlist est affiché en **lien sortant**, pas en
  iframe : la CSP le bloquerait sans un mot, et un cadre blanc ment sur
  l'existence de l'image

**Surf — le tableau horaire**
- Cinq jours **heure par heure**, colonnes = heures, lignes = variables,
  défilement horizontal, jours en en-tête collante, colonne des libellés figée
  (`components/surf/HourlyTable.tsx`)
- Houle : hauteur, période moyenne, **énergie**, direction en **flèche** ;
  swell secondaire en ligne repliable ; vent moyen, rafales, direction en
  flèche **teintée terre / mer** depuis `onshore_dir_deg` ; marée en
  **mini-courbe continue** sur toute la largeur, extrêmes chiffrés ; eau ;
  lever / coucher en en-tête de jour ; **nuit grisée, jamais supprimée** ;
  note 1-5 en ligne du bas, meilleur créneau du jour cerclé d'accent
- **Deux échelles de couleur qui ne se mélangent jamais** : le séquentiel
  (l'intensité) sur les hauteurs et les vents, l'échelle 1 → 5 (la qualité) sur
  la seule ligne de note. Une houle de 3 m est grosse, ce qui n'est pas la même
  chose que bonne
- **Énergie** : `geo.wave_energy_kj` = `0,49 × H² × T`, en kJ par seconde et
  par mètre de crête (kW/m) — la feature 9 du registre avec sa constante
  physique. `wave_energy` garde la forme brute `H²T` : c'est elle qui entre
  dans le vecteur de features, et une constante d'affichage ne doit pas
  déplacer un historique d'apprentissage
- **Détail d'un créneau** (`GET /spots/{ref}/slot`) : le **seul** endroit où
  les directions sont des degrés et des lettres. Écart à l'orientation du spot,
  composante offshore chiffrée, `run_ts` d'origine et **écart avec le run de la
  veille au soir** — le bénéfice visible de l'historisation des runs
- Sur **Jour**, les huit créneaux de 3 h portent maintenant hauteur, période,
  flèche de houle, vent et flèche, note. Un tap ouvre Surf **positionné sur
  cette heure**

**Sessions depuis le navigateur**
- `/sessions/nouvelle` et l'écran de notation partagent **un seul**
  `SessionForm` : deux formulaires divergeraient, et une session saisie à la
  main finirait par ne plus porter les mêmes champs qu'une session notée
- Date en molette, spot cherché dans tout le catalogue, les deux notes exigées.
  Le serveur fait exactement le même travail que pour le raccourci : backfill
  d'archive, et volet `forecast` **borné aux runs émis avant le début**, dates
  passées comprises
- Modifier une session : tous les champs. Changer le spot ou l'heure refait le
  figeage et **empile** l'ancien dans `snapshot_history` — jamais d'écrasement
  silencieux. Un cran de quinze minutes n'y touche pas : la fenêtre est calée à
  l'heure pleine
- Supprimer = **corbeille 30 jours**, purgée par un job quotidien. Restaurer
  rend la session telle qu'elle est entrée, rien n'est recalculé
- Historique dans Surf : filtres **spot / mois / note**, appliqués côté
  serveur — à 240 sessions par an, un filtre qui ne trie que la page visible
  ment

**Migration `0006`** — `snapshot_history`, `deleted_at`, index associé.
**305 tests pytest + 25 vitest verts**, `npm run lint` et `npm run build`
propres. En-têtes vérifiés en production sur les deux hôtes.

### Lot 4 — ce qui est livré (2026-09-13)

**Objectifs mesurés**
- Les trois du document design : mains-sol, rotation thoracique, gainage tenu.
  **Aucune valeur de départ n'est semée** — le départ *est* la première mesure.
  Un départ tapé au clavier est une estimation qu'on prendrait ensuite pour une
  mesure
- `direction` (`up` / `down`) sur l'objectif : « mains-sol » va de −14 cm vers
  0, donc **vers le haut**. Sans cette colonne, la moitié des jauges liraient
  un progrès comme un recul
- Saisie **à la molette**, pas de pavé numérique. Une mesure par jour et par
  objectif : se remesurer le même jour remplace
- Rappel « mesurer » quand la fréquence (21 jours) est dépassée — il passe
  devant tout sur l'écran Training

**Bibliothèque et formules**
- `services/training_catalog.py` — 30 exercices **rédigés ici, en français**.
  Les consignes nous appartiennent : c'est ce qui permet de composer des
  séances sans reprendre le texte de personne
- `scripts/import_exercises.py` — **bases ouvertes uniquement** : wger (API
  publique) et free-exercise-db (domaine public, 876 exercices avec images).
  Rapprochement par `aliases` anglais : l'import **enrichit** la ligne rédigée
  à la main au lieu d'en créer une deuxième. Source et licence sur chaque ligne
- `--sample` montre un échantillon et **n'écrit rien** : la leçon de
  `sport=surfing`, appliquée. Le classement en trois catégories est **grossier
  et on le sait** — on le relit avant de l'écrire
- ⚠️ **wger a renommé `exercisebaseinfo` en `exerciseinfo`** ; l'ancien rend un
  404 (vérifié le 13/09). Un échec de source est journalisé, l'autre continue
- **15 formules** : les cinq du design plus deux variantes chacune. Les
  variantes ne sont pas cosmétiques — une séance faite tous les matins pendant
  six mois se fait de moins en moins bien, puis plus du tout. L'avancement
  hebdo se compte **par famille**
- Chaque formule porte **le principe qui la justifie**, en une ligne. C'est ce
  qui la distingue d'un programme recopié, et ce qui la rend corrigible

**Proposition du jour**
- Une seule, remplaçable en un tap : la formule qui sert l'objectif le plus en
  retard, pondérée par ce qui a déjà été fait cette semaine et par les sessions
  de surf. **Trois jours de surf d'affilée → Post-surf ou Réveil, jamais
  Renfo**
- Les alternatives sont **une par famille** : remplacer doit proposer autre
  chose, pas une variante de la même séance
- Une phrase dit pourquoi celle-ci. Une proposition qu'on ne comprend pas se
  remplace au hasard, et on finit par ne plus la lire

**Mode séance** (plein écran, modal)
- Exercice en cours très grand, image, minuteur de repos géant, Fait / Passer /
  +30 s, progression en tête. **Zéro clavier**
- **Screen Wake Lock**, repris au retour d'onglet ; **vibration et bip
  synthétisé** en fin de repos — pas de fichier audio, donc rien à charger
- Les comptes à rebours sont des **échéances**, pas des compteurs décrémentés :
  un onglet en arrière-plan ralentit `setInterval`, et un repos de 45 s
  finirait par en durer 70
- **Écourter est compté à part**, et c'est le serveur qui tranche à partir des
  séries réellement faites (seuil 80 %). Une séance de 28 min arrêtée à la
  sixième est un renseignement sur la formule ; la compter comme faite
  effacerait exactement ce qui permettrait de la corriger — et la proposition
  du jour continuerait de la servir
- Ressenti 1-5 à la fin, un écran, un tap

**Migration `0007`** — sept tables. Le **contenu** est semé par l'application,
pas par la migration : il évoluera, et on n'écrit pas une migration par
correction de tempo. Semis idempotent, au premier accès à l'écran Training.

**338 tests pytest + 25 vitest verts**, `npm run lint` et `npm run build`
propres. Schéma de production vérifié à la révision `0007`.

### Lot 2 ter et lot 4 — ce qui reste (hors code)
- [ ] Lancer `python -m scripts.import_exercises --sample` puis, si les
      catégories tiennent, `python -m scripts.import_exercises` en production
      (depuis le conteneur Railway). Sans lui, les exercices n'ont pas
      d'image — les séances marchent quand même
- [ ] Poser la première mesure de chacun des trois objectifs, sinon les jauges
      restent vides et la proposition du jour se rabat sur le défaut
- [ ] Saisir les URL de webcams des spots maison depuis la fiche spot (le
      formulaire existe maintenant, et refuse le http)
- [ ] Vérifier le tableau horaire **au soleil, à bout de bras** — c'est le seul
      test qui compte pour cet écran
