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

  const buy = await request('/themes/buy', {method: 'POST', body: JSON.stringify({theme_id: 'neon_terminal'})});
  const bought = await buy.json();
  if (!buy.ok || bought.theme_name !== 'Неоновый Терминал') throw new Error(`Buy response is not usable: ${JSON.stringify(bought)}`);

  const afterBuyThemes = await (await request('/themes/')).json();
  const afterBuyProfile = await (await request('/profile/me')).json();
  const neonBought = afterBuyThemes.find(theme => theme.theme_id === 'neon_terminal');
  if (!neonBought?.owned || neonBought.active || afterBuyProfile.zarniki !== beforeProfile.zarniki - 440) {
    throw new Error('Purchase must mark the theme owned and deduct exactly 440 zarniki.');
  }

  const equip = await request('/themes/equip', {method: 'POST', body: JSON.stringify({theme_id: 'neon_terminal'})});
  const equipped = await equip.json();
  if (!equip.ok || equipped.theme_name !== 'Неоновый Терминал') throw new Error(`Equip response is not usable: ${JSON.stringify(equipped)}`);

  const afterEquipThemes = await (await request('/themes/')).json();
  const active = afterEquipThemes.filter(theme => theme.active).map(theme => theme.theme_id);
  if (active.length !== 1 || active[0] !== 'neon_terminal') throw new Error(`Expected exactly Neon Terminal to be active, got ${active.join(', ')}`);

  console.log('OK: local theme purchase deducts the exact price, grants ownership, and equips the selected theme');
} catch (error) {
  failed = error;
} finally {
  await request('/__preview/reset', {method: 'POST'});
}

if (failed) {
  console.error('FAIL:', failed.message);
  process.exit(1);
}
