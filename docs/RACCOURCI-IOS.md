# Raccourci iOS — « Sortie de l'eau »

> Recette pas à pas. Une seule mise en place, puis un tap par session.
> Compte dix minutes pour la première fois.

## Pourquoi ce raccourci existe

Environ **240 sessions par an**. À 90 secondes de formulaire pièce, cela fait
six heures de saisie annuelles et un abandon au bout de trois mois. À 15
secondes, l'historique existe — et sans historique, la reco du lot 3 n'a rien à
apprendre.

Ce raccourci est le chemin le plus court qui existe : on sort de l'eau, on tape
une fois, la session est enregistrée avec le bon spot et les conditions figées.
La notation, elle, se fait plus tard, au sec, sur l'écran que le raccourci
ouvre juste après.

Il ne remplace pas l'app : il évite d'avoir à la déverrouiller, l'ouvrir,
attendre, trouver le bouton — les gestes dont aucun ne survit à une main
mouillée et à un téléphone sous 30 % de batterie.

---

## Étape 1 — Créer le jeton

Le raccourci iOS n'a pas de cookies : il ne peut pas se servir de la session du
navigateur. Il lui faut un jeton `Bearer`.

1. Dans l'app, ouvrir **Profil** (icône en haut à droite de l'écran Jour) →
   **Raccourci iPhone**.
2. Toucher **Créer un jeton**.
3. Copier les trois valeurs affichées. **Le jeton n'est montré qu'une fois** :
   il n'est pas stocké côté serveur, qui ne garde que de quoi le révoquer. S'il
   est perdu, on en refait un et on révoque l'ancien — ça prend dix secondes.

On repart avec :

| | |
|---|---|
| **URL** | `https://api-sport.atelier-okomi.fr/api/v1/sessions/quick` |
| **En-tête** | `Authorization` → `Bearer eyJhbGciOi…` |

Le jeton vaut **un an**. C'est long, et c'est pour ça qu'il est révocable :
téléphone perdu, revendu, prêté — un tap sur **Révoquer** le coupe
immédiatement, sans déconnecter le navigateur.

---

## Étape 2 — Monter le raccourci

Ouvrir l'app **Raccourcis** d'iOS, toucher **+** en haut à droite, puis ajouter
les quatre actions suivantes **dans cet ordre**.

### 1. Obtenir la position actuelle

Chercher « position », choisir **Obtenir la position actuelle**.

Rien à régler. La première exécution demandera l'autorisation de localisation :
répondre **Autoriser**. Sans elle, le raccourci marche quand même, mais la
session sera rattachée au spot favori du profil au lieu du spot réel.

### 2. Obtenir le contenu de l'URL

Chercher « contenu de l'URL », choisir **Obtenir le contenu de l'URL**.

Dans le champ URL, coller :

```
https://api-sport.atelier-okomi.fr/api/v1/sessions/quick
```

Déplier **Afficher plus** et régler :

- **Méthode** : `POST`
- **En-têtes** : toucher **Ajouter un nouvel en-tête**
  - Clé : `Authorization`
  - Valeur : `Bearer ` suivi du jeton copié à l'étape 1
    *(un espace après `Bearer`, et rien après le jeton — pas de retour à la
    ligne, pas de guillemets)*
- **Corps de la requête** : `JSON`
- Ajouter deux champs, tous les deux de type **Nombre** :

  | Clé | Valeur |
  |---|---|
  | `lat` | variable **Latitude** de l'action précédente |
  | `lon` | variable **Longitude** de l'action précédente |

  Pour insérer la variable : toucher le champ de valeur, puis la barre de
  variables au-dessus du clavier, choisir **Position actuelle**, et sélectionner
  **Latitude** (puis **Longitude** pour le second champ).

> **Ne rien ajouter d'autre.** Le serveur déduit le reste : l'heure de fin est
> « maintenant », le début est estimé à 90 minutes plus tôt, et le spot est le
> plus proche du catalogue à moins de 2 km. Chaque champ de plus est un réglage
> de plus à maintenir, pour une information que la notation corrigera d'un tap
> si elle est fausse.

### 3. Obtenir la valeur du dictionnaire

Chercher « dictionnaire », choisir **Obtenir la valeur du dictionnaire**.

- **Obtenir** : `Valeur`
- **Pour** : `rate_url`
- **Dans** : la variable **Contenu de l'URL** (l'action précédente)

C'est le lien profond que le serveur renvoie, du type
`https://sport.atelier-okomi.fr/sessions/412/noter`.

### 4. Ouvrir l'URL

Chercher « ouvrir », choisir **Ouvrir des URL**, et lui passer la variable
**Valeur du dictionnaire** de l'action précédente.

L'app s'ouvre directement sur l'écran de notation de la session qui vient
d'être créée. C'est ce qui fait que « noter plus tard » ne veut pas dire
« ne jamais noter ».

### Nommer et poser sur l'écran d'accueil

- Renommer le raccourci **Sortie de l'eau**.
- Menu **⋯** → **Ajouter à l'écran d'accueil**, ou ajouter le widget
  **Raccourcis** en taille moyenne pour l'avoir sans déverrouiller.
- Optionnel et recommandé : l'ajouter au **bouton Action** (iPhone 15 Pro et
  au-delà) ou à un **double tap au dos** (Réglages → Accessibilité → Toucher →
  Toucher le dos). Le raccourci devient alors utilisable sans regarder l'écran,
  ce qui est exactement la situation : debout, mouillé, ébloui.

---

## Étape 3 — Vérifier

Le déclencher une fois, depuis chez soi.

Ce qui doit se passer : une seconde ou deux d'attente, puis l'app s'ouvre sur
« Noter la session ». Le spot affiché sera probablement faux si le domicile
n'est pas sur la plage — c'est normal, et c'est justement pour ça que le spot
est modifiable en un tap en tête d'écran.

Supprimer ensuite la session d'essai : ouvrir son détail, tout en bas,
**Supprimer la session**.

---

## Ce qui se passe vraiment côté serveur

À réception, `POST /sessions/quick` :

1. cherche le **spot du catalogue le plus proche à moins de 2 km**. Hors de ce
   rayon, il retombe sur le **spot favori du profil** ;
2. estime le début à **fin − 90 minutes**, et marque cette heure comme estimée
   (`start_estimated`) — une estimation ne doit jamais pouvoir se lire plus tard
   comme une heure relevée ;
3. crée la session en statut **« à noter »** ;
4. **fige les conditions** dans une fenêtre T−2 h / T−1 h / T0, en deux volets :
   `observed` depuis l'archive Open-Meteo, et `forecast` limité aux runs **émis
   avant le début de la session**. C'est le seul geste irrattrapable de la
   chaîne — une prévision passée ne se reconstitue pas ;
5. renvoie l'identifiant et le lien profond.

**L'appel est idempotent sur dix minutes.** Deux déclenchements rapprochés —
un doigt mouillé, un bouton Action pressé deux fois dans la poche — donnent une
seule session, et la réponse le dit (`created: false`).

---

## Si ça ne marche pas

| Ce qu'on voit | Ce que c'est | Quoi faire |
|---|---|---|
| `401` | Jeton absent, mal recopié, expiré ou révoqué | Vérifier qu'il y a bien un espace après `Bearer` et rien après le jeton. Sinon en créer un nouveau depuis le profil. |
| `409` | Aucun spot à moins de 2 km **et** aucun spot favori | Choisir un spot favori dans le profil, ou ajouter le spot depuis la carte. |
| `422` | Le corps n'est pas du JSON, ou `lat`/`lon` sont partis en texte | Dans l'action, repasser le corps en **JSON** et les deux champs en **Nombre**. |
| Le raccourci tourne sans fin | Pas de réseau | Le chemin rapide **exige** le réseau : c'est iOS qui réessaiera. Rien n'est perdu, mais rien n'est enregistré non plus — relancer une fois la 4G revenue, l'heure de fin sera juste décalée, et la notation la corrige. |
| L'app ne s'ouvre pas à la fin | L'action 3 ou 4 ne reçoit pas la bonne variable | Vérifier que l'action 3 lit bien `rate_url` dans **Contenu de l'URL**, et que l'action 4 reçoit **Valeur du dictionnaire**. |

---

## Ce que le raccourci ne fait pas

- **Il ne note pas.** Les deux notes — qualité des conditions et ressenti perso —
  se posent dans l'app, en cinq boutons chacune. Les demander à la sortie de
  l'eau ferait exploser les quinze secondes, et une note donnée en grelottant
  n'est pas une note.
- **Il ne marche pas hors ligne.** C'est assumé : la file hors ligne de l'app
  couvre la **notation**, pas l'enregistrement. Sur un parking sans réseau, on
  ouvre l'app quand ça revient, ou on saisit la session après coup —
  l'archive Open-Meteo reconstitue les conditions de n'importe quelle date.
- **Il n'envoie pas de photo.** Trois mégaoctets n'ont rien à faire sur le
  chemin des quinze secondes. La photo s'ajoute depuis l'écran de notation,
  repliée, en bas, quand on y tient.
