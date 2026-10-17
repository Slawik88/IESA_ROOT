// Chart maths of the coin exchange: the module must only draw server ticks and
// stay a pure function of them (no DOM, no network, no price generation).
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const ctx=vm.createContext({window:{}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../FastAPI/static/coin-market-chart.js'),'utf8'),ctx);
const C=ctx.window.CM2Chart,{PLOT,W,H}=C;
const close=(got,want,eps=.51)=>assert(Math.abs(got-want)<=eps,`expected ${want}, got ${got}`);
const series=(values,from=100)=>values.map((value,index)=>({tick:from+index,price:String(value)}));
const values=list=>list.map(p=>({tick:p.tick,value:Number(p.price)}));

assert.equal(typeof C.render,'function','render stays the public entry point');
assert.equal(PLOT.x0,10);assert.equal(PLOT.x1,W-12);assert.equal(PLOT.y1,H-26,'time labels need room under the plot');

// bounds: а flush series must not collapse into a zero-height plot; values order is free
assert.deepEqual({...C.bounds([3,1,2])},{min:1,max:3});
assert.deepEqual({...C.bounds([])},{min:0,max:1},'an empty series cannot produce NaN bounds');
const flat=C.bounds([5,5,5]);assert(flat.min<5&&flat.max>5,'a flat series gets air so the line stays visible');
assert(flat.max-flat.min<.2,'air must stay proportional to the price');

// path: x spacing is uniform, y follows the price, the ends touch the plot frame
assert.equal(C.path([],{min:0,max:1}),'');
const one=C.path([7],{min:6,max:8});assert.match(one,/^M/);assert.equal(one,`M${((PLOT.x0+PLOT.x1)/2).toFixed(2)},${((PLOT.y0+PLOT.y1)/2).toFixed(2)}`);
const line=C.path([1,2,3],{min:1,max:3}).split(' ');
assert.equal(line.length,3);assert.equal(line[0][0],'M');
const [x0,yLow]=line[0].slice(1).split(',').map(Number),[xm,ym]=line[1].slice(1).split(',').map(Number),[x1,yHigh]=line[2].slice(1).split(',').map(Number);
assert.equal(x0,PLOT.x0);assert.equal(x1,PLOT.x1);close(xm,(PLOT.x0+PLOT.x1)/2);
assert.equal(yLow,PLOT.y1);assert.equal(yHigh,PLOT.y0);close(ym,(PLOT.y0+PLOT.y1)/2);
assert(C.path([1,2,3],{min:1,max:3}).match(/L/g).length===2,'every point after the first is a line command');

// label: server tick numbers become UTC axis captions
assert.equal(C.label(0,1,300),'00:00');assert.equal(C.label(288,24,300),'00:00');
assert.equal(C.label(288,168,300),'02.01','a week-long window shows dates, not clock time');
assert.equal(C.label(1,24,300),'00:05','one tick equals 300 server seconds');

// downsample: keeps both ends and the order, never invents points
const many=series([...Array(1000).keys()]);
const thin=C.downsample(many,300);assert.equal(thin.length,300,'the cap is exact, not a ceiling');
assert.equal(thin[0].tick,many[0].tick);assert.equal(thin.at(-1).tick,many.at(-1).tick);
assert(thin.every((p,i)=>i===0||p.tick>thin[i-1].tick),'downsampling keeps ticks ordered and unique');
assert.equal(thin[1].tick,many[Math.round(999/299)].tick,'the kept points are real published ticks, evenly spaced');
assert.equal(C.downsample([],300).length,0);
const small=series([1,2]);assert.equal(C.downsample(small,300),small,'a short series is returned as is');

// nearest: a tap maps to the closest published tick, misses far outside the plot are ignored
assert.equal(C.nearest(159,320,3),1);assert.equal(C.nearest(159,0,3),-1,'a hidden chart cannot resolve taps');
assert.equal(C.nearest(0,320,3),0,'edge taps still clamp to the nearest end tick');
assert.equal(C.nearest(-999,100,3),-1,'a tap far outside the frame is a miss');assert.equal(C.nearest(9999,100,3),-1);
assert.equal(C.nearest(-999,320,1),0,'a single tick is always the answer');
assert.equal(C.nearest(159,320,0),-1);

// markers: a trade sits on its own tick and on its own price
const data=series([1,2,3,4]),marker=C.markerPoints([{tick:101,value:2,side:'buy'}],values(data),{min:1,max:4})[0];
close(marker.x,PLOT.x0+(PLOT.x1-PLOT.x0)/3);close(marker.y,PLOT.y1-(PLOT.y1-PLOT.y0)/3);
assert.equal(marker.side,'buy');assert.equal(marker.price,2);
const late=C.markerPoints([{tick:9999,value:4,side:'sell'}],values(data),{min:1,max:4})[0];
assert.equal(late.x,PLOT.x1,'a marker after the window sticks to the last tick');

// tooltip: indexes outside the series clamp instead of throwing
const at=C.tooltipFor(values(data),{min:1,max:4});
assert.equal(at(-5).tick,100);assert.equal(at(99).tick,103);close(at(99).y,PLOT.y0);

console.log('OK: chart bounds, uniform path, UTC labels, downsample ends, tap radius, trade markers and tooltip clamping');
