// One project planet; rule satellites are not projects. UI-only fictional conditions.
const lawRules=YL.lawRules();
// Entrance copied from v16 app.js: each frame moves k=1-0.0015^dt of the remaining distance,
// starting from where this project sits on the v16 overview (SPOT), small planet, flat small orbit.
const ENT_RM=matchMedia('(prefers-reduced-motion: reduce)').matches;
const V16_SPOT={'台子':[.13,.72],'富琦':[.17,.36],'水尾':[.37,.22],'大庄':[.59,.19],'林中':[.86,.27],'崙峯':[.71,.48],'新庄':[.84,.74],'大德':[.57,.67],'後埔':[.41,.49],'崙仔':[.31,.80]};
let ENTC=null,ENT_DONE=ENT_RM;   // current animated state in screen space (VZ already applied)
const ENT_Z=1.35;
const lawPositions=new Map();let lawSelected=null;let orbitTime=0,orbitPaused=false,orbitHover=false;const reducedMotion=matchMedia("(prefers-reduced-motion: reduce)").matches;
render=function(){const svg=document.getElementById('svg');svg.setAttribute('viewBox',`${-VX/VZ} ${-VY/VZ} ${Wd/VZ} ${Hd/VZ}`);svg.innerHTML='';TRACKS.length=0;ORPH.length=0;
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
