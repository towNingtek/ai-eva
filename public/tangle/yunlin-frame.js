// v17: feeds the selected Yunlin project(s) into the unchanged v15 graph pages.
// Parent passes ?p=<project id>&q=<partner id>. Subject 1 = primary, 2 = partner.
const YQS=new URLSearchParams(location.search);
const YP=PROJECTS.find(p=>p.id===YQS.get('p'))||PROJECTS[0];
const YQ2=PROJECTS.find(p=>p.id===YQS.get('q')&&p.id!==YP.id)||PROJECTS.find(p=>p.id!==YP.id);
const YL={
 BN:Object.fromEntries(Object.entries(THEMES).map(([k,v])=>[k,v.label])),
 primary:YP,partner:YQ2,
 // Step 3a: satellites are B1–B8. need/offer come from kv-match-mock.js (demo roles, real quotes).
 // Routes are built by the page from need × offer; same-side (need↔need) never connects.
 matchP(){const sim={topic:.5,exec:.5,stage:.5,xborder:0},pick=(pr,role)=>{const m=KV_MATCH.projects[pr.id].match;return Object.keys(m).filter(k=>m[k].role===role||m[k].role==='both').map(k=>[k,.8,1])};   // standard v1.1: BOTH = need and offer
  const PS=(YQS.get('ps')||'').split(',').map(id=>PROJECTS.find(p=>p.id===id)).filter((p,i,a)=>p&&a.indexOf(p)===i).slice(0,4);   // step D: 2–4 plans
  return(PS.length>=2?PS:[YP,YQ2]).map((pr,i)=>({id:i+1,pid:pr.id,name:pr.name,n:pick(pr,'need'),o:pick(pr,'offer'),sim}))},
 lawRules(){return YP.issues.map(i=>({code:i.theme,label:THEMES[i.theme].label,q:i.concrete?1:.3}))}
};
