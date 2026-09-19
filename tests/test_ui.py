import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from dualai.app import App

class FakeWorker:
    def __init__(self):
        self.calls = []
    def send(self, keys, prompt):
        self.calls.append((keys, prompt))
    def submit(self, coroutine):
        pass

class UiSmoke(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = App(self.root, Path(self.folder.name), demo=True)
        self.root.update()
    def tearDown(self):
        self.app.worker = None
        self.app.busy = False
        self.app.close()
        self.folder.cleanup()

    def test_controller_layout_and_unicode(self):
        app = self.app
        app.prompt.insert("1.0", "오늘 서울 날씨 알려줘\nprint('한글')")
        self.assertEqual(app.prompt.get("1.0", "end-1c"), "오늘 서울 날씨 알려줘\nprint('한글')")
        self.assertEqual(app.ratio.get(), 50)
        self.assertEqual(len(app.geometry()), 4)
        app.set_busy(True)
        self.assertTrue(all(str(b["state"]) == "disabled" for b in app.buttons))
        app.set_busy(False)

    def test_partial_retry_does_not_resend_success(self):
        app = self.app
        app.worker = FakeWorker()
        app.prompt.insert("1.0", "same prompt")
        app.results = {"chatgpt": {"state": "success", "prompt": "same prompt"},
                       "gemini": {"state": "failed", "prompt": "same prompt"}}
        app.send(["chatgpt", "gemini"])
        self.assertEqual(app.worker.calls, [(["gemini"], "same prompt")])

    def test_retry_keeps_original_prompt_after_editing(self):
        app = self.app
        app.worker = FakeWorker()
        app.prompt.insert("1.0", "new draft")
        app.results = {"gemini": {"state": "failed", "prompt": "original"}}
        app.retry("gemini")
        self.assertEqual(app.worker.calls, [(["gemini"], "original")])

    def test_unknown_delivery_stays_locked_for_new_prompt(self):
        app = self.app
        app.worker = FakeWorker()
        app.prompt.insert("1.0", "new prompt")
        app.results = {"chatgpt": {"state": "unknown", "prompt": "original"}}
        app.send(["chatgpt", "gemini"])
        self.assertEqual(app.worker.calls, [(["gemini"], "new prompt")])

if __name__ == "__main__":
    unittest.main()
