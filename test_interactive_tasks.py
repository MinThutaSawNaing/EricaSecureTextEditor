import gc
import os
import sys
import threading
import time
import unittest
import weakref
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QThread, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QWidget

import erica_tasks


class InteractiveTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.parent = QWidget()
        self.parent.show()

    def tearDown(self):
        self.parent.close()
        self.parent.deleteLater()
        self.app.processEvents()

    def test_heartbeat_modal_non_cancellable_and_joined(self):
        release = threading.Event()
        entered = threading.Event()
        observations = []
        threads = []
        original = erica_tasks._TaskThread

        def make_thread(task):
            worker = original(task)
            threads.append(worker)
            return worker

        def heartbeat():
            dialog = self.app.activeModalWidget()
            if release.is_set() or not entered.is_set() or dialog is None:
                return
            observations.append(dialog.windowModality())
            dialog.reject()
            dialog.close()
            observations.append(dialog.isVisible())
            observations.append(self.parent.isEnabled())
            release.set()

        timer = QTimer()
        timer.setInterval(5)
        timer.timeout.connect(heartbeat)

        def work():
            worker_thread = QThread.currentThread()
            entered.set()
            if not release.wait(3):
                raise AssertionError("GUI heartbeat did not release worker")
            return worker_thread

        timer.start()
        try:
            with patch.object(erica_tasks, "_TaskThread", side_effect=make_thread):
                result = erica_tasks.run_background_task(self.parent, work)
            self.assertIs(result, threads[0])
            self.assertNotEqual(result, self.app.thread())
            self.assertFalse(threads[0].isRunning())
            self.assertIsNone(threads[0].task)
            self.assertEqual(observations, [Qt.WindowModality.ApplicationModal, True, False])
            self.assertTrue(self.parent.isEnabled())
        finally:
            timer.stop()
            release.set()

    def test_exception_on_gui_thread_releases_callable_and_joins(self):
        workers = []
        original = erica_tasks._TaskThread

        class Secret:
            pass

        secret = Secret()
        secret_ref = weakref.ref(secret)

        def make_task(value):
            def task():
                password = value
                raise ValueError("crypto failed")
            return task

        task = make_task(secret)
        del secret

        def make_thread(operation):
            worker = original(operation)
            workers.append(worker)
            return worker

        with patch.object(erica_tasks, "_TaskThread", side_effect=make_thread):
            with self.assertRaisesRegex(ValueError, "crypto failed") as caught:
                erica_tasks.run_background_task(self.parent, task)
        del task
        gc.collect()
        self.assertIsNone(secret_ref())
        self.assertFalse(workers[0].isRunning())
        self.assertIsNone(workers[0].task)
        self.assertIsNone(workers[0].error)
        self.assertEqual(QThread.currentThread(), self.app.thread())
        self.assertIsNone(caught.exception.__traceback__)

    def test_fast_results_and_failures_do_not_miss_finished_signal(self):
        for index in range(20):
            self.assertEqual(erica_tasks.run_background_task(self.parent, lambda: index), index)
        self.assertIsNone(self.app.activeModalWidget())

    @unittest.skipUnless(sys.version_info >= (3, 11), "ExceptionGroup requires Python 3.11+")
    def test_exception_group_does_not_retain_nested_secret_frames(self):
        class Secret:
            pass

        secret = Secret()
        reference = weakref.ref(secret)

        def make_task(value):
            def task():
                password = value
                try:
                    raise ValueError("inner failure")
                except ValueError as error:
                    raise ExceptionGroup("worker failures", [error]) from None
            return task

        task = make_task(secret)
        del secret
        with self.assertRaises(ExceptionGroup) as caught:
            erica_tasks.run_background_task(self.parent, task)
        del task
        gc.collect()
        self.assertIsNone(reference())
        self.assertIsNone(caught.exception.exceptions[0].__traceback__)

    def test_preserves_disabled_parent(self):
        self.parent.setEnabled(False)
        erica_tasks.run_background_task(self.parent, lambda: None)
        self.assertFalse(self.parent.isEnabled())

    def test_interrupted_nested_loop_still_joins_worker(self):
        original = erica_tasks.QEventLoop
        finished = threading.Event()

        def make_loop():
            loop = original()
            QTimer.singleShot(1, loop.quit)
            return loop

        def work():
            time.sleep(0.05)
            finished.set()
            return "completed"

        with patch.object(erica_tasks, "QEventLoop", side_effect=make_loop):
            self.assertEqual(erica_tasks.run_background_task(self.parent, work), "completed")
        self.assertTrue(finished.is_set())
        self.assertTrue(self.parent.isEnabled())

    def test_rejects_use_outside_gui_thread(self):
        errors = []

        def wrong_thread():
            try:
                erica_tasks.run_background_task(None, lambda: None)
            except RuntimeError as error:
                errors.append(str(error))

        worker = threading.Thread(target=wrong_thread)
        worker.start()
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, ["Background tasks must be started on the GUI thread"])


if __name__ == "__main__":
    unittest.main()