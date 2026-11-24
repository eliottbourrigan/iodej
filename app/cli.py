"""Ligne de commande : `uv run iodej <commande>`."""
import argparse
import os

from . import codes, daily, db

DEMO_RESTAURANTS = [
    ("Le Bistrot du Coin", "Plat du jour maison, terrasse au soleil."),
    ("Sushi Shop", "Makis, sashimis et bento rapides."),
    ("Pizza Napoli", "Pâte fine, four à bois, burrata généreuse."),
    ("Burger Factory", "Smash burgers et frites maison."),
    ("Le Thaï", "Pad thaï, curry vert, bobun."),
    ("Taco Loco", "Tacos, burritos et nachos qui piquent."),
    ("La Crêperie", "Galettes complètes et crêpes caramel beurre salé."),
    ("Green Bowl", "Salades et bowls healthy à composer."),
    ("Chez Mario", "Pâtes fraîches et tiramisu de la nonna."),
    ("Le Kebab d'Or", "Le classique galette-frites, efficace."),
    ("Ramen Ya", "Bouillons tonkotsu, gyozas croustillants."),
    ("La Cantine Libanaise", "Mezzés, falafels, chawarma."),
]
DEMO_USERS = [
    ("Alice", "Team salade"), ("Bastien", "Toujours partant pour un burger"),
    ("Chloé", "Végétarienne"), ("David", "Fan de sushis"), ("Emma", "Mange épicé"),
    ("Farid", "Le roi du kebab"),
]


def cmd_serve(args):
    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload,
                proxy_headers=True, forwarded_allow_ips="*")


def cmd_codes(_args):
    db.init()
    conn = db.connect()
    print(f"Code collègues : {db.get_setting(conn, 'access_code')}")
    print(f"Code admin     : {db.get_setting(conn, 'admin_code')}")


def cmd_rotate(args):
    db.init()
    conn = db.connect()
    key = "access_code" if args.which == "access" else "admin_code"
    value = codes.generate_code(3 if args.which == "access" else 4)
    db.set_setting(conn, key, value)
    print(f"Nouveau code {'collègues' if args.which == 'access' else 'admin'} : {value}")


def cmd_seed(_args):
    db.init()
    conn = db.connect()
    if conn.execute("SELECT COUNT(*) FROM restaurants WHERE kind = 'restaurant'").fetchone()[0] == 0:
        conn.executemany("INSERT INTO restaurants(name, description) VALUES (?, ?)", DEMO_RESTAURANTS)
        print(f"{len(DEMO_RESTAURANTS)} restaurants de démo ajoutés.")
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.executemany("INSERT INTO users(name, description) VALUES (?, ?)", DEMO_USERS)
        print(f"{len(DEMO_USERS)} collègues de démo ajoutés.")


def cmd_reset_day(_args):
    db.init()
    daily.reset_day(db.connect())
    print("Tirage du jour réinitialisé.")


def main():
    p = argparse.ArgumentParser(prog="iodej", description="On mange où ?")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Lancer le serveur web")
    s.add_argument("--host", default=os.environ.get("IODEJ_HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("IODEJ_PORT", "8000")))
    s.add_argument("--reload", action="store_true", help="Rechargement auto (dev)")
    s.set_defaults(func=cmd_serve)

    sub.add_parser("codes", help="Afficher les codes d'accès").set_defaults(func=cmd_codes)

    r = sub.add_parser("rotate-code", help="Régénérer un code")
    r.add_argument("which", choices=["access", "admin"])
    r.set_defaults(func=cmd_rotate)

    sub.add_parser("seed", help="Ajouter des données de démo (si base vide)").set_defaults(func=cmd_seed)
    sub.add_parser("reset-day", help="Relancer le tirage du jour").set_defaults(func=cmd_reset_day)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
