'use strict';
const params = new URLSearchParams(location.search);
const variant = ['a','a6','b','c'].includes(params.get('v')) ? params.get('v') : 'a';
const exchange = params.get('exchange') === '1';
const admin = params.get('admin') === '1';
const width = [320,390,430].includes(Number(params.get('w'))) ? Number(params.get('w')) : 390;
const mainKeys = ['profile','arena','questlog','pets',...(variant === 'a6' ? ['looks'] : []),'more'];
const quickKeys = variant === 'c' ? ['chests','looks','inventory','top'] : [];
const railKeys = ['profile','arena',...(exchange ? ['exchange-v1'] : []),'pets','questlog','looks','chests','inventory','top','wallet'];
const dockKeys = variant === 'b' ? railKeys.concat('more') : mainKeys;
const content = document.getElementById('content');
const wallet = document.getElementById('wallet');
let current = 'profile';
let walletOrigin = null;
let lastFocus = null;
document.body.className = variant;
function button(key, className = 'tab') {
  const entry = NAV_FIXTURE.items[key];
  const node = document.createElement('button');
  node.type = 'button'; node.className = className; node.dataset.key = key;
  node.innerHTML = `${entry.icon}<span>${entry.label}</span>`;
  node.addEventListener('click', () => openSection(key));
  return node;
}
function setActive(key) {
  const primary = dockKeys.includes(key) ? key : quickKeys.includes(key) ? null : 'more';
  document.querySelectorAll('#dock button,#quick button').forEach(node => {
    const active = node.dataset.key === primary || (quickKeys.includes(key) && node.dataset.key === key);
    node.classList.toggle('active', active);
    if (active) node.setAttribute('aria-current','page'); else node.removeAttribute('aria-current');
  });
  const rail = document.getElementById('rail'), active = rail?.querySelector('.active');
  if (active) {
    const item=active.getBoundingClientRect(), bounds=rail.getBoundingClientRect();
    if(item.left<bounds.left) rail.scrollLeft+=item.left-bounds.left;
    else if(item.right>bounds.right) rail.scrollLeft+=item.right-bounds.right;
  }
}
function closeWallet() { wallet.close(); }
document.getElementById('close-wallet').addEventListener('click', closeWallet);
wallet.addEventListener('close', () => {setActive(walletOrigin);lastFocus?.focus();});
function openSection(key) {
  if (key === 'wallet') {
    if (wallet.open) return;
    walletOrigin = current; lastFocus = document.activeElement;
    setActive('wallet'); wallet.showModal(); return;
  }
  current = key; content.replaceChildren(); setActive(key); window.scrollTo(0,0);
  if (key === 'profile') {
    const capture = document.createElement('div'); capture.className = 'profile-capture';
    const image = document.createElement('img'); image.src = `profile-content-${width}.webp`;
    image.className = 'profile-shot'; image.alt = 'Настоящий профиль вымышленного игрока; здесь меняется только навигация'; capture.append(image);
    (NAV_FIXTURE.hotspots[String(width)] || []).forEach(hit => {
      const node=document.createElement('button');node.type='button';node.className='profile-hit';node.dataset.key=hit.key;
      node.setAttribute('aria-label', NAV_FIXTURE.items[hit.key].label);
      Object.assign(node.style,{left:`${hit.x/width*100}%`,top:`${hit.y}px`,width:`${hit.width/width*100}%`,height:`${hit.height}px`});
      node.addEventListener('click',()=>openSection(hit.key));capture.append(node);
    });content.append(capture);return;
  }
  const header = document.createElement('header'); const back = document.createElement('button');
  back.type='button';back.className='back';back.textContent='‹';back.setAttribute('aria-label','Назад в профиль');back.addEventListener('click',()=>openSection('profile'));
  const title = document.createElement('h1');title.textContent = NAV_FIXTURE.items[key]?.label || key;header.append(back,title);content.append(header);
  if (key !== 'more') {
    const note = document.createElement('p'); note.className='section-note';note.textContent='Раздел открыт в макете. Его содержимое остаётся прежним в приложении.';content.append(note);return;
  }
  const label = document.createElement('label');label.className='search-label';label.htmlFor='search';label.textContent='Найти раздел';
  const search=document.createElement('input');search.id='search';search.type='search';search.placeholder='Например, сундуки';content.append(label,search);
  const list=document.createElement('div');list.id='sections';content.append(list);
  const groups = NAV_FIXTURE.groups.map(group=>({...group,keys:group.keys.filter(item =>
    !dockKeys.includes(item) && !quickKeys.includes(item) && (item !== 'exchange-v1' || exchange) && (!['admin','purge'].includes(item) || admin))}));
  function renderRows() {
    list.replaceChildren(); const query=search.value.trim().toLocaleLowerCase('ru');let count=0;
    groups.forEach(group=>{
      const keys=group.keys.filter(item=>`${NAV_FIXTURE.items[item].label} ${NAV_FIXTURE.items[item].hint || ''}`.toLocaleLowerCase('ru').includes(query));
      if(!keys.length)return;
      const section=document.createElement('section');const heading=document.createElement('h2');heading.className='eyebrow';heading.textContent=group.title;section.append(heading);
      keys.forEach(item=>{const node=button(item,'row');const span=node.querySelector('span');span.className='label';
        const hint=NAV_FIXTURE.items[item].hint;if(hint){const small=document.createElement('small');small.textContent=hint;span.append(small);}
        const arrow=document.createElement('span');arrow.className='chevron';arrow.textContent='›';node.append(arrow);section.append(node);count++;});list.append(section);
    });
    if(!count){const empty=document.createElement('p');empty.className='empty';empty.textContent='Такого раздела нет. Попробуй другое название.';list.append(empty);}
  }
  search.addEventListener('input',renderRows);renderRows();
}
const dock = document.getElementById('dock');
if (variant === 'b') {
  const wrap=document.createElement('div');wrap.id='rail-wrap';const rail=document.createElement('div');rail.id='rail';
  railKeys.forEach(key=>rail.append(button(key)));const track=document.createElement('div');track.id='track';const thumb=document.createElement('span');thumb.id='thumb';track.append(thumb);wrap.append(rail,track);
  const more=button('more');more.classList.add('pinned');dock.append(wrap,more);
  const update=()=>{const ratio=rail.clientWidth/rail.scrollWidth;thumb.style.width=`${ratio*100}%`;thumb.style.transform=`translateX(${rail.scrollLeft/rail.scrollWidth*track.clientWidth}px)`;};
  rail.addEventListener('scroll',update);window.addEventListener('resize',update);requestAnimationFrame(update);
} else mainKeys.forEach(key=>dock.append(button(key)));
const quick=document.getElementById('quick');
if(quickKeys.length){quick.hidden=false;quickKeys.forEach(key=>quick.append(button(key,'quick-button')));}
openSection('profile');
