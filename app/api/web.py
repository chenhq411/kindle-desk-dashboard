from contextlib import asynccontextmanager
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response


def create_app(service, *, workers=True):
    token = secrets.token_urlsafe(32)
    @asynccontextmanager
    async def lifespan(app):
        if workers:
            service.start()
        yield
        if workers:
            service.close()
    app = FastAPI(title='Kindle Desk Dashboard', docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    @app.middleware('http')
    async def local_only(request: Request, call_next):
        port = service.settings.snapshot()['management_port']
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if request.headers.get('host') not in hosts:
            return JSONResponse({'detail': 'Local host required'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin not in {'http://' + host for host in hosts}:
            return JSONResponse({'detail': 'Local origin required'}, status_code=403)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            received = request.headers.get('x-kdd-token', '')
            if not secrets.compare_digest(received.encode('utf-8'), token.encode('ascii')):
                return JSONResponse({'detail': 'Refresh the local management page'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        return response

    @app.get('/', response_class=HTMLResponse)
    def index():
        return (Path(__file__).parent / 'index.html').read_text(encoding='utf-8')

    @app.get('/app.js')
    def javascript():
        return Response((Path(__file__).parent / 'app.js').read_text(encoding='utf-8'), media_type='text/javascript')

    @app.get('/api/bootstrap')
    def bootstrap():
        return {'app_id': 'KindleDeskDashboard', 'token': token, 'state': service.snapshot()}

    @app.get('/api/state')
    def state():
        return service.snapshot()

    @app.get('/api/logs')
    def logs():
        return {'lines': service.logs()}

    @app.get('/preview/{page}.png')
    def preview(page: str):
        if page not in ('work', 'pc'):
            raise HTTPException(404)
        frame = service.frame(page)
        if not frame:
            raise HTTPException(503, 'Rendering initial frame')
        return Response(frame['png'], media_type='image/png', headers={'ETag': '"' + frame['sha256'] + '"'})

    @app.post('/api/tasks')
    def add_task(body: dict):
        try:
            task = service.tasks.write(body)
        except (ValueError, TypeError):
            raise HTTPException(422, '请检查事项、日期、时间和地点；结束时间不能早于开始时间')
        service.request_refresh()
        return task

    @app.put('/api/tasks/{task_id}')
    def edit_task(task_id: int, body: dict):
        try:
            task = service.tasks.write(body, task_id)
        except KeyError:
            raise HTTPException(404, '待办不存在')
        except (ValueError, TypeError):
            raise HTTPException(422, '请检查事项、日期、时间和地点；结束时间不能早于开始时间')
        service.request_refresh()
        return task

    @app.delete('/api/tasks/{task_id}')
    def delete_task(task_id: int):
        try:
            service.tasks.delete(task_id)
        except KeyError:
            raise HTTPException(404, '待办不存在')
        service.request_refresh()
        return {'ok': True}

    @app.post('/api/settings')
    def settings(body: dict):
        try:
            service.settings.save(body)
        except (ValueError, TypeError):
            raise HTTPException(422, '无效设置：刷新间隔至少60秒')
        service.request_refresh()
        return service.settings.snapshot()

    @app.post('/api/refresh')
    def refresh():
        service.request_refresh()
        return {'queued': True}

    @app.post('/api/service/{action}')
    def control(action: str):
        if action not in ('start', 'stop'):
            raise HTTPException(404)
        service.set_running(action == 'start')
        return {'running': service.running}

    @app.post('/api/shutdown')
    def shutdown():
        service.shutdown_requested.set()
        return {'shutdown_requested': True}

    return app
