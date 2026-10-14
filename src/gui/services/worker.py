from PyQt6.QtCore import QCoreApplication, QThread, pyqtSignal

class FunctionWorker(QThread):
    """
    Run any blocking callable off the UI thread and emit its result.
    """
    done = pyqtSignal(object)
    progress = pyqtSignal(int, str)

    def __init__(self, function, *args, report_progress: bool = False, **kwargs):
        super().__init__()
        self._function = function
        self._args = args
        self._kwargs = kwargs
        if report_progress:
            self._kwargs["progress_callback"] = self.progress.emit
        application = QCoreApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(self.stop)

    def stop(self):
        """Keep the thread alive until its callable exits during app shutdown."""
        self.requestInterruption()
        self.wait()

    def run(self):
        try:
            self.done.emit(self._function(*self._args, **self._kwargs))
        except Exception as e:
            self.done.emit({"error": str(e)})
