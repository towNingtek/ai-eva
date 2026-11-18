"""Loopback-only browser fixture for real law task persistence and report generation.

Chainlit's transport objects are captured, not its actual UI/socket or authentication.
Run with the app Python environment: PYTHONPATH=. python tests/lab/law-task-fixture.py 8794.
"""
import asyncio
import base64
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.routing import Route

from app.apps.regulation_check import task

ROOT = Path(__file__).resolve().parents[2]
work = tempfile.TemporaryDirectory(prefix="eva-law-fixture-")
task.TASK_DIR = Path(work.name)
thread_path = task.scope_path({"tenant_id": "fixture", "user_id": "fixture"}, "fixture-thread")
commands, files = [], {}
released = asyncio.Event()
judge_calls = 0
name, uuid = "海風社區測試計畫", "fixture-project"
phrase = "本社區計畫辦理食農體驗及場域導覽，由社區居民共同參與。"
result = {
    "findings": [{"regulation": "測試法規", "article_no": "第1條", "law_domain": "土地使用",
                  "verdict": "觸發", "section": "合規提醒", "severity": "low",
                  "evidence": phrase, "evidence_verified": True, "reasoning": "原始報告測試證據"}],
    "coverage": {"evaluated": 1, "controls": 1, "category": "農村再生", "domains": ["土地使用"]},
    "elapsed": 1.25,
}


class Runtime:
    async def execute(self, operation, args):
        if operation == "list_my_projects":
            return {"status": "ok", "result": {"data": {"projects": [uuid]}}}
        assert operation == "get_project_info" and args == {"uuid": uuid}
        return {"status": "ok", "result": {"data": {"name": name, "philosophy": f"<p>{phrase * 6}</p>"}}}


class CopilotFunction:
    def __init__(self, **kwargs):
        self.command = kwargs

    async def acall(self):
        commands.append(self.command)
        return {"ok": True}


class File:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Message:
    def __init__(self, content, elements=()):
        self.content, self.elements, self.id = content, elements, uuid4().hex

    async def send(self):
        for file in self.elements:
            assert file.mime == "text/markdown" and file.display == "inline"
            files[self.id] = file
        return self


async def run_check(plan, category, *, model, on_progress):
    global judge_calls
    judge_calls += 1
    assert plan == phrase * 6 and category == "農村再生" and model == "fixture-judge"
    await on_progress({"domain": "土地使用", "total": 1, "hit": 1, "elapsed": 1.25})
    await released.wait()
    return result


async def no_profile(_):
    return None  # prevent external notifications


class FixedReportTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 18, 21, 30, tzinfo=tz)


task.cl.CopilotFunction = CopilotFunction
task.cl.Message = Message
task.cl.File = File
class UserSession(dict):
    def set(self, key, value):
        self[key] = value


task.cl.user_session = UserSession()
task.handler.judge.run_check = run_check
task.handler.project_registry.get_project = no_profile
task.handler.report.datetime = FixedReportTime
runtime = Runtime()
app = Starlette()
app.mount('/public', StaticFiles(directory=ROOT / 'public'))

def route(path, methods=None):
    def install(endpoint):
        app.routes.append(Route(path, endpoint, methods=methods))
        return endpoint
    return install


@route('/')
async def index(_):
    return HTMLResponse('''<!doctype html><meta charset="utf-8"><body>
<div id="root"><button id="open">法規檢核</button><section id="chat"></section></div>
<script src="/public/tangle-lab-overlay.js"></script>
<script>
  const post = (url, data) => fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  document.querySelector('#open').onclick = () => post('/fixture/open', {});
  window.addEventListener('message', e => {
    if (e.origin === location.origin && e.data?.tangle?.kind === 'law_task') post('/fixture/event', e.data);
  });
  let cursor = 0;
  async function pump(){
    const data = await fetch(`/fixture/transport?cursor=${cursor}`).then(r => r.json());
    cursor += data.commands.length;
    for (const detail of data.commands) window.dispatchEvent(new CustomEvent('chainlit-call-fn',{detail}));
    for (const file of data.files) {
      if (document.getElementById(file.id)) continue;
      const link = document.createElement('a');
      link.id = file.id;
      link.href = '/fixture/attachment/' + file.id;
      link.download = file.name;
      link.textContent = file.name;
      document.querySelector('#chat').append(link);
    }
    setTimeout(pump, 35);
  }
  pump();
</script></body>''')


@route('/fixture/open', methods=['POST'])
async def open_task(_):
    await task.open_task(thread_path, runtime)
    return Response(status_code=204)


@route('/fixture/event', methods=['POST'])
async def event(request):
    data = (await request.json()).get('tangle') or {}
    await task.handle_event(thread_path, runtime, data, 'fixture-judge')
    return Response(status_code=204)


@route('/fixture/transport')
async def transport(request):
    cursor = int(request.query_params.get('cursor', '0'))
    return JSONResponse({'commands':commands[cursor:], 'files':[{'id':id, 'name':f.name} for id, f in files.items()]})


@route('/fixture/release', methods=['POST'])
async def release(_):
    released.set()
    return Response(status_code=204)


@route('/fixture/state')
async def state(_):
    md = task.handler.report.build(result, plan_name=name, plan_uuid=uuid)
    return JSONResponse({'judgeCalls':judge_calls, 'persisted':task._load(thread_path), 'attachmentCount':len(files),
                         'expectedMd':base64.b64encode(md.encode('utf-8')).decode('ascii')})


@route('/fixture/attachment/{id}')
async def attachment(request):
    file = files.get(request.path_params['id'])
    return Response(file.content, media_type=file.mime) if file else Response(status_code=404)


if __name__ == '__main__':
    import sys
    uvicorn.run(app, host='127.0.0.1', port=int(sys.argv[1]), access_log=False)
