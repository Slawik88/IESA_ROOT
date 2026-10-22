// ── Набор «Тайное Знание»: сцены и фирменные детали трёх образов ────────────────────────────────────────────
// Три разных способа показать знание, три разные композиции (не «предмет слева + предмет справа»):
// Тихая Библиотека — диагональ: луч из высокого окна идёт через всю сцену, пыль живёт только в нём, внизу стол со свечой. Движение почти замерло.
// Лаборатория Алхимика — снизу вверх: эликсир кипит по всему низу, пузыри и пар поднимаются, на полу круг стихий, на SSS вспышка превращения.
// Живой Гримуар — вихрь: кольцо рун медленно вращается вокруг всего героя, страницы вырываются из книги на кафедре и улетают вверх, буквы всплывают.
// Средняя колонка (аватар, ник, значки) свободна: крупные предметы стоят у краёв и в самом низу. Картинки: tools/scene_art_f.py.
_scAdd('quiet_library', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'linear-gradient(200deg, #2a1d1299, transparent 46%), linear-gradient(0deg, #1c140c, #0f0c08 70%)'}],
  [2, 'sil i-libShelves', {l:'-6%',b:'-2%',w:'30%',h:'62%',o:.5}],
  [3, 'sil i-libWindow', {r:'1%',t:'6%',w:'16%',h:'50%',o:.32}],
  [3, 'band breathe', {l:'26%',t:'-20%',w:'30%',h:'150%',rot:'38deg',org:'50% 0%',o:.9,bg:'linear-gradient(90deg, transparent, #fff4dc14 30%, #fff4dc24 50%, #fff4dc14 70%, transparent)',dur:9}],
  [4, 'dot float', {l:'52%',t:'18%',s:'2px',c:'#fff4dc',o:.75,bs:_scBs([[-20,30,1,0,'#fff4dc'],[-44,62,1,0,'c'],[-70,96,1,0,'#fff4dc'],[-96,128,1,0,'c'],[-30,84,1,0,'#fff4dc'],[-58,140,1,0,'#fff4dc']]),dx:'6px',dy:'-8px',dur:14}],
  [4, 'dot float w2', {l:'46%',t:'30%',s:'1.5px',c:'#e9d3a3',o:.6,bs:_scBs([[-14,20,1,0,'#e9d3a3'],[-40,52,1,0,'#fff4dc'],[-64,88,1,0,'#e9d3a3'],[-88,120,1,0,'#fff4dc']]),dx:'-5px',dy:'-10px',dur:19,del:-7}],
  [5, 'sil i-libDesk', {r:'-2%',b:'-3%',w:'34%',h:'58%'}],
  [5, 'glow flicker', {r:'4%',b:'26%',w:'18%',h:'24%',c:'#ffd38a',k:'40%',dur:5}],
  [6, 'sil m i-libPage float', {l:'40%',t:'12%',w:'20px',h:'26px',c:'#fff4dc',o:.55,rot:'-12deg',dx:'-26px',dy:'18px',dur:17}],
  [7, 'glow drift', {l:'-14%',b:'4%',w:'46%',h:'40%',c:'#ffe3a8',k:'16%',dx:'6%',dur:21}],
  [7, 'dot twinkle', {l:'3%',b:'40%',s:'2px',c:'#e9d3a3',bs:_scBs([[18,40,2,0,'#e9d3a3'],[40,80,2,0,'c'],[8,118,2,0,'#e9d3a3']]),dur:6}],
]);
_scAdd('alchemist', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'radial-gradient(ellipse at 50% 120%, #3fcf8644, transparent 60%), linear-gradient(180deg, #050b08, #0b1a12)'}],
  [2, 'wave go i-alcLiquidTile m', {l:'0',b:'-3%',w:'calc(100% + 160px)',h:'15%',tw:'160px',c:'#3fcf86',o:.55,dur:6}],
  [3, 'wave go i-alcLiquidTile m rev w2', {l:'-160px',b:'-1%',w:'calc(100% + 160px)',h:'11%',tw:'160px',c:'#8cf2b0',o:.25,dur:9}],
  [3, 'sil m i-alcSigils st breathe', {l:'calc(50% - 130px)',b:'2%',w:'260px',h:'54px',c:'#8cf2b0',o:.3,dur:6}],
  [4, 'sil i-alcShelf', {r:'-4%',t:'4%',w:'22%',h:'40%',o:.8}],
  [4, 'dot rise', {l:'8%',b:'6%',s:'3px',c:'#8cf2b0',o:.8,bs:_scBs([[30,0,1,0,'#e9fff2'],[90,4,1,0,'#8cf2b0'],[150,-2,1,0,'#e9fff2'],[210,2,1,0,'#8cf2b0'],[270,0,1,0,'#e9fff2']]),dx:'4px',dy:'-46px',s0:'.6',s1:'1.2',dur:3.4}],
  [5, 'sil i-alcRetort', {r:'1%',b:'-2%',w:'28%',h:'56%'}],
  [5, 'glow flicker', {r:'9%',b:'-8%',w:'18%',h:'20%',c:'#d8973f',k:'46%',dur:2.4}],
  [6, 'dot rise w2', {r:'4%',b:'26%',s:'4px',c:'#8cf2b0',o:.5,bs:_scBs([[-6,-4,4,1,'#8cf2b0'],[4,-10,4,1,'#e9fff2']]),dx:'-14px',dy:'-90px',s0:'.6',s1:'2',dur:5}],
  [6, 'dot rise', {l:'40%',b:'2%',s:'2px',c:'#d8973f',bs:_scBs([[20,0,2,0,'#ffd88a'],[60,-6,2,0,'#d8973f'],[100,2,2,0,'#ffd88a']]),dx:'0px',dy:'-120px',s0:'1',s1:'.4',dur:6,del:-2}],
  [7, 'glow flash', {l:'-10%',t:'-10%',w:'120%',h:'120%',c:'#8cf2b0',k:'18%',dur:11}],
  [7, 'dot twinkle', {l:'calc(50% - 2px)',b:'8%',s:'3px',c:'#ffd88a',bs:_scBs([[-110,-6,3,1,'#ffd88a'],[110,-6,3,1,'#ffd88a'],[-60,-18,3,1,'#8cf2b0'],[60,-18,3,1,'#8cf2b0']]),dur:3}],
]);
_scAdd('grimoire', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'radial-gradient(ellipse at 50% 60%, #7a52e033, transparent 62%), linear-gradient(180deg, #07050e, #120c22)'}],
  [2, 'dot twinkle', {l:'10%',t:'12%',s:'2px',c:'#ffe6a8',bs:_scBs([[60,40,1,0,'#ffe6a8'],[170,10,1,0,'c'],[240,70,1,0,'#ffe6a8'],[300,20,1,0,'a']]),dur:5.5}],
  [3, 'sil m i-grimRunes spin rev', {l:'calc(50% - 220px)',t:'calc(50% - 220px)',w:'440px',h:'440px',c:'#c9b2ff',o:.13,dur:150}],
  [4, 'sil i-grimLectern', {r:'-1%',b:'-3%',w:'30%',h:'52%'}],
  [4, 'sil i-grimCandles', {l:'-3%',b:'-3%',w:'20%',h:'34%',o:.9}],
  [5, 'glow flicker', {l:'0%',b:'14%',w:'16%',h:'20%',c:'#ffcf7a',k:'40%',dur:4}],
  [5, 'glow breathe', {r:'4%',b:'18%',w:'24%',h:'26%',c:'#c9b2ff',k:'30%',dur:5}],
  [6, 'sil m i-grimPage cross', {r:'12%',b:'26%',w:'18px',h:'24px',c:'#e9dcc0',o:.8,rot:'-16deg',fx:'0px',fy:'0px',tx:'-260px',ty:'-150px',dur:11}],
  [6, 'sil m i-grimPage cross w2', {r:'10%',b:'28%',w:'14px',h:'18px',c:'#ddcfae',o:.65,rot:'14deg',fx:'0px',fy:'0px',tx:'-200px',ty:'-190px',dur:14,del:-6}],
  [7, 'dot rise', {r:'15%',b:'30%',s:'2px',c:'#ffe6a8',bs:_scBs([[-8,0,2,0,'#ffe6a8'],[6,-6,2,0,'#c9b2ff'],[-2,-14,2,0,'#ffe6a8']]),dx:'-30px',dy:'-120px',s0:'1',s1:'.5',dur:5}],
  [7, 'sil m i-grimPage cross', {r:'14%',b:'24%',w:'16px',h:'20px',c:'#ffe6a8',o:.7,rot:'30deg',fx:'0px',fy:'0px',tx:'-320px',ty:'-90px',dur:17,del:-3}],
]);

// Фирменные детали (рамка аватара, холст -30..130, кольцо ≈ 57): свеча на оправе и лента-закладка; уроборос вокруг кольца и четыре стихии;
// раскрытая книга над кольцом листает сама себя, буквы уходят по дуге, руны на кольце загораются по очереди. Цвет и движение: skin-sig-d-v3.css.
(() => {
  const R = n => Math.round(n * 10) / 10;
  const xy = (r, deg) => [R(50 + r * Math.cos(deg * Math.PI / 180)), R(50 + r * Math.sin(deg * Math.PI / 180))];
  const pt = (r, deg) => xy(r, deg).join(' ');
  const svg = (name, inner) => `<svg class="sa sk-${name}" viewBox="-30 -30 160 160" aria-hidden="true">${inner}</svg>`;
  const arc = (r, a0, a1) => `M${pt(r, a0)}A${r} ${r} 0 ${(a1 - a0) % 360 > 180 ? 1 : 0} 1 ${pt(r, a1)}`;

  const [cx, cy] = xy(57, -40);
  const candlelit = svg('candle', `<g transform="translate(${cx} ${cy})">
    <path class="sk-wax" d="M-4.5 2V-14h9V2Z"/><path class="sk-drip" d="M-4.5-14q0 6 1.5 9 1.5-3 1.5-9M2-14q0 4 1.2 7 1.3-2 1.3-7"/>
    <path class="sk-wick" d="M0-14v-3"/><circle class="sk-halo" cx="0" cy="-21" r="9"/>
    <g class="sk-flame"><path class="sk-fl" d="M0-17q-4-5 0-11 4 6 0 11Z"/><path class="sk-core" d="M0-18q-1.6-2.4 0-5 1.6 2.6 0 5Z"/></g>
    <path class="sk-base" d="M-7 2h14l-2 3H-5Z"/></g>
    <g transform="translate(${pt(57, 128)})"><g class="sk-ribbon"><path class="sk-rib" d="M0 0q-2 10 1 20 2 8-1 16l-3 4 4-1 3 3 0-6q2-8-1-16-3-9-1-20Z"/></g></g>
    <g class="sk-mote"><circle cx="${R(cx - 6)}" cy="${R(cy - 30)}" r=".9"/><circle cx="${R(cx + 7)}" cy="${R(cy - 26)}" r=".7"/></g>`);

  const scales = Array.from({ length: 28 }, (_, i) => { const a = -70 + i * 11.5; return `<path class="sk-scale" transform="translate(${pt(64, a)}) rotate(${R(a + 90)})" d="M-2.4-1q2.4 2.6 4.8 0"/>`; }).join('');
  const elements = ['M-4 3 0-4 4 3Z', 'M-4-3 0 4 4-3Z', 'M-4 3 0-4 4 3ZM-3 0h6', 'M-4-3 0 4 4-3ZM-3 0h6']
    .map((d, i) => `<path class="sk-el sk-el${i}" transform="translate(${pt(77, 45 + i * 90)})" d="${d}"/>`).join('');
  const [hx, hy] = xy(64, -76);
  const ouroboros = svg('ouro', `<g class="sk-turn"><path class="sk-body" d="${arc(64, -70, 266)}"/><path class="sk-belly" d="${arc(64, -70, 266)}"/>${scales}
    <g transform="translate(${hx} ${hy}) rotate(14)"><path class="sk-head" d="M-5-5Q4-7 8 0Q4 7-5 5Q-3 0-5-5Z"/><circle class="sk-eye" cx="2" cy="-1.8" r="1"/><path class="sk-jaw" d="M8 0l-5 1.6"/></g></g>${elements}`);

  const glyphs = ['M0-3v6M0-1l2-2', 'M-2-3v6M-2-3l3 2-3 2', 'M2-3-2 0l4 3', 'M-2-3 2 3M2-3-2 3'];
  const runes = Array.from({ length: 8 }, (_, i) => `<path class="sk-rune" style="--i:${i}" transform="translate(${pt(61, -150 + i * 45)}) rotate(${-60 + i * 45})" d="${glyphs[i % 4]}"/>`).join('');
  const [bx, by] = xy(66, -128);
  const grimoire = svg('grim', `${runes}<g transform="translate(${bx} ${by}) rotate(-18)"><g class="sk-hover">
    <circle class="sk-aura" cx="0" cy="0" r="14"/>
    <path class="sk-cover" d="M-15 4-14-6Q-7-9 0-6Q7-9 14-6L15 4Q7 1 0 4Q-7 1-15 4Z"/>
    <path class="sk-pg" d="M-13 2-12.5-6Q-6-8.5 0-6V3Q-6 0-13 2Z"/><path class="sk-pg" d="M13 2 12.5-6Q6-8.5 0-6V3Q6 0 13 2Z"/>
    <path class="sk-ln" d="M-11-3q4-1.5 9 0M-11-.6q4-1.5 9 0M2-3q4-1.5 9 0M2-.6q4-1.5 9 0"/>
    <path class="sk-flip" d="M0-6Q6-8.5 12.5-6L13 2Q6 0 0 3Z"/><path class="sk-clasp" d="M15 0q4 0 4 4v8"/></g></g>
    <g class="sk-drift"><path class="sk-gl" style="--d:0s" transform="translate(${R(bx + 10)} ${R(by - 14)})" d="${glyphs[0]}"/><path class="sk-gl" style="--d:-2s" transform="translate(${R(bx + 20)} ${R(by - 8)})" d="${glyphs[2]}"/><path class="sk-gl" style="--d:-4s" transform="translate(${R(bx + 28)} ${R(by + 2)})" d="${glyphs[3]}"/></g>`);

  if (typeof _AP_DECOR !== 'undefined') Object.assign(_AP_DECOR, { candlelit: candlelit, ouroboros: ouroboros, grimoire: grimoire });
})();
