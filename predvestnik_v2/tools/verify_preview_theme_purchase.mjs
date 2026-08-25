// Локальный стенд обязан вести тему через тот же очевидный цикл, что и интерфейс:
// цена → покупка → владение → надевание. После проверки возвращаем состояние
// стенда, чтобы остальные визуальные тесты были независимыми.
const base = 'http://localhost:8402';
const request = (path, options = {}) => fetch(base + path, {
  headers: {'content-type': 'application/json', ...(options.headers || {})},
  ...options,
});

let failed = null;
try {
  await request('/__preview/reset', {method: 'POST'});
  const beforeThemes = await (await request('/themes/')).json();
  const beforeProfile = await (await request('/profile/me')).json();
  const neonBefore = beforeThemes.find(theme => theme.theme_id === 'neon_terminal');
  if (!neonBefore || neonBefore.owned || neonBefore.active || neonBefore.source !== 'zarniki') {
    throw new Error('Neon terminal must start as an unowned directly sold local theme.');
  }

  const requestKey='preview-theme-purchase-1';
  const buy = await request('/themes/buy', {method: 'POST', headers: {'Idempotency-Key': requestKey}, body: JSON.stringify({theme_id: 'neon_terminal'})});
  const bought = await buy.json();
  if (!buy.ok || bought.theme_name !== 'Неоновый Терминал' || !bought.applied) throw new Error(`Buy response is not usable: ${JSON.stringify(bought)}`);

  const afterBuyThemes = await (await request('/themes/')).json();
  const afterBuyProfile = await (await request('/profile/me')).json();
  const neonBought = afterBuyThemes.find(theme => theme.theme_id === 'neon_terminal');
  if (!neonBought?.owned || neonBought.active || afterBuyProfile.zarniki !== beforeProfile.zarniki - 440) {
    throw new Error('Purchase must mark the theme owned and deduct exactly 440 zarniki.');
  }

  const replay = await request('/themes/buy', {method: 'POST', headers: {'Idempotency-Key': requestKey}, body: JSON.stringify({theme_id: 'neon_terminal'})});
  const replayed = await replay.json();
  const afterReplayProfile = await (await request('/profile/me')).json();
  if (!replay.ok || !replayed.replayed || replayed.applied || afterReplayProfile.zarniki !== afterBuyProfile.zarniki) {
    throw new Error(`Purchase retry must replay without a second debit: ${JSON.stringify(replayed)}`);
  }

  const keyConflict = await request('/themes/buy', {method: 'POST', headers: {'Idempotency-Key': requestKey}, body: JSON.stringify({theme_id: 'shadow_merchant'})});
  if (keyConflict.ok || keyConflict.status !== 400) throw new Error('A purchase key may not be rebound to another theme.');

  const alreadyOwned = await request('/themes/buy', {method: 'POST', headers: {'Idempotency-Key': 'preview-theme-purchase-2'}, body: JSON.stringify({theme_id: 'neon_terminal'})});
  const alreadyOwnedResult = await alreadyOwned.json();
  const afterSecondKeyProfile = await (await request('/profile/me')).json();
  if (!alreadyOwned.ok || !alreadyOwnedResult.already_owned || afterSecondKeyProfile.zarniki !== afterBuyProfile.zarniki) {
    throw new Error(`A repeated double tap must not debit an owned theme: ${JSON.stringify(alreadyOwnedResult)}`);
  }

  const equip = await request('/themes/equip', {method: 'POST', body: JSON.stringify({theme_id: 'neon_terminal'})});
  const equipped = await equip.json();
  if (!equip.ok || equipped.theme_name !== 'Неоновый Терминал') throw new Error(`Equip response is not usable: ${JSON.stringify(equipped)}`);

  const afterEquipThemes = await (await request('/themes/')).json();
  const active = afterEquipThemes.filter(theme => theme.active).map(theme => theme.theme_id);
  if (active.length !== 1 || active[0] !== 'neon_terminal') throw new Error(`Expected exactly Neon Terminal to be active, got ${active.join(', ')}`);

  console.log('OK: local theme purchase grants once, replays safely, rejects key reuse, and equips the selected theme');
} catch (error) {
  failed = error;
} finally {
  await request('/__preview/reset', {method: 'POST'});
}

if (failed) {
  console.error('FAIL:', failed.message);
  process.exit(1);
}
