// v17 workspace embedded in Chainlit's default UI (iframe from tangle-lab-overlay.js).
// Workspace -> Eva: window.parent.postMessage({tangle}) — Chainlit relays window messages to on_window_message.
// Eva -> workspace: parent posts {type:"tangle-mark"} after the user confirms a supplement.
(function(){
 const Q=new URLSearchParams(location.search),MODE=Q.get('mode')==='match'?'match':'law';
 const S=document.createElement('style');
 S.textContent='.sidebar,.main>header,.chat-pane,.mobile-toggle{display:none!important}.shell{grid-template-columns:1fr!important}'
  +'.stage-layout,.workspace-open .stage-layout{grid-template-columns:minmax(0,1fr)!important}.desk{display:block!important;grid-column:1!important;padding:22px 26px}'
  +'.desk-top small,.analysis-head,.desk .source-note,.desk .warning,.desk .field+p.muted,.desk .actions:has(button[onclick^="restartOriginal"]){display:none!important}'+'.desk-actions{display:none!important}.original-tangle{height:calc(100dvh - 250px)!important;min-height:380px}.desk-top{margin-bottom:16px;padding-right:110px}';
 document.head.append(S);
 const toEva=(text,payload)=>window.parent.postMessage({tangle:payload,text},location.origin);

 // Copy that is not removed outright is rewritten to what is true for this lab.
 // Only write when the text differs, otherwise the observer re-triggers itself forever.
 const FOOT='資料來源：雲林社區 AI 知識系統公開計畫理念（固定快照）',HINT='點衛星，在右邊對話補充。';
 const tidy=()=>{const f=document.querySelector('.desk-foot');if(f&&f.textContent!==FOOT)f.textContent=FOOT;
  document.querySelectorAll('.desk .body > p.muted').forEach(e=>{if(/拖曳大節點/.test(e.textContent))e.textContent=HINT})};
 new MutationObserver(tidy).observe(document.documentElement,{subtree:true,childList:true});
 window.addEventListener('load',()=>{document.body.classList.add('workspace-open');
  currentMode=MODE;const id=++seq;const tmp=document.createElement('div');tmp.innerHTML=frame(MODE,id,'setup');
  const slot=document.createElement('div');slot.dataset.slot=id;slot.hidden=true;slot.append(tmp.firstElementChild);document.body.append(slot);openDesk(MODE,id)});

 const runPrev=run;run=function(mode,id){runPrev(mode,id);const s=ylSel.get(id)||{};
  toEva('open',{event:'open',mode,id,p:s.p,q:mode==='match'?s.q:null})};

 window.addEventListener('message',e=>{if(e.origin!==location.origin)return;const d=e.data||{};
  if(d.type==='tangle-relation'&&d.code){const found=[...frames.entries()].find(([,f])=>f.contentWindow===e.source);if(!found)return;
   e.stopImmediatePropagation();const id=found[0],s=ylSel.get(id)||{},r=records.find(x=>x.id===id);
   toEva('pick',Object.assign({event:'pick',id,mode:r?r.mode:currentMode,p:s.p,q:s.q,code:d.code,subject:d.subject,kind:d.kind},d.pa&&d.pb?{pa:d.pa,pb:d.pb}:{},d.who?{who:d.who,others:d.others}:{}));return}
  if(d.type==='tangle-mark'&&e.source===window.parent){const a=d.args||{},f=frames.get(a.id);
   if(f&&f.contentWindow){if(a.mfStatus)f.contentWindow.postMessage(Object.assign({type:'mf-status',status:a.mfStatus,filled:a.filled||{}},a.pair?{pair:a.pair}:{}),location.origin);else f.contentWindow.postMessage({type:'dd-confirmed',subject:a.subject,code:a.code,text:a.text},location.origin)}}
 },true);
})();
