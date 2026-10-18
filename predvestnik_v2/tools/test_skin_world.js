const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const dir=path.join(__dirname,'../FastAPI/static');
const nodes=new Map(),classes=new Set();
const document={getElementById:id=>nodes.get(id),body:{classList:{add:x=>classes.add(x),remove:x=>classes.delete(x)},prepend:n=>nodes.set(n.id,n)},createElement:()=>({dataset:{},setAttribute(){},remove(){nodes.delete(this.id)}})};
const box={document,window:{}};vm.createContext(box);
for(const n of [35,36,37,38,48])vm.runInContext(fs.readFileSync(path.join(dir,`app.${n}.js`),'utf8'),box);
const ids=vm.runInContext('[..._AP_SCENES.keys()]',box),apply=box.window.applySkinWorldV3;
for(const id of ids)for(const tier of ['D','C','B','A','S','SS','SSS']){
 const look={id,tier,pal:['#aabbcc','#112233','#fedcba'],kinds:{bg:'mesh'}};
 assert.equal(apply(look),true);const root=nodes.get('skin-world');
 const html=root.innerHTML;assert((html.match(/class="sc /g)||[]).length<=8);
 for(const match of html.matchAll(/class="sc ([^"]*)"/g))if(/\b(?:sil|wave)\b/.test(match[1]))assert(/\bi-[a-zA-Z0-9]+\b/.test(match[1]),`${id}: lost artwork class`);
 assert(!/class="sc [^"]*\b(?:drift|pulse|spin|sway|w2|rise|peek|sweep|twinkle)\b/.test(html));
 if(tier==='D')assert(!html.includes('class="sc '));
 apply(look);assert.equal(root.innerHTML,html);assert.equal(nodes.size,1);
}
for(const look of [null,{id:'forest',tier:'SSS',pal:['red','#123456','#654321'],kinds:{bg:'mesh'}},{id:'foreign',tier:'S',pal:['#123456','#123456','#123456'],kinds:{bg:'mesh'}}]){
 assert.equal(apply(look),false);assert.equal(nodes.size,0);assert(!classes.has('has-skin-world'));
}
apply({id:'aurora',tier:'SSS',pal:['#123456','#123456','#123456'],kinds:{bg:'vortex'}});
assert(nodes.get('skin-world').innerHTML.includes('i-curtain2'));
const css=fs.readFileSync(path.join(dir,'skin-world-v3.css'),'utf8');
assert(/\.ap-bg-vortex b:first-child\s*\{ filter:none/.test(css));
const profile=fs.readFileSync(path.join(dir,'app.20.js'),'utf8');assert(profile.includes('ownWorld && document.getElementById'));
assert(fs.readFileSync(path.join(dir,'app.15.js'),'utf8').includes('apStage(ap, identity, true)'));
assert(!fs.readFileSync(path.join(dir,'app.23.js'),'utf8').includes('applySkinWorldV3'));
console.log(`PASS: ${ids.length} scenes x 7 tiers; bounded static layers, removal, validation, preview isolation`);
