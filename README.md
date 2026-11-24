# IODEJ — On mange où ?

Petite appli entre collègues pour décider où déjeuner, façon Tinder × jeu mobile.

- **Chaque jour**, 10 restaurants sont tirés au sort dans la base (la même liste pour tout le monde).
  Le changement de jour se fait à minuit (fuseau `Europe/Paris` par défaut), vérifié à chaque appel : pas de tâche planifiée.
- Tu **swipes** (glisser ou boutons ✗ / ♥, flèches ← → au clavier).
- Une fois tes 10 swipes faits, tu débloques :
  - **Choix** — ce que tout le monde a validé, resto par resto ;
  - **Groupes** — une répartition qui fait les groupes les plus gros possibles
    (on préfère 2 + 3 à 4 + 1 : personne ne mange seul si on peut l'éviter) ;
  - **Historique** — où tu as mangé ces 7 derniers jours (bouton « J'y vais ! »).
- **Connexion** : ton prénom + le code d'accès commun, mémorisés en cookie pour toujours. « Déconnexion » efface tous les cookies.
- **Backoffice** `/admin` (code admin séparé) : CRUD restaurants & collègues avec photo, affichage/régénération des codes, relance du tirage du jour.

Stack : FastAPI · Jinja2 · htmx · Alpine.js · SQLite · uv. Aucun build front, tout est servi par le monolithe
(htmx, Alpine et les polices sont embarqués dans `app/static`, aucun CDN). Installable en PWA.

## Démarrage local

```bash
./scripts/dev.sh
```

→ http://localhost:8000 (des restos et collègues de démo sont ajoutés si la base est vide, les codes sont affichés dans le terminal).

## Déploiement sur un VPS Ubuntu (Hostinger…)

```bash
git clone <url-du-depot> iodej && cd iodej
sudo ./scripts/install.sh --domain dej.mondomaine.fr
```

Le script installe `uv`, les dépendances, crée le service systemd `iodej` et configure **Caddy** en reverse proxy
avec HTTPS automatique (Let's Encrypt). Pointe d'abord l'enregistrement DNS A du domaine vers l'IP du VPS.
Sans domaine (`sudo ./scripts/install.sh`), l'appli est servie en HTTP sur le port 80 de l'IP du VPS
(la PWA « installable » nécessite HTTPS).

Les **codes d'accès** sont générés au premier lancement et affichés à la fin de l'installation.

| Tâche | Commande |
|---|---|
| Mettre à jour (pull + deps + restart, avec sauvegarde) | `sudo ./scripts/update.sh` |
| Sauvegarder base + photos dans `backups/` | `./scripts/backup.sh` |
| Afficher les codes | `uv run iodej codes` |
| Régénérer le code collègues / admin | `uv run iodej rotate-code access` / `admin` |
| Relancer le tirage du jour | `uv run iodej reset-day` |
| Logs | `journalctl -u iodej -f` |

## Configuration (variables d'environnement, toutes optionnelles)

| Variable | Défaut | Rôle |
|---|---|---|
| `IODEJ_DATA_DIR` | `./data` | Base SQLite + photos uploadées |
| `IODEJ_TZ` | `Europe/Paris` | Fuseau pour le passage à minuit |
| `IODEJ_SHORTLIST_SIZE` | `10` | Nombre de restos tirés par jour |
| `IODEJ_COOKIE_SECURE` | `0` (`1` si domaine) | Cookies `Secure` (HTTPS) |
| `IODEJ_HOST` / `IODEJ_PORT` | `127.0.0.1` / `8000` | Écoute du serveur |

## Structure

```
app/
  main.py         FastAPI, montages statiques, PWA
  routes/         public.py (collègues) · admin.py (backoffice)
  daily.py        jour courant + tirage paresseux de la shortlist
  grouping.py     algorithme de constitution des groupes
  db.py           schéma SQLite + réglages (codes)
  templates/      Jinja2 (+ partials htmx)
  static/         CSS, JS (swipe, confettis…), polices, htmx, Alpine, icônes
scripts/          install · update · backup · dev
tests/            uv run pytest
```

### L'algorithme des groupes

Chaque collègue est placé dans un restaurant qu'il a validé ; ceux qui vont au même endroit forment un groupe.
On trie les tailles de groupes par ordre croissant et on maximise lexicographiquement :
`[2, 3]` bat `[1, 4]`, `[5]` bat `[2, 3]`, `[2, 6]` bat `[2, 3, 3]`. À égalité, les restos les plus plébiscités gagnent.
Recherche exhaustive quand c'est raisonnable, sinon recherche locale avec redémarrages (déterministe pour la journée).
