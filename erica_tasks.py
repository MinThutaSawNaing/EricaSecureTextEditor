"""Synchronous GUI-facing bridge for non-cancellable background file operations."""

import traceback
from typing import Callable, TypeVar

from PyQt6.QtCore import QEventLoop, QThread, Qt
from PyQt6.QtWidgets import QApplication, QProgressDialog


_T = TypeVar("_T")


class _BusyDialog(QProgressDialog):
    """Do not imply that closing a window can cancel an atomic file operation."""

    def reject(self):
        pass

    def done(self, result):
        pass

    def closeEvent(self, event):
        event.ignore()


class _TaskThread(QThread):
    def __init__(self, task):
        super().__init__()
        self.task = task
        self.result = None
        self.error = None

    def run(self):
        task, self.task = self.task, None
        try:
            self.result = task()
        except BaseException as error:
            # A traceback can retain crypto frames, plaintext and passwords. Keep
            # the exception type/message, but not the worker's frame locals.
            seen = set()
            pending = [error]
            while pending:
                current = pending.pop()
                if id(current) in seen:
                    continue
                seen.add(id(current))
                traceback.clear_frames(current.__traceback__)
                current.__traceback__ = None
                for related in (current.__cause__, current.__context__):
                    if related is not None:
                        pending.append(related)
                pending.extend(getattr(current, "exceptions", ()))
            self.error = error
        finally:
            task = None


def run_background_task(parent, task: Callable[[], _T]) -> _T:
    """Run widget-free work and return its result (or raise) on the GUI thread.

    Capture document text, paths and passwords *before* calling; the callable
    must never read widgets. Application modality blocks user edits/actions
    while a nested Qt loop keeps painting and timers responsive. This is not
    cancellation: even Escape/window-close cannot abandon an in-flight write.
    Callers still own their original password references and must release them.
    """
    app = QApplication.instance()
    if app is None or QThread.currentThread() != app.thread():
        raise RuntimeError("Background tasks must be started on the GUI thread")

    dialog = _BusyDialog("Working…", "", 0, 0, parent)
    dialog.setWindowTitle("Please wait")
    dialog.setCancelButton(None)
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
    dialog.setMinimumDuration(0)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    loop = QEventLoop()
    worker = _TaskThread(task)
    task = None
    worker.finished.connect(loop.quit)
    parent_enabled = parent.isEnabled() if parent is not None else None
    try:
        if parent is not None:
            parent.setEnabled(False)
        dialog.setEnabled(True)
        dialog.show()
        worker.start()
        loop.exec()
        # finished is delivered via the GUI event loop. Join before disposing
        # the QThread, including during application shutdown/loop interruption.
        worker.wait()
        error, worker.error = worker.error, None
        result, worker.result = worker.result, None
        if error is not None:
            raise error
        return result
    finally:
        worker.wait()
        worker.task = None
        worker.result = None
        worker.error = None
        dialog.hide()
        if parent is not None:
            parent.setEnabled(parent_enabled)
        dialog.deleteLater()
        worker.deleteLater()