const fs=require('node:fs'),vm=require('node:vm');global.window=global;
vm.runInThisContext(fs.readFileSync(require('node:path').join(__dirname,'../FastAPI/static/local-games-v1.js'),'utf8'));
const fixtures=JSON.parse(fs.readFileSync(0,'utf8'));
console.log(JSON.stringify(fixtures.map(({packet,actions})=>{
  const engine=new PVLocal.Mines(packet);return actions.map(a=>engine.step(a.cell,a.kind,a.elapsed_ms));
})));
