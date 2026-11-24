"""Constitution des groupes du midi.

Chaque collègue est envoyé dans un restaurant qu'il a validé ; tous ceux qui
vont au même restaurant forment un groupe.  On cherche la répartition dont les
groupes sont « les plus gros possibles » au sens suivant : on trie les tailles
de groupe par ordre croissant et on maximise lexicographiquement.

    2 + 3  >  4 + 1      (personne ne mange seul si on peut l'éviter)
    5      >  2 + 3      (un seul gros groupe, c'est encore mieux)
    2 + 6  >  2 + 3 + 3  (à plus petit groupe égal, on préfère les gros)

À score égal, on préfère les restaurants les plus plébiscités.
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from math import prod

EXACT_LIMIT = 100_000  # nombre max de combinaisons pour la recherche exhaustive
RESTARTS = 300


@dataclass
class Group:
    restaurant_id: int
    user_ids: list[int] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.user_ids)


def _score(assign: dict[int, int], popularity: Counter) -> tuple:
    sizes = Counter(assign.values())
    return (
        tuple(sorted(sizes.values())),
        sum(popularity[r] for r in sizes),
    )


def _better(a: tuple, b: tuple | None) -> bool:
    return b is None or a > b


def _exact(users: list[int], likes: dict[int, list[int]], popularity: Counter):
    best, best_score = None, None
    assign: dict[int, int] = {}

    def rec(i: int):
        nonlocal best, best_score
        if i == len(users):
            s = _score(assign, popularity)
            if _better(s, best_score):
                best, best_score = dict(assign), s
            return
        u = users[i]
        for r in likes[u]:
            assign[u] = r
            rec(i + 1)
        del assign[u]

    rec(0)
    return best


def _local_search(assign, likes, popularity):
    score = _score(assign, popularity)
    improved = True
    while improved:
        improved = False
        # 1) déplacer un collègue
        for u, opts in likes.items():
            current = assign[u]
            for r in opts:
                if r == current:
                    continue
                assign[u] = r
                s = _score(assign, popularity)
                if s > score:
                    score, current, improved = s, r, True
                else:
                    assign[u] = current
        # 2) fusionner un groupe entier dans un autre restaurant
        groups: dict[int, list[int]] = {}
        for u, r in assign.items():
            groups.setdefault(r, []).append(u)
        for r, members in groups.items():
            common = set.intersection(*(set(likes[u]) for u in members)) - {r}
            for target in common:
                trial = dict(assign)
                for u in members:
                    trial[u] = target
                s = _score(trial, popularity)
                if s > score:
                    assign, score, improved = trial, s, True
                    break
            if improved:
                break
    return assign, score


def _heuristic(users, likes, popularity, seed):
    rng = random.Random(seed)
    best, best_score = None, None
    for attempt in range(RESTARTS):
        unassigned = set(users)
        assign: dict[int, int] = {}
        while unassigned:
            counts = Counter(r for u in unassigned for r in likes[u])
            if attempt == 0:
                r = max(counts, key=lambda k: (counts[k], popularity[k], -k))
            else:
                r = max(counts, key=lambda k: counts[k] + rng.random() * 1.5)
            for u in [u for u in unassigned if r in likes[u]]:
                assign[u] = r
                unassigned.discard(u)
        assign, s = _local_search(assign, likes, popularity)
        if _better(s, best_score):
            best, best_score = assign, s
    return best


def make_groups(likes_by_user: dict[int, set[int] | list[int]], seed: int | str = 0) -> list[Group]:
    """`likes_by_user` : {user_id: restaurants validés}. Les collègues sans
    aucun restaurant validé sont ignorés."""
    likes = {u: sorted(set(rs)) for u, rs in likes_by_user.items() if rs}
    if not likes:
        return []
    popularity = Counter(r for rs in likes.values() for r in rs)
    # Les plus contraints d'abord : élague mieux et stabilise le résultat.
    users = sorted(likes, key=lambda u: (len(likes[u]), u))

    if prod(len(likes[u]) for u in users) <= EXACT_LIMIT:
        assign = _exact(users, likes, popularity)
    else:
        assign = _heuristic(users, likes, popularity, seed)

    groups: dict[int, Group] = {}
    for u in sorted(assign):
        groups.setdefault(assign[u], Group(assign[u])).user_ids.append(u)
    return sorted(groups.values(), key=lambda g: (-g.size, -popularity[g.restaurant_id], g.restaurant_id))
