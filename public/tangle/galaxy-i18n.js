// #249 媒合星球頁的介面字（tangle-match.html）。語言由網址 ?lang=en|ja|ko|zh 決定（match-task.js 建 iframe 時帶上）；
// 沒帶或不認得一律 zh，畫面與原本完全相同。B1–B8 名稱與 app/matching/i18n.py 的 CAPABILITY_NAMES 一致。
// 專案名稱、計畫原文是使用者資料，不經過這裡。送給 parent 的 postMessage（tag 等）維持中文，只換畫面上看得到的字。
(function(){
 var q=new URLSearchParams(location.search),raw=String(q.get('lang')||'').toLowerCase().split(/[-_]/)[0];
 var lang={en:1,ja:1,ko:1}[raw]?raw:'zh';
 var ZH_BN={B1:'空間與場域',B2:'產品與生產',B3:'服務與體驗',B4:'內容與品牌',B5:'人才與專業',B6:'社群與關係',B7:'市場與通路',B8:'治理與平台'};
 var BN={
  en:{B1:'Space & Venues',B2:'Products & Production',B3:'Services & Experiences',B4:'Content & Branding',
      B5:'Talent & Expertise',B6:'Community & Relationships',B7:'Markets & Channels',B8:'Governance & Platforms'},
  ja:{B1:'スペースと場づくり',B2:'ものづくりと生産',B3:'サービスと体験',B4:'コンテンツとブランド',
      B5:'人材とスキル',B6:'コミュニティとつながり',B7:'マーケットと販路',B8:'ガバナンスとプラットフォーム'},
  ko:{B1:'공간과 장소',B2:'제품과 생산',B3:'서비스와 체험',B4:'콘텐츠와 브랜드',
      B5:'인재와 전문성',B6:'커뮤니티와 관계',B7:'시장과 유통',B8:'거버넌스와 플랫폼'}
 };
 // zh 原字 → 各語言。查不到就回原字（zh 一定回原字）。
 var T={
  en:{'・需要':' · Needs','・能提供':' · Can offer','・需要＋能提供':' · Needs + can offer','沒有對象':'No partner yet',
      '：':': ','兩邊都需要':'both need it','兩邊都能提供':'both can offer it','待釐清':'to be clarified','有依據的關係':'relation backed by evidence',
      '媒合狀態':'Match status','已補充 · 未查證':'Added · not verified','← 返回兩個星系':'← Back to both galaxies',
      '兩邊都能提供：可聯合或交流（需另判競合）':'Both can offer: joint work or exchange (check for competition separately)',
      '互補候選：能提供 → 需要':'Complement candidate: can offer → needs',
      '可探索':'Worth exploring','先補資料':'Add details first','可排序・未建議':'Rankable, not suggested','不在範圍':'Out of scope',
      '重設':'Reset view'},
  ja:{'・需要':'・必要','・能提供':'・提供できる','・需要＋能提供':'・必要＋提供できる','沒有對象':'相手なし',
      '：':'：','兩邊都需要':'両方とも必要','兩邊都能提供':'両方とも提供できる','待釐清':'確認が必要','有依據的關係':'根拠のある関係',
      '媒合狀態':'マッチングのステータス','已補充 · 未查證':'追加ずみ・まだ確認していません','← 返回兩個星系':'← 2つの星系にもどる',
      '兩邊都能提供：可聯合或交流（需另判競合）':'両方とも提供できる：いっしょに動く・交流する（競合かどうかは別に判断）',
      '互補候選：能提供 → 需要':'補いあいの候補：提供できる → 必要',
      '可探索':'検討できる','先補資料':'先に情報を補う','可排序・未建議':'順位付けのみ・提案なし','不在範圍':'対象外',
      '重設':'表示をリセット'},
  ko:{'・需要':' · 필요','・能提供':' · 제공 가능','・需要＋能提供':' · 필요 + 제공 가능','沒有對象':'상대 없음',
      '：':': ','兩邊都需要':'양쪽 모두 필요','兩邊都能提供':'양쪽 모두 제공 가능','待釐清':'확인 필요','有依據的關係':'근거 있는 관계',
      '媒合狀態':'매칭 상태','已補充 · 未查證':'보충됨 · 미확인','← 返回兩個星系':'← 두 은하로 돌아가기',
      '兩邊都能提供：可聯合或交流（需另判競合）':'양쪽 모두 제공 가능: 공동 추진 또는 교류(경쟁 여부는 따로 판단)',
      '互補候選：能提供 → 需要':'보완 후보: 제공 가능 → 필요',
      '可探索':'탐색 가능','先補資料':'먼저 정보 보완','可排序・未建議':'순위만·제안 없음','不在範圍':'범위 밖',
      '重設':'보기 초기화'}
 };
 var QUOTES={zh:function(n){return n+' 段原文'},en:function(n){return n+(n===1?' source quote':' source quotes')},
  ja:function(n){return '原文 '+n+' か所'},ko:function(n){return '원문 '+n+'개'}};
 function t(zh){var m=T[lang];return m&&Object.prototype.hasOwnProperty.call(m,zh)?m[zh]:zh}
 var names={};Object.keys(ZH_BN).forEach(function(k){names[k]=lang==='zh'?ZH_BN[k]:BN[lang][k]});
 window.GI18N={lang:lang,t:t,bn:names,bnZh:ZH_BN,quotes:QUOTES[lang]};
 if(lang!=='zh'){
  document.documentElement.lang=lang;
  var fit=function(){var b=document.getElementById('zFit');if(b)b.setAttribute('title',t('重設'))};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fit);else fit();
 }
})();
