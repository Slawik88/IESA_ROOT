"""Callback payloads for chat Mafia (prefixes are kept stable for buttons already in chats)."""
from aiogram.filters.callback_data import CallbackData


class MafiaLobbyCB(CallbackData, prefix="mf"):
    match_id: int
    action: str  # join | leave | settings | start | cancel


class MafiaSettingsCB(CallbackData, prefix="mfs"):
    match_id: int
    action: str  # menu/back/open_*/slots_*/role_*/vote_*/tempo_*/preset_*


class MafiaControlCB(CallbackData, prefix="mfc"):
    match_id: int
    action: str  # role | skip | stop_ask | stop_yes | stop_no | resume | cancel | again


class MafiaReadyCB(CallbackData, prefix="mfr"):
    action: str  # ready


class MafiaActionCB(CallbackData, prefix="mfa"):
    match_id: int
    phase_number: int
    action: str  # vote | mafia_target | doctor_save | detective_check
    target_user_id: int  # 0 means "nobody" (abstain) for votes


class MafiaRulesCB(CallbackData, prefix="mfh"):
    page: str  # intro | roles | flow | tips
