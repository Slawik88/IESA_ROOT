var T=window.TelegramWidget,S={},R=-1,B=0,Q=0,ER={BUSY:"Секунду…",RATE_LIMITED:"Слишком часто, подожди",TIMEOUT:"Бот не ответил, попробуй ещё",FAILED:"Нет связи с ботом",NOT_ALLOWED:"Тут виджет не спросит бота"};
function $(i){return document.getElementById(i)}
function J(s){try{return JSON.parse(s)||{}}catch(e){return{}}}
function say(t,ok){var m=$("m");if(m){m.textContent=t||"";m.className=ok?"ok":""}}
function take(o,f){var r=+(o&&o.r)||0;if(o&&(f||r>=R)){R=r;S=o;draw(S)}}
function ask(d,tap){if(!T)return Promise.resolve(null);if(Q){if(tap)say(ER.BUSY);return Promise.resolve(null)}if(!tap){var n=Date.now();if(n-B<5e3)return Promise.resolve(null);B=n}else say("…");Q=1;return T.request(d).then(function(a){Q=0;var o=J(a&&a.result);say(o.e||o.o||"",!o.e&&o.o);if(!o.e)take(o);after();return o},function(e){Q=0;say(ER[e&&e.code]||"Не вышло, попробуй ещё");after();return null})}
function after(){if(typeof AFTER=="function")setTimeout(AFTER,0)}
function snap(){return typeof SNAP=="function"?SNAP():KEY+":s"}
take(J(T&&T.chatData),1);
if(T){T.onEvent("chatDataChanged",function(){take(J(T.chatData))});if(typeof LIVE!="undefined"&&LIVE){T.onEvent("activated",function(){ask(snap())});ask(snap())}if(T.ready)T.ready()}
if(typeof start=="function")start()
