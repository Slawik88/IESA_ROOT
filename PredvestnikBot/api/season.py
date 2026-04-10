"""
Season Pass API endpoints.
"""
from aiohttp import web
from database.db import (
    get_active_season,
    get_season_progress, 
    get_season_rewards,
    claim_season_reward,
    buy_season_premium
)


async def season_data(request):
    """GET /api/season/data?user_id=X — get season info and user progress."""
    try:
        user_id_str = request.query.get("user_id")
        if not user_id_str or not user_id_str.isdigit():
            return web.json_response({"error": "user_id required"}, status=400)
        
        user_id = int(user_id_str)
        
        # Get active season
        season = await get_active_season()
        if not season:
            return web.json_response({"error": "No active season"}, status=404)
        
        season_id = season["id"]
        
        # Get user progress
        progress = await get_season_progress(user_id, season_id)
        
        # Get rewards
        rewards = await get_season_rewards(season_id)
        
        return web.json_response({
            "season": {
                "id": season["id"],
                "name": season["name"],
                "start_date": season["start_date"].isoformat() if season["start_date"] else None,
                "end_date": season["end_date"].isoformat() if season["end_date"] else None,
                "active": season["active"]
            },
            "progress": progress,
            "rewards": rewards
        })
        
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def claim_reward(request):
    """POST /api/season/claim {user_id, season_id, level, is_premium} — claim reward."""
    try:
        data = await request.json()
        
        user_id = int(data.get("user_id", 0))
        season_id = int(data.get("season_id", 0))
        level = int(data.get("level", 0))
        is_premium = bool(data.get("is_premium", False))
        
        if not all([user_id, season_id, level]):
            return web.json_response({"error": "user_id, season_id, and level required"}, status=400)
        
        result = await claim_season_reward(user_id, season_id, level, is_premium)
        
        if result["ok"]:
            return web.json_response(result)
        else:
            return web.json_response(result, status=400)
            
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def buy_premium(request):
    """POST /api/season/premium {user_id, season_id} — buy premium pass."""
    try:
        data = await request.json()
        
        user_id = int(data.get("user_id", 0))
        season_id = int(data.get("season_id", 0))
        
        if not all([user_id, season_id]):
            return web.json_response({"error": "user_id and season_id required"}, status=400)
        
        success = await buy_season_premium(user_id, season_id)
        
        if success:
            return web.json_response({"ok": True})
        else:
            return web.json_response({"error": "Purchase failed"}, status=400)
            
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)