"""Local-only listener selection and an OS-released single-instance lock."""
from contextlib import contextmanager
import errno
from pathlib import Path
import socket


@contextmanager
def single_instance(root):
    import msvcrt
    path = Path(root) / 'data' / 'dashboard.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+b')
    handle.seek(0, 2)
    if handle.tell() == 0:
        handle.write(b'0')
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        raise RuntimeError('Another Dashboard instance owns the project lock; it was not terminated.')
    try:
        yield
    finally:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            handle.close()


def reserve_loopback(preferred, factory=None):
    """Try configured port once, then let Windows select one. Never bind all NICs."""
    if type(preferred) is not int or not 1 <= preferred <= 65535:
        raise ValueError('Invalid management port')
    factory = factory or socket.socket
    first_error = None
    for port in (preferred, 0):
        listener = factory(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(('127.0.0.1', port))
            listener.listen(128)
            listener.setblocking(False)
            selected = int(listener.getsockname()[1])
            return listener, selected, first_error
        except OSError as error:
            listener.close()
            retryable = error.errno in (errno.EACCES, errno.EADDRINUSE) or getattr(error, 'winerror', None) in (10013, 10048)
            if port != 0 and retryable:
                first_error = getattr(error, 'winerror', None) or error.errno
                continue
            if port == 0 and first_error is not None:
                code = getattr(error, 'winerror', None) or error.errno
                raise OSError(error.errno, f'Loopback listening failed on configured port {preferred} (code {first_error}) and OS-selected port (code {code}).') from error
            raise

