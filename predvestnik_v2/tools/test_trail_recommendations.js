const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../FastAPI/static/app.41.js'),'utf8');
const state={track:{},trial:{}};
let pets=[];
const ctx=vm.createContext({_tr:state,_trPet:id=>pets.find(p=>p.id===id),_trE:String,_trSec:x=>x,_trBestMark:on=>on?'BEST_MARK':'',fmt:String});
for(const name of ['_trTrackPicker','_trTrialPets'])vm.runInContext(source.match(new RegExp(`^function ${name}\\([\\s\\S]*?^\\}`,'m'))[0],ctx);
function check(points,matches,expectedTrack,expectedTrial){
  pets=points.map((n,i)=>({id:i+1,name:'Pet'+i,icon:'',level:5+i,track_points:n,trial:{matches:matches[i],hits:{}}}));
  const model={pets,track:{attempts_left:2},rules:{track:{daily:2,free_clues:3}}};
  const track=ctx._trTrackPicker(model),trial=ctx._trTrialPets(model,[]);
  assert.equal((track.match(/BEST_MARK/g)||[]).length,expectedTrack);
  assert.equal((trial.match(/BEST_MARK/g)||[]).length,expectedTrial);
}
check([3,3],[0,0],0,0);
check([4,3],[2,1],1,1);
check([4,4,2],[2,2,1],0,0);
check([3],[0],1,0);
check([],[],0,0);
console.log('OK: no false best pet for equal scores or zero trial matches; unique best and empty lists work');
