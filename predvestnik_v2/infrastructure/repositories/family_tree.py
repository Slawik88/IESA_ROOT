"""Bounded active relationship graph; no family wallet or private profile data."""
MAX_NODES = 60
MAX_DEPTH = 3


async def graph(db, user_id: int) -> dict:
    nodes, edges, frontier, truncated = {int(user_id): 0}, set(), [int(user_id)], False
    for depth in range(MAX_DEPTH):
        if not frontier:
            break
        marks = ','.join('?' for _ in frontier)
        # The marriage registry is authoritative for active spouses.
        async with db.execute(
            f"SELECT m.user1_id,m.user2_id FROM marriages m "
            f"JOIN marriage_members a ON a.marriage_id=m.id AND a.user_id=m.user1_id "
            f"JOIN marriage_members b ON b.marriage_id=m.id AND b.user_id=m.user2_id "
            f"WHERE m.ended_at IS NULL AND (m.user1_id IN ({marks}) OR m.user2_id IN ({marks})) ORDER BY m.id LIMIT 181",
            (*frontier, *frontier)) as cursor:
            marriages = await cursor.fetchall()
        async with db.execute(
            f"SELECT m.user1_id,m.user2_id,c.user_id,c.role FROM family_children c JOIN marriages m ON m.id=c.marriage_id "
            f"WHERE c.left_at IS NULL AND m.ended_at IS NULL AND "
            f"(c.user_id IN ({marks}) OR m.user1_id IN ({marks}) OR m.user2_id IN ({marks})) ORDER BY c.created_at,c.id LIMIT 181",
            (*frontier, *frontier, *frontier)) as cursor:
            children = await cursor.fetchall()
        candidates = [(int(r[0]), int(r[1]), "spouse", "") for r in marriages]
        candidates += [(int(r[i]), int(r[2]), "parent", str(r[3] or "Ребёнок")[:40]) for r in children for i in (0, 1)]
        next_frontier = []
        truncated |= len(marriages) > 180 or len(children) > 180
        for source, target, kind, role in candidates:
            if source == target:
                continue
            for uid in (source, target):
                if uid not in nodes:
                    if len(nodes) >= MAX_NODES:
                        truncated = True
                        continue
                    nodes[uid] = depth + 1
                    next_frontier.append(uid)
            if source in nodes and target in nodes:
                edges.add((source, target, kind, role))
        frontier = next_frontier
    marks = ','.join('?' for _ in nodes)
    async with db.execute(f"SELECT u.user_tg_id,u.user_tg_username,r.profile_ref FROM users u "
                          f"LEFT JOIN public_profile_v1_refs r ON r.user_id=u.user_tg_id "
                          f"WHERE u.user_tg_id IN ({marks})", tuple(nodes)) as cursor:
        labels = {int(r[0]): {"name": str(r[1] or "Участник")[:80], "profile_ref": r[2]} for r in await cursor.fetchall()}
    return {"nodes": nodes, "labels": labels, "edges": sorted(edges), "truncated": truncated,
            "max_depth": MAX_DEPTH, "max_nodes": MAX_NODES}
