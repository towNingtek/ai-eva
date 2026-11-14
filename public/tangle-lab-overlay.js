// Keep the site's original custom.js (brand / forced light theme) exactly as it is.
(function(){var s=document.createElement("script");s.src="/public/custom.js?v=20260820brand";document.head.appendChild(s)})();
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
 var state={open:false,hadSidebar:null};
 function css(){if(document.getElementById(KEY+"-css"))return;var s=document.createElement("style");s.id=KEY+"-css";
  s.textContent='#'+KEY+'{position:fixed;top:60px;left:0;bottom:0;z-index:40;background:#101519;border-right:1px solid #24302f;box-shadow:8px 0 30px #0002;transition:transform .32s ease}'
  +'#'+KEY+'.hide{transform:translateX(-102%)}#'+KEY+' iframe{width:100%;height:100%;border:0;display:block}'
  +'body.'+KEY+'-on #root{padding-left:var(--tws-w)}body.'+KEY+'-on #root{transition:padding-left .32s ease}'
  +'#'+KEY+'-close{position:absolute;right:14px;top:12px;z-index:2;font:13px system-ui;color:#e3efed;background:#1b2a29;border:1px solid #2f5d59;border-radius:9px;padding:6px 12px;cursor:pointer}';
  document.head.appendChild(s)}
 function width(){return Math.max(520,Math.round(window.innerWidth*0.62))}
 function open(args){css();var p=document.getElementById(KEY);
  if(!p){p=document.createElement("div");p.id=KEY;p.className="hide";
   p.innerHTML='<button id="'+KEY+'-close" title="收合工作區，回到原本的聊天畫面">收合 ↙</button><iframe title="雲林專案工作區"></iframe>';
   document.body.appendChild(p);document.getElementById(KEY+"-close").onclick=close}
  var src="/public/workspace/embed.html?mode="+encodeURIComponent(args.mode||"law")+"&v="+(args.v||"1")+"&b=1794647644";
  var f=p.querySelector("iframe");if(f.getAttribute("src")!==src)f.setAttribute("src",src);
  if(!state.open){state.hadSidebar=sidebarOpen();if(state.hadSidebar)toggleSidebar()}
  state.open=true;var w=width();p.style.width=w+"px";document.body.style.setProperty("--tws-w",w+"px");document.body.classList.add(KEY+"-on");
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
  if(d.name==="tangle_workspace"){open(d.args||{});d.callback&&d.callback({ok:true})}
  else if(d.name==="tangle_mark"){var f=document.querySelector("#"+KEY+" iframe");if(f&&f.contentWindow)f.contentWindow.postMessage({type:"tangle-mark",args:d.args},location.origin);d.callback&&d.callback({ok:!!(f&&state.open)})}
  else if(d.name==="tangle_close"){close();d.callback&&d.callback({ok:true})}});
 // workspace (iframe) -> Eva : forward as a hidden system message on the same Chainlit chat
 window.addEventListener("message",function(e){if(e.origin!==location.origin)return;var m=e.data||{};
  if(m.type==="tangle-ws-close")close()});
 // Workspace events need no relay here: Chainlit's own UI already forwards every window "message"
 // (including ones from this iframe) to the server as window_message -> @cl.on_window_message.
})();
