/* Local gameplay and durable delivery. No game action waits for a network. */
(() => {
  const clone = value => JSON.parse(JSON.stringify(value));
  const floor = Math.floor;
  async function request(url, options={}) {
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),12000);
    try{return await fetch(url,{...options,signal:controller.signal});}finally{clearTimeout(timeout);}
  }
  class Store {
    constructor(game, tg, session, init='') {
      let owner = tg?.initDataUnsafe?.user?.id;
      if(!owner&&init)try{owner=JSON.parse(new URLSearchParams(init).get('user')||'null')?.id;}catch(_){}
      let hash = 2166136261;
      for (const c of session || tg?.initData || 'anonymous') hash = Math.imul(hash ^ c.charCodeAt(0), 16777619);
      this.key = 'pv-local-v1:' + game + ':' + (owner || (hash >>> 0));
      this.data = { active: null, outbox: [] }; this.durable = true;
      try { this.data = JSON.parse(localStorage.getItem(this.key)) || this.data; } catch (_) {}
      this.data.outbox ||= []; this.data.delivered ||= []; this.data.rejected ||= [];
    }
    save() {
      try {
        const disk=JSON.parse(localStorage.getItem(this.key)||'null');
        this.data.delivered=[...new Set([...(disk?.delivered||[]),...this.data.delivered])];
        const pending=new Map([...(disk?.outbox||[]),...this.data.outbox].map(r=>[r.run_id,r]));
        this.data.outbox=[...pending.values()].filter(r=>!this.data.delivered.includes(r.run_id));
        localStorage.setItem(this.key, JSON.stringify(this.data)); return this.durable = true;
      } catch (_) { return this.durable = false; }
    }
    async fresh(game, difficulty='normal') {
      if(!this.data.template)return null;
      const p=clone(this.data.template);
      p.run_id=crypto.randomUUID();p.seed=Array.from(crypto.getRandomValues(new Uint8Array(32)),x=>x.toString(16).padStart(2,'0')).join('');
      p.origin={seed:p.seed,ruleset_version:p.ruleset_version||p.state.ruleset_version,difficulty:p.state.difficulty};
      if(game==='rhythm')p.state={status:'active',selected:[],perks:{owned:{},shield:0,ebb:0,bloody:0,miss_debt:0,recovery:0,weather:0},health:5,score:0,combo:0,correct_streak:0,correct_taps:0,mistakes:0,next_signal_no:1,signal_opened_at:null,finished_at:null,analysis:null};
      else {
        // Upgrade only NEW boards, never mutate an active packet or its journal.
        p.ruleset_version=p.origin.ruleset_version='minesweeper-v2';
        const [size,mineCount,label]={easy:[6,6,'Лёгкий'],normal:[9,10,'Средний'],hard:[9,18,'Сложный']}[difficulty];
        p.state={run_id:p.run_id,difficulty,label,size,mine_count:mineCount,ruleset_version:p.ruleset_version,status:'awaiting_first_open',revision:0,opened_actions:0,revealed:[],flags:[],changed:[],mines:[],elapsed_ms:0};
        p.origin.difficulty=difficulty;p.first_cell=null;p.layouts={};
        const seed=Uint8Array.from(p.seed.match(/../g),x=>parseInt(x,16));
        // The server shuffle hashes only seed+index. Compute its swaps once,
        // then prepare every first-cell board without network or input delay.
        const swapsFor=async source=>Promise.all(Array.from({length:size*size},async(_,i)=>{
          const data=new Uint8Array(36);data.set(source);new DataView(data.buffer).setUint32(32,i);
          const h=new Uint8Array(await crypto.subtle.digest('SHA-256',data));
          let value=0n;for(const byte of h.slice(0,8))value=value*256n+BigInt(byte);
          return Number(value%BigInt(i+1));
        }));
        const swapsByAttempt=new Map([[0,await swapsFor(seed)]]);
        const attemptSwaps=async attempt=>{
          if(!swapsByAttempt.has(attempt)){
            let source=new Uint8Array(32);
            if(attempt!==8){
              const salt=new TextEncoder().encode(':minesweeper-v2:'),data=new Uint8Array(32+salt.length+4);
              data.set(seed);data.set(salt,32);new DataView(data.buffer).setUint32(32+salt.length,attempt);
              source=new Uint8Array(await crypto.subtle.digest('SHA-256',data));
            }
            swapsByAttempt.set(attempt,await swapsFor(source));
          }
          return swapsByAttempt.get(attempt);
        };
        const engine=new Mines(p);
        for(let first=0;first<size*size;first++){
          const protectedCells=new Set([first,...engine.neighbours(first)]),candidates=[];
          for(let c=0;c<size*size;c++)if(!protectedCells.has(c))candidates.push(c);
          // Attempts 0..7 mirror core; attempt 8 is the verified zero-seed fallback.
          for(let attempt=0;attempt<=8;attempt++){
            const cells=[...candidates],swaps=await attemptSwaps(attempt);
            for(let i=cells.length-1;i>0;i--)[cells[i],cells[swaps[i]]]=[cells[swaps[i]],cells[i]];
            const layout=cells.slice(0,mineCount).sort((a,b)=>a-b);
            const trial=new Mines({state:p.state,first_cell:null,layouts:{[first]:layout}});
            if(trial.step(first,'open',0).status!=='won'){p.layouts[first]=layout;break;}
          }
          if(!p.layouts[first])throw new Error('Не удалось подготовить поле Сапёра.');
        }
      }
      return p;
    }
    async refreshRules(api) {
      const rules=await api('/local-rules');
      if(!this.data.template)return;
      const next=clone(this.data.template);
      next.ruleset_version=rules.ruleset_version;
      next.state.ruleset_version=rules.ruleset_version;
      if(rules.catalog){next.catalog=rules.catalog;next.legacy=false;}
      if(rules.weather)next.weather=rules.weather;
      this.data.template=next;this.save();
    }
    queue(packet, actions) {
      const result = { run_id: packet.run_id, actions: clone(actions), origin:packet.origin };
      if (!this.data.outbox.some(r => r.run_id === result.run_id)) this.data.outbox.push(result);
      this.data.active = null; this.save();
    }
    async flush(api, onResult = () => {}) {
      if (this.sending) return;
      this.sending = true;
      try {
        for (const result of [...this.data.outbox]) {
          try {
            const confirmed = await api('/runs/' + encodeURIComponent(result.run_id) + '/local-result',
              { method: 'POST', body: JSON.stringify({ actions: result.actions, origin:result.origin }) });
            this.data.delivered.push(result.run_id);
            this.data.outbox = this.data.outbox.filter(r => r.run_id !== result.run_id);
            this.save(); onResult(confirmed);
          } catch(error) {
            if(![400,409,422].includes(error.status))throw error;
            this.data.rejected.push({...result,error:error.message});this.data.delivered.push(result.run_id);
            this.data.outbox=this.data.outbox.filter(r=>r.run_id!==result.run_id);this.save();
            onResult({run_id:result.run_id,rejected:true,message:error.message});
          }
        }
      } finally { this.sending = false; }
    }
  }
  class Rhythm {
    constructor(packet, state = packet.state) {
      this.packet = packet; this.state = clone(state);
      this.catalog = Object.fromEntries(packet.catalog.map(p => [p.id, p]));
      this.key = crypto.subtle.importKey('raw', Uint8Array.from(packet.seed.match(/../g), x => parseInt(x, 16)),
        { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    }
    async hash(text) { return new Uint8Array(await crypto.subtle.sign('HMAC', await this.key, new TextEncoder().encode(text))); }
    total(field, p = this.state.perks) { return Object.entries(p.owned).reduce((n, [id, count]) => n + (this.catalog[id][field] || 0) * count, 0); }
    chunk() { return floor((this.state.next_signal_no - 1) / 20); }
    // Погода такта (core/rhythm_weather.py): по номеру блока, одинаково для всех; таблицу присылает сервер в пакете.
    ev(chunk = this.chunk()) { const w = this.packet.weather; if (!w || !w.on || chunk < 1 || chunk % 2 === 0) return null; const id = w.cycle[floor(chunk / 2) % w.cycle.length]; return { id, ...w.events[id] }; }
    fx(field) { const e = this.ev(); return (e && e[field]) || 0; }
    describe(chunk) { const e = this.ev(chunk); return e ? { id: e.id, name: e.name, icon: e.icon, effect: e.effect } : null; }
    pace(p = this.state.perks) { const c = BigInt(this.chunk()); return Math.max(100, Number(100n * 108n ** c / 100n ** c) + this.total('pace_pct', p)); }
    window(p = this.state.perks) {
      const min = Math.max(200, 350 - Math.max(0, this.chunk() - 14) * 15);
      const percent = Math.max(-45, this.total('window_pct', p) + (p.ebb > 0 ? 40 : 0) + (p.recovery > 0 ? 25 : 0) + this.fx('window_pct'));
      return Math.max(min, floor(floor(220000 / this.pace(p)) * (100 + percent) / 100));
    }
    score(elapsed, p = this.state.perks, health = this.state.health) {
      const s = this.state, w = this.window(p), tier = elapsed * 3 <= w ? 0 : elapsed * 3 <= 2 * w ? 1 : 2;
      let timing = [100, 70, 45][tier];
      if (this.total('sharp_eye', p)) timing = tier === 0 ? floor(timing * 3 / 2) : tier === 2 ? floor(timing / 2) : timing;
      const raw = (timing + Math.min(80 + this.total('combo_cap', p), s.combo * (4 + this.total('combo_step', p)))) * (p.bloody > 0 ? 3 : 1);
      let bonus = 0;
      for (const [id, count] of Object.entries(p.owned)) { const g = this.catalog[id]; if (g.cadence_every && (s.combo + 1) % g.cadence_every === 0) bonus += count * g.cadence_bonus_pct; }
      if (health <= 2) bonus += this.total('low_health_bonus_pct', p);
      return Math.max(1, floor(raw * (100 + Math.max(-60, this.total('score_pct', p) + bonus + this.fx('score_pct'))) / 100));
    }
    eligible(g) {
      const s = this.state, p = s.perks;
      return g.filler || !((p.owned[g.id] || 0) >= g.max_stack || g.sacrifice && s.health <= g.sacrifice ||
        g.recovery_signals && s.health <= 1 || g.heal && s.health >= 7 || g.id === 'blood_price' && s.health < 3 || g.cap_health && s.health <= g.cap_health);
    }
    async offers() {
      const number = this.state.selected.length + 1;
      const sorted = await Promise.all(Object.values(this.catalog).filter(g => this.eligible(g) &&
        !(this.packet.legacy && ['metronome', 'last_spark', 'second_wind'].includes(g.id))).map(async g => ({ g, h: await this.hash('perk:' + number + ':' + g.id) })));
      sorted.sort((a, b) => { for (let i = 0; i < a.h.length; i++) if (a.h[i] !== b.h[i]) return a.h[i] - b.h[i]; return 0; });
      const ranked = sorted.filter(x => !x.g.filler).map(x => x.g), chosen = ranked.slice(0, 3);
      chosen.push(...sorted.filter(x => x.g.filler).map(x => x.g).slice(0, 3 - chosen.length));
      const safe = ranked.find(g => g.kind === 'safe');
      if (safe && !chosen.some(g => g.kind === 'safe')) chosen[chosen.length - 1] = safe;
      return chosen.map(g => { const next = this.apply(g.id); const metrics = (hp, p) => ({health: hp, window_ms: this.window(p), speed_percent: this.pace(p), shield:p.shield, ebb:p.ebb, bloody:p.bloody, sample_score:this.score(floor(this.window(p)/2),p,hp)}); return {...g,preview:{before:metrics(this.state.health,this.state.perks),after:metrics(next.health,next.perks)}}; });
    }
    apply(id) {
      const g = this.catalog[id], p = clone(this.state.perks);
      p.owned[id] = (p.owned[id] || 0) + 1; p.shield += g.shield; p.ebb = Math.max(p.ebb, g.ebb); p.bloody = Math.max(p.bloody, g.bloody);
      let health = Math.min(7, this.state.health + g.heal) - g.sacrifice;
      if (g.cap_health) health = Math.min(health, g.cap_health);
      if (id === 'blood_price') health--;
      return { health, perks: p };
    }
    pick(id) { Object.assign(this.state, this.apply(id)); this.state.selected.push(id); }
    step(rune, elapsed, expected) {
      const s = this.state, p = s.perks, correct = rune === expected && elapsed <= this.window(), timeout = rune == null || elapsed > this.window();
      if (correct) {
        s.score += this.score(elapsed); s.combo++; s.correct_streak++; s.correct_taps++;
        p.bloody = Math.max(0, p.bloody - 1);
        const every = [...Object.keys(p.owned).map(id => this.catalog[id].regen_every), this.fx('regen_every')].filter(Boolean);
        if (every.length && s.correct_streak % Math.min(...every) === 0) s.health = Math.min(7, s.health + 1);
      } else { s.combo = s.correct_streak = 0; s.mistakes++; }
      p.ebb = Math.max(0, p.ebb - 1); p.recovery = Math.max(0, p.recovery - 1);
      if (!correct) {
        if (p.shield > 0) p.shield--;
        else if (!(timeout && this.total('timeout_free') && ++p.miss_debt % 2 === 1)) {
          s.health = Math.max(0, s.health - 1 - this.total('damage_extra') - (timeout ? 0 : this.total('wrong_extra')) - this.fx('damage_extra'));
          if (s.health > 0) p.recovery = Math.max(p.recovery, ...Object.keys(p.owned).map(id => this.catalog[id].recovery_signals));
        }
      }
      s.next_signal_no++; if (s.health === 0) s.status = 'finished'; return correct;
    }
    async view() {
      const s = this.state, draft = s.status === 'active' && this.chunk() > s.selected.length;
      return {...clone(s), run_id:this.packet.run_id, mode:'normal', ruleset_version:this.packet.ruleset_version,
        selected_perks:s.selected, gifts:Object.entries(s.perks.owned).map(([id,count]) => ({id,count,name:this.catalog[id].name})),
        rune:['left','center','right'][(await this.hash('rune:' + s.next_signal_no))[0] % 3],
        draft:draft?{number:s.selected.length+1, offers:await this.offers()}:null,
        speed_percent:this.pace(), window_ms:this.window(), remaining_ms:this.window(), chunk:this.chunk(), starts_in_ms:0,
        weather:this.describe(this.chunk()), next_weather:this.packet.weather?.on ? this.describe(this.chunk() + 1) : null};
    }
  }
  class Mines {
    constructor(packet, state = packet.state, first = packet.first_cell) { this.packet=packet; this.state=clone(state); this.first=first; }
    neighbours(cell) { const a=[], n=this.state.size, y=floor(cell/n), x=cell%n; for(let yy=y-1;yy<=y+1;yy++)for(let xx=x-1;xx<=x+1;xx++)if(yy>=0&&yy<n&&xx>=0&&xx<n&&(yy!==y||xx!==x))a.push(yy*n+xx);return a; }
    step(cell, kind, elapsed) {
      const s=this.state;if(this.first==null){this.first=cell;kind='open';}
      const mines=new Set(this.packet.layouts[this.first]),revealed=new Set(s.revealed),flags=new Set(s.flags);
      const adjacent=c=>this.neighbours(c).filter(x=>mines.has(x)).length;
      let status='active';
      if(kind==='toggle_flag'){if(!revealed.has(cell)){if(flags.has(cell))flags.delete(cell);else if(flags.size<s.mine_count)flags.add(cell);}}
      else if(!revealed.has(cell)&&!flags.has(cell)){
        s.opened_actions++;
        if(mines.has(cell)){revealed.add(cell);status='lost';}
        else {const queue=[cell];while(queue.length){const c=queue.pop();if(revealed.has(c)||flags.has(c)||mines.has(c))continue;revealed.add(c);if(adjacent(c)===0)queue.push(...this.neighbours(c));}if(revealed.size===s.size*s.size-s.mine_count)status='won';}
      }
      Object.assign(s,{status,revision:s.revision+1,revealed:[...revealed],flags:[...flags],elapsed_ms:elapsed,
        changed:[...revealed].map(c=>({cell:c,adjacent:adjacent(c)})),mines:status==='lost'?[...mines]:[]});
      return clone(s);
    }
  }
  window.PVLocal = { Store, Rhythm, Mines, request };
})();
