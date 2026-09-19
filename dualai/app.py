"""Tk controller: prompts live in RAM, browser owns all authentication."""
import asyncio
import ctypes
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from .adapters import SITES, SafeFailure, UnknownDelivery
from .browser import BrowserHost

BG, PANEL, TEXT, MUTED, BLUE = "#edf2f7", "#ffffff", "#172b42", "#586b80", "#2563eb"

class Worker:
    def __init__(self, data_dir, events):
        self.events = events
        self.loop = asyncio.new_event_loop()
        self.host = BrowserHost(data_dir)
        self.locks = {key: asyncio.Lock() for key in SITES}
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    async def connect(self, rect, ratio):
        try:
            await asyncio.wait_for(self.host.reconnect(), timeout=70)
            await self.host.arrange(rect, ratio)
            self.events.put(("connected", True))
        except Exception as exc:
            # Do not surface URLs, browser internals, or prompt-bearing exceptions.
            msg = str(exc) if isinstance(exc, RuntimeError) else "브라우저 연결을 확인할 수 없습니다. 창을 닫고 다시 연결해 주세요."
            self.events.put(("connection_error", msg))

    async def probe(self):
        for key in SITES:
            try:
                adapter = self.host.adapters.get(key)
                status = await asyncio.wait_for(adapter.probe(), 3) if adapter else "연결되지 않음"
            except Exception:
                status = "화면 확인 필요 · 다시 연결"
            self.events.put(("probe", key, status))

    async def send_one(self, key, prompt):
        async with self.locks[key]:
            self.events.put(("result", key, "sending", "질문 전달 중…", prompt))
            try:
                adapter = self.host.adapters.get(key)
                if adapter is None:
                    raise SafeFailure("서비스를 연결한 뒤 다시 시도해 주세요.")
                await adapter.send_prompt(prompt)
                state, msg = "success", "전송 확인됨 · 답변은 아래 서비스 화면에서 확인"
            except SafeFailure as exc:
                state, msg = "failed", str(exc)
            except UnknownDelivery as exc:
                state, msg = "unknown", str(exc)
            except Exception:
                state, msg = "failed", "서비스 화면에 연결할 수 없습니다. 다시 연결한 후 확인해 주세요."
            self.events.put(("result", key, state, msg, prompt))

    async def send(self, keys, prompt):
        await asyncio.gather(*(self.send_one(key, prompt) for key in keys))
        self.events.put(("done",))

    async def new_chat(self, keys):
        for key in keys:
            try:
                adapter = self.host.adapters.get(key)
                if adapter is None:
                    raise RuntimeError()
                await adapter.new_chat()
                self.events.put(("reset", key))
            except Exception:
                self.events.put(("new_error", key))
        self.events.put(("done",))

class App:
    def __init__(self, root, data_dir, demo=False):
        self.root, self.data_dir = root, Path(data_dir)
        self.events = queue.Queue()
        self.worker = None if demo else Worker(data_dir, self.events)
        self.busy = False
        self.connected = False
        self.closing = False
        self.results = {}
        self.buttons = []
        self.probing = None
        self.arrange_job = None
        root.title("DualAI · 하나의 질문, 두 개의 관점")
        root.configure(bg=BG)
        root.minsize(1000, 260)
        root.resizable(True, False)
        root.geometry(f"{root.winfo_screenwidth()}x260+0+0")
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", font=("맑은 고딕", 10), padding=(12, 6))
        style.configure("Primary.TButton", background=BLUE, foreground="white")
        style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("disabled", "#9caec5")])
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=18, pady=(10, 5))
        tk.Label(header, text="DualAI", bg=BG, fg=TEXT, font=("맑은 고딕", 17, "bold")).pack(side="left")
        tk.Label(header, text="  같은 질문을 한 번에", bg=BG, fg=MUTED, font=("맑은 고딕", 10)).pack(side="left")
        self.button(header, "다시 연결", self.connect).pack(side="right", padx=(6, 0))
        self.button(header, "화면 정렬", self.arrange).pack(side="right")
        self.button(header, "양쪽 새 대화", lambda: self.new_chat(list(SITES))).pack(side="right", padx=6)
        composer = tk.Frame(root, bg=BG)
        composer.pack(fill="both", expand=True, padx=18)
        self.prompt = tk.Text(composer, height=3, wrap="word", undo=True, font=("맑은 고딕", 11),
                              relief="solid", borderwidth=1, padx=10, pady=7, bg=PANEL, fg=TEXT)
        self.prompt.pack(side="left", fill="both", expand=True)
        self.prompt.bind("<Control-Return>", self.ctrl_enter)
        # Enter always inserts a newline, avoiding Korean IME composition submissions.
        self.button(composer, "둘 다 전송", lambda: self.send(list(SITES)), primary=True).pack(side="left", fill="y", padx=(10, 0))
        options = tk.Frame(root, bg=BG)
        options.pack(fill="x", padx=18, pady=(3, 2))
        tk.Label(options, text="Enter / Shift+Enter 줄바꿈  ·  Ctrl+Enter 전송  ·  로그인과 파일 첨부는 각 브라우저에서",
                 bg=BG, fg=MUTED, font=("맑은 고딕", 9)).pack(side="left")
        tk.Label(options, text="좌우 비율", bg=BG, fg=MUTED, font=("맑은 고딕", 9)).pack(side="right")
        ratio = 50
        try:
            ratio = max(30, min(70, int(json.loads((self.data_dir / "settings.json").read_text()).get("ratio", 50))))
        except (OSError, ValueError, TypeError):
            pass
        self.ratio = tk.Scale(options, from_=30, to=70, orient="horizontal", length=130,
                              showvalue=False, bg=BG, highlightthickness=0, command=self.ratio_changed)
        self.ratio.set(ratio)
        self.ratio.pack(side="right", padx=7)
        statuses = tk.Frame(root, bg=BG)
        statuses.pack(fill="x", padx=18, pady=(0, 8))
        self.status_labels, self.result_labels, self.retry_buttons = {}, {}, {}
        for key, site in SITES.items():
            frame = tk.Frame(statuses, bg=BG)
            frame.pack(side="left", fill="x", expand=True)
            row = tk.Frame(frame, bg=BG)
            row.pack(fill="x")
            tk.Label(row, text=site.name, bg=BG, fg=TEXT, font=("맑은 고딕", 10, "bold")).pack(side="left")
            self.status_labels[key] = tk.Label(row, text="· 연결 준비", bg=BG, fg=MUTED, font=("맑은 고딕", 9))
            self.status_labels[key].pack(side="left", padx=6)
            self.button(row, "전송", lambda k=key: self.send([k])).pack(side="right", padx=2)
            self.button(row, "새 대화", lambda k=key: self.new_chat([k])).pack(side="right", padx=2)
            retry = ttk.Button(row, text="실패 재시도", command=lambda k=key: self.retry(k), state="disabled")
            retry.pack(side="right", padx=2)
            self.retry_buttons[key] = retry
            label = tk.Label(frame, text="최초 한 번 각 서비스에 직접 로그인해 주세요.", anchor="w",
                             bg=BG, fg=MUTED, font=("맑은 고딕", 9), wraplength=650)
            label.pack(fill="x")
            self.result_labels[key] = label
        root.after(100, self.poll)
        root.after(350, self.connect)
        self.prompt.focus_set()

    def button(self, parent, label, fn, primary=False):
        button = ttk.Button(parent, text=label, command=fn, style="Primary.TButton" if primary else "TButton")
        self.buttons.append(button)
        return button

    def ctrl_enter(self, event):
        self.send(list(SITES))
        return "break"

    def geometry(self):
        self.root.update_idletasks()
        # CDP uses device-independent pixels; Tk uses physical pixels in a DPI-aware process.
        factor = 1
        try:
            factor = ctypes.windll.user32.GetDpiForWindow(self.root.winfo_id()) / 96 or 1
        except Exception:
            pass
        from ctypes import wintypes
        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        user32 = ctypes.windll.user32
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        monitor = user32.MonitorFromWindow(self.root.winfo_id(), 2)
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
        user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        rect = info.rcWork
        top = max(rect.top, self.root.winfo_rooty() + self.root.winfo_height() + 4)
        return tuple(int(v / factor) for v in (rect.left, top, rect.right - rect.left, max(300, rect.bottom - top)))

    def set_busy(self, value):
        self.busy = value
        for button in self.buttons:
            button.configure(state="disabled" if value else "normal")
        for key, button in self.retry_buttons.items():
            button.configure(state="normal" if not value and self.results.get(key, {}).get("state") == "failed" else "disabled")

    def connect(self):
        if self.busy or not self.worker:
            return
        self.set_busy(True)
        for label in self.status_labels.values():
            label.configure(text="· 연결 중…")
        self.worker.submit(self.worker.connect(self.geometry(), self.ratio.get() / 100))

    def arrange(self):
        if self.worker and self.connected:
            self.worker.submit(self.worker.host.arrange(self.geometry(), self.ratio.get() / 100))

    def ratio_changed(self, value):
        if self.arrange_job:
            self.root.after_cancel(self.arrange_job)
        self.arrange_job = self.root.after(250, self.arrange)

    def send(self, keys):
        if self.busy or not self.worker:
            return
        prompt = self.prompt.get("1.0", "end-1c")
        if not prompt.strip():
            self.prompt.focus_set()
            return
        allowed = []
        for key in keys:
            prior = self.results.get(key, {})
            if prior.get("state") == "unknown":
                continue
            if prior.get("prompt") == prompt and prior.get("state") == "success":
                continue
            allowed.append(key)
        if not allowed:
            messagebox.showinfo("중복 전송 방지", "이미 전송한 질문이거나 전송 여부를 확인해야 합니다. 새 질문을 입력하거나, 서비스 화면을 확인한 후 새 대화를 시작해 주세요.")
            return
        self.set_busy(True)
        self.worker.submit(self.worker.send(allowed, prompt))

    def retry(self, key):
        prior = self.results.get(key, {})
        if self.busy or prior.get("state") != "failed":
            return
        self.set_busy(True)
        self.worker.submit(self.worker.send([key], prior["prompt"]))

    def new_chat(self, keys):
        if self.busy or not self.worker:
            return
        if not messagebox.askyesno("새 대화", "선택한 서비스에서 새 대화를 시작합니다. 서비스 입력창에 작성 중인 글은 사라질 수 있습니다. 계속할까요?"):
            return
        self.set_busy(True)
        self.worker.submit(self.worker.new_chat(keys))

    def poll(self):
        if self.closing:
            return
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "connected":
                    self.connected = True
                    self.set_busy(False)
                elif event[0] == "connection_error":
                    self.set_busy(False)
                    messagebox.showerror("연결 확인", event[1])
                elif event[0] == "probe":
                    self.status_labels[event[1]].configure(text="· " + event[2])
                elif event[0] == "result":
                    _, key, state, msg, prompt = event
                    self.results[key] = {"state": state, "prompt": prompt}
                    self.result_labels[key].configure(text=msg, fg={"success": "#16704a", "failed": "#b34321", "unknown": "#9c640b"}.get(state, BLUE))
                elif event[0] == "reset":
                    self.results.pop(event[1], None)
                    self.result_labels[event[1]].configure(text="새 대화 화면을 열었습니다.", fg=MUTED)
                elif event[0] == "new_error":
                    self.result_labels[event[1]].configure(text="새 대화를 열지 못했습니다. 다시 연결해 주세요.", fg="#b34321")
                elif event[0] == "done":
                    self.set_busy(False)
        except queue.Empty:
            pass
        if self.worker and not self.busy and (self.probing is None or self.probing.done()):
            # Schedule at most one probe cycle per 3 seconds.
            if getattr(self, "probe_ticks", 0) <= 0:
                self.probing = self.worker.submit(self.worker.probe())
                self.probe_ticks = 30
            else:
                self.probe_ticks -= 1
        self.root.after(100, self.poll)

    def close(self):
        if self.closing:
            return
        if self.busy and not messagebox.askyesno("종료", "작업 중입니다. 지금 종료하면 전송 결과를 확인하지 못할 수 있습니다. 종료할까요?"):
            return
        self.closing = True
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            (self.data_dir / "settings.json").write_text(json.dumps({"ratio": self.ratio.get()}), encoding="utf-8")
        except OSError:
            pass
        self.root.withdraw()
        if self.worker:
            future = self.worker.submit(self.worker.host.close())
            self.wait_close(future, 0)
        else:
            self.root.destroy()

    def wait_close(self, future, ticks):
        if future.done() or ticks >= 250:
            self.root.destroy()
        else:
            self.root.after(100, lambda: self.wait_close(future, ticks + 1))

def main():
    import msvcrt
    import sys
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    data_dir = Path(os.environ["LOCALAPPDATA"]) / "DualAI"
    data_dir.mkdir(parents=True, exist_ok=True)
    lock = (data_dir / "app.lock").open("a+b")
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        root.withdraw()
        messagebox.showinfo("DualAI", "DualAI가 이미 실행 중입니다. 열린 입력창을 확인해 주세요.")
        root.destroy()
        lock.close()
        return
    try:
        App(root, data_dir, demo="--demo" in sys.argv)
        root.mainloop()
    finally:
        lock.close()
