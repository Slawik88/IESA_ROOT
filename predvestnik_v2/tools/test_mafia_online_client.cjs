// Execute the actual client functions with controlled network ACKs/storage.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const files=['app.55.js','app.56.js'].map(n=>fs.readFileSync(path.join(__dirname,'../FastAPI/static',n),'utf8')).join('\n');
function code(name){const start=files.search(new RegExp('^(?:async )?function '+name+'\\(','m'));assert(start>=0,name);const rest=files.slice(start),next=rest.slice(1).search(/^(?:async )?function /m);return next<0?rest:rest.slice(0,next+1);}
const storage=new Map(),nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',innerHTML:'',setAttribute(){},removeAttribute(){}});return nodes.get(id);}
const MO={gen:1,room:7,channel:'table',self:101,draftOwner:101,data:{channel:'table',me:{can_write:true}},busy:false,nonce:'',draft:'',reply:null};
let request=async()=>{},alive=true;
const context={MO,_uid:101,BASE:'',Headers,AbortController,setTimeout,clearTimeout,crypto:require('node:crypto').webcrypto,
  sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  el:node,esc:String,moAlive:()=>alive,moReady:()=>alive,moRefresh:async()=>{},moReplyMarkup:()=>{},moRequest:(...args)=>request(...args),
  moError:e=>e.message,moComposeState:()=>{},moPendingMessageDialog:()=>{},moSheetClose:()=>{},moPendingNotice:()=>{},moToast:()=>{},moShowError:e=>{node('mo-error').textContent=e.message;},document:{activeElement:null}};
vm.createContext(context);
for(const name of ['moOwner','moDraftKey','moStore','moRestore','moMessageKey','moPendingMessage','moRetryMessage','moBusy','moRunMessage','moSend','moCommandKey','moPendingCommand','moRunControl','moControl','moDiscardMessage','moDiscardControl'])vm.runInContext(code(name),context);
(async()=>{
  // Production hdrs() uses lowercase content-type; JSON must keep one value.
  const http={BASE:'',Headers,AbortController,setTimeout,clearTimeout,hdrs:()=>({'content-type':'application/json','x-user':'101'}),fetch:async(url,options)=>{
    assert.equal(options.headers.get('content-type'),'application/json');assert.equal(options.headers.get('x-user'),'101');return{ok:true,json:async()=>({ok:true})};}};
  vm.createContext(http);vm.runInContext(code('moJSONHeaders'),http);vm.runInContext(code('moRequest'),http);await http.moRequest('/quick',{});
  // A lost ACK + editing keeps the old immutable body and new draft separately.
  const sent=[];request=async(path,body)=>{sent.push(JSON.parse(JSON.stringify(body)));throw Error('lost ACK');};
  node('mo-text').value='Первое';await context.moSend();const original=sent[0];assert(original.nonce);
  node('mo-text').value='Следующий черновик';MO.draft=node('mo-text').value;MO.nonce='';context.moStore();
  await context.moSend();assert.equal(sent.length,1,'editing must not create another uncertain delivery');
  request=async(path,body)=>{sent.push(JSON.parse(JSON.stringify(body)));};await context.moRetryMessage();
  assert.deepEqual(sent[1],original);assert.equal(node('mo-text').value,'Следующий черновик');assert.equal(context.moPendingMessage(),null);
  await context.moSend();assert.equal(sent[2].text,'Следующий черновик');assert.notEqual(sent[2].nonce,original.nonce);assert.equal(node('mo-text').value,'');
  // Message/control receipts survive transient auth/rate limiting.
  for(const status of [401,403,429,503]){
    request=async()=>{throw Object.assign(Error('retry'),{status});};node('mo-text').value='Повтор '+status;await context.moSend();
    assert(context.moPendingMessage());storage.delete(context.moMessageKey());
    const payload={command:'pause',nonce:'control-'+status};storage.set(context.moCommandKey(),JSON.stringify(payload));await context.moRunControl(payload);assert(context.moPendingCommand());storage.delete(context.moCommandKey());
  }
  // Discard is local-only and preserves a newer draft; it cannot undo a committed send.
  let discardPosts=0;request=async()=>{discardPosts++;};
  const pending={text:'Previous delivery',channel:'table',reply_to:null,nonce:'discard-test'};
  storage.set(context.moMessageKey(),JSON.stringify(pending));
  node('mo-text').value='New draft';MO.draft='New draft';MO.reply=null;
  context.moDiscardMessage();assert.equal(context.moPendingMessage(),null);assert.equal(node('mo-text').value,'New draft');
  storage.set(context.moMessageKey(),JSON.stringify(pending));node('mo-text').value=pending.text;MO.draft=pending.text;
  context.moDiscardMessage();assert.equal(node('mo-text').value,'');assert.equal(MO.draft,'');
  storage.set(context.moCommandKey(),JSON.stringify({command:'pause',nonce:'discard-command'}));
  context.moDiscardControl();assert.equal(context.moPendingCommand(),null);assert.equal(discardPosts,0);
  // Success arriving after navigation removes the old committed draft; no resend.
  request=async()=>{alive=false;};node('mo-text').value='Уже отправлено';MO.draft=node('mo-text').value;await context.moSend();assert.equal(storage.has(context.moDraftKey()),false);alive=true;
  // A newly selected account cannot overwrite its storage with the previous text.
  MO.draft='Личное';MO.draftOwner=101;context._uid=202;context.moStore();assert.equal(storage.has(context.moDraftKey()),false);
  alive=false;const before=storage.size;request=async()=>{throw Error('must never POST under a changed owner');};
  await context.moControl('start');await context.moSend();assert.equal(storage.size,before);
  // The profile can bind a cold Telegram launch after the room opened as uid=0.
  const identity={MO:{gen:1,owner:0,self:0},_uid:0,Headers,hdrs:()=>({'x-session-token':'same-auth'}),el:id=>id==='modal'?{open:true}:{isConnected:true},moStop:()=>{identity.MO.gen++;}};
  vm.createContext(identity);for(const name of ['moOwner','moAuth','moAlive','moReady'])vm.runInContext(code(name),identity);
  identity.MO.auth=identity.moAuth();assert(identity.moAlive(1));identity._uid=101;assert(identity.moAlive(1),'0 to first profile identity is allowed');
  identity.MO.owner=101;identity.MO.self=101;assert(identity.moAlive(1));identity._uid=202;assert(!identity.moAlive(1));assert(!identity.moReady());
  console.log('PASS JSON header, frozen send replay after edits, transient receipts, ACK after navigation, owner-separated drafts, cold identity and pre-POST account guards');
})().catch(e=>{console.error(e);process.exitCode=1;});
