// Holiday scenes extend the master V3 scene engine. C ground → B light → A objects
// → S life → SS event → SSS signature. Deliberately no page-wide overlays/masks.
// Big objects stay in the lower corners at about half strength: the avatar and the name in the middle are never covered
// (2026-10-22 review: the first versions stood opaque over the avatar and the nickname in the profile and in «Образы»).
_scAdd('raven_masquerade', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'radial-gradient(ellipse at 50% 20%, #30143e99, transparent 75%)'}],
  [2, 'band', {l:'0',b:'0',w:'100%',h:'26%',bg:'linear-gradient(0deg,#201120aa,transparent)'}],
  [3, 'glow breathe', {l:'-20%',t:'-10%',w:'70%',h:'90%',c:'b',k:'35%',dur:12}],
  [3, 'dot twinkle', {l:'12%',t:'14%',s:'2px',c:'c',bs:_scBs([[55,14,2,0,'a'],[180,-7,2,0,'c'],[245,20,2,0,'a']]),dur:5}],
  [4, 'sil i-ravenMask', {l:'-9%',b:'-4%',w:'30%',h:'60%',bp:'0% 100%',o:.55}],
  [4, 'sil i-ravenKey', {r:'-8%',b:'-3%',w:'27%',h:'56%',bp:'100% 100%',o:.55}],
  [4, 'band', {l:'24%',t:'60%',w:'55%',h:'35%',bg:'radial-gradient(closest-side,#0b0712cc,transparent)'}],
  [5, 'sil m i-ravenKey sway', {r:'0',t:'6%',w:'65px',h:'100px',c:'c',o:.35,ang:'3deg',dur:9}],
  [5, 'dot float', {l:'17%',t:'30%',s:'2px',c:'c',bs:_scBs([[45,35,2,0,'c'],[230,45,2,0,'a']]),dx:'6px',dy:'-18px',dur:8}],
  [6, 'band sweep w2', {l:'0',t:'12%',w:'100%',h:'1px',bg:'linear-gradient(90deg,transparent,#ffe5ae88,transparent)',dur:23}],
  [7, 'ring', {l:'calc(50% - 132px)',t:'calc(50% - 132px)',w:'264px',h:'264px',c:'c',o:.18,bw:'1px'}],
]);
_scAdd('phantom_carriage', [
  [2, 'band', {l:'0',b:'0',w:'100%',h:'40%',bg:'radial-gradient(ellipse at 50% 100%,#43898544,transparent 80%)'}],
  [2, 'glow drift', {l:'-20%',b:'-10%',w:'140%',h:'40%',c:'a',k:'20%',dx:'8%',dur:32}],
  [3, 'sil i-ghostGate', {r:'-10%',t:'-4%',w:'40%',h:'96%',o:.4}],
  [3, 'glow breathe', {l:'-8%',t:'14%',w:'56%',h:'70%',c:'b',k:'24%',dur:11}],
  [4, 'sil i-ghostCoach', {l:'-9%',b:'-4%',w:'33%',h:'58%',bp:'0% 100%',o:.55}],
  [4, 'band', {l:'24%',t:'60%',w:'55%',h:'34%',bg:'radial-gradient(closest-side,#040e10cc,transparent)'}],
  [5, 'dot float', {r:'10%',t:'28%',s:'4px',c:'c',bs:'0 0 10px 3px #89f3da55',dx:'-8px',dy:'-16px',dur:6}],
  [5, 'glow drift', {l:'-20%',t:'48%',w:'140%',h:'12%',c:'a',k:'18%',dx:'-8%',dur:29}],
  [6, 'dot cross w2', {l:'0',t:'22%',s:'3px',c:'c',bs:'0 0 8px 2px #89f3da77',fx:'-30px',tx:'480px',ty:'25px',dur:24}],
  [7, 'sil m i-ghostGate', {l:'calc(50% - 150px)',t:'calc(50% - 175px)',w:'300px',h:'350px',c:'a',o:.18}],
]);
_scAdd('gingerbread_house', [
  [2, 'band', {l:'0',b:'0',w:'100%',h:'35%',bg:'linear-gradient(0deg,#9e573833,transparent)'}],
  [2, 'glow', {l:'-10%',b:'-10%',w:'120%',h:'40%',c:'b',k:'22%'}],
  [3, 'glow breathe', {l:'-8%',t:'10%',w:'64%',h:'75%',c:'a',k:'28%',dur:9}],
  [3, 'dot twinkle', {l:'10%',t:'12%',s:'2px',c:'c',bs:_scBs([[90,19,1,0,'c'],[210,-3,1,0,'a'],[265,28,1,0,'c']]),dur:6}],
  [4, 'sil i-sugarBakery', {l:'-9%',b:'-4%',w:'31%',h:'60%',bp:'0% 100%',o:.5}],
  [4, 'sil i-sugarTools', {r:'-8%',b:'-3%',w:'26%',h:'52%',bp:'100% 100%',o:.5}],
  [4, 'band', {l:'25%',t:'60%',w:'50%',h:'34%',bg:'radial-gradient(closest-side,#150b08dd,transparent)'}],
  [5, 'dot rise', {l:'10%',t:'42%',s:'2px',c:'c',bs:_scBs([[9,-9,2,0,'a'],[-8,-26,2,0,'c']]),dx:'8px',dy:'-50px',dur:9}],
  [5, 'glow pulse', {l:'0',b:'10%',w:'100px',h:'90px',c:'a',k:'24%',dur:5}],
  [6, 'sil m i-sugarTools float w2', {r:'6%',t:'1%',w:'40px',h:'50px',c:'c',o:.4,dx:'3px',dy:'-7px',dur:14}],
  [7, 'ring dash', {l:'calc(50% - 135px)',t:'calc(50% - 135px)',w:'270px',h:'270px',c:'c',o:.4,bw:'2px'}],
]);
_scAdd('polar_express', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'linear-gradient(180deg,#16304e88,transparent 70%)'}],
  [2, 'sil i-northBridge st', {l:'-4%',b:'-6%',w:'108%',h:'24%',o:.6}],
  [3, 'dot twinkle', {l:'9%',t:'9%',s:'2px',c:'c',bs:_scBs([[52,18,1,0,'c'],[124,-3,2,1,'a'],[235,20,1,0,'c'],[302,4,1,0,'a']]),dur:5}],
  [3, 'glow breathe', {r:'-10%',t:'-20%',w:'70%',h:'80%',c:'a',k:'26%',dur:13}],
  [4, 'sil i-northEngine', {r:'-10%',b:'-2%',w:'34%',h:'56%',bp:'100% 100%',o:.55}],
  [4, 'band', {l:'18%',t:'62%',w:'64%',h:'30%',bg:'radial-gradient(closest-side,#06101acc,transparent)'}],
  [5, 'glow rise', {r:'14%',t:'30%',w:'65px',h:'28px',c:'c',k:'20%',dx:'-30px',dy:'-38px',dur:9}],
  [5, 'dot float', {l:'8%',t:'22%',s:'2px',c:'c',bs:_scBs([[40,52,1,0,'c'],[110,12,1,0,'a'],[210,50,1,0,'c']]),dx:'-8px',dy:'16px',dur:11}],
  [6, 'band cross w2', {l:'0',t:'10%',w:'65px',h:'1px',bg:'linear-gradient(90deg,transparent,#ffe0a0)',fx:'-70px',tx:'480px',ty:'50px',dur:25}],
  [7, 'ring dash', {l:'calc(50% - 138px)',t:'calc(50% - 138px)',w:'276px',h:'276px',c:'c',o:.28,bw:'1px'}],
]);
_scAdd('rose_letter', [
  [2, 'band', {l:'0',b:'0',w:'100%',h:'32%',bg:'linear-gradient(0deg,#74394744,transparent)'}],
  [2, 'glow', {l:'-15%',t:'5%',w:'75%',h:'90%',c:'b',k:'20%'}],
  [3, 'glow breathe', {r:'-15%',t:'0',w:'65%',h:'80%',c:'a',k:'26%',dur:10}],
  [3, 'dot twinkle', {l:'17%',t:'16%',s:'2px',c:'c',bs:_scBs([[110,-8,2,0,'a'],[220,28,2,0,'c']]),dur:7}],
  [4, 'sil i-roseEnvelope', {l:'-10%',b:'-4%',w:'31%',h:'56%',bp:'0% 100%',o:.55}],
  [4, 'sil i-roseQuill', {r:'-9%',b:'-4%',w:'28%',h:'62%',bp:'100% 100%',o:.55}],
  [4, 'band', {l:'23%',t:'60%',w:'54%',h:'35%',bg:'radial-gradient(closest-side,#14090fdd,transparent)'}],
  [5, 'dot float', {l:'16%',t:'27%',s:'3px',c:'a',bs:_scBs([[235,55,2,0,'c'],[200,-10,2,0,'a']]),dx:'10px',dy:'14px',dur:12}],
  [6, 'glow pulse w2', {l:'-5%',b:'-5%',w:'110%',h:'35%',c:'a',k:'22%',dur:18}],
  [7, 'sil m i-roseQuill', {l:'calc(50% - 140px)',t:'calc(50% - 165px)',w:'280px',h:'330px',c:'c',o:.16}],
]);
_scAdd('glass_heart', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'radial-gradient(ellipse at 70% 35%,#4b2c6c66,transparent 75%)'}],
  [2, 'glow', {l:'-20%',b:'-20%',w:'140%',h:'55%',c:'b',k:'22%'}],
  [3, 'sil i-crystalArc', {l:'-8%',t:'-6%',w:'48%',h:'90%',o:.35}],
  [3, 'glow breathe', {r:'-10%',t:'5%',w:'70%',h:'80%',c:'a',k:'24%',dur:11}],
  [4, 'sil i-crystalHeart', {r:'-10%',b:'-4%',w:'30%',h:'58%',bp:'100% 100%',o:.55}],
  [4, 'band', {l:'24%',t:'60%',w:'52%',h:'34%',bg:'radial-gradient(closest-side,#0f0919dd,transparent)'}],
  [5, 'sil m i-crystalArc sway', {l:'-8%',t:'-6%',w:'48%',h:'90%',c:'c',o:.25,ang:'2deg',dur:16}],
  [5, 'dot twinkle', {l:'13%',t:'22%',s:'2px',c:'c',bs:_scBs([[55,45,2,0,'a'],[235,-4,2,0,'c']]),dur:6}],
  [6, 'band sweep w2', {l:'0',t:'22%',w:'100%',h:'2px',bg:'linear-gradient(90deg,transparent,#e4fbff77,transparent)',dur:21}],
  [7, 'sil m i-crystalArc', {l:'calc(50% - 155px)',t:'calc(50% - 185px)',w:'310px',h:'370px',c:'c',o:.18}],
]);

// Individual engraved medallions. The signature gate comes from the server.
if (typeof _AP_DECOR !== 'undefined') Object.assign(_AP_DECOR, {
  ravenmask: '<svg class="holiday-seal" viewBox="0 0 100 100"><path d="M25 42Q38 30 50 43Q65 30 76 42L69 61 56 66 50 58 43 66 30 61Z M34 46l9 3-7 5Z m23 3 9-3-2 8Z"/></svg>',
  ghostcoach: '<svg class="holiday-seal" viewBox="0 0 100 100"><path d="M30 34Q50 20 70 34L66 59H34Z M50 30v29 M28 62h44"/><circle cx="35" cy="68" r="8"/><circle cx="65" cy="68" r="8"/></svg>',
  sugarhouse: '<svg class="holiday-seal" viewBox="0 0 100 100"><path d="m25 46 25-24 25 24 M31 45v29h38V45 M44 74V56h12v18 M34 46q5 8 10 0t10 0 10 0"/></svg>',
  northtrain: '<svg class="holiday-seal" viewBox="0 0 100 100"><path d="M24 49h34V33h18v30H24Z M32 49V36h8v13 M62 37h8v9 M24 64h52"/><circle cx="37" cy="69" r="6"/><circle cx="63" cy="69" r="6"/></svg>',
  rosequill: '<svg class="holiday-seal" viewBox="0 0 100 100"><path d="M28 70V37h44v33Z m0-33 22 20 22-20 M28 70l18-17m26 17L54 53 M50 40q-15-9-8-15 5-4 8 1 4-5 8-1 7 6-8 15Z"/></svg>',
  crystalheart: '<svg class="holiday-seal" viewBox="0 0 100 100"><path d="m50 76-28-32 6-16h15l7 9 7-9h15l6 16Z M22 44h56 M28 28l22 48 22-48 M43 28l7 16 7-16"/></svg>',
});
