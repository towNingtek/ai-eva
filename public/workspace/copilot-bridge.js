// v17 workspace + Chainlit copilot. Loaded last, after the v17 scripts.
// Layout: v17 desk is the whole main area; Eva (copilot sidebar) replaces v17's chat column.
// Page -> Eva: sendChainlitMessage(system_message + metadata.tangle).
// Eva -> page: CopilotFunction("tangle_mark") -> window "chainlit-call-fn" event.
(function(){
 const S=document.createElement('style');
 S.textContent=
  // Session list collapsed by default; toggle with ☰.
  '.shell{grid-template-columns:1fr!important}.sidebar{display:none!important}'
 +'body.side-open .shell{grid-template-columns:210px 1fr!important}body.side-open .sidebar{display:flex!important}'
 +'.side-toggle{position:fixed;left:12px;top:14px;z-index:30;padding:6px 11px;font-size:14px;background:#1d1e26;border:1px solid #41434e;border-radius:9px}'
 +'.main>header{padding-left:62px}'
 // Desk always shown and full width; v17 chat column hidden (Eva takes its role).
 +'.chat-pane{display:none!important}.stage-layout,.workspace-open .stage-layout{grid-template-columns:minmax(0,1fr)!important}'
 +'.desk{display:block!important;grid-column:1!important}.original-tangle{height:calc(100dvh - 300px)!important;min-height:420px}'
 +'.cop-home{max-width:720px;margin:9vh auto 0}.cop-home h1{font-size:30px;font-weight:500;margin:0 0 10px}.cop-home:before{content:"✳";display:block;font-size:44px;color:#c0a5e4;margin-bottom:14px}'
 +'.cop-home p{color:#aca7b7}.cop-home .chips{display:flex;gap:10px;margin-top:20px}.cop-home .chips button{padding:12px 21px;border-radius:12px;background:#25232d;border-color:#4a3c59}'
 +'.cop-home .hint{font-size:12px;color:#8f8a9c;margin-top:26px}';
 document.head.append(S);
 const t=document.createElement('button');t.className='side-toggle';t.textContent='☰';t.title='分析紀錄';t.onclick=()=>document.body.classList.toggle('side-open');document.body.append(t);

 // Workspace landing: the two entry buttons live in the desk (they used to be in v17's chat column).
 function home(){const m=$('deskMount');if(!m)return;$('deskTitle').textContent='雲林 10 案';
  m.innerHTML='<div class="cop-home"><h1>把判斷說清楚，讓下一步有依據。</h1><p>雲林 10 個農村再生計畫。選一種分析，在這裡選專案；右邊的 Eva 會陪你看星圖、補充資料。</p>'
  +'<div class="chips"><button onclick="copChoose(\'match\')">🤝 媒合分析</button><button onclick="copChoose(\'law\')">⚖ 法規檢核</button></div>'
  +'<p class="hint">試作：雲林公開計畫理念固定快照；不連線正式系統、不呼叫 AI；說明為示範文字，不作法規適用或合作判定。</p></div>'}
 // Reuse v17's own analysis frame + desk; only the place it is opened from changes.
 window.copChoose=function(mode){currentMode=mode;const m=$('deskMount');if(m)m.innerHTML='';const id=++seq;const tmp=document.createElement('div');tmp.innerHTML=frame(mode,id,'setup');
  const slot=document.createElement('div');slot.dataset.slot=id;slot.hidden=true;slot.append(tmp.firstElementChild);document.body.append(slot);openDesk(mode,id)};
 const collapsePrev=collapseDesk;collapseDesk=function(){collapsePrev();document.body.classList.add('workspace-open');home()};
 window.addEventListener('load',()=>{document.body.classList.add('workspace-open');home();
  const back=document.querySelector('.desk-actions button:last-child');if(back)back.textContent='← 回到選擇'});

 const ready=()=>typeof window.sendChainlitMessage==='function'&&window.__copilotReady;
 function toEva(text,payload){if(!ready()){console.warn('copilot not ready');return}
  window.sendChainlitMessage({type:'system_message',output:text,metadata:{tangle:payload}})}
 window.__toEva=toEva;

 const runPrev=run;run=function(mode,id){runPrev(mode,id);const s=ylSel.get(id)||{};
  toEva('▸ '+names[mode],{event:'open',mode,id,p:s.p,q:mode==='match'?s.q:null})};

 window.addEventListener('message',e=>{if(e.origin!==location.origin||e.data?.type!=='tangle-relation')return;
  const found=[...frames.entries()].find(([,f])=>f.contentWindow===e.source);if(!found||!e.data.code)return;
  e.stopImmediatePropagation();const id=found[0],s=ylSel.get(id)||{},r=records.find(x=>x.id===id);
  toEva('▸ '+e.data.tag,{event:'pick',id,mode:r?r.mode:currentMode,p:s.p,q:s.q,code:e.data.code,subject:e.data.subject,kind:e.data.kind});
 },true);

 window.addEventListener('chainlit-call-fn',e=>{const {name,args,callback}=e.detail||{};if(name!=='tangle_mark')return;
  const f=frames.get(args.id);if(f&&f.contentWindow)f.contentWindow.postMessage({type:'dd-confirmed',subject:args.subject,code:args.code,text:args.text},location.origin);
  callback&&callback({ok:!!f})});
})();
