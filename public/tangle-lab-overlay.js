// Keep the site's original custom.js (brand / forced light theme) exactly as it is.
(function(){var s=document.createElement("script");s.src="/public/custom.js?v=20261123return";document.head.appendChild(s)})();
// feat/tangle-lab: runs inside Chainlit's own UI (custom_js). Default page stays Chainlit.
// When Eva sends CopilotFunction "tangle_workspace" (after the user picks 法規/媒合):
//   - Chainlit's left session list collapses (remembered so it can be restored)
//   - the v17 workspace opens over the main area; Chainlit chat stays on the right as the copilot
// "收合" restores everything to how it was.
(function(){
 var KEY="tangle-ws";
 function sbEl(){return document.querySelector('div[data-side="left"][data-state][data-collapsible]')}
 function sidebarOpen(){var s=sbEl();return s?s.getAttribute("data-state")==="expanded":null}
 function toggleSidebar(){var b=document.getElementById("sidebar-trigger-button")||document.querySelector('[data-sidebar="trigger"]');if(b){b.click();return true}return false}
 var state={open:false,hadSidebar:null,liveLaw:false,lawTask:null};
 function postLaw(f){if(state.liveLaw&&state.lawTask&&f&&f.contentWindow)f.contentWindow.postMessage({type:'tangle-law-task',snapshot:state.lawTask,closed:!state.open},location.origin)}
 function css(){if(document.getElementById(KEY+"-css"))return;var s=document.createElement("style");s.id=KEY+"-css";
  s.textContent='#'+KEY+'{position:fixed;top:60px;left:0;bottom:0;z-index:40;background:#101519;border-right:1px solid #24302f;box-shadow:8px 0 30px #0002;transition:transform .32s ease}'
  +'#'+KEY+'.hide{transform:translateX(-102%)}#'+KEY+' iframe{width:100%;height:100%;border:0;display:block}'
  +'body.'+KEY+'-on #root{padding-left:var(--tws-w)}body.'+KEY+'-on #root{transition:padding-left .32s ease}'
  +'#'+KEY+'-close{position:absolute;right:14px;top:12px;z-index:2;font:13px system-ui;color:#e3efed;background:#1b2a29;border:1px solid #2f5d59;border-radius:9px;padding:6px 12px;cursor:pointer}';
  document.head.appendChild(s)}
 // #229 外框文字依使用者語言：任務狀態帶的 lang 優先（matchTask／lawTask），沒有時讀 eva_lang cookie，都沒有用 zh（與改版前相同）。
 var FRAME_I18N={zh:{close:"收合 ↙",tip:"收合工作區，回到原本的聊天畫面",frame:"雲林專案工作區"},
  en:{close:"Collapse ↙",tip:"Collapse the workspace and return to the chat",frame:"Project workspace"},
  ja:{close:"折りたたむ ↙",tip:"ワークスペースを折りたたんで、もとのチャットにもどります",frame:"プロジェクトのワークスペース"},
  ko:{close:"접기 ↙",tip:"작업 공간을 접고 원래 대화 화면으로 돌아갑니다",frame:"프로젝트 작업 공간"}};
 var LANG_ALIAS={zh:"zh",en:"en",ja:"ja",jp:"ja",ko:"ko",kr:"ko"};
 function normLang(v){return LANG_ALIAS[String(v||"").trim().toLowerCase().split(/[-_]/)[0]]||null}
 function cookieLang(){var m=document.cookie.match(/(?:^|;\s*)eva_lang=([^;]*)/);try{return m?normLang(decodeURIComponent(m[1])):null}catch(_){return null}}
 function langOf(a){a=a||{};var t=a.matchTask||a.lawTask||{};return normLang(t.lang)||normLang(a.lang)||cookieLang()||"zh"}
 function localize(p,lang){p=p||document.getElementById(KEY);if(!p)return;var T=FRAME_I18N[lang]||FRAME_I18N.zh,b=document.getElementById(KEY+"-close"),f=p.querySelector("iframe");
  if(b){if(b.textContent!==T.close)b.textContent=T.close;if(b.getAttribute("title")!==T.tip)b.setAttribute("title",T.tip)}
  if(f&&f.getAttribute("title")!==T.frame)f.setAttribute("title",T.frame)}
 function width(){return Math.max(520,Math.round(window.innerWidth*0.62))}
 function open(args){css();var p=document.getElementById(KEY);
  if(!p){p=document.createElement("div");p.id=KEY;p.className="hide";
   p.innerHTML='<button id="'+KEY+'-close" title="收合工作區，回到原本的聊天畫面">收合 ↙</button><iframe title="雲林專案工作區"></iframe>';
   document.body.appendChild(p);document.getElementById(KEY+"-close").onclick=close}
  localize(p,langOf(args));
  state.liveLaw=args.mode==='law'&&!!args.lawTask;state.lawTask=state.liveLaw?args.lawTask:null;
   var src="/public/workspace/embed.html?mode="+encodeURIComponent(args.mode||"law")+"&v="+encodeURIComponent(args.v||"1")+"&b=law-task-1"+(state.liveLaw?'&liveLaw=1':'');
  if(!state.open){state.hadSidebar=sidebarOpen();if(state.hadSidebar)toggleSidebar()}
   state.open=true;
  var f=p.querySelector("iframe");f.onload=function(){postLaw(f)};if(f.getAttribute("src")!==src)f.setAttribute("src",src);else postLaw(f);
  var w=width();p.style.width=w+"px";document.body.style.setProperty("--tws-w",w+"px");document.body.classList.add(KEY+"-on");
  requestAnimationFrame(function(){p.classList.remove("hide")})}
 function close(){var p=document.getElementById(KEY);if(!p||!state.open)return;p.classList.add("hide");document.body.classList.remove(KEY+"-on");
  if(state.hadSidebar&&sidebarOpen()===false)toggleSidebar();state.open=false;
  var f=p.querySelector("iframe");f&&f.contentWindow&&f.contentWindow.postMessage({type:"tangle-ws-closed"},location.origin)}
 // Chainlit may re-render the layout (e.g. first message navigates to /thread/<id>), which re-expands the
 // session list. While the workspace is open, keep it collapsed; "收合" restores the user's original state.
 new MutationObserver(function(){if(!state.open)return;if(sidebarOpen()===true){toggleSidebar()}
  var p=document.getElementById(KEY);if(p&&!document.body.contains(p))document.body.appendChild(p);
  if(!document.body.classList.contains(KEY+"-on"))document.body.classList.add(KEY+"-on")})
  .observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:["data-state"]});
 window.__tangleWS={open:open,close:close,state:state};
 // Eva -> page
 window.addEventListener("chainlit-call-fn",function(e){var d=e.detail||{};
  if(d.name==="tangle_workspace"){var a=d.args||{};
    if(a.update===true){if(state.open&&(a.matchTask||a.lawTask))localize(null,langOf(a));if(state.liveLaw&&a.mode==='law'&&a.lawTask){state.lawTask=a.lawTask;postLaw(document.querySelector('#'+KEY+' iframe'))}}
    else open(a);
    d.callback&&d.callback({ok:true})}
  else if(d.name==="tangle_mark"){var f=document.querySelector("#"+KEY+" iframe");if(f&&f.contentWindow)f.contentWindow.postMessage({type:"tangle-mark",args:d.args},location.origin);d.callback&&d.callback({ok:!!(f&&state.open)})}
  else if(d.name==="tangle_close"){close();d.callback&&d.callback({ok:true})}});
 // workspace (iframe) -> Eva : forward as a hidden system message on the same Chainlit chat
 window.addEventListener("message",function(e){if(e.origin!==location.origin)return;var m=e.data||{};
  if(m.type==="tangle-ws-close")close()});
 // Workspace events need no relay here: Chainlit's own UI already forwards every window "message"
 // (including ones from this iframe) to the server as window_message -> @cl.on_window_message.
})();

// Self-heal (2026-11-17): Chainlit 2.12 sometimes opens the socket before it has read the thread id from the URL
// (auth.threadId=""), so the server starts a fresh session instead of resuming and /thread/<id> spins forever with
// no messages and no input box. If that is still the case 8 s after load, reload once more (at most twice per tab
// visit, tracked in sessionStorage). Nothing else is changed; a normal resume never triggers it.
(function(){
 var K="tangle-resume-heal",n=+(sessionStorage.getItem(K)||0),t0=Date.now();
 var iv=setInterval(function(){
  if(!/\/thread\/[0-9a-f-]{8,}/.test(location.pathname)){clearInterval(iv);return}
  var ok=document.querySelector("#chat-input")||document.querySelector("[data-step-type]");
  if(ok){sessionStorage.removeItem(K);clearInterval(iv);return}
  if(Date.now()-t0<6000)return;
  clearInterval(iv);if(n>=3)return;
  sessionStorage.setItem(K,String(n+1));location.reload();
 },1000);
})();
