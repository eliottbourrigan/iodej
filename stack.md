# stack.md — la recette « no-build » d'IODEJ

> **Pour un agent** : « Porte ce projet sur cette stack » = reproduire *exactement* ce qui suit.
> Le code de référence est dans ce dépôt : copie les fichiers cités, remplace `iodej` / `IODEJ_` par le
> nom du projet, garde les conventions. Ne rajoute ni bundler, ni `package.json`, ni ORM, ni Docker.

## 1. Principes

- **Le serveur rend du HTML, c'est l'API.** HTMX échange des fragments ; pas de JSON sauf pour 2-3 appels JS.
- **Zéro build** : pas de npm, TypeScript, Tailwind, Sass, bundler. Le code écrit est le code servi.
- **Monolithe** : 1 processus Python + SQLite + fichiers. Tout le code front est dans `app/static/`.
- **Tout est vendorisé** (htmx, alpine, polices) : aucun CDN, aucun appel externe au chargement.
- **Données hors du code** (`/home/<projet>/data`) : un déploiement ne les touche jamais ; migrations additives.
- **Mises à jour sans coupure** : 2 instances derrière Caddy, redémarrées l'une après l'autre.
- **Mobile d'abord**, PWA installable.

## 2. Briques

| Rôle | Choix |
|---|---|
| Python / paquets | Python ≥ 3.11, **uv** (`uv sync --frozen`, `uv.lock` commité, `[project.scripts]` pour la CLI) |
| Web | **FastAPI** + **Jinja2** + `python-multipart`, servi par **uvicorn** |
| Interactions | **HTMX 2** (serveur) + **Alpine.js 3** (état local), copiés dans `static/vendor/` |
| Style | 1 fichier CSS maison, tokens en custom properties, polices woff2 vendorisées (Fontsource) |
| Données | **SQLite** via `sqlite3` brut (WAL, `foreign_keys=ON`), pas d'ORM |
| Images | **Pillow** : upload → redressé, réduit à 1000 px, WebP, nom aléatoire |
| Notifications | **pywebpush** (Web Push / VAPID) + timers systemd |
| Tests | **pytest** + `TestClient` ; contrôle visuel avec Playwright (préinstallé) |
| Serveur | VPS Ubuntu · **Caddy** (HTTPS auto) · **systemd** (services + timers) |
| CI/CD | **GitHub Actions** : tests → rsync → install → sonde de disponibilité |

## 3. Arborescence

```
app/
  main.py          app FastAPI, montages /static & /uploads, en-têtes (cache, sécurité), /healthz, /sw.js, manifest
  config.py        tout vient de variables d'env PREFIX_* (avec défauts)
  db.py            SCHEMA (CREATE IF NOT EXISTS) + _migrate() additif + settings clé/valeur + get_db()
  web.py           templates Jinja + helpers globaux : static() versionné, render(), filtres
  auth.py          cookies + dépendances require_user / require_admin
  cli.py           `<projet> serve|init|codes|seed|notify…`
  routes/          public.py (pages + partials + /api), admin.py (CRUD générique)
  templates/       base.html → layout.html → pages ; partials/ pour HTMX ; macros.html
  static/          css/app.css · js/app.js, js/sw.js · vendor/ · fonts/ · icons/ · manifest.webmanifest
scripts/           install.sh · remote-deploy.sh · update.sh · backup.sh · dev.sh
tests/             conftest.py (DB temporaire par test) + test_*.py
.github/workflows/deploy.yml
```

## 4. Conventions backend

- **Connexion SQLite par requête** (`Depends(db.get_db)`, `check_same_thread=False`), `isolation_level=None`,
  écritures concurrentes sous `BEGIN IMMEDIATE` (`db.transaction`).
- **Migrations** : uniquement additives et idempotentes dans `_migrate()` (`PRAGMA table_info` → `ALTER TABLE ADD
  COLUMN`, `INSERT` si absent). Jamais de `DROP`. Testées sur une base à l'ancien schéma (`tests/test_migration.py`).
- **Secrets applicatifs** (codes d'accès, clés VAPID) générés au premier `init`, stockés dans `settings`,
  jamais affichés en CI (`iodej codes` seulement en session interactive).
- **Pages** = routes HTML complètes ; **fragments** = `/partials/<nom>` ; erreurs d'auth → `HX-Redirect`
  si requête HTMX, sinon 303.
- **Logique « du jour »** calculée à l'appel (fuseau `PREFIX_TZ`), pas de cron pour l'état.
- `/healthz` (toujours 200 si vivant) pour le déploiement et la sonde ; `/healthz/lb` pour Caddy, qui répond
  503 quand le fichier `data/drain-<port>` existe (mise hors trafic). `/robots.txt` + `X-Robots-Tag: noindex` si appli interne.
- Auth légère possible : cookie longue durée contenant un *hash* du code partagé (changer le code = tout le
  monde déconnecté).

## 5. Conventions front

- **Frontière HTMX / Alpine** : besoin de données serveur → HTMX ; état purement local (menu, popup) → Alpine ;
  logique lourde (drag, canvas) → JS natif dans un IIFE.
- Scripts en `defer` dans `<head>` ; `app.js` avant `alpine.min.js` (les composants `x-data="foo()"` doivent exister).
- **Assets** : toujours `{{ static('css/app.css') }}` → `/static/css/app.css?v=<md5 du fichier>` calculé au démarrage.
  Réponses `/static?v=` et `/uploads` : `Cache-Control: public, max-age=31536000, immutable` ;
  pages HTML : `no-cache, private` ; `Vary: HX-Request` sur les réponses HTMX.
- **Design** : tokens CSS (`--ink`, couleurs, `--r`, `--bw`…), un seul fichier, animations CSS, `prefers-reduced-motion`.
- **PWA** : `manifest.webmanifest` + icônes PNG (192/512/maskable/apple-touch) + `/sw.js` servi à la racine
  (`Cache-Control: no-cache`) qui ne met en cache que l'immuable (assets versionnés, uploads).
  Encart d'installation selon l'OS (Android : `beforeinstallprompt`, iOS : Partager → écran d'accueil),
  masquable 7 jours.
- **Web Push** : bouton dans le menu ; permission demandée *directement* dans le clic (iOS) ; clé publique VAPID
  chargée d'avance ; abonnement `POST /api/push/subscribe` ; désabonnement à la déconnexion.
  iOS : uniquement depuis l'appli installée.

## 6. Serveur (un VPS, plusieurs projets)

```
DNS  *.domaine.fr  A → IP du VPS            (un joker, plus jamais à toucher)
Caddy  /etc/caddy/Caddyfile = "import sites/*.caddy"   ← un fichier par projet
Projet <p> : utilisateur Linux <p>, code /home/<p>/app, données /home/<p>/data, sauvegardes /home/<p>/backups
             instances <p>@PORT et <p>@PORT+1 (127.0.0.1 seulement), timers <p>-*.timer
```

Ports : iodej `8000/8001`, projet suivant `8010/8011`, etc.

Site Caddy généré par `install.sh` :

```
iodej.domaine.fr {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000 127.0.0.1:8001 {
        lb_policy first            # tout va sur la 1re instance saine…
        lb_try_duration 15s        # …et bascule sur l'autre pendant un redémarrage
        lb_try_interval 250ms
        fail_duration 10s
        health_uri /healthz/lb     # 503 pendant la mise hors trafic
        health_interval 2s
    }
}
```

Unité systemd **modèle** `/etc/systemd/system/<p>@.service` (`%i` = port), `User=<p>`,
`Environment=PREFIX_DATA_DIR=…`, `Environment=PREFIX_PORT=%i`, `ExecStart=~/.local/bin/uv run --frozen --no-dev <p> serve --port %i`,
`Restart=always`, `TimeoutStopSec=20`. Tâches planifiées = paires `.service` (oneshot) + `.timer`
(`OnCalendar=Mon..Fri *-*-* 11:30:00 Europe/Paris`, `Persistent=false`).

## 7. Déploiement

**`git push` sur la branche par défaut → en ligne en ~40 s, sans coupure.**

1. **test** : `uv sync --frozen && uv run pytest -q`.
2. **deploy** (si tests verts) :
   - clé SSH depuis le secret (réparée si mal collée, vérifiée avec `ssh-keygen -y`) ;
   - `rsync` du dépôt (sans `.git`, `data`, `.venv`) vers `/tmp/<p>-release-<sha>` ;
   - `remote-deploy.sh` en root : crée l'utilisateur au 1er passage, **sauvegarde** la base, `rsync --delete`
     du code vers `/home/<p>/app` (`data/` exclu), puis `install.sh` (`--skip-system` après le 1er passage) ;
   - `install.sh` : `uv sync`, `init` (migrations), unités systemd, timers, site Caddy, **redémarrage progressif** :
     pour chaque port (PORT+1 puis PORT) → **mise hors trafic** (`touch data/drain-<port>`, 5 s : Caddy bascule
     tout sur l'autre instance) → stop → vérifie que le port est libre (sinon échoue en nommant le programme)
     → start → attend `/healthz` *servi par cette unité* (vérif. du cgroup) → 3 s → suivant ;
   - **sonde** : `curl https://<domaine>/healthz` toutes les 200 ms pendant tout le déploiement →
     « Disponibilité pendant le déploiement : N/N requêtes OK » dans le résumé du run, échecs horodatés dans le log ;
   - vérification HTTPS finale (12 essais, timeouts courts, simple avertissement si échec).

**Secrets du dépôt** : `VPS_HOST`, `VPS_SSH_KEY` (clé privée *entière*, lignes BEGIN/END comprises)
— ou `VPS_PASSWORD` ; optionnels `VPS_USER` (root par défaut, sinon sudo sans mot de passe), `VPS_PORT`.
Domaine et port dans `env:` du workflow. `concurrency` : un seul déploiement à la fois.

**Retour arrière** : `git revert` + push (ou relancer un ancien run vert). Restaurer des données :

```bash
systemctl stop 'iodej@*' && cd /tmp && tar xzf /home/iodej/backups/iodej-<date>.tar.gz \
 && rm -f /home/iodej/data/iodej.sqlite3-* && cp iodej.sqlite3 /home/iodej/data/ && cp -a uploads /home/iodej/data/ \
 && chown -R iodej: /home/iodej/data && systemctl start iodej@8000 iodej@8001
```

**Premier déploiement d'un nouveau projet** : DNS → clé SSH dédiée (`ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""`,
`.pub` dans `authorized_keys`, privée dans le secret) → secrets → push. Rien à installer à la main sur le VPS.

## 8. Garde-fous (appris en production)

- Un `dev.sh` oublié ou un **nginx** d'un ancien projet occupe le port → le script échoue et nomme le coupable.
- Ne jamais croire un `/healthz` local sans vérifier **quel processus** répond (cgroup de l'unité).
- Sans mise hors trafic, un redémarrage perd encore ~1 requête sur 30 (Caddy route vers l'instance qui s'arrête) ;
  avec : 0 sur 3 700 en test local. La santé « load balancer » doit être distincte de la santé publique.
- Tous les `curl` de CI ont `--connect-timeout`/`-m` ; chaque étape a un `timeout-minutes`.
- Codes et secrets jamais dans les logs de CI ; pas de mot de passe root dans les secrets si une clé suffit.
- Migrations testées sur une copie de l'ancien schéma avant de pousser.
- Changement d'un secret applicatif (code d'accès) = action explicite dans l'admin, jamais automatique.

## 9. Différences avec Blake Crosley (« No-Build Manifesto »)

Même cœur (FastAPI + Jinja2 + HTMX + Alpine, zéro build, ~40 s du push à la prod, assets versionnés par hash
et cache immuable, scripts `defer`, vendor/ local). Différences assumées :

| | Lui | Nous |
|---|---|---|
| Hébergement | Railway (PaaS) + Cloudflare CDN | VPS + Caddy + systemd, multi-projets, 2 instances |
| Paquets | pip + requirements.txt | uv + uv.lock |
| CSS | Bootstrap 5 + CSS maison | CSS maison seul |
| Données | contenu Markdown (+ D1) | SQLite applicatif + uploads, migrations maison |
| Perf | Lighthouse 100, CSS critique, preload/Early Hints, images srcset | non visé (appli interne, PWA) |
| Sécurité | CSP stricte, CSRF HMAC, rate limiting, nh3 | en-têtes de base ; pas de CSP (Alpine), pas de CSRF/rate limit (appli entre collègues) |
| En plus chez nous | — | PWA, Web Push, tâches planifiées, sonde de disponibilité, sauvegardes auto |

À reprendre si le projet est public : CSRF (token HMAC sans session), rate limiting sur la connexion,
`app.router.max_body_size`, CSP.

## 10. Checklist nouveau projet

```
[ ] uv init ; dépendances : fastapi uvicorn[standard] jinja2 python-multipart (+ pillow, pywebpush si besoin)
[ ] copier app/{main,config,db,web,auth,cli}.py, templates/base.html, static/{vendor,fonts,js/sw.js}, scripts/, deploy.yml
[ ] renommer iodej → <p>, IODEJ_ → <P>_, domaine et port dans deploy.yml (port libre : 8010, 8020…)
[ ] /healthz, robots.txt, static() partout, tests (conftest DB temporaire) verts
[ ] icônes PWA + manifest ; écran testé en viewport mobile (Playwright)
[ ] DNS, secrets VPS_*, push → vérifier « N/N requêtes OK » dans le résumé du run
```

## 11. Commandes utiles (sur le VPS)

```bash
systemctl status 'iodej@*'                # instances
journalctl -u 'iodej@*' -f                # logs
systemctl list-timers 'iodej-*'           # tâches planifiées
sudo -u iodej -H bash -c 'cd ~/app && IODEJ_DATA_DIR=~/data ~/.local/bin/uv run iodej codes'
ls /etc/caddy/sites/ && journalctl -u caddy -n 50
```
