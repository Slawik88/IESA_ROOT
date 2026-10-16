/* Independent prototype mechanics probe. No browser, source writes, network or production state. */
'use strict';
const fs=require('fs'),vm=require('vm'),path=require('path'),crypto=require('crypto');
const dir=__dirname,sourcePath=path.join(dir,'../FastAPI/static/pet-practice-game.js');
function load(){
 const html=fs.readFileSync(sourcePath,'utf8');
 let script=html;
 script=script.replace(/const sleep=ms=>[^\n]*;/,'const sleep=async()=>{};');
 const hook=`
 render=()=>{};renderPanel=()=>{};hit=()=>{};save=()=>{};
 globalThis.game={
  fresh(seed,contract,layout){state=base(undefined,seed,contract);state.layout=layout;state.status='playing';busy=false;mode='walk';travel=null;reveal();return structuredClone(state);},
  put(value){epoch++;state=structuredClone(value);busy=false;travel=null;mode='walk';selected=null;panel='';},
  get(){return structuredClone(state);},
  restoreSnapshot(value){restore(value);return {state:structuredClone(state),rescueCell,mode,panel};},
  scan(direction){return {cells:scanCells(direction),benefit:sniffBenefit(direction)};},
  addRecord(status,turn,hp){state.status=status;state.turn=turn;state.hp=hp;state.recorded=false;record();return structuredClone(state.memory);},
  async act(a){if(a.type==='chest'){const steps=solveSeals(state.seals,code().map(x=>sealKeys.indexOf(x)));for(const i of steps)state.seals=rotateSeals(state.seals,i);a={...a,correct:sealsMatch(),freeRotations:steps.length};}await commit(a);return {state:structuredClone(state),action:a};},
  recordKey,neighbors,dist,ground,occupied,actionFor,intents,forecast,
  legalMoves(){const result=[];for(let i=0;i<42;i++){mode='walk';if(canMove(i))result.push({type:'move',to:i});mode='dash';if(canMove(i))result.push({type:'dash',to:i});}mode='walk';return result;},
  sniff(){return sniffBenefit();}
 };return;
 `;
 const needle='restore(window.PetPractice?.widgetState);render();';
 if(!script.includes(needle))throw Error('Startup hook missing');
 script=script.replace(needle,hook);
 function element(){return {children:[],dataset:{},style:{},classList:{add(){},remove(){},toggle(){}},append(x){this.children.push(x)},appendChild(x){this.children.push(x)},addEventListener(){},contains(){return false},querySelector(){return element()},querySelectorAll(){return []},setAttribute(){},focus(){},innerHTML:'',textContent:'',hidden:false};}
 const root=element(),elements=new Map();root.querySelector=(s)=>{if(!elements.has(s))elements.set(s,element());return elements.get(s)};
 const context=vm.createContext({structuredClone,crypto,console,setTimeout,clearTimeout,document:{getElementById(){return root},createElement:element,addEventListener(){}},window:{matchMedia(){return {matches:true}},addEventListener(){}},globalThis:null});
 context.globalThis=context;vm.runInContext(script,context,{filename:sourcePath,timeout:10000});
 return {game:context.game,sha256:crypto.createHash('sha256').update(html).digest('hex')};
}

module.exports={load};
