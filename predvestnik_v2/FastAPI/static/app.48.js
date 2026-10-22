// ── Сезонные истории, второе издание (владелец 2026-10-22: «к каждому скину свой подход») ───────────────────────────
// Не шаблон «предмет слева + предмет справа + кольцо»: у каждой сцены своя композиция и своё движение.
// Маскарад — театр сверху вниз (ламбрекен, кулисы, прожектор, рампа, падающие перья, ворон над сценой, золотое конфетти).
// Экипаж — дорога в глубину (туман ползёт лентой, фонари уменьшаются к горизонту, экипаж проезжает, фосфорное колесо).
// Пряничная — изнутри тёплого окна (иней по углам стекла, гирлянда пряников качается, жар печи, сахарная пудра, пар над какао).
// Экспресс — путь (горы и виадук едут с разной скоростью, косой снег, Полярная звезда, локомотив проносится, пар).
// Письмо — лист бумаги (линовка, строки пишутся сами, перо, сургуч, лепестки падают).
// Хрусталь — преломление (спектральные лучи из-под аватара, осколки, двойная звезда на орбите).
// Средний центр сцены пуст: аватар и ник всегда читаются. Картинки: tools/scene_art_g.py.
_scAdd('raven_masquerade', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'radial-gradient(ellipse at 50% -10%, #3a1a5299, transparent 64%), linear-gradient(0deg, #12081899, transparent 34%)'}],
  [2, 'band', {l:'0',b:'0',w:'100%',h:'10%',bg:'repeating-linear-gradient(90deg, #2c18129e 0 38px, #3a2216a8 38px 40px), linear-gradient(0deg, #1a0e0a, transparent)'}],
  [2, 'band', {l:'0',b:'10%',w:'100%',h:'1px',bg:'linear-gradient(90deg, transparent, #d6b06aaa, transparent)'}],
  [3, 'glow breathe', {l:'22%',t:'-42%',w:'56%',h:'136%',c:'#ffe6a8',k:'14%',dur:11}],
  [3, 'dot twinkle', {l:'38%',t:'16%',s:'2px',c:'#ffe6a8',bs:_scBs([[40,30,1,0,'#ffe6a8'],[80,70,1,0,'c'],[-20,90,1,0,'#ffe6a8'],[60,120,1,0,'c']]),dur:4.4}],
  [4, 'band', {l:'0',t:'0',w:'100%',h:'19%',bg:'radial-gradient(60px 26px at 12.5% 100%, transparent 96%, #2a0f3a) 0 0 / 25% 100% repeat-x'}],
  [4, 'band', {l:'0',t:'19%',w:'100%',h:'2px',bg:'repeating-linear-gradient(90deg, #d6b06a 0 3px, transparent 3px 7px)'}],
  [4, 'sil i-curtainL sway', {l:'-3%',t:'0',w:'15%',h:'92%',org:'0% 0%',ang:'1deg',dur:12}],
  [4, 'sil i-curtainL fl sway', {r:'-3%',t:'0',w:'15%',h:'92%',org:'100% 0%',ang:'1deg',dur:13,del:-4}],
  [5, 'dot pulse', {l:'8%',b:'6%',s:'4px',c:'#ffd88a',bs:_scBs([[40,0,6,1,'#ffd88a'],[80,0,6,1,'#ffd88a'],[120,0,6,1,'#ffd88a'],[160,0,6,1,'#ffd88a'],[200,0,6,1,'#ffd88a'],[240,0,6,1,'#ffd88a'],[280,0,6,1,'#ffd88a'],[320,0,6,1,'#ffd88a']]),dur:2.6}],
  [5, 'sil m i-ravenFeather rise', {l:'20%',t:'4%',w:'9px',h:'18px',c:'c',o:.85,dx:'18px',dy:'170px',s0:'1',s1:'1',rot:'20deg',dur:12}],
  [5, 'sil m i-ravenFeather rise w2', {r:'24%',t:'2%',w:'8px',h:'16px',c:'a',o:.7,dx:'-14px',dy:'180px',s0:'1',s1:'1',rot:'-24deg',dur:15,del:-6}],
  [6, 'sil m i-ravenFly cross', {l:'0',t:'14%',w:'64px',h:'28px',c:'#0b0712',o:.95,fx:'-90px',tx:'500px',ty:'-24px',dur:27}],
  [7, 'dot rise', {l:'30%',t:'-2%',s:'3px',c:'#ffe6a8',bs:_scBs([[30,10,0,0,'c'],[70,-4,0,0,'#ffe6a8'],[110,6,0,0,'a'],[150,-2,0,0,'#ffe6a8'],[-20,8,0,0,'c']]),dx:'10px',dy:'190px',s0:'1',s1:'1',dur:9}],
  [7, 'dot rise w2', {l:'26%',t:'-6%',s:'2px',c:'#ffd88a',bs:_scBs([[50,0,0,0,'a'],[90,12,0,0,'#ffe6a8'],[130,-6,0,0,'c'],[170,4,0,0,'#ffd88a']]),dx:'-12px',dy:'200px',s0:'1',s1:'1',dur:11,del:-5}],
]);
_scAdd('phantom_carriage', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'linear-gradient(180deg, #040e10, #0b2a2a99 58%, #12302c 100%)'}],
  [2, 'wave go i-fogTile m', {l:'0',b:'-2%',w:'calc(100% + 200px)',h:'26%',tw:'200px',c:'#89f3da',o:.18,dur:38}],
  [3, 'glow', {l:'58%',t:'-8%',w:'34%',h:'44%',c:'#ddfff5',k:'22%'}],
  [3, 'band', {l:'34%',t:'58%',w:'32%',h:'42%',bg:'linear-gradient(180deg, transparent, #89f3da14 40%, #89f3da26)'}],
  [3, 'wave go i-fogTile m w2', {l:'0',b:'14%',w:'calc(100% + 200px)',h:'18%',tw:'200px',c:'#c8fff0',o:.12,dur:64}],
  [4, 'sil i-lanternPost', {l:'3%',b:'0',w:'9%',h:'56%',o:.85}],
  [4, 'sil i-lanternPost', {l:'17%',b:'14%',w:'5%',h:'32%',o:.6}],
  [4, 'sil i-lanternPost', {l:'27%',b:'22%',w:'3%',h:'18%',o:.4}],
  [4, 'sil i-lanternPost fl', {r:'3%',b:'0',w:'9%',h:'56%',o:.85}],
  [4, 'sil i-lanternPost fl', {r:'17%',b:'14%',w:'5%',h:'32%',o:.6}],
  [4, 'sil i-lanternPost fl', {r:'27%',b:'22%',w:'3%',h:'18%',o:.4}],
  [5, 'dot float blink', {l:'12%',t:'30%',s:'4px',c:'#c8fff0',bs:'0 0 10px 3px #89f3da66',dx:'14px',dy:'-10px',dur:9}],
  [5, 'dot float blink', {r:'14%',t:'40%',s:'3px',c:'#c8fff0',bs:'0 0 8px 2px #89f3da55',dx:'-12px',dy:'-14px',dur:11,del:-3}],
  [6, 'sil i-ghostCoach cross', {l:'0',b:'-2%',w:'110px',h:'78px',o:.75,fx:'-140px',tx:'520px',dur:24}],
  [7, 'sil m i-ghostWheel spin', {l:'calc(50% - 190px)',t:'calc(50% - 190px)',w:'380px',h:'380px',c:'#89f3da',o:.13,dur:60}],
]);
_scAdd('gingerbread_house', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'linear-gradient(0deg, #3a1d0e, #150b08 60%)'}],
  [2, 'glow breathe', {l:'-10%',b:'-36%',w:'120%',h:'62%',c:'#ff9a4a',k:'26%',dur:5}],
  [3, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'linear-gradient(90deg, #ffe8c512, transparent 16%, transparent 84%, #ffe8c512), linear-gradient(180deg, #ffe8c514, transparent 20%)'}],
  [3, 'sil m i-frostCorner', {l:'0',t:'6%',w:'34%',h:'40%',c:'#fff4e2',o:.5,bp:'0% 0%'}],
  [3, 'sil m i-frostCorner fl', {r:'0',t:'6%',w:'34%',h:'40%',c:'#fff4e2',o:.5,bp:'0% 0%'}],
  [4, 'sil i-cookieGarland sway', {l:'-2%',t:'7%',w:'104%',h:'34%',bp:'50% 0%',org:'50% 0%',ang:'1.5deg',dur:7}],
  [5, 'dot rise', {l:'10%',t:'-4%',s:'2px',c:'#fff7ea',bs:_scBs([[40,6,0,0,'#fff7ea'],[90,-2,0,0,'#fff7ea'],[150,10,0,0,'#fff7ea'],[210,0,0,0,'#fff7ea'],[260,8,0,0,'#fff7ea'],[310,-4,0,0,'#fff7ea']]),dx:'8px',dy:'190px',s0:'1',s1:'1',o:.8,dur:10}],
  [5, 'dot rise w2', {l:'4%',t:'-10%',s:'1.5px',c:'#ffe1b8',bs:_scBs([[70,0,0,0,'#ffe1b8'],[130,8,0,0,'#ffe1b8'],[190,-6,0,0,'#ffe1b8'],[240,4,0,0,'#ffe1b8'],[300,-2,0,0,'#ffe1b8']]),dx:'-6px',dy:'200px',s0:'1',s1:'1',o:.7,dur:13,del:-6}],
  [6, 'glow flash', {l:'8%',t:'6%',w:'22%',h:'28%',c:'#fff4e2',k:'40%',dur:15}],
  [7, 'sil m i-steamPuff rise', {r:'10%',b:'2%',w:'44px',h:'28px',c:'#ffe1b8',o:.22,dx:'-10px',dy:'-110px',s0:'.5',s1:'1.5',dur:8}],
  [7, 'glow flicker', {l:'-6%',b:'-12%',w:'30%',h:'36%',c:'#ffb35c',k:'30%',dur:3}],
]);
_scAdd('polar_express', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'linear-gradient(180deg, #06101a, #16304e 70%, #23415f)'}],
  [2, 'dot twinkle', {l:'8%',t:'8%',s:'2px',c:'#e6f2ff',bs:_scBs([[50,20,1,0,'#e6f2ff'],[120,6,1,0,'c'],[200,30,1,0,'#e6f2ff'],[280,12,1,0,'a'],[330,40,1,0,'#e6f2ff']]),dur:5}],
  [3, 'wave go i-peaksTile', {l:'0',b:'14%',w:'calc(100% + 240px)',h:'24%',tw:'240px',o:.85,dur:70}],
  [3, 'glow breathe', {r:'2%',t:'-8%',w:'34%',h:'44%',c:'#ffe0a0',k:'22%',dur:7}],
  [4, 'wave go i-trackTile', {l:'0',b:'-1%',w:'calc(100% + 120px)',h:'17%',tw:'120px',dur:9}],
  [4, 'sil m i-northStar breathe', {r:'9%',t:'4%',w:'46px',h:'46px',c:'#fff3d6',o:.95,dur:4}],
  [5, 'dot sweep', {l:'0',t:'6%',s:'2px',c:'#ffffff',bs:_scBs([[-40,30,0,0,'#fff'],[-90,70,0,0,'#e6f2ff'],[-150,20,0,0,'#fff'],[-210,90,0,0,'#e6f2ff'],[-260,50,0,0,'#fff']]),fx:'420px',tx:'-120px',ty:'120px',dur:5}],
  [5, 'dot sweep w2', {l:'0',t:'30%',s:'1.5px',c:'#e6f2ff',bs:_scBs([[-60,10,0,0,'#e6f2ff'],[-130,50,0,0,'#fff'],[-190,-10,0,0,'#e6f2ff'],[-250,30,0,0,'#fff']]),fx:'440px',tx:'-140px',ty:'110px',dur:6.5,del:-2}],
  [6, 'sil i-northEngine cross', {l:'0',b:'11%',w:'96px',h:'80px',fx:'-120px',tx:'520px',dur:18}],
  [7, 'sil m i-steamPuff rise', {l:'8%',b:'16%',w:'58px',h:'38px',c:'#dce9f5',o:.55,dx:'-20px',dy:'-120px',s0:'.6',s1:'1.6',dur:7}],
  [7, 'sil m i-steamPuff rise w2', {l:'14%',b:'14%',w:'46px',h:'30px',c:'#dce9f5',o:.45,dx:'-30px',dy:'-140px',s0:'.6',s1:'1.8',dur:9,del:-4}],
]);
_scAdd('rose_letter', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'repeating-linear-gradient(180deg, transparent 0 27px, #ffa9c11c 27px 28px), linear-gradient(180deg, #2a1218, #14090f)'}],
  [2, 'band', {l:'9%',t:'0',w:'1px',h:'100%',bg:'#ff7a9a33'}],
  [3, 'glow breathe', {r:'-14%',t:'-20%',w:'60%',h:'80%',c:'#ffcf8a',k:'18%',dur:8}],
  [4, 'sil m i-inkLine sweep', {l:'0',b:'18%',w:'46%',h:'18px',c:'#ffa9c1',o:.55,fx:'-180px',tx:'0px',dur:9}],
  [4, 'sil m i-inkLine sweep w2', {l:'0',b:'8%',w:'38%',h:'16px',c:'#ffa9c1',o:.42,fx:'-160px',tx:'0px',dur:9,del:-4.5}],
  [4, 'sil i-roseQuill sway', {r:'-4%',b:'-6%',w:'22%',h:'54%',bp:'100% 100%',org:'80% 100%',ang:'4deg',o:.75,dur:3}],
  [5, 'sil m i-petal rise', {l:'16%',t:'-6%',w:'12px',h:'10px',c:'#d84a72',o:.85,dx:'30px',dy:'190px',s0:'1',s1:'.8',rot:'30deg',dur:10}],
  [5, 'sil m i-petal rise', {r:'30%',t:'-6%',w:'10px',h:'8px',c:'#ff8fae',o:.75,dx:'-24px',dy:'200px',s0:'1',s1:'.8',rot:'-40deg',dur:13,del:-5}],
  [5, 'sil m i-petal rise w2', {l:'44%',t:'-8%',w:'9px',h:'8px',c:'#c43f66',o:.7,dx:'14px',dy:'210px',s0:'1',s1:'.8',dur:15,del:-9}],
  [6, 'sil i-waxSeal beat', {l:'4%',b:'4%',w:'40px',h:'40px',o:.9,dur:5}],
  [7, 'sil m i-petal rise', {l:'6%',t:'-6%',w:'14px',h:'12px',c:'#ff6f92',o:.9,dx:'40px',dy:'200px',s0:'1',s1:'.7',rot:'10deg',dur:8,del:-2}],
  [7, 'glow pulse', {l:'calc(50% - 120px)',t:'calc(50% - 120px)',w:'240px',h:'240px',c:'#ff9ab6',k:'14%',dur:4}],
]);
_scAdd('glass_heart', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'radial-gradient(ellipse at 50% 120%, #4b2c6c88, transparent 60%), linear-gradient(180deg, #0f0919, #170e26)'}],
  [3, 'band', {l:'calc(50% - 2px)',b:'-10%',w:'4px',h:'120%',org:'50% 100%',rot:'-34deg',bg:'linear-gradient(0deg, #ff7ad955, #ffd36b33, #7affc322, transparent)'}],
  [3, 'band', {l:'calc(50% - 2px)',b:'-10%',w:'4px',h:'120%',org:'50% 100%',rot:'-12deg',bg:'linear-gradient(0deg, #7ac8ff55, #b5b5ef33, transparent)'}],
  [3, 'band', {l:'calc(50% - 2px)',b:'-10%',w:'4px',h:'120%',org:'50% 100%',rot:'14deg',bg:'linear-gradient(0deg, #ffd36b55, #ff7ad933, transparent)'}],
  [3, 'band', {l:'calc(50% - 2px)',b:'-10%',w:'4px',h:'120%',org:'50% 100%',rot:'36deg',bg:'linear-gradient(0deg, #7affc355, #7ac8ff33, transparent)'}],
  [4, 'sil i-shard float', {l:'3%',t:'12%',w:'26px',h:'46px',o:.8,rot:'-18deg',dx:'4px',dy:'-8px',dur:9}],
  [4, 'sil i-shard float', {r:'5%',t:'50%',w:'20px',h:'36px',o:.7,rot:'24deg',dx:'-4px',dy:'-10px',dur:11,del:-3}],
  [4, 'sil i-shard float w2', {l:'12%',b:'6%',w:'16px',h:'28px',o:.6,rot:'40deg',dx:'5px',dy:'-6px',dur:13,del:-6}],
  [5, 'dot spin', {l:'calc(50% - 2px)',t:'calc(50% - 2px)',s:'4px',c:'transparent',bs:_scBs([[118,0,6,2,'#f6b6ed'],[-118,0,6,2,'#b5e4ff']]),dur:26}],
  [5, 'dot twinkle', {l:'14%',t:'20%',s:'2px',c:'#e4fbff',bs:_scBs([[60,50,2,0,'#f6b6ed'],[230,10,2,0,'#e4fbff'],[280,90,2,0,'#f6b6ed']]),dur:4}],
  [6, 'band sweep', {l:'0',t:'34%',w:'90px',h:'2px',bg:'linear-gradient(90deg, transparent, #f6b6ed, #b5e4ff, #ffd36b, transparent)',rot:'-8deg',fx:'-100px',tx:'480px',ty:'20px',dur:13}],
  [7, 'dot spin rev', {l:'calc(50% - 2px)',t:'calc(50% - 2px)',s:'3px',c:'transparent',bs:_scBs([[0,-146,5,2,'#ffffff'],[0,146,5,2,'#f6b6ed']]),dur:40}],
  [7, 'sil i-crystalHeart beat', {r:'4%',b:'4%',w:'40px',h:'46px',o:.85,dur:3.2}],
]);

// Фирменные детали сезонных образов (SSS): у каждой своя мысль, не медальон-шаблон. Рисунок в единицах рамки (центр 50,50, кольцо ≈ 57), холст -30..130.
// Маска соскользнула на оправу; фосфорное колесо кареты за кольцом и фонарь на крюке; пряничный человечек держится за кольцо глазури;
// огонёк экспресса бежит по латунным рельсам вокруг; роза вьётся по кольцу и роняет лепесток; кристаллы прорастают из оправы, две звезды на парной орбите.
// Цвет и движение: skin-holidays-v3.css (только под .ap-anim, .ap-low и reduced-motion гасят).
(() => {
  const R = n => Math.round(n * 10) / 10;
  const pt = (r, deg) => `${R(50 + r * Math.cos(deg * Math.PI / 180))} ${R(50 + r * Math.sin(deg * Math.PI / 180))}`;
  const svg = (name, inner, back) => `<svg class="sa hs-${name}${back ? ' sa-b' : ''}" viewBox="-30 -30 160 160" aria-hidden="true">${inner}</svg>`;
  const ring = (n, f) => Array.from({ length: n }, (_, i) => f(i * 360 / n, i)).join('');
  const SPARK = 'M0-1L.27-.27L1 0L.27.27L0 1L-.27.27L-1 0L-.27-.27Z';

  const ravenmask = svg('mask', `<g transform="translate(88 8) rotate(36)"><g class="hs-bob">
    <path class="hs-rib" d="M-19-1q-9 7-7 18 2 9-4 17"/><path class="hs-rib hs-rib2" d="M-17 2q-4 9 0 17 3 7-1 14"/>
    <path class="hs-fth" d="M18-4Q30-17 27-36Q17-22 18-4Z"/><path class="hs-vein" d="M18-4Q25-18 27-34"/>
    <path class="hs-mk" fill-rule="evenodd" d="M-20-2Q-14-11-4-6Q0-3 4-6Q14-11 20-2Q18 8 8 7Q3 6 0 2Q-3 6-8 7Q-18 8-20-2ZM-13 0a4.6 2.7 0 1 0 9.2 0a4.6 2.7 0 1 0-9.2 0ZM3.8 0a4.6 2.7 0 1 0 9.2 0a4.6 2.7 0 1 0-9.2 0Z"/>
    <path class="hs-fil" d="M-17-3Q-12-8-5-5M5-5Q12-8 17-3M0-1v-3"/><circle class="hs-gem" cx="0" cy="-5.5" r="1.4"/></g></g>`);
  const ghostcoach = [svg('wheel', `<g class="hs-spin"><circle class="hs-rim" cx="50" cy="50" r="67"/><circle class="hs-rim2" cx="50" cy="50" r="62"/>
    ${ring(16, a => `<path class="hs-spk" d="M${pt(57, a)}L${pt(67, a)}"/>`)}${ring(8, a => `<circle class="hs-stud" cx="${pt(67, a).split(' ')[0]}" cy="${pt(67, a).split(' ')[1]}" r="1.3"/>`)}</g>`, true),
    svg('lamp', `<path class="hs-hook" d="M-4-18H14v6"/><g class="hs-swing"><path class="hs-hook" d="M14-12v5"/><circle class="hs-halo" cx="14" cy="5" r="11"/>
    <path class="hs-lbody" d="M8-7h12l-2 4v13l2 3H8l2-3V-3Z"/><path class="hs-lglass" d="M11-2h6v11h-6Z"/><circle class="hs-flame" cx="14" cy="4" r="1.8"/></g>`)];
  const sugarhouse = svg('icing', `<path class="hs-scal" d="${ring(28, (a, i) => `${i ? 'L' : 'M'}${pt(i % 2 ? 61 : 64, a)}`)}Z"/>
    ${ring(22, (a, i) => `<path class="hs-spr hs-spr${i % 3}" transform="translate(${pt(i % 2 ? 67.5 : 69.5, a + 6)}) rotate(${(i * 47) % 180})" d="M-1.6 0h3.2"/>`)}
    <g transform="translate(${pt(66, 38)}) rotate(-28)"><g class="hs-rock"><path class="hs-gb" d="M0-14a5 5 0 1 1 0 .1ZM-4-9h8l9 5-2 4-7-3 1 9 5 9-4 2-6-8-6 8-4-2 5-9 1-9-7 3-2-4Z"/>
    <path class="hs-gbi" d="M-2-15h1m2 0h1M-2-11q2 1 4 0M-3 3q3 2 6 0M0-5v1m0 3v1M-8-6q-2 1-4 0M8-6q2 1 4 0"/></g></g>`);
  const northtrain = svg('rail', `<circle class="hs-rl" cx="50" cy="50" r="61.5"/><circle class="hs-rl" cx="50" cy="50" r="65.5"/>
    ${ring(40, a => `<path class="hs-tie" d="M${pt(59.5, a)}L${pt(67.5, a)}"/>`)}
    <g class="hs-run"><circle class="hs-trail" cx="${pt(63.5, -104).split(' ')[0]}" cy="${pt(63.5, -104).split(' ')[1]}" r="1.1"/><circle class="hs-trail" cx="${pt(63.5, -98).split(' ')[0]}" cy="${pt(63.5, -98).split(' ')[1]}" r="1.5"/>
    <circle class="hs-lglow" cx="50" cy="-13.5" r="7"/><circle class="hs-lamp" cx="50" cy="-13.5" r="2.3"/></g>
    <g transform="translate(108 -8) scale(5)"><path class="hs-star" d="${SPARK}"/></g>`);
  const rosequill = svg('rose', `<path class="hs-vine" d="M${pt(60, 150)}C${pt(70, 175)} ${pt(55, 195)} ${pt(62, 215)}S${pt(66, 245)} ${pt(60, 262)}"/>
    ${[160, 188, 228].map((a, i) => `<path class="hs-leaf" transform="translate(${pt(62 + (i % 2) * 3, a)}) rotate(${a + (i % 2 ? 50 : -40)}) scale(7)" d="M0 0C.15-.55.7-.62 1 0C.7.55.15.5 0 0Z"/>`).join('')}
    ${[172, 205, 240].map(a => `<path class="hs-thorn" transform="translate(${pt(64, a)}) rotate(${a})" d="M0-1l3 1-3 1Z"/>`).join('')}
    <g transform="translate(${pt(60, 264)})"><g class="hs-bud"><path class="hs-pt hs-pt1" d="M0 2Q-7-1-5-8Q-2-6 0-4Z"/><path class="hs-pt hs-pt1" d="M0 2Q7-1 5-8Q2-6 0-4Z"/>
    <path class="hs-pt" d="M0 1Q-4-4 0-10Q4-4 0 1Z"/><path class="hs-sepal" d="M-4 3Q0 1 4 3L0 6Z"/></g><path class="hs-fall" d="M2-4q3-2 5 1-2 3-5 1Z"/></g>`);
  const prism = (x, y, ang, L, w) => `<g transform="translate(${x} ${y}) rotate(${ang})"><path class="hs-cf1" d="M0 ${-w}L${L} ${-w * .6}L${L + w * 1.6} 0L${L} ${w * .6}L0 ${w}Z"/><path class="hs-cf2" d="M0 0L${L} ${-w * .6}L${L + w * 1.6} 0Z"/><path class="hs-ce" d="M0 0H${L + w * 1.6}"/></g>`;
  const clus = (a, specs) => { const [x, y] = pt(55, a).split(' '); return specs.map(([d, L, w]) => prism(x, y, a + d, L, w)).join(''); };
  const crystalheart = svg('cryst', `${clus(38, [[-22, 12, 2.6], [0, 20, 3.4], [20, 9, 2.2], [36, 6, 1.6]])}${clus(218, [[-14, 9, 2.2], [8, 13, 2.8], [28, 5, 1.4]])}
    <g transform="translate(${pt(78, 38)}) scale(3.2)"><path class="hs-glint" d="${SPARK}"/></g>
    <g class="hs-orb"><circle class="hs-tw1" cx="${pt(71, -60).split(' ')[0]}" cy="${pt(71, -60).split(' ')[1]}" r="2"/><circle class="hs-tw2" cx="${pt(71, 120).split(' ')[0]}" cy="${pt(71, 120).split(' ')[1]}" r="2"/></g>`);
  if (typeof _AP_DECOR !== 'undefined') Object.assign(_AP_DECOR, { ravenmask: ravenmask, ghostcoach: ghostcoach.join(''), sugarhouse: sugarhouse, northtrain: northtrain, rosequill: rosequill, crystalheart: crystalheart });
})();
