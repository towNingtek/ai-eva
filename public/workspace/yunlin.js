// v17: replaces the single fictional project with the 10 Yunlin projects. Layout and flow are v15's.
const ylSel=new Map();
const ylById=id=>PROJECTS.find(p=>p.id===id);
const ylTheme=(p,t)=>p&&p.issues.find(i=>i.theme===t);
// step 3a: rank partners by need × offer links (both directions) in kv-match-mock.js
const ylShared=(a,b)=>{const M=window.KV_MATCH;if(!M||!M.projects[a.id]||!M.projects[b.id])return 0;const A=M.projects[a.id].match,B=M.projects[b.id].match;const N=r=>r==='need'||r==='both',O=r=>r==='offer'||r==='both';return Object.keys(A).filter(k=>(N(A[k].role)&&O(B[k].role))||(O(A[k].role)&&N(B[k].role))).length};
function ylPartners(pid){const a=ylById(pid);return PROJECTS.filter(p=>p.id!==pid).sort((x,y)=>ylShared(a,y)-ylShared(a,x))}
function ylOptions(list,selected,withShared){const a=withShared&&ylById(withShared);return list.map(p=>'<option value="'+p.id+'"'+(p.id===selected?' selected':'')+'>'+esc(p.name)+(a?'（可對接 '+ylShared(a,p)+'）':'')+'</option>').join('')}
setup=function(mode,id){const p0=PROJECTS[0].id,q0=ylPartners(p0)[0].id;ylSel.set(id,{p:p0,q:q0});
 return '<div class="field"><label>分析專案<select aria-label="分析專案" id="yl-p-'+id+'" onchange="ylPick('+id+')">'+ylOptions(PROJECTS,p0)+'</select></label>'+(mode==='match'?'<label>合作對象<select aria-label="合作對象" id="yl-q-'+id+'" onchange="ylPick('+id+')">'+ylOptions(ylPartners(p0),q0,p0)+'</select></label><div id="yl-x-'+id+'" class="yl-extra"></div><button type="button" id="yl-add-'+id+'" class="yl-add" onclick="ylAdd('+id+')">＋ 加入比較</button>':'')+'</div><p class="muted">依雲林社區 AI 知識系統公開的計畫理念（固定快照），使用「'+(mode==='match'?'合作比對條件':'法規適用條件')+'」預寫規則 v0.2。</p><div class="actions"><button class="primary" onclick="run(\''+mode+'\','+id+')">確認並開始分析 →</button><button onclick="inputView(\''+mode+'\','+id+')">先看本次輸入</button></div><div class="warning">雲林 10 案固定資料；不連線正式系統，也不呼叫 AI。</div>'};
function ylPick(id){const ps=$('yl-p-'+id),qs=$('yl-q-'+id),p=ps.value;let q=qs?qs.value:null;
 if(qs){const list=ylPartners(p);if(!list.some(x=>x.id===q))q=list[0].id;qs.innerHTML=ylOptions(list,q,p)}const px=(ylSel.get(id)||{}).x||[];ylSel.set(id,{p,q,x:px.filter(x=>x!==p&&x!==q)});ylTitle(id);ylDrawX(id)}
function ylLabel(id){const s=ylSel.get(id);if(!s)return'';const r=records.find(x=>x.id===id),mode=r?r.mode:currentMode,a=ylById(s.p);return a.name+(mode==='match'&&s.q?' × '+ylById(s.q).name:'')+(mode==='match'&&s.x&&s.x.length?s.x.map(x=>' × '+ylById(x).name).join(''):'')}
function ylTitle(id){if(currentId===id&&$('deskTitle'))$('deskTitle').textContent=names[currentMode]+' / '+ylLabel(id);const r=$('yl-receipt-'+id);if(r)r.textContent=ylLabel(id)}
function ylDefault(mode){const a=PROJECTS[0];return a.name+(mode==='match'?' × '+ylPartners(a.id)[0].name:'')}
const ylOpenDesk=openDesk;openDesk=function(mode,id){ylOpenDesk(mode,id);currentMode=mode;$('deskTitle').textContent=names[mode]+' / '+ylLabel(id)};
const ylRun=run;run=function(mode,id){const ps=$('yl-p-'+id);if(ps){const qs=$('yl-q-'+id);ylSel.set(id,{p:ps.value,q:qs?qs.value:null,x:((ylSel.get(id)||{}).x||[])})}ylRun(mode,id);ylTitle(id)};
const ylFrame=originalFrame;originalFrame=function(mode,id){const fresh=!frames.has(id),f=ylFrame(mode,id);if(fresh){const s=ylSel.get(id)||{};f.src='/public/tangle/tangle-'+mode+'.html?v=1794812392&p='+encodeURIComponent(s.p||'')+'&q='+encodeURIComponent(s.q||'')+(s.x&&s.x.length?'&ps='+[s.p,s.q,...s.x].map(encodeURIComponent).join(','):'')}return f};
inputView=function(mode,id){const s=ylSel.get(id)||{p:PROJECTS[0].id},list=[ylById(s.p)].concat(mode==='match'&&s.q?[ylById(s.q)]:[]);
 ai('<p>本次輸入（公開計畫理念原文）：</p>'+list.map(p=>'<p><b>'+esc(p.name)+'</b></p><div class="evidence">'+esc(p.philosophy)+'</div>').join('')+'<p class="muted">固定快照，擷取自雲林社區 AI 知識系統公開頁面；後續引用都出自這段原文。</p>')};
// DD content for the selected project; replaces the fictional evidence table.
function ylSubject(f){const s=ylSel.get(f.id)||{};return ylById(f.subject===2?s.q:s.p)}
function ylEvidence(f){const s=ylSel.get(f.id)||{},T=THEMES[f.code];if(!T)return['這項在計畫理念中沒有原文依據。','關於這項，目前有哪些已知事實可以補充？'];
 const A=ylById(s.p),B=s.q&&ylById(s.q),q=(p)=>{const i=ylTheme(p,f.code);return i?p.name+'：「'+i.quote+'」'+(i.concrete?'':'（原文只寫方向）'):p.name+'：原文未提到'};
 if(f.mode==='law')return[q(A),'可能要留意：'+T.law+' 想先確認：'+T.lawQ];
 if(f.kind==='relation'&&B)return[q(A)+'　'+q(B),'可以從這裡談：'+T.match+'。雙方意願與可投入的人力、時間，原文沒有寫。'];
 return[q(ylSubject(f)),'這項有更具體的人力、時間或資源嗎？知道的話可以補充，「還不知道」也可以。']}

// Step D (2026-11-15): 「＋ 加入比較」— add up to 2 more plans (4 in total). Two-plan use is unchanged.
(function(){const st=document.createElement('style');st.textContent='.yl-add{margin-top:6px;background:none;border:1px dashed transparent;color:#8fd8cf;cursor:pointer;padding:4px 0;font:inherit}.yl-add:disabled{color:#5f6b7a;cursor:default}.yl-extra label{display:flex;gap:6px;align-items:center;margin-top:6px}.yl-extra .yl-rm{background:none;border:0;color:#8a9592;cursor:pointer;font:inherit}';document.head.appendChild(st)})();
function ylDrawX(id){const box=$('yl-x-'+id),btn=$('yl-add-'+id),s=ylSel.get(id)||{};if(!box)return;const x=s.x||[],used=[s.p,s.q,...x];
 box.innerHTML=x.map((pid,i)=>'<label>比較對象 '+(i+3)+'<select aria-label="比較對象 '+(i+3)+'" onchange="ylSetX('+id+','+i+',this.value)">'+ylOptions(PROJECTS.filter(p=>p.id===pid||!used.includes(p.id)),pid)+'</select><button type="button" class="yl-rm" aria-label="移除比較對象 '+(i+3)+'" onclick="ylRmX('+id+','+i+')">移除</button></label>').join('');
 if(btn){btn.disabled=x.length>=2;btn.textContent=x.length>=2?'最多比較 4 個專案':'＋ 加入比較'}}
function ylAdd(id){const s=ylSel.get(id)||{};const x=s.x||[];if(x.length>=2)return;const used=[s.p,s.q,...x],next=ylPartners(s.p).find(p=>!used.includes(p.id));if(!next)return;ylSel.set(id,{...s,x:[...x,next.id]});ylDrawX(id);ylTitle(id)}
function ylSetX(id,i,v){const s=ylSel.get(id)||{};const x=(s.x||[]).slice();x[i]=v;ylSel.set(id,{...s,x});ylDrawX(id);ylTitle(id)}
function ylRmX(id,i){const s=ylSel.get(id)||{};const x=(s.x||[]).slice();x.splice(i,1);ylSel.set(id,{...s,x});ylDrawX(id);ylTitle(id)}
