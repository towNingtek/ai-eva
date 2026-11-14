// v17: replaces the single fictional project with the 10 Yunlin projects. Layout and flow are v15's.
const ylSel=new Map();
const ylById=id=>PROJECTS.find(p=>p.id===id);
const ylTheme=(p,t)=>p&&p.issues.find(i=>i.theme===t);
const ylShared=(a,b)=>a.issues.filter(i=>ylTheme(b,i.theme)).length;
function ylPartners(pid){const a=ylById(pid);return PROJECTS.filter(p=>p.id!==pid).sort((x,y)=>ylShared(a,y)-ylShared(a,x))}
function ylOptions(list,selected,withShared){const a=withShared&&ylById(withShared);return list.map(p=>'<option value="'+p.id+'"'+(p.id===selected?' selected':'')+'>'+esc(p.name)+(a?'（共同議題 '+ylShared(a,p)+'）':'')+'</option>').join('')}
setup=function(mode,id){const p0=PROJECTS[0].id,q0=ylPartners(p0)[0].id;ylSel.set(id,{p:p0,q:q0});
 return '<div class="field"><label>分析專案<select aria-label="分析專案" id="yl-p-'+id+'" onchange="ylPick('+id+')">'+ylOptions(PROJECTS,p0)+'</select></label>'+(mode==='match'?'<label>合作對象<select aria-label="合作對象" id="yl-q-'+id+'" onchange="ylPick('+id+')">'+ylOptions(ylPartners(p0),q0,p0)+'</select></label>':'')+'</div><p class="muted">依雲林社區 AI 知識系統公開的計畫理念（固定快照），使用「'+(mode==='match'?'合作比對條件':'法規適用條件')+'」預寫規則 v0.2。</p><div class="actions"><button class="primary" onclick="run(\''+mode+'\','+id+')">確認並開始分析 →</button><button onclick="inputView(\''+mode+'\','+id+')">先看本次輸入</button></div><div class="warning">雲林 10 案固定資料；不連線正式系統，也不呼叫 AI。</div>'};
function ylPick(id){const ps=$('yl-p-'+id),qs=$('yl-q-'+id),p=ps.value;let q=qs?qs.value:null;
 if(qs){const list=ylPartners(p);if(!list.some(x=>x.id===q))q=list[0].id;qs.innerHTML=ylOptions(list,q,p)}ylSel.set(id,{p,q});ylTitle(id)}
function ylLabel(id){const s=ylSel.get(id);if(!s)return'';const r=records.find(x=>x.id===id),mode=r?r.mode:currentMode,a=ylById(s.p);return a.name+(mode==='match'&&s.q?' × '+ylById(s.q).name:'')}
function ylTitle(id){if(currentId===id&&$('deskTitle'))$('deskTitle').textContent=names[currentMode]+' / '+ylLabel(id);const r=$('yl-receipt-'+id);if(r)r.textContent=ylLabel(id)}
function ylDefault(mode){const a=PROJECTS[0];return a.name+(mode==='match'?' × '+ylPartners(a.id)[0].name:'')}
const ylOpenDesk=openDesk;openDesk=function(mode,id){ylOpenDesk(mode,id);currentMode=mode;$('deskTitle').textContent=names[mode]+' / '+ylLabel(id)};
const ylRun=run;run=function(mode,id){const ps=$('yl-p-'+id);if(ps){const qs=$('yl-q-'+id);ylSel.set(id,{p:ps.value,q:qs?qs.value:null})}ylRun(mode,id);ylTitle(id)};
const ylFrame=originalFrame;originalFrame=function(mode,id){const fresh=!frames.has(id),f=ylFrame(mode,id);if(fresh){const s=ylSel.get(id)||{};f.src='/public/tangle/tangle-'+mode+'.html?v=1794660267&p='+encodeURIComponent(s.p||'')+'&q='+encodeURIComponent(s.q||'')}return f};
inputView=function(mode,id){const s=ylSel.get(id)||{p:PROJECTS[0].id},list=[ylById(s.p)].concat(mode==='match'&&s.q?[ylById(s.q)]:[]);
 ai('<p>本次輸入（公開計畫理念原文）：</p>'+list.map(p=>'<p><b>'+esc(p.name)+'</b></p><div class="evidence">'+esc(p.philosophy)+'</div>').join('')+'<p class="muted">固定快照，擷取自雲林社區 AI 知識系統公開頁面；後續引用都出自這段原文。</p>')};
// DD content for the selected project; replaces the fictional evidence table.
function ylSubject(f){const s=ylSel.get(f.id)||{};return ylById(f.subject===2?s.q:s.p)}
function ylEvidence(f){const s=ylSel.get(f.id)||{},T=THEMES[f.code];if(!T)return['這項在計畫理念中沒有原文依據。','關於這項，目前有哪些已知事實可以補充？'];
 const A=ylById(s.p),B=s.q&&ylById(s.q),q=(p)=>{const i=ylTheme(p,f.code);return i?p.name+'：「'+i.quote+'」'+(i.concrete?'':'（原文只寫方向）'):p.name+'：原文未提到'};
 if(f.mode==='law')return[q(A),'可能要留意：'+T.law+' 想先確認：'+T.lawQ];
 if(f.kind==='relation'&&B)return[q(A)+'　'+q(B),'可以從這裡談：'+T.match+'。雙方意願與可投入的人力、時間，原文沒有寫。'];
 return[q(ylSubject(f)),'這項有更具體的人力、時間或資源嗎？知道的話可以補充，「還不知道」也可以。']}
