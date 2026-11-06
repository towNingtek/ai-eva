// v17: feeds the selected Yunlin project(s) into the unchanged v15 graph pages.
// Parent passes ?p=<project id>&q=<partner id>. Subject 1 = primary, 2 = partner.
const YQS=new URLSearchParams(location.search);
const YP=PROJECTS.find(p=>p.id===YQS.get('p'))||PROJECTS[0];
const YQ2=PROJECTS.find(p=>p.id===YQS.get('q')&&p.id!==YP.id)||PROJECTS.find(p=>p.id!==YP.id);
const YL={
 BN:Object.fromEntries(Object.entries(THEMES).map(([k,v])=>[k,v.label])),
 primary:YP,partner:YQ2,
 // Shared topics become routes; uncertain (direction-only) quotes stay faded. No NEED/OFFER claim.
 matchP(){const t=i=>[i.theme,.7,i.concrete?1:.3],sim={topic:.5,exec:.5,stage:.5,xborder:0};
  return[{id:1,name:YP.name,n:YP.issues.map(t),o:[],sim},{id:2,name:YQ2.name,n:[],o:YQ2.issues.map(t),sim}]},
 lawRules(){return YP.issues.map(i=>({code:i.theme,label:THEMES[i.theme].label,q:i.concrete?1:.3}))}
};
