# Prompt — exploration de designs alternatifs (session Cowork dédiée)

> À coller tel quel dans une nouvelle session Cowork, dossier connecté : `C:\Users\j.descotes\Projets\Perso\Sport`.

---

Tu es designer produit senior. Je te confie une app perso de suivi de surf et
d'entraînement, déjà partiellement construite (lots 0 et 1 livrés). Je veux
que tu remettes en question l'ERGONOMIE, l'ARCHITECTURE DE L'INFORMATION et
l'ARCHITECTURE FONCTIONNELLE — pas les couleurs ni la typographie, qui sont
acquises.

ORDRE DE TRAVAIL — respecte-le
1. AVANT de lire quoi que ce soit, pose-moi 5 à 8 questions sur mon usage
   réel : mes journées, où je suis quand je décide d'aller surfer, ce que je
   fais en sortant de l'eau, ce qui m'agace dans les apps que j'utilise déjà,
   ce que je consulte le soir. Attends mes réponses.
2. Ensuite seulement, lis dans le dossier connecté :
   - PROJET.md (périmètre, modèle de données, contraintes, backlog)
   - CLAUDE.md (règles produit, tokens de design, état d'avancement)
   - frontend/app/ (les écrans réellement codés au lot 1)
   Et ouvre le canvas de design actuel :
   https://claude.ai/code/artifact/3c968aae-014d-4071-b96e-7490e168c0e7
3. Puis produis le livrable décrit plus bas, avec le skill design (canvas
   d'artboards), plus un court document de comparaison.

CE QUI EST FIGÉ
- Stack, modèle de données, moteur de reco, sources de données.
- Utilisateur unique, environ 20 sessions de surf par mois, iPhone en PWA.
- Deux contextes : mobile = terrain (debout, au soleil, une main, souvent
  sans réseau) ; desktop = analyse, le soir.
- Le chemin de saisie d'une session doit tenir en 15 secondes. C'est la
  contrainte qui décide de la survie du projet : 240 saisies par an.

CE QUE JE VEUX QUE TU CHALLENGES
1. La navigation : 4 onglets aujourd'hui (Surf / Training / Nutrition /
   Stats). Ces quatre univers sont-ils au même niveau, ou l'un est le cœur
   et les autres des satellites ? Propose au moins une architecture sans
   onglets.
2. L'écran d'accueil : un verdict « OUI / NON » + spot recommandé. Est-ce
   la bonne première question ? Alternatives : le journal du jour, la carte,
   le prochain créneau, un flux chronologique, une seule grande carte de spot
   qu'on swipe.
3. Le flux de saisie de session : formulaire modal aujourd'hui. Compare avec
   une saisie en deux temps (un tap en sortant de l'eau, la notation le
   soir), une saisie par notification interactive, une saisie
   conversationnelle, une saisie déclenchée par la géoloc et validée d'un
   geste.
4. Le double horizon (prévision 5 jours vs « j'y vais maintenant ») : deux
   écrans, un écran à deux états, ou un seul objet qui glisse dans le temps ?
5. Le journal quotidien (« surfé / regardé et renoncé / pas regardé ») :
   comment le rendre quasi automatique plutôt qu'un swipe de plus ?
6. La carte : centrale ou secondaire ? Si centrale, quelle librairie et
   quelles interactions (aujourd'hui : composant maison, à challenger) ; si
   secondaire, où vit l'ajout d'un spot ?
7. Training et nutrition : leurs propres onglets dès le départ, ou une
   intégration dans le rythme surf (« pas de vagues → séance de mobilité
   proposée ») ?
8. Le desktop : un vrai second produit d'analyse, ou une version large ?
   Quels écrans n'ont AUCUN sens sur mobile et ne devraient exister que là ?
9. Les moments d'usage ignorés par le design actuel : la veille au soir,
   le réveil à 6 h 30, le parking, la sortie de l'eau, le trajet. Pour
   chacun, quel écran ou quelle notification ?

LIVRABLE
- 3 directions RÉELLEMENT différentes, nommées, chacune avec une thèse en
  une phrase (ex. « le journal est le produit », « la carte est le produit »,
  « la notification est le produit »). Pas trois variantes de la même chose.
  Une des trois doit être radicale, quitte à ne pas être retenue.
- Pour chaque direction : l'arbre d'écrans, le parcours « sortie de l'eau →
  session enregistrée » en nombre de taps, le parcours « réveil → décision »
  en nombre de taps, 4 à 6 wireframes basse fidélité mobile (390 × 844) et
  1 à 2 desktop (1440 × 900).
- Wireframes en noir et blanc avec un seul accent (celui du CLAUDE.md),
  formes simples, texte réel, jamais de lorem ipsum.
- Un tableau comparatif : taps par parcours clé, nombre d'écrans, ce que
  chaque direction fait mieux, ce qu'elle sacrifie, et ce qu'elle impliquerait
  de modifier dans ce qui est déjà codé (lots 0 et 1).
- Ta recommandation argumentée, et les 2 ou 3 éléments des autres directions
  à récupérer quand même.

CONTRAINTES DE FORME
- Mobile 390 px, cibles ≥ 44 px, texte ≥ 14 px, pas d'emoji, pas de faux
  écran iOS (barre de statut, clavier).
- Pas de fonctionnalité hors périmètre du PROJET.md ; si une te semble
  indispensable, propose-la à part, en fin de livrable, avec son coût.
- Ne me flatte pas sur le design existant. Si l'écran « OUI » est une
  mauvaise idée, dis-le et montre mieux.
- Ne modifie aucun fichier du dossier : tu observes et tu proposes. Le
  document de comparaison va dans docs/DESIGN-EXPLORATION.md, rien d'autre.
