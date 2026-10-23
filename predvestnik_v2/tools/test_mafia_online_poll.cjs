// Execute the production poller: a late error cannot destroy a recovered room.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../FastAPI/static/app.55.js'),'utf8');
const start=source.indexOf('async function moPoll('),end=source.indexOf('async function moRefresh(',start);
const pending=[],root={innerHTML:'healthy'},connection={textContent:''};
const MO={gen:1,room:7,channel:'table',messages:new Map(),pollSeq:0,errors:0,data:null};
const context={MO,AbortController,document:{hidden:false},setTimeout:()=>1,
  moAlive:g=>g===MO.gen,moRequest:()=>new Promise((resolve,reject)=>pending.push({resolve,reject})),
  el:id=>id==='mo-root'?root:connection,moRenderRoom:()=>{},moChannel:()=>{throw Error('unexpected channel switch');},
  moStop:()=>{MO.gen++;},moPendingNotice:()=>{},moError:()=>''};
vm.createContext(context);vm.runInContext(source.slice(start,end),context);
(async()=>{
  const first=context.moPoll(1),second=context.moPoll(1);
  pending[1].resolve({version:2,me:{id:1},players:[],messages:[],channels:['table']});
  await second;
  assert.equal(MO.data.version,2);
  pending[0].reject(Object.assign(new Error('late forbidden'),{status:403}));
  await first;
  assert.equal(root.innerHTML,'healthy');assert.equal(MO.gen,1);assert.equal(MO.errors,0);
  MO.messages.set(1,{});MO.redactions=0;
  const old=context.moPoll(1),fresh=context.moPoll(1);
  pending[3].resolve({version:4,redactions:0,me:{id:1},players:[],messages:[],channels:['table']});
  await fresh;
  pending[2].resolve({version:3,redactions:1,me:{id:1},players:[],messages:[],channels:['table']});
  await old;
  assert.equal(pending.length,4,'an obsolete response must not start a redaction refetch with the new poll controller');
  assert.equal(MO.data.version,4);
  console.log('PASS stale poll errors and stale redaction responses cannot overwrite recovery or borrow the current abort controller');
})().catch(error=>{console.error(error);process.exitCode=1;});
