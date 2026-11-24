import argparse
import threading
import uvicorn

from app.api.web import create_app
from app.core.service import DashboardService
from app.core.settings import Settings
from app.core.listener import reserve_loopback, single_instance


def main():
    parser = argparse.ArgumentParser(description='Kindle Desk Dashboard local Windows service')
    parser.add_argument('--render-once', action='store_true', help='Collect and generate both PNG pages, no listeners')
    args = parser.parse_args()
    settings = Settings()
    if args.render_once:
        service = DashboardService(settings)
        try:
            service.state['hardware'] = service.hardware.collect()
            from app.collectors.codex import collect
            service.state['codex'] = collect(settings.snapshot()['codex_executable'])
            service.render()
            for page in ('work', 'pc'):
                path = settings.root / 'data' / (page + '.png')
                path.write_bytes(service.frame(page)['png'])
                print(path)
        finally:
            service.close()
        return
    with single_instance(settings.root):
        preferred = settings.snapshot()['management_port']
        listener, port, denied_code = reserve_loopback(preferred)
        service = None
        try:
            if port != preferred:
                settings.set_management_port(port)
                print(f'Management port {preferred} unavailable (code {denied_code}); Windows selected local port {port}.', flush=True)
            print(f'Kindle Desk Dashboard: http://127.0.0.1:{port}', flush=True)
            service = DashboardService(settings)
            server = uvicorn.Server(uvicorn.Config(create_app(service), host='127.0.0.1', port=port,
                                                 access_log=False, log_level='warning', use_colors=False))
            def shutdown_watch():
                service.shutdown_requested.wait()
                server.should_exit = True
            threading.Thread(target=shutdown_watch, daemon=True).start()
            try:
                server.run(sockets=[listener])
            finally:
                service.shutdown_requested.set()
        finally:
            listener.close()
            if service and not service.stop.is_set():
                service.close()


if __name__ == '__main__':
    main()
