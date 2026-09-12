# Sport

Suivi perso surf / training / nutrition. Mobile d'abord, PWA installable,
un seul utilisateur.

Cadrage fonctionnel : `PROJET.md` · conventions de code : `CLAUDE.md`.

## Prérequis

- Python 3.12
- Node 20 ou plus

## Lancer le back-end

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows — sous Unix : source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # puis renseigner SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
alembic upgrade head
python run.py
```

API sur http://localhost:8000 · documentation sur http://localhost:8000/docs
· sonde sur http://localhost:8000/health.

L'utilisateur unique est créé au démarrage à partir de `ADMIN_EMAIL` et
`ADMIN_PASSWORD`. Il n'y a pas d'inscription publique.

## Lancer le front-end

```bash
cd frontend
npm install
npm run dev
```

App sur http://localhost:3000. `frontend/.env.local` pointe vers le back
**local** (`http://localhost:8000/api/v1`) : le dev local tape le local.

## Lancer les tests

```bash
pytest tests/ -v
```

Les tests tournent sur SQLite en mémoire, sans base ni serveur à démarrer.

## Migrations

```bash
alembic revision --autogenerate -m "message"
alembic upgrade head
```

## Déploiement

Push sur `main` : Railway déploie le back (Dockerfile, sonde `/health`) et
Vercel déploie le front. Pas de workflow de déploiement maison —
`.github/workflows/ci.yml` ne fait que les tests et le build.
