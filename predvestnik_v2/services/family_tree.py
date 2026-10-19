"""Self-rooted family view. Clients cannot pivot to unrelated people's trees."""
from infrastructure.repositories import family_tree as repo


async def own_tree(db, *, user_id: int) -> dict:
    data = await repo.graph(db, user_id)
    from services.appearance_public_v3 import nick_styles
    looks = await nick_styles(db, list(data["nodes"]))
    from services.skins_v3 import own_look
    looks[user_id] = await own_look(db, user_id)
    refs = {uid: f"n{i}" for i, uid in enumerate(data["nodes"])}
    return {"root": refs[user_id],
            "nodes": [{"id": refs[uid], "depth": depth, "self": uid == user_id, "look": looks.get(uid),
                       **data["labels"].get(uid, {"name": "Участник", "profile_ref": None})}
                      for uid, depth in data["nodes"].items()],
            "edges": [{"source": refs[a], "target": refs[b], "kind": kind, "role": role}
                      for a, b, kind, role in data["edges"]],
            "truncated": data["truncated"], "max_depth": data["max_depth"], "max_nodes": data["max_nodes"],
            "notice": "Текущие родственные связи. Завершённые браки и выход из семьи не показываются. Кошельки и личные данные родственников не раскрываются."}
