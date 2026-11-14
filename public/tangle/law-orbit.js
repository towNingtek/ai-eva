// One project planet; rule satellites are not projects. UI-only fictional conditions.
const lawRules=YL.lawRules();
let kvView='topic';   // 'topic' = existing view (default) | 'domain' = 10 law domains (step 1, demo data)
// Entrance copied from v16 app.js: each frame moves k=1-0.0015^dt of the remaining distance,
// starting from where this project sits on the v16 overview (SPOT), small planet, flat small orbit.
const ENT_RM=matchMedia('(prefers-reduced-motion: reduce)').matches;
const V16_SPOT={'台子':[.13,.72],'富琦':[.17,.36],'水尾':[.37,.22],'大庄':[.59,.19],'林中':[.86,.27],'崙峯':[.71,.48],'新庄':[.84,.74],'大德':[.57,.67],'後埔':[.41,.49],'崙仔':[.31,.80]};
let ENTC=null,ENT_DONE=ENT_RM;   // current animated state in screen space (VZ already applied)
const ENT_Z=1.35;
const lawPositions=new Map();let lawSelected=null;let orbitTime=0,orbitPaused=false,orbitHover=false;const reducedMotion=matchMedia("(prefers-reduced-motion: reduce)").matches;
render=function(){if(kvView==='domain')return renderDomain();const svg=document.getElementById('svg');svg.setAttribute('viewBox',`${-VX/VZ} ${-VY/VZ} ${Wd/VZ} ${Hd/VZ}`);svg.innerHTML='';TRACKS.length=0;ORPH.length=0;
 const bg=el('rect',{x:-VX/VZ,y:-VY/VZ,width:Wd/VZ,height:Hd/VZ,fill:'#060a10'});svg.appendChild(bg);
 for(let j=0;j<45;j++){svg.appendChild(el('circle',{cx:(j*137.51)%Wd,cy:(j*j*33.7)%Hd,r:j%4===0?.65:.35,fill:'#a5a5c0',opacity:.08+.08*Math.sin(orbitTime*.4+j),'pointer-events':'none'}));}
 const cx=Wd/2,cy=Hd/2,radius0=Math.min(Wd,Hd)*.24,E=entGeom();
 const defs=el('defs',{});svg.appendChild(defs);
 // Only one planet, with a persistent independent drag position.
 let center=lawPositions.get('planet')||{x:E.x+Math.sin(orbitTime*.3)*4,y:E.y+Math.cos(orbitTime*.25)*3};
 const haze=el('radialGradient',{id:'planet-haze'});haze.appendChild(el('stop',{offset:0,'stop-color':'#75b3ad','stop-opacity':.18}));haze.appendChild(el('stop',{offset:1,'stop-color':'#75b3ad','stop-opacity':0}));defs.appendChild(haze);svg.appendChild(el('circle',{cx:center.x,cy:center.y,r:85,fill:'url(#planet-haze)','pointer-events':'none'}));
 lawRules.forEach((rule,i)=>{const radius=E.orbit,angle=-Math.PI/2+i*(Math.PI*2/lawRules.length)+orbitTime*(.018+i*.002)+E.spin;let target=lawPositions.get(rule.code)||{x:center.x+Math.cos(angle)*radius,y:center.y+Math.sin(angle)*radius*E.flat};
 const fact={x:center.x+Math.cos(angle)*43*E.f,y:center.y+Math.sin(angle)*43*E.f*E.flat},mx=(fact.x+target.x)/2,my=(fact.y+target.y)/2-24;
 const gid='law-route-'+i,gr=el('linearGradient',{id:gid,gradientUnits:'userSpaceOnUse',x1:fact.x,y1:fact.y,x2:target.x,y2:target.y});[[0,.1],[.3,.5],[.65,rule.q<.6?.1:.5],[1,rule.q<.6?0:.2]].forEach(([o,a])=>gr.appendChild(el('stop',{offset:o,'stop-color':'#add6d3','stop-opacity':a})));defs.appendChild(gr);
 if(rule.q>=.6)TRACKS.push({A:fact,B:target,cx:mx,cy:my,st:.55,q:1,tag:rule.code,from:1,to:1});
 const d=`M${fact.x},${fact.y} Q${mx},${my} ${target.x},${target.y}`;svg.appendChild(el('path',{d,fill:'none',stroke:'url(#'+gid+')','stroke-width':.8}));
 const path=el('path',{d,fill:'none',stroke:'transparent','stroke-width':12,role:'button',tabindex:0,'aria-label':rule.label});path.onpointerdown=e=>{e.stopPropagation();chooseRule(rule)};path.onkeydown=e=>{if(e.key==='Enter')chooseRule(rule)};svg.appendChild(path);
 const glow=el('radialGradient',{id:'law-glow-'+i});glow.appendChild(el('stop',{offset:0,'stop-color':'#aae2dd','stop-opacity':.5}));glow.appendChild(el('stop',{offset:1,'stop-color':'#aae2dd','stop-opacity':0}));defs.appendChild(glow);
 svg.appendChild(el('circle',{cx:fact.x,cy:fact.y,r:2,fill:'#b6bfcb','pointer-events':'none'}));
 const g=el('g',{'data-rule':rule.code,role:'button',tabindex:0,'aria-label':rule.label,style:'cursor:pointer',opacity:E.o.toFixed(3)});svg.appendChild(g);
 g.appendChild(el('circle',{cx:target.x,cy:target.y,r:15,fill:'url(#law-glow-'+i+')'}));drawMoon(g,target.x,target.y,11*E.moon,'rule',lawSelected===rule.code);
 const text=el('text',{x:target.x,y:target.y-25,'text-anchor':'middle',fill:'#cedfde','font-size':12/VZ,opacity:E.o.toFixed(3)});text.textContent=rule.label;g.appendChild(text);
 if(ddSupplements.has('1:'+rule.code)){const label=el('text',{x:target.x,y:target.y+25,'text-anchor':'middle',fill:'#b8e0dd','font-size':10/VZ});label.textContent='已補充・未查證';g.appendChild(label)}
 const hit=el('circle',{cx:target.x,cy:target.y,r:14,fill:'transparent'});g.appendChild(hit);
 bindDrag(g,rule.code,target,()=>chooseRule(rule));
 });
 const planet=el('g',{'data-project-planet':'1',style:'cursor:grab',opacity:E.o.toFixed(3)});drawPlanet(planet,center,28*E.r,1,true);svg.appendChild(planet);const name=el('text',{x:center.x,y:center.y+48,'text-anchor':'middle',fill:'#c9e1df','font-size':13/VZ,opacity:E.o.toFixed(3)});name.textContent=YP.name;planet.appendChild(name);bindDrag(planet,'planet',center,()=>{});
};
function chooseRule(rule){lawSelected=rule.code;parent.postMessage({type:'tangle-relation',mode:'law',code:rule.code,tag:rule.label,subject:1,kind:'rule',unknown:rule.q<.6},location.origin)}
function bindDrag(g,key,position,onClick){g.onpointerdown=e=>{e.stopPropagation();e.preventDefault();const svg=document.getElementById('svg'),pt=new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());let moved=false;const move=ev=>{const p=new DOMPoint(ev.clientX,ev.clientY).matrixTransform(svg.getScreenCTM().inverse());if(Math.hypot(p.x-pt.x,p.y-pt.y)>3)moved=true;if(moved){lawPositions.set(key,{x:position.x+p.x-pt.x,y:position.y+p.y-pt.y});render()}};const up=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up);if(!moved)onClick()};window.addEventListener('pointermove',move);window.addEventListener('pointerup',up,{once:true})};g.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();onClick()}}}
// Prevent inherited two-project physics and graph hit testing from handling this view.
IDLE=false;bang=null;flowOn=false;SPARK=[];focus=null;
// World-space targets. Start = v16 overview: spot position, r=3.8% of min(W,H) vs final 28px planet; orbit m*.038+15 flattened .55.
function entTargets(){const m=Math.min(Wd,Hd),sp=[.86,.18],toW=(sx,sy)=>({x:(sx-VX)/VZ,y:(sy-VY)/VZ}),st=toW(sp[0]*Wd,sp[1]*Hd);
 return{start:{x:st.x,y:st.y,r:(m*.038)/VZ/28,orbit:(m*.038+15)/VZ,flat:.55,f:.3,moon:3.2/VZ/11,o:0,spin:0},end:{x:Wd/2,y:Hd/2,r:1,orbit:Math.min(Wd,Hd)*.24,flat:1,f:1,moon:1,o:1,spin:0}}}
function entGeom(){if(ENT_DONE||!ENTC)return entTargets().end;return ENTC}
let entLast=0;
function entStep(now){const T=entTargets();if(!ENTC){ENTC={...T.start};entLast=now}const dt=Math.min(.05,(now-entLast)/1000);entLast=now;const k=1-Math.pow(.0015,dt);
 let left=0;for(const key of ['x','y','r','orbit','flat','f','moon','o']){ENTC[key]+=(T.end[key]-ENTC[key])*k;left=Math.max(left,Math.abs(T.end[key]-ENTC[key])/(Math.abs(T.end[key])||1))}
 IDLE=false;bang=null;render();if(left<.002){ENT_DONE=true;render();return}requestAnimationFrame(entStep)}
IDLE=false;bang=null;VZ=ENT_Z;VX=Wd/2*(1-VZ);VY=Hd/2*(1-VZ);if(window.updZ)updZ();
if(!ENT_RM)requestAnimationFrame(entStep);
window.addEventListener('resize',()=>{Wd=document.getElementById('stage').clientWidth;Hd=document.getElementById('stage').clientHeight;render()});
render();

const orbitStage=document.getElementById('svg');
orbitStage.addEventListener('pointerenter',()=>{orbitHover=true});orbitStage.addEventListener('pointerleave',()=>{orbitHover=false});orbitStage.addEventListener('focusin',()=>{orbitHover=true});
document.getElementById('bIdle').onclick=()=>{orbitPaused=!orbitPaused;flowOn=!orbitPaused&&!reducedMotion;};
document.getElementById('bFlow').onclick=()=>{flowOn=!flowOn&&!reducedMotion;};
let lastOrbit=0;function orbitLoop(now){if(now-lastOrbit>50){if(!orbitPaused&&!orbitHover&&!reducedMotion){orbitTime+=.05;render();buildParticles()}lastOrbit=now}requestAnimationFrame(orbitLoop)}
setTimeout(()=>{flowOn=!reducedMotion;buildParticles();requestAnimationFrame(orbitLoop)},1300);

// ── Step 1: 法領域 view (added alongside the topic view; demo data from kv-law-mock.js) ──────────
// key = 10 law domains, value.state = hit | gap | na, plus "uncovered" outer bodies. No click handling yet.
const KV_P=(typeof KV_LAW!=='undefined'&&KV_LAW.projects[YP.id])||null;
function renderDomain(){const svg=document.getElementById('svg');svg.setAttribute('viewBox',`${-VX/VZ} ${-VY/VZ} ${Wd/VZ} ${Hd/VZ}`);svg.innerHTML='';TRACKS.length=0;ORPH.length=0;
 svg.appendChild(el('rect',{x:-VX/VZ,y:-VY/VZ,width:Wd/VZ,height:Hd/VZ,fill:'#060a10'}));
 for(let j=0;j<45;j++){svg.appendChild(el('circle',{cx:(j*137.51)%Wd,cy:(j*j*33.7)%Hd,r:j%4===0?.65:.35,fill:'#a5a5c0',opacity:.08+.08*Math.sin(orbitTime*.4+j),'pointer-events':'none'}));}
 const defs=el('defs',{});svg.appendChild(defs);
 const cx=Wd/2,cy=Hd/2-Hd*.035/VZ,R=Math.min(Wd,Hd)*.235,center={x:cx+Math.sin(orbitTime*.3)*4,y:cy+Math.cos(orbitTime*.25)*3};
 const haze=el('radialGradient',{id:'planet-haze'});haze.appendChild(el('stop',{offset:0,'stop-color':'#70b8b0','stop-opacity':.18}));haze.appendChild(el('stop',{offset:1,'stop-color':'#70b8b0','stop-opacity':0}));defs.appendChild(haze);
 svg.appendChild(el('circle',{cx:center.x,cy:center.y,r:85,fill:'url(#planet-haze)','pointer-events':'none'}));
 const fog=el('radialGradient',{id:'kv-fog'});[[0,.26],[.55,.1],[1,0]].forEach(([o,a])=>fog.appendChild(el('stop',{offset:o,'stop-color':'#d5dfdc','stop-opacity':a})));defs.appendChild(fog);
 const glow=el('radialGradient',{id:'kv-glow'});glow.appendChild(el('stop',{offset:0,'stop-color':'#a5e7df','stop-opacity':.5}));glow.appendChild(el('stop',{offset:1,'stop-color':'#a5e7df','stop-opacity':0}));defs.appendChild(glow);
 const fs=n=>(n/VZ).toFixed(2),STOPS={high:[[0,.3],[.5,.8],[1,.6]],mid:[[0,.22],[.45,.6],[1,.18]],low:[[0,.2],[.4,.45],[.82,.05],[1,0]],gap:[[0,.16],[.3,.36],[.62,0],[1,0]],unc:[[0,.2],[.5,.5],[1,.38]]};
 function label(g,x,y,ang,name,fill,sub,subFill,off){const ux=Math.cos(ang),uy=Math.sin(ang),anchor=ux>.3?'start':ux<-.3?'end':'middle',lx=x+ux*off,ly=y+uy*off+(Math.abs(ux)>.3?3:(uy<0?-(sub?14:4):10));
  const t=el('text',{x:lx,y:ly,'text-anchor':anchor,fill,'font-size':fs(12)});t.textContent=name;g.appendChild(t);
  if(sub){const t2=el('text',{x:lx,y:ly+12/VZ*1.15,'text-anchor':anchor,fill:subFill,'font-size':fs(10)});t2.textContent=sub;g.appendChild(t2)}}
 function route(i,from,to,kind,stop){const dx=to.x-from.x,dy=to.y-from.y,L=Math.hypot(dx,dy)||1,ex=to.x-dx/L*stop,ey=to.y-dy/L*stop,mx=(from.x+ex)/2,my=(from.y+ey)/2-18;
  const gid='kv-route-'+i,gr=el('linearGradient',{id:gid,gradientUnits:'userSpaceOnUse',x1:from.x,y1:from.y,x2:ex,y2:ey});STOPS[kind].forEach(([o,a])=>gr.appendChild(el('stop',{offset:o,'stop-color':'#a9dad5','stop-opacity':a})));defs.appendChild(gr);
  svg.appendChild(el('path',{d:`M${from.x},${from.y} Q${mx},${my} ${ex},${ey}`,fill:'none',stroke:'url(#'+gid+')','stroke-width':.8,'pointer-events':'none'}));
  if(kind==='high'||kind==='mid')TRACKS.push({A:from,B:{x:ex,y:ey},cx:mx,cy:my,st:.55,q:1,tag:'kv'+i,from:1,to:1});}
 function dots(ang,n){for(let k=0;k<n;k++){const a=ang+(k-(n-1)/2)*.14;svg.appendChild(el('circle',{cx:center.x+Math.cos(a)*43,cy:center.y+Math.sin(a)*43,r:2,fill:'#b6bfcb','pointer-events':'none'}))}}
 if(KV_P)KV_LAW.domains.forEach((name,i)=>{const v=KV_P.law[name],ang=-Math.PI*.4+i*(Math.PI*2/KV_LAW.domains.length)+orbitTime*.012,t={x:center.x+Math.cos(ang)*R,y:center.y+Math.sin(ang)*R},from={x:center.x+Math.cos(ang)*43,y:center.y+Math.sin(ang)*43};
  const g=el('g',{'data-kv-key':name,'data-kv-state':v.state});
  if(v.state==='hit'){dots(ang,v.evidence.length);route(i,from,t,v.confidence,15);svg.appendChild(g);g.appendChild(el('circle',{cx:t.x,cy:t.y,r:17,fill:'url(#kv-glow)'}));drawMoon(g,t.x,t.y,11,'rule',false);
   const parts=[];if(v.count.risk)parts.push(v.count.risk+' 風險');if(v.count.note)parts.push(v.count.note+' 提醒');label(g,t.x,t.y,ang,name,'#d5e1e0',parts.join('・'),v.count.risk?'#e3c79c':'#8fcfc5',19);}
  else if(v.state==='gap'){dots(ang,v.evidence.length);route(i,from,t,'gap',15);svg.appendChild(g);g.appendChild(el('circle',{cx:t.x,cy:t.y,r:27,fill:'url(#kv-fog)'}));const inner=el('g',{opacity:.5});drawMoon(inner,t.x,t.y,11,'rule',false);g.appendChild(inner);
   label(g,t.x,t.y,ang,name,'#b9c6c3','缺：'+v.missing,'#96a5a2',22);}
  else{svg.appendChild(g);const inner=el('g',{opacity:.26});drawMoon(inner,t.x,t.y,7,'rule',false);g.appendChild(inner);label(g,t.x,t.y,ang,name,'#56625f',null,null,14);}
 });
 if(KV_P)KV_P.uncovered.forEach((name,j)=>{const ang=(j?.1:.9)*Math.PI+orbitTime*.012,R2=Math.min((Wd/(2*VZ)-74)/Math.abs(Math.cos(ang)),R*1.5),t={x:center.x+Math.cos(ang)*R2,y:center.y+Math.sin(ang)*R2},from={x:center.x+Math.cos(ang)*43,y:center.y+Math.sin(ang)*43};
  dots(ang,1);route(100+j,from,t,'unc',14);const g=el('g',{'data-kv-key':name,'data-kv-state':'uncovered'});svg.appendChild(g);
  g.appendChild(el('circle',{cx:t.x,cy:t.y,r:11,fill:'#9fb5b1','fill-opacity':.04,stroke:'#a9bfbb','stroke-width':.8,opacity:.8}));label(g,t.x,t.y,ang,name,'#aebdba','未收錄','#7f8f8c',17);});
 const planet=el('g',{'data-project-planet':'1'});drawPlanet(planet,center,28,1,true);svg.appendChild(planet);
 const nm=el('text',{x:center.x,y:center.y+62,'text-anchor':'middle',fill:'#c7e3e1','font-size':fs(13),stroke:'#060a10','stroke-width':3/VZ,'paint-order':'stroke'});nm.textContent=YP.name;planet.appendChild(nm);
}
// View switch (議題｜法領域) next to the zoom buttons; the demo note shows only in the domain view.
(function(){const zc=document.getElementById('zc');if(!zc||!KV_P)return;
 const st=document.createElement('style');st.textContent='#kvView{position:absolute;left:14px;bottom:74px;z-index:14;display:flex;gap:2px;padding:3px;background:rgba(16,21,28,.82);border:1px solid var(--line);border-radius:8px}'
  +'#kvView button{background:transparent;border:0;color:#8b949e;font:12px inherit;font-family:inherit;padding:4px 10px;border-radius:6px;cursor:pointer}#kvView button.on{background:rgba(45,212,191,.15);color:#8fd8cf}'
  +'#kvDemo{position:absolute;left:14px;top:12px;z-index:14;font-size:11px;color:#8b9aa0;display:none;pointer-events:none;background:rgba(16,21,28,.82);border:1px solid var(--line);border-radius:8px;padding:4px 10px}';document.head.appendChild(st);
 const box=document.createElement('div');box.id='kvView';box.setAttribute('role','group');box.setAttribute('aria-label','檢視方式');
 box.innerHTML='<button data-kv-view="topic" class="on" aria-pressed="true">議題</button><button data-kv-view="domain" aria-pressed="false">法領域</button>';zc.parentNode.insertBefore(box,zc);
 const note=document.createElement('div');note.id='kvDemo';note.setAttribute('data-kv-demo-note','');note.textContent='示範資料：狀態與數字是假設值';zc.parentNode.insertBefore(note,zc);
 box.addEventListener('click',e=>{const b=e.target.closest('button[data-kv-view]');if(!b||b.dataset.kvView===kvView)return;kvView=b.dataset.kvView;
  box.querySelectorAll('button').forEach(x=>{const on=x===b;x.classList.toggle('on',on);x.setAttribute('aria-pressed',on)});note.style.display=kvView==='domain'?'block':'none';
  render();buildParticles()});
})();
