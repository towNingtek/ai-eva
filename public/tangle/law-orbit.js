// One project planet; rule satellites are not projects. UI-only fictional conditions.
const KV_P=(typeof KV_LAW!=='undefined'&&KV_LAW.projects[YP.id])||null;
// Step 2a: click a domain satellite -> select it, fade the rest, tell Eva. Camera does not move.
let kvSel=null,kvPulse=null;const kvSupp=new Set();
// Orbit pace: same order as the pre-step-1 view (it used .018+i*.002 per moon). One shared value keeps the ring rigid so labels never collide.
const KV_SPIN=.026;
// Step 2b: walk into a domain satellite. kvFx 0..1 eases between the ring view and the focus view.
let kvFocus=null,kvFx=0,kvFocusT0=0,kvFxRaf=0;const KV_DEB_W=.6;
// Entrance copied from v16 app.js: each frame moves k=1-0.0015^dt of the remaining distance,
// starting from where this project sits on the v16 overview (SPOT), small planet, flat small orbit.
const ENT_RM=matchMedia('(prefers-reduced-motion: reduce)').matches;
const V16_SPOT={'台子':[.13,.72],'富琦':[.17,.36],'水尾':[.37,.22],'大庄':[.59,.19],'林中':[.86,.27],'崙峯':[.71,.48],'新庄':[.84,.74],'大德':[.57,.67],'後埔':[.41,.49],'崙仔':[.31,.80]};
let ENTC=null,ENT_DONE=ENT_RM;   // current animated state in screen space (VZ already applied)
const ENT_Z=1.35;
const lawPositions=new Map();let lawSelected=null;let orbitTime=0,orbitPaused=false,orbitHover=false;const reducedMotion=matchMedia("(prefers-reduced-motion: reduce)").matches;
render=function(){return (kvFocus&&kvFx>0)?renderFocus(kvFocus,kvFx):renderDomain()};
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
  const PLACED=[],BODY=r=>(x,y)=>PLACED.push({x0:x-r,y0:y-r,x1:x+r,y1:y+r});(function(){const toW=(r,el)=>{if(!el)return;const b=el.getBoundingClientRect(),sb=document.getElementById('svg').getBoundingClientRect(),k=Wd/sb.width/VZ;
    PLACED.push({x0:(b.left-sb.left)*k-VX/VZ,y0:(b.top-sb.top)*k-VY/VZ,x1:(b.right-sb.left)*k-VX/VZ,y1:(b.bottom-sb.top)*k-VY/VZ})};toW(0,document.getElementById('kvDemo'));toW(0,document.getElementById('zc'))})();
  // Label placement: candidate spots around the moon (radial first, then the other sides, then further out).
  // A spot is accepted only if the whole text block is on screen and touches no placed label, moon, planet or overlay.
  function label(g,x,y,ang,name,fill,sub,subFill,off,clear){const ux=Math.cos(ang),uy=Math.sin(ang);
   const f1=12/VZ,f2=10/VZ,w=Math.max(name.length*f1,sub?sub.length*f2:0),h=f1+(sub?f2*1.15+2:0),m=4/VZ,gap=Math.max(off-8,clear||0,6);
   const X0=-VX/VZ+m,Y0=-VY/VZ+m,X1=-VX/VZ+Wd/VZ-m,Y1=-VY/VZ+Hd/VZ-m;
   // a spot = text block's top-left; anchor decides how x maps back to the <text> x attribute
   const spot=(side,d)=>side==='r'?{l:x+d,t:y-h/2,an:'start'}:side==='l'?{l:x-d-w,t:y-h/2,an:'end'}:side==='t'?{l:x-w/2,t:y-d-h,an:'middle'}:{l:x-w/2,t:y+d,an:'middle'};
   const pref=Math.abs(ux)>.3?(ux>0?['r','t','b','l']:['l','t','b','r']):(uy<0?['t','r','l','b']:['b','r','l','t']);
   const fits=s=>s.l>=X0&&s.t>=Y0&&s.l+w<=X1&&s.t+h<=Y1,free=s=>!PLACED.some(q=>s.l-2<q.x1&&q.x0<s.l+w+2&&s.t-2<q.y1&&q.y0<s.t+h+2);
   let pick=null;search:for(const d of [gap,gap+8,gap+18,gap+30])for(const side of pref){const s=spot(side,d);if(fits(s)&&free(s)){pick=s;break search}}
   if(!pick){const s=spot(pref[0],gap);s.l=Math.min(Math.max(s.l,X0),X1-w);s.t=Math.min(Math.max(s.t,Y0),Y1-h);pick=s}
   PLACED.push({x0:pick.l-2,y0:pick.t-2,x1:pick.l+w+2,y1:pick.t+h+2});
   const anchor=pick.an,lx=anchor==='start'?pick.l:anchor==='end'?pick.l+w:pick.l+w/2,ly=pick.t+f1;
   const t=el('text',{x:lx,y:ly,'text-anchor':anchor,fill,'font-size':fs(12)});t.textContent=name;g.appendChild(t);
  if(sub){const t2=el('text',{x:lx,y:ly+12/VZ*1.15,'text-anchor':anchor,fill:subFill,'font-size':fs(10)});t2.textContent=sub;g.appendChild(t2)}}
 function route(i,from,to,kind,stop,dim){const dx=to.x-from.x,dy=to.y-from.y,L=Math.hypot(dx,dy)||1,ex=to.x-dx/L*stop,ey=to.y-dy/L*stop,mx=(from.x+ex)/2,my=(from.y+ey)/2-18;
  const gid='kv-route-'+i,gr=el('linearGradient',{id:gid,gradientUnits:'userSpaceOnUse',x1:from.x,y1:from.y,x2:ex,y2:ey});STOPS[kind].forEach(([o,a])=>gr.appendChild(el('stop',{offset:o,'stop-color':'#a9dad5','stop-opacity':a})));defs.appendChild(gr);
  svg.appendChild(el('path',{d:`M${from.x},${from.y} Q${mx},${my} ${ex},${ey}`,fill:'none',stroke:'url(#'+gid+')','stroke-width':.8,'pointer-events':'none',opacity:dim?'.25':'1'}));
  if(!dim&&(kind==='high'||kind==='mid'))TRACKS.push({A:from,B:{x:ex,y:ey},cx:mx,cy:my,st:.55,q:1,tag:'kv'+i,from:1,to:1});
  else if(!dim&&kind==='gap'){const T=.6,m=1-T,B={x:m*m*from.x+2*m*T*mx+T*T*ex,y:m*m*from.y+2*m*T*my+T*T*ey},C={x:from.x+(mx-from.x)*T,y:from.y+(my-from.y)*T};TRACKS.push({A:from,B,cx:C.x,cy:C.y,st:.4,q:.65,tag:'kvg'+i,from:1,to:1})}}
 function dots(ang,n,dim){for(let k=0;k<n;k++){const a=ang+(k-(n-1)/2)*.14;svg.appendChild(el('circle',{cx:center.x+Math.cos(a)*43,cy:center.y+Math.sin(a)*43,r:2,fill:'#b6bfcb','pointer-events':'none',opacity:dim?'.3':'1'}))}}
  if(KV_P){KV_LAW.domains.forEach((name,i)=>{const a=-Math.PI*.4+i*(Math.PI*2/KV_LAW.domains.length)+orbitTime*KV_SPIN,st=KV_P.law[name].state;BODY(kvSel===name?17:(st==='na'?8:13))(center.x+Math.cos(a)*R,center.y+Math.sin(a)*R)});
   KV_P.uncovered.forEach((name,j)=>{const a=(j?.1:.9)*Math.PI+orbitTime*KV_SPIN,ux=Math.cos(a),uy=Math.sin(a),vx0=-VX/VZ,vy0=-VY/VZ,vx1=vx0+Wd/VZ,vy1=vy0+Hd/VZ,hx=(ux>=0?vx1-center.x:center.x-vx0)-118,hy=(uy>=0?vy1-center.y:center.y-vy0)-58,R2=Math.min(R*1.5,Math.abs(ux)>.01?hx/Math.abs(ux):1e9,Math.abs(uy)>.01?hy/Math.abs(uy):1e9);BODY(13)(center.x+ux*R2,center.y+uy*R2)});
   BODY(32)(center.x,center.y);{const nf=13/VZ,nw=YP.name.length*nf;PLACED.push({x0:center.x-nw/2-3,y0:center.y+62-nf-3,x1:center.x+nw/2+3,y1:center.y+62+4})}}
 if(KV_P)KV_LAW.domains.forEach((name,i)=>{const v=KV_P.law[name],ang=-Math.PI*.4+i*(Math.PI*2/KV_LAW.domains.length)+orbitTime*KV_SPIN,t={x:center.x+Math.cos(ang)*R,y:center.y+Math.sin(ang)*R},from={x:center.x+Math.cos(ang)*43,y:center.y+Math.sin(ang)*43};
  const st=kvSupp.has(name)?'supplemented':v.state,sel=kvSel===name,dim=!!(kvSel&&!sel);
  const g=el('g',{'data-kv-key':name,'data-kv-state':st,role:'button',tabindex:0,'aria-label':name,style:'cursor:pointer',opacity:dim?'.3':'1'});if(sel)g.setAttribute('data-kv-selected','');if(dim)g.setAttribute('data-kv-dim','');
  if(st==='supplemented'){dots(ang,v.evidence.length,dim);route(i,from,t,'mid',15,dim);svg.appendChild(g);drawMoon(g,t.x,t.y,11,'rule',sel);label(g,t.x,t.y,ang,name,'#d5e1e0','已補充・待重判','#b8e0dd',19,sel?16:0);}
  else if(v.state==='hit'){dots(ang,v.evidence.length,dim);route(i,from,t,v.confidence,15,dim);svg.appendChild(g);g.appendChild(el('circle',{cx:t.x,cy:t.y,r:17,fill:'url(#kv-glow)'}));drawMoon(g,t.x,t.y,11,'rule',sel);
   const parts=[];if(v.count.risk)parts.push(v.count.risk+' 風險');if(v.count.note)parts.push(v.count.note+' 提醒');label(g,t.x,t.y,ang,name,'#d5e1e0',parts.join('・'),v.count.risk?'#e3c79c':'#8fcfc5',19,sel?16:0);}
  else if(v.state==='gap'){dots(ang,v.evidence.length,dim);route(i,from,t,'gap',15,dim);svg.appendChild(g);g.appendChild(el('circle',{cx:t.x,cy:t.y,r:27,fill:'url(#kv-fog)'}));const inner=el('g',{opacity:.5});drawMoon(inner,t.x,t.y,11,'rule',sel);g.appendChild(inner);
   label(g,t.x,t.y,ang,name,'#b9c6c3','缺：'+v.missing,'#96a5a2',22,sel?16:0);}
  else{svg.appendChild(g);const inner=el('g',{opacity:kvPulse===name?.75:.26});drawMoon(inner,t.x,t.y,7,'rule',false);g.appendChild(inner);label(g,t.x,t.y,ang,name,kvPulse===name?'#a9bdb9':'#56625f',null,null,14);}
  if(sel)g.appendChild(el('circle',{cx:t.x,cy:t.y,r:15,fill:'none',stroke:'#a9e3dc','stroke-width':.8,opacity:.85,'pointer-events':'none','data-kv-ring':''}));
  g.appendChild(el('circle',{cx:t.x,cy:t.y,r:16,fill:'transparent'}));kvBind(g,name,v.state);
 });
 if(KV_P)KV_P.uncovered.forEach((name,j)=>{const ang=(j?.1:.9)*Math.PI+orbitTime*KV_SPIN,ux=Math.cos(ang),uy=Math.sin(ang),vx0=-VX/VZ,vy0=-VY/VZ,vx1=vx0+Wd/VZ,vy1=vy0+Hd/VZ,hx=(ux>=0?vx1-center.x:center.x-vx0)-118,hy=(uy>=0?vy1-center.y:center.y-vy0)-58,R2=Math.min(R*1.5,Math.abs(ux)>.01?hx/Math.abs(ux):1e9,Math.abs(uy)>.01?hy/Math.abs(uy):1e9),t={x:center.x+ux*R2,y:center.y+uy*R2},from={x:center.x+Math.cos(ang)*43,y:center.y+Math.sin(ang)*43};
  const dim=!!kvSel;dots(ang,1,dim);route(100+j,from,t,'unc',14,dim);const g=el('g',{'data-kv-key':name,'data-kv-state':'uncovered',role:'button',tabindex:0,'aria-label':name,style:'cursor:pointer',opacity:dim?'.3':'1'});if(dim)g.setAttribute('data-kv-dim','');svg.appendChild(g);
  g.appendChild(el('circle',{cx:t.x,cy:t.y,r:11,fill:'#9fb5b1','fill-opacity':kvPulse===name?.18:.04,stroke:'#a9bfbb','stroke-width':.8,opacity:.8}));label(g,t.x,t.y,ang,name,'#aebdba','未收錄','#7f8f8c',17);kvBind(g,name,'uncovered');});
 const planet=el('g',{'data-project-planet':'1'});drawPlanet(planet,center,28,1,true);svg.appendChild(planet);
 const nm=el('text',{x:center.x,y:center.y+62,'text-anchor':'middle',fill:'#c7e3e1','font-size':fs(13),stroke:'#060a10','stroke-width':3/VZ,'paint-order':'stroke'});nm.textContent=YP.name;planet.appendChild(nm);
}
// Demo disclosure; domain satellites replace the previous fictional topic satellites.
(function(){const zc=document.getElementById('zc');if(!zc||!KV_P)return;
 const st=document.createElement('style');st.textContent='#kvDemo{position:absolute;left:14px;top:12px;z-index:14;font-size:11px;color:#8b9aa0;pointer-events:none;background:rgba(16,21,28,.82);border:1px solid var(--line);border-radius:8px;padding:4px 10px}';document.head.appendChild(st);
 const note=document.createElement('div');note.id='kvDemo';note.setAttribute('data-kv-demo-note','');note.textContent='示範資料：狀態與數字是假設值';zc.parentNode.insertBefore(note,zc);
 const bs=document.createElement('style');bs.textContent='#kvBack{position:absolute;right:14px;top:12px;z-index:14;display:none;font:12px inherit;font-family:inherit;color:#8fd8cf;background:rgba(16,21,28,.82);border:1px solid var(--line);border-radius:8px;padding:5px 11px;cursor:pointer}#kvBack.on{display:block}';document.head.appendChild(bs);
 const back=document.createElement('button');back.id='kvBack';back.setAttribute('data-kv-back','');back.type='button';back.textContent='← 返回專案星系';back.onclick=()=>kvLeave();zc.parentNode.insertBefore(back,zc);
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&kvFocus)kvLeave()});
})();

// ── Step 2a: select / fade / tell Eva ─────────────────────────────────────────────
// hit / gap / supplemented: select it (others fade). na / uncovered: only a short flash.
function kvBind(g,name,state){const go=()=>kvPick(name,state);
 g.onpointerdown=e=>{e.stopPropagation();e.preventDefault();const x=e.clientX,y=e.clientY;
  window.addEventListener('pointerup',u=>{if(Math.hypot(u.clientX-x,u.clientY-y)<5)go()},{once:true})};
 g.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}}
function kvPick(name,state){
 if(state==='hit'||state==='gap'||kvSupp.has(name)){kvSel=name;kvPulse=null;
  if(!kvFocus){kvFocusT0=orbitTime;kvFocus=name;kvAnim(1)}else kvFocus=name}
 else{kvSel=null;kvPulse=name;if(kvFocus)kvAnim(0);setTimeout(()=>{if(kvPulse===name){kvPulse=null;render();buildParticles()}},700)}
 render();buildParticles();
 parent.postMessage({type:'tangle-relation',mode:'law',code:name,tag:name,subject:1,kind:'domain',state},location.origin)}
// click on empty space (no drag) clears the selection
(function(){const sv=document.getElementById('svg');let down=null;
 sv.addEventListener('pointerdown',e=>{down={x:e.clientX,y:e.clientY}});
 sv.addEventListener('pointerup',e=>{if(!down||!kvSel)return;const moved=Math.hypot(e.clientX-down.x,e.clientY-down.y)>=5;down=null;
  if(!moved&&!(e.target.closest&&e.target.closest('[data-kv-key],[data-clause]'))){if(kvFocus){kvLeave();return}kvSel=null;render();buildParticles()}})})();
// Eva confirmed a supplement -> that domain becomes "已補充・待重判" (never the 對上了 look)
window.addEventListener('message',e=>{if(e.origin!==location.origin||e.source!==parent||e.data?.type!=='dd-confirmed')return;
 const k=e.data.code;if(KV_P&&KV_P.law[k]){kvSupp.add(k);render();buildParticles()}});

// ── Step 2b: walk into a satellite ────────────────────────────────────────────────
// hit / gap / supplemented walk in: the satellite moves to centre-right and grows, the planet recedes to the
// lower-left, the other domains fade around it. 對上了 shows its clause debris (real clauses from the corpus;
// WHICH ones match is demo data). The debris ring leaves a gap facing the planet so evidence routes never
// cross a clause body; debris sway gently (stop while the pointer is over the graph). One level only.
function kvAnim(to){const back=document.getElementById('kvBack');if(back)back.classList.toggle('on',to===1);
 cancelAnimationFrame(kvFxRaf);
 const done=()=>{if(to===0){kvFocus=null;orbitTime=kvFocusT0}render();buildParticles()};
 if(ENT_RM){kvFx=to;done();return}
 const from=kvFx,t0=performance.now(),D=600;
 const step=now=>{const k=Math.min(1,(now-t0)/D),ez=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;kvFx=from+(to-from)*ez;
  if(k>=1){kvFx=to;done();return}render();buildParticles();kvFxRaf=requestAnimationFrame(step)};
 kvFxRaf=requestAnimationFrame(step)}
function kvLeave(){if(kvFocus)kvAnim(0)}
function kvTextW(t,f){let w=0;for(const ch of t)w+=ch.charCodeAt(0)>255?f:f*.6;return w}
function renderFocus(key,e){const svg=document.getElementById('svg');svg.setAttribute('viewBox',`${-VX/VZ} ${-VY/VZ} ${Wd/VZ} ${Hd/VZ}`);svg.innerHTML='';TRACKS.length=0;ORPH.length=0;
 svg.appendChild(el('rect',{x:-VX/VZ,y:-VY/VZ,width:Wd/VZ,height:Hd/VZ,fill:'#060a10'}));
 for(let j=0;j<45;j++){svg.appendChild(el('circle',{cx:(j*137.51)%Wd,cy:(j*j*33.7)%Hd,r:j%4===0?.65:.35,fill:'#a5a5c0',opacity:.08+.08*Math.sin(orbitTime*.4+j),'pointer-events':'none'}));}
 const defs=el('defs',{});svg.appendChild(defs);
 const rg=(id,stops)=>{const g=el('radialGradient',{id});stops.forEach(([o,c,a])=>g.appendChild(el('stop',{offset:o,'stop-color':c,'stop-opacity':a})));defs.appendChild(g)};
 rg('kv-glow',[[0,'#a5e7df',.5],[1,'#a5e7df',0]]);rg('kv-fog',[[0,'#d5dfdc',.26],[.55,'#d5dfdc',.1],[1,'#d5dfdc',0]]);rg('fx-haze',[[0,'#70b8b0',.16],[1,'#70b8b0',0]]);
 rg('fx-risk',[[0,'#e3c79c',.5],[1,'#e3c79c',0]]);rg('fx-note',[[0,'#8fcfc5',.42],[1,'#8fcfc5',0]]);
 const fs=n=>(n/VZ).toFixed(2),Lr=(a,b)=>a+(b-a)*e,LP=(a,b)=>({x:Lr(a.x,b.x),y:Lr(a.y,b.y)});
 const W=Wd/VZ,H=Hd/VZ,ox=-VX/VZ,oy=-VY/VZ,T=kvFocusT0;
 // ring-view geometry frozen at the moment we walked in (so walking out lands exactly where we started)
 const cx=Wd/2,cy=Hd/2-Hd*.035/VZ,R=Math.min(Wd,Hd)*.235,oc={x:cx+Math.sin(T*.3)*4,y:cy+Math.cos(T*.25)*3},N=KV_LAW.domains.length;
 const opos=i=>{const a=-Math.PI*.4+i*(Math.PI*2/N)+T*KV_SPIN;return{x:oc.x+Math.cos(a)*R,y:oc.y+Math.sin(a)*R}};
 const upos=j=>{const a=(j?.1:.9)*Math.PI+T*KV_SPIN,ux=Math.cos(a),uy=Math.sin(a),vx0=-VX/VZ,vy0=-VY/VZ,vx1=vx0+Wd/VZ,vy1=vy0+Hd/VZ,hx=(ux>=0?vx1-oc.x:oc.x-vx0)-118,hy=(uy>=0?vy1-oc.y:oc.y-vy0)-58,
   R2=Math.min(R*1.5,Math.abs(ux)>.01?hx/Math.abs(ux):1e9,Math.abs(uy)>.01?hy/Math.abs(uy):1e9);return{x:oc.x+ux*R2,y:oc.y+uy*R2}};
 // focus-view geometry
 const F={x:ox+W*.6,y:oy+H*.47},P={x:ox+W*.17,y:oy+H*.74};
 const v=KV_P.law[key],st=kvSupp.has(key)?'supplemented':v.state,pc=LP(oc,P),pr=Lr(28,17),bc=LP(opos(KV_LAW.domains.indexOf(key)),F),br=Lr(11,30);
 const pd=Math.atan2(P.y-F.y,P.x-F.x);   // direction from the focused satellite to the planet
 // the other domains (and uncovered) fade onto an arc above the receded planet
 const rest=KV_LAW.domains.filter(n=>n!==key).map(n=>({name:n,state:kvSupp.has(n)?'supplemented':KV_P.law[n].state,from:opos(KV_LAW.domains.indexOf(n))}))
  .concat(KV_P.uncovered.map((n,j)=>({name:n,state:'uncovered',from:upos(j)})));
 rest.forEach((o,k)=>{const a=-Math.PI+(k+.5)*(Math.PI/rest.length);o.to={x:P.x+Math.cos(a)*72,y:P.y+Math.sin(a)*58};o.p=LP(o.from,o.to)});
 // evidence routes: planet rim (facing the satellite) -> satellite rim (facing the planet)
 const ev=v.evidence||[];if(e>.05)ev.forEach((q,k)=>{const off=(k-(ev.length-1)/2),a1=pd+Math.PI+off*.35,a2=pd+off*.3,
   from={x:pc.x+Math.cos(a1)*(pr+5),y:pc.y+Math.sin(a1)*(pr+5)},to={x:bc.x+Math.cos(a2)*(br+3),y:bc.y+Math.sin(a2)*(br+3)},
   dx=to.x-from.x,dy=to.y-from.y,Ln=Math.hypot(dx,dy)||1,mx=(from.x+to.x)/2-dy/Ln*(10+k*5),my=(from.y+to.y)/2+dx/Ln*(10+k*5),id='fx-e'+k,
   gr=el('linearGradient',{id,gradientUnits:'userSpaceOnUse',x1:from.x,y1:from.y,x2:to.x,y2:to.y});[[0,.15],[.5,.55],[1,.7]].forEach(([o,al])=>gr.appendChild(el('stop',{offset:o,'stop-color':'#a9dad5','stop-opacity':al})));defs.appendChild(gr);
  svg.appendChild(el('circle',{cx:from.x,cy:from.y,r:1.9,fill:'#d6dee6',opacity:e,'pointer-events':'none'}));
  svg.appendChild(el('path',{d:`M${from.x},${from.y} Q${mx},${my} ${to.x},${to.y}`,fill:'none',stroke:`url(#${id})`,'stroke-width':.8,opacity:e,'pointer-events':'none','data-fx-route':''}));
  if(e>=1)TRACKS.push({A:from,B:to,cx:mx,cy:my,st:.55,q:1,tag:'fx'+k,from:1,to:1})});
 // clause debris (對上了 only)
 const C=(st==='hit'&&v.clauses)||[],ap=Math.max(0,Math.min(1,(e-.45)/.55)),dR=Math.min(88,Math.min(W,H)*.2)*(.6+.4*ap),GAP=.62,span=Math.PI*2-2*GAP,
  sway=e>=1?.1*Math.sin((orbitTime-T)*KV_DEB_W):0;
 const deb=ap>0?C.map((c,i)=>{const a=pd+GAP+(i+.5)*span/C.length+sway;return{c,risk:c.kind==='risk',a,x:bc.x+Math.cos(a)*dR,y:bc.y+Math.sin(a)*dR*.86}}):[];
 deb.forEach((d,i)=>{const ux=Math.cos(d.a),uy=Math.sin(d.a),s0={x:bc.x+ux*(br+4),y:bc.y+uy*(br+4)*.86},s1={x:d.x-ux*8,y:d.y-uy*8},id='fx-s'+i,
   gr=el('linearGradient',{id,gradientUnits:'userSpaceOnUse',x1:s0.x,y1:s0.y,x2:s1.x,y2:s1.y});[[0,.35],[1,.08]].forEach(([o,al])=>gr.appendChild(el('stop',{offset:o,'stop-color':d.risk?'#e8d2ad':'#a9dad5','stop-opacity':al})));defs.appendChild(gr);
  svg.appendChild(el('path',{d:`M${s0.x},${s0.y} L${s1.x},${s1.y}`,stroke:`url(#${id})`,'stroke-width':.6,fill:'none',opacity:ap,'pointer-events':'none'}))});
 // faded domains
 rest.forEach(o=>{const g=el('g',{'data-kv-key':o.name,'data-kv-state':o.state,'data-kv-dim':'',role:'button',tabindex:0,'aria-label':o.name,style:'cursor:pointer',opacity:Lr(o.state==='na'?.26:1,.22).toFixed(3)});svg.appendChild(g);
  if(o.state==='uncovered')g.appendChild(el('circle',{cx:o.p.x,cy:o.p.y,r:Lr(11,4.5),fill:'#9fb5b1','fill-opacity':.04,stroke:'#a9bfbb','stroke-width':.8}));
  else drawMoon(g,o.p.x,o.p.y,Lr(o.state==='na'?7:11,4.5),'rule',false);
  g.appendChild(el('circle',{cx:o.p.x,cy:o.p.y,r:9,fill:'transparent'}));kvBind(g,o.name,o.state)});
 // planet
 svg.appendChild(el('circle',{cx:pc.x,cy:pc.y,r:Lr(85,46),fill:'url(#fx-haze)','pointer-events':'none'}));
 const planet=el('g',{'data-project-planet':'1'});drawPlanet(planet,pc,pr,1,false);svg.appendChild(planet);
 // focused satellite
 const g=el('g',{'data-kv-key':key,'data-kv-state':st,'data-kv-selected':'','data-focus':key,role:'button',tabindex:0,'aria-label':key,style:'cursor:pointer'});svg.appendChild(g);
 if(st==='gap'){g.appendChild(el('circle',{cx:bc.x,cy:bc.y,r:Lr(27,70),fill:'url(#kv-fog)'}));const inner=el('g',{opacity:.5});drawMoon(inner,bc.x,bc.y,br,'rule',true);g.appendChild(inner)}
 else{g.appendChild(el('circle',{cx:bc.x,cy:bc.y,r:Lr(17,58),fill:'url(#kv-glow)'}));drawMoon(g,bc.x,bc.y,br,'rule',true)}
 g.appendChild(el('circle',{cx:bc.x,cy:bc.y,r:br+2,fill:'transparent'}));kvBind(g,key,v.state);
 // debris bodies
 const debG=deb.map(d=>{const dg=el('g',{'data-clause':d.c.law+' '+d.c.no,'data-clause-kind':d.risk?'risk':'note',opacity:ap.toFixed(3)});svg.appendChild(dg);
  dg.appendChild(el('circle',{cx:d.x,cy:d.y,r:11,fill:d.risk?'url(#fx-risk)':'url(#fx-note)','pointer-events':'none'}));drawMoon(dg,d.x,d.y,5.2,d.risk?'need':'offer',false);return dg});
 // ── text: title + status on the satellite, project name, debris labels (placed to avoid everything) ──
 const parts=[];if(st==='hit'){if(v.count.risk)parts.push(v.count.risk+' 風險');if(v.count.note)parts.push(v.count.note+' 提醒')}
 const subT=st==='hit'?parts.join('・'):st==='gap'?'缺：'+v.missing:'已補充・待重判',subC=st==='hit'?(v.count.risk?'#e3c79c':'#8fcfc5'):st==='gap'?'#96a5a2':'#b8e0dd';
 const t1=el('text',{x:bc.x,y:bc.y-br-12/VZ,'text-anchor':'middle',fill:'#e4efed','font-size':fs(15),opacity:e.toFixed(3)});t1.textContent=key;g.appendChild(t1);
 const t2=el('text',{x:bc.x,y:bc.y+br+16/VZ,'text-anchor':'middle',fill:subC,'font-size':fs(11),opacity:e.toFixed(3)});t2.textContent=subT;g.appendChild(t2);
 const nm=el('text',{x:pc.x,y:pc.y+pr+16/VZ,'text-anchor':'middle',fill:'#9fb8b6','font-size':fs(11),stroke:'#060a10','stroke-width':3/VZ,'paint-order':'stroke'});nm.textContent=YP.name;planet.appendChild(nm);
 if(e<1)return;
 const m=4/VZ,X0=ox+m,Y0=oy+m,X1=ox+W-m,Y1=oy+H-m,PLACED=[];
 const scr=el2=>{if(!el2||getComputedStyle(el2).display==='none')return;const b=el2.getBoundingClientRect(),sb=svg.getBoundingClientRect(),k=Wd/sb.width/VZ;PLACED.push({x0:(b.left-sb.left)*k+ox,y0:(b.top-sb.top)*k+oy,x1:(b.right-sb.left)*k+ox,y1:(b.bottom-sb.top)*k+oy})};
 ['kvDemo','zc','kvBack'].forEach(id=>scr(document.getElementById(id)));
 const body=(x,y,r)=>PLACED.push({x0:x-r,y0:y-r,x1:x+r,y1:y+r});body(bc.x,bc.y,br+3);body(pc.x,pc.y,pr+4);rest.forEach(o=>body(o.p.x,o.p.y,6));deb.forEach(d=>body(d.x,d.y,7));
 const tb=(t,f,an)=>{const w=kvTextW(t.textContent,f),x=+t.getAttribute('x'),y=+t.getAttribute('y'),l=an==='middle'?x-w/2:an==='end'?x-w:x;PLACED.push({x0:l-2,y0:y-f-2,x1:l+w+2,y1:y+3})};
 tb(t1,15/VZ,'middle');tb(t2,11/VZ,'middle');tb(nm,11/VZ,'middle');
 const f=9/VZ;deb.forEach((d,i)=>{const short=d.c.law.replace(/^(辦理|農業部補助直轄市及縣（市）政府推動|農村社區)/,''),lbl=(short.length>11?short.slice(0,11)+'…':short)+' '+d.c.no,w=kvTextW(lbl,f),h=f+2;
  const ux=Math.cos(d.a),uy=Math.sin(d.a),spot=(side,dd)=>side==='r'?{l:d.x+dd,t:d.y-h/2,an:'start'}:side==='l'?{l:d.x-dd-w,t:d.y-h/2,an:'end'}:side==='t'?{l:d.x-w/2,t:d.y-dd-h,an:'middle'}:{l:d.x-w/2,t:d.y+dd,an:'middle'};
  const pref=Math.abs(ux)>.35?(ux>0?['r','t','b','l']:['l','t','b','r']):(uy<0?['t','r','l','b']:['b','r','l','t']);
  const fits=s=>s.l>=X0&&s.t>=Y0&&s.l+w<=X1&&s.t+h<=Y1,free=s=>!PLACED.some(q=>s.l-1<q.x1&&q.x0<s.l+w+1&&s.t-1<q.y1&&q.y0<s.t+h+1);
  let pick=null;search:for(const dd of [10,16,24,34])for(const side of pref){const sp=spot(side,dd);if(fits(sp)&&free(sp)){pick=sp;break search}}
  if(!pick){const sp=spot(pref[0],10);sp.l=Math.min(Math.max(sp.l,X0),X1-w);sp.t=Math.min(Math.max(sp.t,Y0),Y1-h);pick=sp}
  PLACED.push({x0:pick.l-1,y0:pick.t-1,x1:pick.l+w+1,y1:pick.t+h+1});
  const lx=pick.an==='start'?pick.l:pick.an==='end'?pick.l+w:pick.l+w/2,lt=el('text',{x:lx,y:pick.t+f,'text-anchor':pick.an,fill:d.risk?'#e8d5b5':'#b9dcd7','font-size':fs(9)});lt.textContent=lbl;debG[i].appendChild(lt)});
}
