from PyQt6.QtCore import QThread, pyqtSignal


class FuncWorker(QThread):
    """Run any blocking callable off the UI thread and emit its result.

    The analyzer's `analyze()` shells out to Docker (seconds per call), so calling it directly
    from a click handler freezes the whole window. Wrapping it here keeps the GUI responsive and
    lets the caller show a busy indicator. Exceptions are delivered as {"error": str} so callers
    can handle failure the same way they handle an analyzer error payload.
    """
    done = pyqtSignal(object)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            self.done.emit(self._func(*self._args, **self._kwargs))
        except Exception as e:  # deliver failures on the same channel as a result
            self.done.emit({"error": str(e)})
