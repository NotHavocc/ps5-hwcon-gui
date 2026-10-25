import asyncio
import concurrent.futures
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from .backend import Backend, logger

SHUTDOWN_TIMEOUT_SECONDS = 6.0

class BackendBridge(QObject):
    ready = pyqtSignal()
    _delivered = pyqtSignal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._backend = Backend()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="ps5hw-backend", daemon=True)
        self._delivered.connect(self._deliver)
        self.is_ready = False

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start(self):
        self._thread.start()
        future = asyncio.run_coroutine_threadsafe(self._backend.start(), self._loop)
        future.add_done_callback(lambda f: self._delivered.emit(self._started, self._outcome(f, "start")))

    def _started(self, _result):
        self.is_ready = True
        self.ready.emit()

    def stop(self):
        if not self._thread.is_alive():
            return
        future = asyncio.run_coroutine_threadsafe(self._backend.stop(), self._loop)
        try:
            future.result(timeout=SHUTDOWN_TIMEOUT_SECONDS)
        except (concurrent.futures.TimeoutError, Exception) as exc:
            logger.error(f"Backend shutdown failed: {exc!r}")
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=1.0)

    def call(self, method, *args, callback=None):
        coro = getattr(self._backend, method)(*args)
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        if callback is not None:
            future.add_done_callback(
                lambda f: self._delivered.emit(callback, self._outcome(f, method))
            )
        return future

    @staticmethod
    def _outcome(future, method):
        try:
            result = future.result()
        except Exception as exc:
            return {"success": False, "error": str(exc) or repr(exc)}
        if not isinstance(result, dict):
            return {"success": False, "error": f"Unexpected response from {method}"}
        return result

    def _deliver(self, callback, result):
        callback(result)
