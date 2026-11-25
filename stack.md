# stack.md — boilerplate FastAPI + HTMX, sans place au doute

> **Mode d'emploi**
> 1. Copier ce fichier dans un dépôt vide et remplir la **fiche projet** (§1).
> 2. Dire à l'agent : *« Applique stack.md à la lettre. »*
> 3. `uv run dev` pour travailler, `git push` pour mettre en ligne.
>
> **Pour l'agent** : ce document fait autorité. En cas de doute, applique la **décision par défaut** (§9) sans
> demander. N'ajoute **rien** qui n'est pas listé ici (pas de npm, de Node, d'ORM, de Docker, de framework JS,
> de lib « au cas où »). Moins de code = mieux. Le dépôt de référence est `eliottbourrigan/iodej` : quand un
> fichier est marqué *« copier depuis iodej »*, copie-le puis renomme `iodej`/`IODEJ_` (§1).

---

## 1. Fiche projet (à remplir — tout le reste en découle)

| Clé | Valeur | Exemple |
|---|---|---|
| Nom (minuscules, sans espace) = `<p>` | | `iodej` |
| Préfixe des variables d'env = `<P>_` | | `IODEJ_` |
| Domaine | | `iodej.ebgn.fr` |
| Port de base (2 instances : port et port+1) | | `8000` (suivant : 8010, 8020…) |
| Fuseau | `Europe/Paris` | |
| Langue de l'interface | `fr` | |
| Public ou interne ? | interne | interne → §9 « auth légère » ; public → §9 « sécurité public » |
| Entités (nom : champs) | | `restaurant : nom, description, photo, actif` |
| Écrans (URL : ce qu'on y fait) | | `/swipe : voter oui/non sur 10 cartes` |
| Back-office admin ? | oui | CRUD des entités, code admin |
| Tâches planifiées (quand : quoi) | aucune | `lun-ven 11:30 : notification` |
| PWA / notifications push ? | PWA oui, push non | |
| Brief design (3 adjectifs + 1 référence) | | `ludique, coloré, contours épais — jeu mobile Supercell` |

---

## 2. Règles non négociables

1. **Le serveur rend du HTML.** Les interactions passent par HTMX (fragments). JSON uniquement pour les 2-3 appels faits
   en JS pur (ex. abonnement push).
2. **Rien à installer hors `uv`.** Aucun `package.json`, aucun Node. Tailwind = binaire autonome via `pytailwindcss`.
3. **Monolithe** : un package `app/`, SQLite, fichiers sur disque. Pas de Redis, pas de file de tâches, pas de Docker.
4. **Tout est local** : htmx, Alpine, polices dans `app/static/vendor|fonts/`. Aucun CDN.
5. **Données hors du code** (`<P>_DATA_DIR`). Migrations **additives** uniquement. Un déploiement ne touche jamais aux données.
6. **Mobile d'abord.** Chaque écran est conçu et vérifié en 390 × 844 avant le desktop.
7. **Une tâche = une commande `uv run …`**, identique sous Windows, macOS, Linux.
8. **Chaque route a un test.** `uv run check` doit être vert avant tout push.

---

## 3. Briques (versions minimales)

| Rôle | Choix |
|---|---|
| Python | 3.11+ (géré par **uv** : `uv.lock` commité, `uv sync --frozen`) |
| Web | `fastapi` · `uvicorn[standard]` · `jinja2` · `python-multipart` |
| Front | **HTMX 2** + **Alpine.js 3** (fichiers `.min.js` vendorisés) · **Tailwind CSS v4** (`pytailwindcss`, dev) |
| Données | SQLite via `sqlite3` standard (WAL, clés étrangères), pas d'ORM |
| Images (si upload) | `pillow` → WebP ≤ 1000 px |
| Push (si besoin) | `pywebpush` |
| Tests | `pytest` + `httpx` (TestClient) · Playwright pour la vérification visuelle |
| Serveur | VPS Ubuntu · Caddy · systemd |
| CI/CD | GitHub Actions |

Récupérer les fichiers vendorisés une fois (pas de npm requis, `npm pack` est une simple alternative de téléchargement) :
`https://unpkg.com/htmx.org@2/dist/htmx.min.js`, `https://unpkg.com/alpinejs@3/dist/cdn.min.js` → `app/static/vendor/`.

---

## 4. Commandes (toutes via uv, multiplateformes)

| Commande | Effet |
|---|---|
| `uv sync` | installe tout (une fois, puis à chaque changement de dépendances) |
| `uv run dev` | Tailwind en mode watch + serveur avec rechargement sur `http://localhost:8000` |
| `uv run css` | CSS de production minifié (`app/static/css/app.css`) |
| `uv run test` | tests (arguments passés à pytest : `uv run test -k swipe`) |
| `uv run check` | css + tests — **exactement ce que lance la CI** |
| `uv run <p> init` / `seed` / `serve` … | CLI applicative (§5, `app/cli.py`) |
| `uv add <pkg>` / `uv add --dev <pkg>` | ajouter une dépendance (jamais `pip`) |

`pyproject.toml` :

```toml
[project]
name = "<p>"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["fastapi>=0.115", "uvicorn[standard]>=0.32", "jinja2>=3.1", "python-multipart>=0.0.12"]

[project.scripts]
<p>   = "app.cli:main"     # CLI de prod (serve, init, seed…)
dev   = "app.tasks:dev"
css   = "app.tasks:css"
test  = "app.tasks:test"
check = "app.tasks:check"

[dependency-groups]
dev = ["pytest>=8", "httpx>=0.27", "pytailwindcss>=0.2"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`app/tasks.py` (testé : build, watch, tests, arrêt propre par Ctrl+C ou SIGTERM) :

```python
"""Tâches de dev, identiques sous Linux, macOS et Windows : uv run dev | css | test | check."""
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS_IN = ROOT / "app/static/css/input.css"
CSS_OUT = ROOT / "app/static/css/app.css"


def _tailwind(*args: str) -> list[str]:
    import pytailwindcss  # dépendance de dev : binaire Tailwind autonome, sans Node

    path = pytailwindcss.get_bin_path()
    if not Path(path).exists():
        pytailwindcss.install()
    return [str(path), "-i", str(CSS_IN), "-o", str(CSS_OUT), *args]


def css() -> None:
    sys.exit(subprocess.call(_tailwind("--minify"), cwd=ROOT))


def test() -> None:
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", *sys.argv[1:]], cwd=ROOT))


def check() -> None:
    for cmd in (_tailwind("--minify"), [sys.executable, "-m", "pytest", "-q"]):
        if code := subprocess.call(cmd, cwd=ROOT):
            sys.exit(code)


def _stop(*_):
    raise KeyboardInterrupt


def dev() -> None:
    port = os.environ.get("PORT", "8000")
    subprocess.call(_tailwind(), cwd=ROOT)  # premier build avant de servir
    procs = [
        subprocess.Popen(_tailwind("--watch=always"), cwd=ROOT),
        subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--reload",
                          "--host", "0.0.0.0", "--port", port], cwd=ROOT),
    ]
    print(f"\n  → http://localhost:{port}   (Ctrl+C pour arrêter)\n", flush=True)
    signal.signal(signal.SIGTERM, _stop)
    try:
        procs[1].wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
```

Les scripts **serveur** (`scripts/*.sh`) restent en bash : ils ne tournent que sur le VPS Linux, lancés par la CI.
Le poste de dev (Windows compris) n'en exécute aucun.

---

## 5. Arborescence (exhaustive)

```
pyproject.toml  uv.lock  .gitignore  README.md  stack.md  CLAUDE.md
app/
  __init__.py
  config.py        ← variables <P>_* + défauts                                (copier depuis iodej)
  db.py            ← SCHEMA, _migrate(), settings, get_db(), transaction()   (copier, vider SCHEMA)
  web.py           ← templates, static() versionné, render(), filtres        (copier)
  auth.py          ← cookies, require_user / require_admin                   (copier si auth)
  main.py          ← app, montages, en-têtes cache/sécurité, /healthz(/lb)   (copier)
  cli.py           ← <p> serve | init | seed …                               (copier, adapter)
  tasks.py         ← §4
  routes/          ← un fichier par zone : public.py, admin.py …
  templates/       ← base.html, layout.html, macros.html, <écran>.html, partials/_<bloc>.html, admin/
  static/
    css/input.css  ← source Tailwind (§7) — app.css est GÉNÉRÉ (gitignoré)
    js/app.js      ← utilitaires globaux + composants Alpine (window.foo = () => ({…}))
    js/sw.js       ← service worker (copier)
    vendor/        ← htmx.min.js, alpine.min.js
    fonts/         ← woff2 + licence
    icons/         ← icon-192/512, icon-maskable-512, apple-touch-icon (180)
    manifest.webmanifest
scripts/           ← install.sh, remote-deploy.sh, backup.sh                 (copier tels quels)
tests/             ← conftest.py (DB temporaire), test_<zone>.py, test_migration.py
.github/workflows/deploy.yml                                                 (copier, §11)
```

`.gitignore` : `__pycache__/ .venv/ .pytest_cache/ data/ backups/ app/static/css/app.css`

---

## 6. Backend — patrons à suivre

- **Config** : `config.py` lit `os.environ.get("<P>_X", défaut)`. Aucune autre source de config.
- **Base** : une connexion par requête (`conn=Depends(db.get_db)`), `row_factory=sqlite3.Row`, requêtes paramétrées
  `?` uniquement. Écritures multiples → `with db.transaction(conn):`.
- **Schéma** : `SCHEMA` = `CREATE TABLE IF NOT EXISTS …`. Évolution = ajouter dans `_migrate()` :
  `ALTER TABLE … ADD COLUMN` si absente (`PRAGMA table_info`), `INSERT` si ligne absente. Jamais `DROP`/`RENAME`.
  Toute migration a un test qui part de l'ancien schéma.
- **Types** : id `INTEGER PRIMARY KEY AUTOINCREMENT` · dates `TEXT` ISO (`YYYY-MM-DD`, `datetime('now')`) ·
  booléens `INTEGER 0/1` · argent en centimes `INTEGER` · JSON en `TEXT`.
- **Trois sortes de routes** :

```python
@router.get("/swipe")                       # page complète
def page(request: Request, conn=Depends(db.get_db), user=Depends(require_user)):
    return render(request, "swipe.html", user=user, items=...)

@router.get("/partials/choix")              # fragment HTMX (même gabarit que la page, sans layout)
def partial(request: Request, conn=Depends(db.get_db), user=Depends(require_user)):
    return render(request, "partials/choix.html", rows=...)

@router.post("/items/save")                 # formulaire : valider → re-rendre avec erreur OU rediriger (303)
def save(request: Request, name: str = Form(""), conn=Depends(db.get_db)):
    if not name.strip():
        return render(request, "form.html", status_code=400, error="Le nom est obligatoire.")
    conn.execute("INSERT INTO items(name) VALUES (?)", (name.strip(),))
    return RedirectResponse("/items", status_code=303)
```

- **Auth refusée** : exception `LoginRequired` → handler : `HX-Redirect` si requête HTMX, 303 sinon, 401 sur `/api/*`.
- **État calculé à l'appel** (« du jour », « en retard »…) plutôt que par une tâche planifiée.
- **Secrets applicatifs** (codes, clés VAPID) : générés au premier `init`, stockés dans `settings`, jamais imprimés hors
  terminal interactif.
- **Santé** : `/healthz` → `{"ok": true}` toujours ; `/healthz/lb` → 503 si `DATA_DIR/drain-<PORT>` existe.

---

## 7. Front — patrons à suivre

**`app/static/css/input.css`** (Tailwind v4, aucune config JS) :

```css
@import "tailwindcss";
@source "../../templates";
@source "../js";

@font-face { font-family: "Display"; src: url("../fonts/display.woff2") format("woff2"); font-display: swap; }

@theme {                       /* = design tokens : seule source des couleurs, polices, rayons */
  --color-ink: #1a1238;
  --color-brand: #7b5cff;
  --color-accent: #ffc933;
  --font-display: "Display", system-ui, sans-serif;
  --radius-card: 6px;
}

@layer components {            /* uniquement pour ce qui se répète ≥ 3 fois */
  .btn { @apply inline-flex items-center justify-center gap-2 px-5 min-h-12 font-display
                rounded-card border-3 border-ink bg-accent active:translate-y-1; }
  .card { @apply bg-white border-3 border-ink rounded-card shadow-[0_6px_0_var(--color-ink)] p-4; }
}
```

Règles CSS : classes utilitaires dans les templates ; `@layer components` pour les motifs répétés ; animations dans
`input.css` (`@keyframes`) ; toujours `motion-safe:` / `prefers-reduced-motion`. Jamais de style inline.

**`<head>` de `base.html`** (ordre imposé) :

```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="{{ static('icons/apple-touch-icon.png') }}">
<link rel="stylesheet" href="{{ static('css/app.css') }}">
<script src="{{ static('vendor/htmx.min.js') }}" defer></script>
<script src="{{ static('js/app.js') }}" defer></script>          <!-- avant Alpine : définit les composants -->
<script src="{{ static('vendor/alpine.min.js') }}" defer></script>
```

**Qui fait quoi** :

| Besoin | Outil |
|---|---|
| Données du serveur (liste, formulaire, recherche, onglets) | HTMX |
| État purement local (menu ouvert, popup, aperçu d'image) | Alpine (`x-data`, `x-show`) |
| Geste ou calcul lourd (swipe, canvas, drag) | JS natif dans `app.js`, IIFE |

**Patrons HTMX** (n'en inventer aucun autre) :

| Cas | Attributs |
|---|---|
| Onglets / navigation partielle | `hx-get="/partials/x" hx-target="#panel" hx-push-url="/page?tab=x"` |
| Rafraîchissement auto | `hx-get="/partials/x?refresh=1" hx-trigger="every 20s" hx-target="#panel"` |
| Recherche | `hx-get="/search" hx-trigger="input changed delay:300ms" hx-target="#results"` |
| Action sur un élément | `hx-post="/api/x" hx-vals='{"id": 3}' hx-target="#panel"` |
| Formulaire avec erreurs | `hx-post` + `hx-target="this" hx-swap="outerHTML"` (le serveur renvoie le formulaire) |
| Chargement | `hx-indicator="#loader"` + `.htmx-request` en CSS |

- **Assets** : toujours `{{ static('chemin') }}` → `?v=<md5 du fichier>` ; servis avec `Cache-Control: immutable` 1 an.
- **États obligatoires de chaque écran** : vide, chargement, erreur (toast), succès.
- **PWA** : manifest + icônes + `sw.js` (cache uniquement l'immuable) + encart d'installation selon l'OS (copier d'iodej).

---

## 8. Design

- Le design part du **brief** de la fiche projet et passe par le skill **frontend-design** (§12) *avant* d'écrire les
  templates : il produit les tokens (`@theme`), les composants (`.btn`, `.card`, …) et un écran de référence.
- Tokens uniquement dans `@theme`. Une couleur ou un rayon en dur dans un template = erreur.
- Vérification : capture Playwright à 390 × 844 (et 1280 × 800) de chaque écran, regardée avant de valider.

---

## 9. Décisions par défaut (appliquer sans demander)

| Sujet | Décision |
|---|---|
| Auth interne | prénom dans une liste + **code partagé** de 6 caractères `[A-HJ-NP-Z2-9]`, cookie 10 ans contenant le hash du code ; admin = second code long |
| Sécurité si public | + jeton CSRF HMAC sur les POST, limite de 10 essais de connexion / 15 min par IP, `app.router.max_body_size`, CSP |
| Identifiants | entiers auto-incrémentés, jamais exposés comme secret |
| Dates | stockées en ISO, affichées en français (« Aujourd'hui », « Lundi 24 nov. ») |
| Fuseau | `<P>_TZ`, tout calcul de jour via `datetime.now(TZ)` |
| Formulaires | validation serveur, re-rendu avec message, `303` après succès |
| Suppression | confirmation `hx-confirm`/`confirm()`, suppression réelle (pas de corbeille) |
| Listes longues | bouton « Voir plus » (`hx-get ?page=n`, `hx-swap="beforeend"`) ; pas de pagination numérotée |
| Images | upload → Pillow → WebP ≤ 1000 px, nom `uuid4().hex`, dans `DATA_DIR/uploads` |
| Textes | interface dans la langue de la fiche, tutoiement si interne |
| Erreurs | toast pour HTMX, page simple pour le reste ; jamais de trace serveur affichée |
| Temps réel | rafraîchissement HTMX toutes les 20 s ; pas de WebSocket |
| Tâches planifiées | timer systemd → `uv run <p> <commande>` |
| Indexation | interne → `robots.txt Disallow: /` + `X-Robots-Tag: noindex` |
| Logs | stdout (journald) ; pas de fichier de log |

---

## 10. Tests

- `tests/conftest.py` : fixture `client` qui redirige `config.DATA_DIR`/`DB_PATH` vers `tmp_path` (copier d'iodej).
- Par route : un test « nominal » + un test « refus » (non connecté, mauvais formulaire).
- Toute logique pure (calculs, algorithmes) : tests unitaires sans HTTP.
- `test_migration.py` : crée l'ancien schéma, lance `init()`, vérifie que rien n'est perdu.
- Pas de mocks sauf pour les appels réseau sortants (push, API externes).

---

## 11. Serveur et déploiement

**Un VPS, plusieurs projets**

```
DNS   *.domaine.fr  A → IP du VPS                       (joker : rien à refaire par projet)
Caddy /etc/caddy/Caddyfile = "import sites/*.caddy"     (un fichier par projet, généré)
<p>   utilisateur Linux <p> · code /home/<p>/app · données /home/<p>/data · sauvegardes /home/<p>/backups
      instances <p>@PORT et <p>@PORT+1 (127.0.0.1) · timers <p>-*.timer
```

`install.sh` (copier depuis iodej, ne pas réécrire) génère : unité modèle `<p>@.service`, timers, site Caddy à deux
upstreams (`lb_policy first`, `health_uri /healthz/lb`, `lb_try_duration 15s`), et fait le **redémarrage progressif** :
pour chaque instance → mise hors trafic 5 s (`drain-<port>`) → arrêt → contrôle du port → démarrage → attente de
`/healthz` servi *par cette unité* → suivante. Il échoue en nommant le coupable si un port est pris (nginx, dev oublié).

**Pipeline** (`git push` sur la branche par défaut → ~40 s, sans coupure)

```yaml
# deploy.yml — différences avec iodej pour Tailwind :
test:   … - run: uv sync --frozen
          - run: uv run check                 # construit le CSS puis teste
deploy: … - uses: astral-sh/setup-uv@v6
          - run: uv sync --frozen && uv run css   # app.css construit en CI, envoyé avec le code
          - (Préparer SSH / Envoyer le code / Installer / Sonde / Vérifier : identiques à iodej)
env:    DOMAIN: <domaine>   APP_PORT: "<port>"
```

- Le serveur n'installe jamais les dépendances de dev (`--no-dev`) : il reçoit le CSS déjà construit.
- **Sonde** : une requête toutes les 200 ms pendant le déploiement → « Disponibilité : N/N » dans le résumé du run.
- **Secrets du dépôt** : `VPS_HOST`, `VPS_SSH_KEY` (clé privée complète, lignes BEGIN/END incluses). Optionnels :
  `VPS_USER` (root par défaut), `VPS_PORT`.
- **Premier déploiement** : enregistrement DNS (une fois pour le joker) → clé dédiée sur le VPS
  (`ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""`, `.pub` dans `authorized_keys`, privée dans le secret) → push.
- **Retour arrière** : `git revert` + push. **Restauration** : arrêter `'<p>@*'`, extraire
  `/home/<p>/backups/<p>-<date>.tar.gz` dans `data/` (supprimer `*.sqlite3-wal/-shm`), `chown`, redémarrer.

---

## 12. Développement assisté par IA

**Skills à installer** (dans Claude Code) :

| Skill | Rôle | Installation |
|---|---|---|
| **ponytail** (communautaire, D. Gebert) | pousse l'agent à écrire moins de code ; `/ponytail-review` pour élaguer | `/plugin marketplace add DietrichGebert/ponytail` puis `/plugin install ponytail@ponytail` |
| **frontend-design** (Anthropic, officiel) | direction visuelle, tokens, composants à partir du brief | `/plugin install frontend-design@claude-plugins-official` |
| `/code-review`, `/simplify`, `/security-review` (intégrés) | relecture avant push | — |

Gains mesurés de ponytail : environ −15 % de code en test indépendant (JetBrains), plus que ce qu'annonce l'auteur ;
utile surtout là où l'agent sur-construit. Vérifier les commandes d'installation sur la page du plugin, elles évoluent.

**`CLAUDE.md`** à la racine (à copier tel quel) :

```markdown
Ce projet suit stack.md à la lettre : le relire avant toute tâche. Décisions par défaut : stack.md §9.
- Utiliser le skill ponytail pour tout code ; frontend-design pour tout travail visuel.
- Avant de conclure : `uv run check` vert + captures Playwright 390×844 des écrans touchés, regardées.
- Ne jamais ajouter de dépendance, de fichier de config ou d'outil absent de stack.md sans le demander.
```

**Boucle par fonctionnalité** : décrire l'écran (URL + action) → l'agent écrit test, route, template → `uv run check`
→ capture mobile → `/ponytail-review` → push. Une fonctionnalité = un commit.

---

## 13. Garde-fous (appris en production)

- Un serveur de dev oublié ou le nginx d'un ancien projet sur le port → `install.sh` échoue et le nomme : l'arrêter.
- Ne jamais croire un `/healthz` sans savoir **quel processus** répond (contrôle du cgroup de l'unité).
- Santé du load balancer (`/healthz/lb`) distincte de la santé publique (`/healthz`), sinon la sonde se trompe.
- Sans mise hors trafic : ~1 requête perdue sur 30 par déploiement ; avec : 0 sur 3 700 en test local derrière Caddy,
  41/41 en production.
- Tous les `curl` de CI ont `--connect-timeout`/`-m` ; chaque étape a un `timeout-minutes`.
- Clé SSH collée sans ses lignes BEGIN/END = « error in libcrypto ».
- Changer un code d'accès = action explicite dans l'admin, jamais automatique.

---

## 14. Vérification finale (checklist de l'agent)

```
[ ] fiche projet remplie ; noms <p>/<P>_ partout ; CLAUDE.md présent
[ ] uv sync ; uv run check vert ; uv run dev affiche l'écran d'accueil
[ ] chaque écran : états vide / chargement / erreur / succès ; capture 390×844 regardée
[ ] /healthz, /healthz/lb, robots.txt, manifest + icônes, static() partout, aucun CDN, aucun style inline
[ ] test de migration présent ; data/ et app.css gitignorés
[ ] deploy.yml : DOMAIN, APP_PORT, étape `uv run css` ; secrets VPS_* posés ; DNS OK
[ ] premier push : run vert, « Disponibilité N/N », site accessible en HTTPS
```

---

*Écarts connus avec le dépôt iodej (pas encore migré) : CSS écrit à la main au lieu de Tailwind, `scripts/dev.sh`
au lieu de `uv run dev`, pas de `CLAUDE.md`. Le reste (serveur, déploiement sans coupure, PWA, push) est à jour.*
