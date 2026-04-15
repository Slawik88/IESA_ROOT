from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve as _static_serve
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.views.generic.base import RedirectView, TemplateView
from django.templatetags.static import static as static_static
from django.http import FileResponse, JsonResponse
from pathlib import Path
from blog.sitemaps import sitemaps
from .protected_media_views import serve_protected_media
from core.admin_site import CustomAdminSite
from .miniapp_views import (
    miniapp_index, miniapp_user_data,
    miniapp_leaderboard, miniapp_checkin, miniapp_boss_damage,
    miniapp_marriage, miniapp_marriage_propose, miniapp_bonds, miniapp_equip,
    miniapp_dev_stats, miniapp_dev_setbalance,
    miniapp_dev_add_mora, miniapp_dev_add_xp, miniapp_dev_give_item, miniapp_dev_users,
    miniapp_dev_chats, miniapp_dev_chat_admins, miniapp_dev_banlist,
    miniapp_dev_logs, miniapp_dev_trigger_event, miniapp_dev_items,
    miniapp_dev_wallet_user,
    miniapp_dev_member_update, miniapp_dev_salary,
    miniapp_treasury,
    miniapp_treasury_payout,
    miniapp_family_deposit, miniapp_family_withdraw, miniapp_family_log, miniapp_divorce,
    miniapp_wallet_history,
    miniapp_inventory,
    miniapp_inventory_sell_junk,
    miniapp_gacha_roll,
    miniapp_gacha_free_roll,
    miniapp_gacha_free_rolls_count,
    miniapp_bonds_buy, miniapp_bonds_sell,
    miniapp_bank, miniapp_bank_deposit, miniapp_bank_withdraw,
    miniapp_pet_walk, miniapp_pet_feed,
    miniapp_shop_catalog, miniapp_shop_buy,
    miniapp_shop_set_title,
    miniapp_set_bio,
    miniapp_themes,
    miniapp_public_profile,
    miniapp_enhance_item,
    miniapp_consume_potion,
    miniapp_batch_sell,
    miniapp_couple_boss_status,
    miniapp_couple_boss_start,
    miniapp_couple_boss_attack,
    miniapp_get_avatar,  # ➕ Новая функция для аватарок
    miniapp_marriage_proposals_list,
    miniapp_marriage_respond,
    miniapp_solo_boss_status,
    miniapp_solo_boss_start,
    miniapp_solo_boss_attack,
    miniapp_solo_boss_forfeit,
    miniapp_quest,
    miniapp_quest_reroll,
    miniapp_spy,
    miniapp_members,
    miniapp_warnlist,
    miniapp_admin_chat_summary,
    miniapp_admin_roster,
    miniapp_transfer,
    miniapp_crystals_transfer,
    miniapp_loans,
    miniapp_loans_create,
    miniapp_loans_repay,
    miniapp_loans_respond,
    miniapp_loans_cancel,
    miniapp_casino_coin,
    miniapp_casino_lottery,
    miniapp_casino_roulette,
    miniapp_expeditions,
    miniapp_expeditions_start,
    miniapp_expeditions_collect,
    miniapp_expeditions_boost,
    miniapp_pets_rename,
    miniapp_cleanup_config,
    miniapp_cleanup_pass,
    miniapp_timezone,
    miniapp_chat_buff,
    miniapp_gifts_catalog,
    miniapp_gifts_send,
    miniapp_auction_list, miniapp_auction_create,
    miniapp_auction_bid, miniapp_auction_buyout, miniapp_auction_cancel,
    miniapp_achievements,
    miniapp_crystals_spend,
    miniapp_dev_give_crystals,
    miniapp_chat_banlist,
    miniapp_dev_error_logs,
    miniapp_frontend_error_log,
    miniapp_convert_crystals,  # Block 3
    miniapp_user_avatar,       # Block 3
    miniapp_season_data,
    miniapp_season_claim,
    miniapp_season_premium,
    miniapp_dev_af2_config,
    miniapp_dev_import_users,
    miniapp_dev_scan_members,
    miniapp_dev_purge_chat_nonmembers,
    miniapp_dev_user_inventory,
    miniapp_dev_delete_inventory_item,
    miniapp_dev_feature_toggle,
    miniapp_save_avatar,
    miniapp_use_transfer_pass,
    miniapp_shards,
    miniapp_shards_craft,
    miniapp_talents,
    miniapp_talents_upgrade,
    miniapp_newbie_quest,
    miniapp_settings_local,
    miniapp_settings_global,
    miniapp_chat_tags,
    miniapp_tag_definitions,
    miniapp_stars_invoice,
    miniapp_promo_activate,
    miniapp_promo_create,
    miniapp_promo_list,
    miniapp_promo_deactivate,
    miniapp_crystals_catalog,
    miniapp_megaphone_list,
    miniapp_megaphone_review,
    miniapp_dev_analytics,
    miniapp_telemetry,
)

# Переопределить стандартный админ на кастомный
admin.site.__class__ = CustomAdminSite

def serve_manifest(request):
    """Serve PWA manifest.json"""
    manifest_path = Path(settings.STATIC_ROOT) / 'manifest.json'
    if manifest_path.exists():
        return FileResponse(
            open(manifest_path, 'rb'),
            content_type='application/manifest+json',
            status=200
        )
    return FileResponse(open(Path(settings.BASE_DIR) / 'static' / 'manifest.json', 'rb'), 
                       content_type='application/manifest+json', 
                       status=200)

def serve_service_worker(request):
    """Serve service worker script"""
    sw_path = Path(settings.STATIC_ROOT) / 'service-worker.js'
    if sw_path.exists():
        return FileResponse(
            open(sw_path, 'rb'),
            content_type='application/javascript',
            status=200
        )
    return FileResponse(open(Path(settings.BASE_DIR) / 'static' / 'service-worker.js', 'rb'), 
                       content_type='application/javascript', 
                       status=200)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),

    # ─── Telegram Mini App ─────────────────────────────────────────────────────
    path('app', miniapp_index, name='miniapp'),
    path('app/', miniapp_index, name='miniapp_slash'),
    path('api/user_data', miniapp_user_data, name='miniapp_api'),
    path('api/user_data/', miniapp_user_data, name='miniapp_api_slash'),
    path('api/leaderboard', miniapp_leaderboard, name='miniapp_leaderboard'),
    path('api/checkin', miniapp_checkin, name='miniapp_checkin'),
    path('api/boss/submit_damage', miniapp_boss_damage, name='miniapp_boss_damage'),
    path('api/marriage', miniapp_marriage, name='miniapp_marriage'),
    path('api/marriage/propose', miniapp_marriage_propose, name='miniapp_marriage_propose'),
    path('api/marriage/proposals', miniapp_marriage_proposals_list, name='miniapp_marriage_proposals_list'),
    path('api/marriage/respond', miniapp_marriage_respond, name='miniapp_marriage_respond'),
    path('api/solo_boss/status', miniapp_solo_boss_status, name='miniapp_solo_boss_status'),
    path('api/solo_boss/start', miniapp_solo_boss_start, name='miniapp_solo_boss_start'),
    path('api/solo_boss/attack', miniapp_solo_boss_attack, name='miniapp_solo_boss_attack'),
    path('api/solo_boss/forfeit', miniapp_solo_boss_forfeit, name='miniapp_solo_boss_forfeit'),
    path('api/bonds', miniapp_bonds, name='miniapp_bonds'),
    path('api/equip', miniapp_equip, name='miniapp_equip'),
    path('api/dev/stats', miniapp_dev_stats, name='miniapp_dev_stats'),
    path('api/dev/setbalance', miniapp_dev_setbalance, name='miniapp_dev_setbalance'),
    path('api/dev/add_mora', miniapp_dev_add_mora, name='miniapp_dev_add_mora'),
    path('api/dev/add_xp', miniapp_dev_add_xp, name='miniapp_dev_add_xp'),
    path('api/dev/give_item', miniapp_dev_give_item, name='miniapp_dev_give_item'),
    path('api/dev/give_crystals', miniapp_dev_give_crystals, name='miniapp_dev_give_crystals'),
    path('api/dev/users', miniapp_dev_users, name='miniapp_dev_users'),
    path('api/dev/chats', miniapp_dev_chats, name='miniapp_dev_chats'),
    path('api/dev/chat_admins', miniapp_dev_chat_admins, name='miniapp_dev_chat_admins'),
    path('api/dev/banlist', miniapp_dev_banlist, name='miniapp_dev_banlist'),
    path('api/dev/logs', miniapp_dev_logs, name='miniapp_dev_logs'),
    path('api/dev/wallet_user', miniapp_dev_wallet_user, name='miniapp_dev_wallet_user'),
    path('api/dev/trigger_event', miniapp_dev_trigger_event, name='miniapp_dev_trigger_event'),
    path('api/dev/items', miniapp_dev_items, name='miniapp_dev_items'),
    path('api/dev/member_update', miniapp_dev_member_update, name='miniapp_dev_member_update'),
    path('api/dev/salary', miniapp_dev_salary, name='miniapp_dev_salary'),
    path('api/treasury', miniapp_treasury, name='miniapp_treasury'),
    path('api/treasury/payout', miniapp_treasury_payout, name='miniapp_treasury_payout'),
    path('api/wallet/history', miniapp_wallet_history, name='miniapp_wallet_history'),
    path('api/family/deposit', miniapp_family_deposit, name='miniapp_family_deposit'),
    path('api/family/withdraw', miniapp_family_withdraw, name='miniapp_family_withdraw'),
    path('api/family/log', miniapp_family_log, name='miniapp_family_log'),
    path('api/marriage/divorce', miniapp_divorce, name='miniapp_divorce'),
    path('api/inventory', miniapp_inventory, name='miniapp_inventory'),
    path('api/inventory/sell_junk', miniapp_inventory_sell_junk, name='miniapp_inventory_sell_junk'),
    path('api/gacha/roll', miniapp_gacha_roll, name='miniapp_gacha_roll'),
    path('api/gacha/free_roll', miniapp_gacha_free_roll, name='miniapp_gacha_free_roll'),
    path('api/gacha/free_rolls', miniapp_gacha_free_rolls_count, name='miniapp_gacha_free_rolls_count'),
    path('api/bonds/buy', miniapp_bonds_buy, name='miniapp_bonds_buy'),
    path('api/bonds/sell', miniapp_bonds_sell, name='miniapp_bonds_sell'),
    path('api/bank', miniapp_bank, name='miniapp_bank'),
    path('api/bank/deposit', miniapp_bank_deposit, name='miniapp_bank_deposit'),
    path('api/bank/withdraw', miniapp_bank_withdraw, name='miniapp_bank_withdraw'),
    path('api/pet/walk', miniapp_pet_walk, name='miniapp_pet_walk'),
    path('api/pet/feed', miniapp_pet_feed, name='miniapp_pet_feed'),
    path('api/shop/catalog', miniapp_shop_catalog, name='miniapp_shop_catalog'),
    path('api/shop/buy', miniapp_shop_buy, name='miniapp_shop_buy'),
    path('api/shop/set_title', miniapp_shop_set_title, name='miniapp_shop_set_title'),
    path('api/profile/bio', miniapp_set_bio, name='miniapp_set_bio'),
    path('api/themes', miniapp_themes, name='miniapp_themes'),
    path('api/public_profile', miniapp_public_profile, name='miniapp_public_profile'),
    path('api/enhance', miniapp_enhance_item, name='miniapp_enhance_item'),
    path('api/consume_potion', miniapp_consume_potion, name='miniapp_consume_potion'),
    path('api/batch_sell', miniapp_batch_sell, name='miniapp_batch_sell'),
    path('api/couple_boss/status', miniapp_couple_boss_status, name='miniapp_couple_boss_status'),
    path('api/couple_boss/start', miniapp_couple_boss_start, name='miniapp_couple_boss_start'),
    path('api/couple_boss/attack', miniapp_couple_boss_attack, name='miniapp_couple_boss_attack'),
    path('api/get_avatar', miniapp_get_avatar, name='miniapp_get_avatar'),
    # ─── Quest / Quests ────────────────────────────────────────────────────────
    path('api/quest', miniapp_quest, name='miniapp_quest'),
    path('api/quest/reroll', miniapp_quest_reroll, name='miniapp_quest_reroll'),
    # ─── Spy / Шпионаж ────────────────────────────────────────────────────────
    path('api/spy', miniapp_spy, name='miniapp_spy'),
    path('api/members', miniapp_members, name='miniapp_members'),
    path('api/warnlist', miniapp_warnlist, name='miniapp_warnlist'),
    path('api/chat_banlist', miniapp_chat_banlist, name='miniapp_chat_banlist'),
    path('api/admin/chat_summary', miniapp_admin_chat_summary, name='miniapp_admin_chat_summary'),
    path('api/admin/roster', miniapp_admin_roster, name='miniapp_admin_roster'),
    # ─── Transfers / Переводы ─────────────────────────────────────────────────
    path('api/transfer', miniapp_transfer, name='miniapp_transfer'),
    path('api/crystals/transfer', miniapp_crystals_transfer, name='miniapp_crystals_transfer'),
    path('api/transfer_pass/use', miniapp_use_transfer_pass, name='miniapp_use_transfer_pass'),
    # ─── Loans / Долги ────────────────────────────────────────────────────────
    path('api/loans', miniapp_loans, name='miniapp_loans'),
    path('api/loans/create', miniapp_loans_create, name='miniapp_loans_create'),
    path('api/loans/repay', miniapp_loans_repay, name='miniapp_loans_repay'),
    path('api/loans/respond', miniapp_loans_respond, name='miniapp_loans_respond'),
    path('api/loans/cancel', miniapp_loans_cancel, name='miniapp_loans_cancel'),
    # ─── Casino / Казино ──────────────────────────────────────────────────────
    path('api/casino/coin', miniapp_casino_coin, name='miniapp_casino_coin'),
    path('api/casino/lottery', miniapp_casino_lottery, name='miniapp_casino_lottery'),
    path('api/casino/roulette', miniapp_casino_roulette, name='miniapp_casino_roulette'),
    # ─── Expeditions / Экспедиции ─────────────────────────────────────────────
    path('api/expeditions', miniapp_expeditions, name='miniapp_expeditions'),
    path('api/expeditions/start', miniapp_expeditions_start, name='miniapp_expeditions_start'),
    path('api/expeditions/collect', miniapp_expeditions_collect, name='miniapp_expeditions_collect'),
    path('api/expeditions/boost', miniapp_expeditions_boost, name='miniapp_expeditions_boost'),
    path('api/pets/rename', miniapp_pets_rename, name='miniapp_pets_rename'),
    # ─── Cleanup config / Настройка чистки ────────────────────────────────────
    path('api/cleanup_config', miniapp_cleanup_config, name='miniapp_cleanup_config'),
    path('api/cleanup_pass', miniapp_cleanup_pass, name='miniapp_cleanup_pass'),
    # ─── Timezone / Часовой пояс ──────────────────────────────────────────────
    path('api/timezone', miniapp_timezone, name='miniapp_timezone'),
    # ─── Chat buff / Глобальный баф чата (Block 8) ────────────────────────────
    path('api/chat_buff', miniapp_chat_buff, name='miniapp_chat_buff'),
    # ─── Gifts / Подарки партнёру ─────────────────────────────────────────────
    path('api/gifts/catalog', miniapp_gifts_catalog, name='miniapp_gifts_catalog'),
    path('api/gifts/send', miniapp_gifts_send, name='miniapp_gifts_send'),
    # ─── Auction / Аукцион ────────────────────────────────────────────────────
    path('api/auction/list', miniapp_auction_list, name='miniapp_auction_list'),
    path('api/auction/create', miniapp_auction_create, name='miniapp_auction_create'),
    path('api/auction/bid', miniapp_auction_bid, name='miniapp_auction_bid'),
    path('api/auction/buyout', miniapp_auction_buyout, name='miniapp_auction_buyout'),
    path('api/auction/cancel', miniapp_auction_cancel, name='miniapp_auction_cancel'),
    # ─── Achievements / Достижения ────────────────────────────────────────────
    path('api/achievements', miniapp_achievements, name='miniapp_achievements'),
    # ─── Crystals / Кристаллы ─────────────────────────────────────────────────
    path('api/crystals/catalog', miniapp_crystals_catalog, name='miniapp_crystals_catalog'),
    path('api/crystals/spend', miniapp_crystals_spend, name='miniapp_crystals_spend'),
    path('api/convert_crystals', miniapp_convert_crystals, name='miniapp_convert_crystals'),
    # ─── Avatar serving / Аватары ─────────────────────────────────────────────
    path('api/user_avatar/<int:user_id>/', miniapp_user_avatar, name='miniapp_user_avatar'),
    # ─── Dev: Error logs / Логи ошибок ────────────────────────────────────────
    path('api/dev/error_logs', miniapp_dev_error_logs, name='miniapp_dev_error_logs'),
    path('api/dev/analytics', miniapp_dev_analytics, name='miniapp_dev_analytics'),
    path('api/telemetry', miniapp_telemetry, name='miniapp_telemetry'),
    path('api/frontend_error_log', miniapp_frontend_error_log, name='miniapp_frontend_error_log'),
    path('api/dev/af2_config', miniapp_dev_af2_config, name='miniapp_dev_af2_config'),
    path('api/dev/import_users', miniapp_dev_import_users, name='miniapp_dev_import_users'),
    path('api/dev/scan_members', miniapp_dev_scan_members, name='miniapp_dev_scan_members'),
    path('api/dev/purge_chat_nonmembers', miniapp_dev_purge_chat_nonmembers, name='miniapp_dev_purge_chat_nonmembers'),
    path('api/dev/user_inventory', miniapp_dev_user_inventory, name='miniapp_dev_user_inventory'),
    path('api/dev/delete_inventory_item', miniapp_dev_delete_inventory_item, name='miniapp_dev_delete_inventory_item'),
    path('api/dev/feature_toggle', miniapp_dev_feature_toggle, name='miniapp_dev_feature_toggle'),
    # ─── Avatar save ──────────────────────────────────────────────────────────
    path('api/save_avatar', miniapp_save_avatar, name='miniapp_save_avatar'),
    # ─── Season Pass / Боевой пропуск ────────────────────────────────────────
    path('api/season/data', miniapp_season_data, name='miniapp_season_data'),
    path('api/season/claim', miniapp_season_claim, name='miniapp_season_claim'),
    path('api/season/premium', miniapp_season_premium, name='miniapp_season_premium'),
    # ─── Shards / Осколки ────────────────────────────────────────────────────
    path('api/shards', miniapp_shards, name='miniapp_shards'),
    path('api/shards/craft', miniapp_shards_craft, name='miniapp_shards_craft'),
    # ─── Talents / Таланты ───────────────────────────────────────────────────
    path('api/talents', miniapp_talents, name='miniapp_talents'),
    path('api/talents/upgrade', miniapp_talents_upgrade, name='miniapp_talents_upgrade'),
    # ─── Newbie Quest / Квест новичка ────────────────────────────────────────
    path('api/newbie_quest', miniapp_newbie_quest, name='miniapp_newbie_quest'),
    # ─── Settings / Настройки ────────────────────────────────────────────────
    path('api/settings/local', miniapp_settings_local, name='miniapp_settings_local'),
    path('api/settings/global', miniapp_settings_global, name='miniapp_settings_global'),
    # ─── Chat Tags / Теги пользователей ──────────────────────────────────────
    path('api/chat_tags', miniapp_chat_tags, name='miniapp_chat_tags'),
    path('api/tag_definitions', miniapp_tag_definitions, name='miniapp_tag_definitions'),
    # ─── Stars / Покупка кристаллов за Telegram Stars ─────────────────────────
    path('api/stars/invoice', miniapp_stars_invoice, name='miniapp_stars_invoice'),
    # ─── Промокоды ────────────────────────────────────────────────────────────
    path('api/promo/activate',      miniapp_promo_activate,   name='miniapp_promo_activate'),
    path('api/dev/promo/create',    miniapp_promo_create,     name='miniapp_promo_create'),
    path('api/dev/promo/list',      miniapp_promo_list,       name='miniapp_promo_list'),
    path('api/dev/promo/deactivate',miniapp_promo_deactivate, name='miniapp_promo_deactivate'),
    # ─── Megaphone / Рупор ────────────────────────────────────────────────────
    path('api/dev/megaphone/list',   miniapp_megaphone_list,   name='miniapp_megaphone_list'),
    path('api/dev/megaphone/review', miniapp_megaphone_review, name='miniapp_megaphone_review'),
    # ──────────────────────────────────────────────────────────────────────────
    path('protected/<path:file_path>', serve_protected_media, name='serve_protected_media'),
    
    # Core app (Главная страница)
    path('', include('core.urls')),
    
    # Users app (Авторизация, Профиль)
    path('auth/', include('users.urls')),
    
    # Blog app (Социальная сеть, События)
    path('blog/', include('blog.urls')),
    
    # Gallery app
    path('gallery/', include('gallery.urls')),
    
    # Products app
    path('products/', include('products.urls')),
    
    # Notifications app
    path('notifications/', include('notifications.urls')),
    
    
    # Sitemap
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),

    # robots.txt — served as plain text from template
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'), name='robots_txt'),

    # /.well-known/traffic-advice — Chrome prerender hint (prevents 404 noise in logs)
    path('.well-known/traffic-advice', lambda r: JsonResponse([{"user_agent": "prefetch-proxy", "google-extended": "disallow"}], safe=False, content_type='application/trafficadvice+json')),

    # /shop → redirect to /products/
    path('shop', RedirectView.as_view(url='/products/', permanent=True)),
    path('shop/', RedirectView.as_view(url='/products/', permanent=True)),

    # CKEditor 5 upload path
    path('ckeditor5/', include('django_ckeditor_5.urls')),
    # Favicon shortcut to static asset
    path('favicon.ico', RedirectView.as_view(url=static_static('img/favicon.png'), permanent=True)),

    # ─── React Mini App — Vite-ассеты (JS/CSS с хешированными именами) ─────────
    # Vite собирает в PredvestnikBot/web/assets/ с абсолютными путями /assets/...
    re_path(
        r'^assets/(?P<path>.+)$',
        _static_serve,
        {'document_root': str(Path(__file__).resolve().parent.parent.parent / 'PredvestnikBot' / 'web' / 'assets')},
        name='miniapp_assets',
    ),

    # ─── SPA-фоллбэк: /app/<anything> → index.html (клиентская навигация) ──────
    re_path(r'^app/.*$', miniapp_index, name='miniapp_spa_fallback'),
]

# Добавляем маршруты для медиа-файлов и static файлов
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    # In production, serve media files through Django
    # TODO: Move to DigitalOcean Spaces for production
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Also serve static files in production (WhiteNoise should handle this, but as fallback)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)