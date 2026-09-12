# Sport — Contexte projet et conventions

> Cadrage fonctionnel, backlog et décisions : `PROJET.md`. Ce fichier = conventions de code et état d'avancement.

## Identité
- Nom : Sport (provisoire)
- Concept : suivi perso surf / training / nutrition, mobile-first, un seul utilisateur
- Site : https://sport.atelier-okomi.fr *(à créer)*
- API : https://api-sport.atelier-okomi.fr *(à créer)*

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
1. **Mobile d'abord** — on dessine le 390 px, le desktop suit. Barre de navigation basse, cibles ≥ 44 px, police ≥ 16 px.
2. **Zéro saisie clavier pendant l'effort** — boutons, curseurs, molettes. Le clavier ne sert qu'aux notes libres optionnelles.
3. **Hors-ligne réel** — enregistrer une session sans réseau, file IndexedDB synchronisée au retour.
4. **Écran d'accueil = une seule question** : « je vais à l'eau, oui ou non, et où ? »
5. **Ingestion météo idempotente** — `ON CONFLICT DO UPDATE` sur `(spot_id, ts, source)`. Le service Railway redémarre, le job repart.
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

Écrans de référence (maquettes) : accueil « OUI + spot recommandé », comparateur heures × spots, fiche spot, saisie rapide (modale, sans nav), séance en cours (modale, timer géant), stats ; desktop : tableau de bord semaine, analyse, historique + panneau détail.

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

## Variables d'environnement — Vercel (front)
```
NEXT_PUBLIC_API_URL=https://api-sport.atelier-okomi.fr/api/v1
NEXT_PUBLIC_SITE_URL=https://sport.atelier-okomi.fr
NEXT_PUBLIC_APP_NAME=Sport
```

## État d'avancement
- [x] Lot 0 — repo, infra, auth, coquille PWA — **code terminé le 2026-09-12**, mise en ligne à faire
- [ ] Lot 1 — spots, ingestion météo, écran d'accueil, webcams
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
- [ ] Créer le dépôt GitHub `jules-descotes/sport` et pousser
- [ ] Railway : service back (Dockerfile) + Postgres dédié, variables d'environnement
- [ ] Vercel : projet front sur `/frontend`, variables `NEXT_PUBLIC_*`
- [ ] OVH : CNAME `sport` et `api-sport` sur `atelier-okomi.fr`
- [ ] Installer la PWA sur le téléphone et vérifier le plein écran iOS

### À décider avant le lot 1 (cf. PROJET.md §11)
- [ ] Liste des 8 à 12 spots de départ (seules les coordonnées sont indispensables)
- [ ] Surf seul, ou surf + foil dès le départ
- [ ] Marées : API payante ou table statique annuelle
