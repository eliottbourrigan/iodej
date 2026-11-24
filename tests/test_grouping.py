from app.grouping import make_groups


def sizes(groups):
    return sorted(g.size for g in groups)


def test_prefers_2_3_over_4_1():
    # A,B,C,D aiment R1 ; E n'aime que R2 ; C et D aiment aussi R2.
    likes = {1: {10}, 2: {10}, 3: {10, 20}, 4: {10, 20}, 5: {20}}
    assert sizes(make_groups(likes)) == [2, 3]


def test_single_big_group_when_possible():
    likes = {1: {10, 20}, 2: {10, 30}, 3: {10}, 4: {10, 20}}
    groups = make_groups(likes)
    assert len(groups) == 1 and groups[0].restaurant_id == 10 and groups[0].size == 4


def test_everyone_assigned_to_a_liked_restaurant():
    likes = {1: {10}, 2: {20}, 3: {10, 20, 30}, 4: {30}, 5: {30, 10}}
    groups = make_groups(likes)
    seen = set()
    for g in groups:
        for u in g.user_ids:
            assert g.restaurant_id in likes[u]
            seen.add(u)
    assert seen == set(likes)


def test_users_without_likes_are_ignored():
    assert make_groups({1: set(), 2: set()}) == []
    assert sizes(make_groups({1: set(), 2: {10}})) == [1]


def test_large_input_uses_heuristic_and_stays_valid():
    import random

    rng = random.Random(1)
    likes = {u: set(rng.sample(range(10), rng.randint(2, 6))) for u in range(40)}
    groups = make_groups(likes, seed="2026-01-01")
    assert sum(g.size for g in groups) == 40
    for g in groups:
        assert all(g.restaurant_id in likes[u] for u in g.user_ids)
    # Déterministe pour une même graine.
    assert [(g.restaurant_id, g.user_ids) for g in groups] == \
        [(g.restaurant_id, g.user_ids) for g in make_groups(likes, seed="2026-01-01")]
