// Execute the complete UI against an HTTP double that loses responses before
// or after the server commit. Storage survives a fresh JS runtime (page reload).
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../FastAPI/static/coin-market-v2.js'),'utf8');
const market={user_id:12,enabled:true,shorts_enabled:true,balances:{mora:'100'},news:[],shorts:[],
 coins:[{id:'orb',name:'Orbit',ticker:'ORB',price:'1',units:'1000',cost:'1',sell_value:'1',result:'0',
 character:'flow',group:'sky',change_24h:0,change_period:'24ч'}]};

function runtime(storage,server){
 const host={innerHTML:'',querySelector:()=>null};
 const nodes={'pg-exchange-v1':host,'cm2-amount':{value:'10'},'cm2-units':null,
  'cm2-preview':{innerHTML:''},'cm2-message':{textContent:'',classList:{toggle(){}}}};
 const context={window:{},document:{hidden:false,getElementById:id=>nodes[id],querySelectorAll:()=>[]},
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  Headers,AbortController,setTimeout,clearTimeout,setInterval:()=>1,clearInterval(){},
  crypto:{randomUUID:()=> 'same-action-id-12'},BASE:'',fetch:server,console};
 vm.runInContext(source,vm.createContext(context));
 return context.window.CM2;
}
async function scenario(afterCommit){
 const storage=new Map(),posts=[];let receipt=null,debits=0,release;
 let lose=true;
 const response=(value,status=200)=>({ok:status<400,status,json:async()=>structuredClone(value)});
 const server=async(url,options)=>{
  const path=url.replace('/coin-market/v2','');
  if(path.startsWith('/me'))return response(market);
  if(path.endsWith('/history?hours=24'))return response({points:[],markers:[],cost:null});
  if(path==='/quote')return response({spent:'10',received_units:'9950',commission:'0.05',tick:1,price:'1'});
  if(path==='/trade'){
   const body=JSON.parse(options.body);posts.push(body);
   const commit=()=>{if(!receipt){debits++;receipt={ok:true,side:'buy',coin_id:'orb'};}};
   if(lose){lose=false;if(afterCommit)commit();await new Promise(r=>{release=r;});throw Error('lost response');}
   commit();return response({...receipt,replayed:true});
  }
  if(path.startsWith('/receipt/'))return receipt?response(receipt):response({detail:'not yet found'},404);
  throw Error('Unexpected path '+path);
 };
 let ui=runtime(storage,server);
 await ui.load();await ui.coin('orb');ui.deal('buy');await ui.preview('buy');
 const inFlight=ui.confirm();
 await ui.confirm(); // Busy must suppress a second click.
 ui.home(); // Navigating away while awaiting POST must not erase saved action.
 assert.equal(posts.length,1);assert(storage.has('cm2_pending_12'));
 release();await inFlight;
 const saved=JSON.parse(storage.get('cm2_pending_12'));
 assert.equal(saved.body.action_id,'same-action-id-12');
 ui=runtime(storage,server);await ui.load();await ui.check();
 if(!afterCommit){
  assert(storage.has('cm2_pending_12'),'receipt404 cannot erase a potentially uncommitted operation');
  await ui.retry();assert.deepEqual(posts[1],posts[0],'retry must reuse exact payload and action id');
 }
 assert.equal(debits,1,'exactly one server mutation despite lost response/reload');
 assert(!storage.has('cm2_pending_12'),'confirmed receipt clears pending storage');
}
async function main(){await scenario(false);await scenario(true);
 console.log('PASS: lost POST before/after commit, double click, navigation, full reload, receipt404 and exact retry');}
main().catch(e=>{console.error(e);process.exitCode=1;});
