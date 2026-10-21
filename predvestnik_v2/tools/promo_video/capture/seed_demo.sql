-- Демо-данные для стенда (только локальная база predvestnik_preprod): вымышленные игроки и чаты,
-- чтобы топ игроков, топ чатов и трекер чатов на снимках были заполнены.
set search_path=predvestnik;
insert into users(user_tg_id,user_tg_username,user_tg_name) values
 (990000011,'mark_off','Марк'),(990000012,'kira_bloom','Кира'),(990000013,'tema_frog','Тёма'),(990000014,'sonya_cat','Соня'),
 (990000015,'danya_bass','Даня'),(990000016,'vika_moon','Вика'),(990000017,'egor_zz','Егор'),(990000018,'alina_star','Алина')
on conflict do nothing;
insert into chat_settings(chat_id,chat_title) values (-1001,'Флудилка 🌚'),(-1002,'10Б 🔥 флуд'),(-1003,'аниме и чай 🍵'),(-1004,'ФЛУД 18:00 ☕'),(-1005,'геймеры без сна 🎮'),(-1006,'клуб полуночников 🌙')
on conflict (chat_id) do update set chat_title=excluded.chat_title;
insert into daily_user_stats(user_id,chat_id,date,message_count)
select u, c, to_char(current_date - d, 'YYYY-MM-DD'),
  (abs(hashtext(u::text||c::text||d::text)) % 140 + 15) * (case c when -1001 then 6 when -1002 then 4 when -1003 then 3 when -1004 then 2 else 1 end) / (case when u=990000001 then 1 else 2 end)
from unnest(array[990000001,990000011,990000012,990000013,990000014,990000015,990000016,990000017,990000018]::bigint[]) u,
     unnest(array[-1001,-1002,-1003,-1004,-1005,-1006]::bigint[]) c, generate_series(0,29) d
on conflict do nothing;
insert into user_chat_stats(user_tg_id,chat_tg_id,user_messages_count_all_time,user_messages_count_per_week,user_messages_count_per_day,local_rank)
select 990000001, c, 12000, 2100, 214, 0 from unnest(array[-1001,-1002,-1003]::bigint[]) c on conflict do nothing;
