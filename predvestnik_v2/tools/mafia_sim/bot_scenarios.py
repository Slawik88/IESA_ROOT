"""Import every whole-bot scenario module so that it registers itself (tools/test_bot_scenarios_sim_pg.py)."""
from tools.mafia_sim import (  # noqa: F401
    scn_bot_business, scn_bot_callbacks, scn_bot_commands, scn_bot_dm_push, scn_bot_dm_social, scn_bot_dm_support, scn_bot_framework, scn_bot_membership, scn_bot_pass_race, scn_bot_payments,
    scn_bot_start,
    scn_bot_topics_limits)
