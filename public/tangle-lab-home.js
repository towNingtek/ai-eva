// feat/tangle-lab only: after Chainlit's login lands on "/", go to the copilot workspace.
(function(){function go(){if(location.pathname==="/"&&!/[?&]chat=1/.test(location.search))location.replace("/workspace")}
 var push=history.pushState;history.pushState=function(){push.apply(this,arguments);setTimeout(go,0)};
 window.addEventListener("popstate",go);if(document.readyState!=="loading")go();else document.addEventListener("DOMContentLoaded",go)})();
