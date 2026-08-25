const base = (process.env.PREVIEW_URL || 'http://127.0.0.1:8402').replace(/\/$/, '');
const failures=[];

function check(label, condition) {
  if(condition) console.log(`OK  ${label}`);
  else { console.error(`FAIL ${label}`); failures.push(label); }
}

async function request(path, options={}) {
  const response=await fetch(`${base}${path}`, options);
  return {response, body:await response.json()};
}

function equipped(catalog) {
  return Object.fromEntries(Object.entries(catalog.slots||{}).map(([slot,items])=>[
    slot, (items||[]).filter(item=>item.equipped).map(item=>item.id),
  ]));
}

try {
  await request('/__preview/reset', {method:'POST'});
  const beforeCatalog=(await request('/cosmetics/')).body;
  const beforeProfile=(await request('/profile/me')).body;
  const beforeBalances=structuredClone(beforeCatalog.balances);
  const beforeOwnership=Object.fromEntries(Object.entries(beforeCatalog.slots).map(([slot,items])=>[
    slot, items.map(item=>[item.id,Boolean(item.owned)]),
  ]));

  const missing=await request('/cosmetics/presets/999/apply', {method:'POST'});
  check('a missing saved look fails with the production-compatible 400', missing.response.status===400 && missing.body.detail==='Пресет не найден.');
  const afterMissingCatalog=(await request('/cosmetics/')).body;
  const afterMissingProfile=(await request('/profile/me')).body;
  check('a rejected saved look leaves the catalog unchanged', JSON.stringify(afterMissingCatalog)===JSON.stringify(beforeCatalog));
  check('a rejected saved look leaves the profile card unchanged', JSON.stringify(afterMissingProfile)===JSON.stringify(beforeProfile));

  const applied=await request('/cosmetics/presets/1/apply', {method:'POST'});
  check('an owned saved look applies through an explicit preview endpoint', applied.response.status===200 && applied.body.ok===true && /Золотой образ/.test(applied.body.message||''));
  const catalog=(await request('/cosmetics/')).body;
  const profile=(await request('/profile/me')).body;
  const active=equipped(catalog);
  check('applying a saved look replaces every wearable slot instead of merging it',
    JSON.stringify(active)===JSON.stringify({
      name_glow:['cos_name_glow_moon'], avatar_frame:['cos_avatar_frame_oak'], avatar_halo:[],
      title:['cos_title_dawnchild'], profile_bg:['cos_profile_bg_forest'], card_fx:[],
    }));
  check('the player-card cosmetics match the applied saved look',
    profile.cosmetics?.name_glow?.css==='glow-moon'
      && profile.cosmetics?.avatar_frame?.css==='frame-oak'
      && profile.cosmetics?.title==='Дитя Зари'
      && profile.cosmetics?.title_css==='title-dawnchild'
      && profile.cosmetics?.profile_bg?.css==='pbg-forest'
      && !profile.cosmetics?.avatar_halo && !profile.cosmetics?.card_fx);
  check('applying a saved look does not spend currency or alter ownership',
    JSON.stringify(catalog.balances)===JSON.stringify(beforeBalances)
      && JSON.stringify(Object.fromEntries(Object.entries(catalog.slots).map(([slot,items])=>[slot,items.map(item=>[item.id,Boolean(item.owned)])])))===JSON.stringify(beforeOwnership));

  await request('/__preview/reset', {method:'POST'});
  const resetCatalog=(await request('/cosmetics/')).body;
  const resetProfile=(await request('/profile/me')).body;
  check('reset restores the cosmetic catalog baseline after applying a look', JSON.stringify(resetCatalog)===JSON.stringify(beforeCatalog));
  check('reset restores the player-card cosmetic baseline after applying a look', JSON.stringify(resetProfile)===JSON.stringify(beforeProfile));
} catch(error) {
  console.error(error);
  failures.push(`unexpected error: ${error.message}`);
}

if(failures.length) {
  console.error(`\n${failures.length} preset-apply check(s) failed.`);
  process.exit(1);
}

console.log('\nALL OK');
