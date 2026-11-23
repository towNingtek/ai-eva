// #203 真實媒合任務：?liveMatch=1 時，把工作區（parent）放在 window.__matchGalaxy 的判斷結果
// 換進原本的媒合畫法（B1–B8 衛星、月牙＝需要、互補光流、走進一對、2–4 案狀態）。
// 只換資料，不改畫法；沒有 liveMatch 時完全不動作（示範／雲林維持原樣）。
// #232 判斷中的預覽（G.preview）：讀到幾案就畫幾顆（A 一顆也畫），判完的才有衛星。
(function(){
 var q=new URLSearchParams(location.search);
 if(q.get('liveMatch')!=='1')return;
 var G=null;
 try{G=parent&&parent!==window&&parent.__matchGalaxy}catch(e){G=null}
 var least=G&&G.preview?1:2;
 if(!G||!Array.isArray(G.projects)||G.projects.length<least)return;
 var ROLES={need:1,offer:1,both:1,none:1};
 var want=(q.get('ps')||'').split(',').filter(Boolean);
 var byPid={};G.projects.forEach(function(p){if(p&&p.pid)byPid[String(p.pid)]=p});
 var shown=(want.length?want:G.projects.map(function(p){return String(p.pid)}))
  .filter(function(id,i,a){return byPid[id]&&a.indexOf(id)===i}).slice(0,4);
 if(shown.length<least)return;
 var keys=G.keys&&typeof G.keys==='object'?G.keys:KV_MATCH.keys,projects={};
 G.projects.forEach(function(p){var m={};Object.keys(keys).forEach(function(k){var v=(p.match||{})[k]||{};
   m[k]={role:ROLES[v.role]?v.role:'none',evidence:Array.isArray(v.evidence)?v.evidence.slice(0,6):[]}});
  projects[String(p.pid)]={name:String(p.name||p.pid),match:m}});
 KV_MATCH.demo=false;
 KV_MATCH.note=G.note||'本次媒合判斷結果（需要／能提供依計畫原文判斷；不是媒合建議）。';
 KV_MATCH.keys=keys;
 KV_MATCH.projects=projects;
 var base=YL.matchP;
 YL.liveMatch=G;
 YL.matchP=function(){var sim={topic:.5,exec:.5,stage:.5,xborder:0};
  var pick=function(pid,role){var m=projects[pid].match;return Object.keys(m).filter(function(k){return m[k].role===role||m[k].role==='both'}).map(function(k){return[k,.8,1]})};
  return shown.map(function(pid,i){return{id:i+1,pid:pid,name:projects[pid].name,n:pick(pid,'need'),o:pick(pid,'offer'),sim:sim}})};
 YL.matchP.base=base;
 // 狀態以伺服器這次的判斷為準：工作區在 iframe load 後送 'mf-status'（頁面原有的接收器只收 parent 來的）。
 document.documentElement.dataset.liveMatch=shown.join(',');
})();
