"""live.py - a Changeling, live on a video call: one snapshot of you, changed once, worn live.

StyleGAN editing (Tiresias, Chronos, Natio) learns a face for a minute: far too slow for every frame of a call.
So this does it once: take a snapshot of you (or pick a photo), the Changeling makes the new you from it, and
Changeling CopyCat Realtime wears that new you live, on your own expressions, out to the call through the virtual
camera (and your voice through Changeling Echo or its voice changer, if you like).

    run.bat                      the window
    run.bat --camera 1           another webcam
    run.bat --source me.jpg      a photo or video instead of the webcam (for trying it out)

Which Changeling this is comes from realtime.json ({"app": "Tiresias"}). This same file is in every
Changeling *-Realtime repo; the master copy is in Changeling Studio's realtime/ (make_realtime.py copies it).
It runs in the Changeling's own environment, so it needs nothing of its own: Changeling <App> and Changeling CopyCat
Realtime next to it (as in Changeling Studio), or in CHANGELING_<APP>_DIR and COPYCAT_REALTIME_DIR.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageTk

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
CONFIG = json.load(open(os.path.join(HERE, "realtime.json"), encoding="utf-8"))
APP = CONFIG["app"]
NAME = f"Changeling {APP} Realtime"
GITHUB = f"https://github.com/CursedPrograms/Changeling-{APP}-Realtime"
KOFI = "https://ko-fi.com/cursedentertainment"
PINK = "#e0408a"
MADE = os.path.join(HERE, "made")
QUALITY = {"Fast": "fast", "Balanced": "balanced", "Best": "best"}
IMAGE_TYPES = [("Pictures", "*.png *.jpg *.jpeg *.webp *.bmp *.jfif"), ("All files", "*.*")]
TAGLINES = {
    "Tiresias": "be the other gender, live on a call",
    "Chronos": "be younger or older, live on a call",
    "Natio": "another ancestry, live on a call",
}
GENDERS = {"Auto": "auto", "Woman": "female", "Man": "male", "Off": "off"}


# ---- where things are
def _python(folder, env):
    win = os.path.join(folder, env, "Scripts", "python.exe")
    return win if os.name == "nt" else os.path.join(folder, env, "bin", "python")


def app_dir(name):
    folder = os.environ.get(f"CHANGELING_{name.upper()}_DIR") or os.path.join(STUDIO, f"Changeling-{name}")
    return folder if os.path.exists(os.path.join(folder, "main.py")) else None


def app_python():
    """The Changeling's environment, or a sibling's: Tiresias, Chronos and Natio need the same things."""
    for name in (APP, "Tiresias", "Chronos", "Natio"):
        folder = app_dir(name)
        if folder and os.path.exists(_python(folder, "psdenv")) and _has_torch(os.path.join(folder, "psdenv")):
            return _python(folder, "psdenv")
    return None


def _has_torch(env):
    """An environment that's actually installed (a half-made one has python but no packages)."""
    import glob
    return bool(glob.glob(os.path.join(env, "Lib", "site-packages", "torch")) or
                glob.glob(os.path.join(env, "lib", "python3*", "site-packages", "torch")))


def copycat_dir():
    folder = os.environ.get("COPYCAT_REALTIME_DIR") or os.path.join(STUDIO, "Changeling-CopyCat-Realtime")
    return folder if os.path.exists(os.path.join(folder, "app.py")) else None


def echo_installed():
    folder = os.environ.get("ECHO_DIR") or os.path.join(STUDIO, "Changeling-Echo")
    return os.path.exists(os.path.join(folder, "echo", "live.py")) and os.path.exists(_python(folder, "venv"))


def read_bgr(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def write_bgr(path, image):
    ok, buf = cv2.imencode(os.path.splitext(path)[1] or ".jpg", image)
    if ok:
        buf.tofile(path)
    return ok


# ---- the look
def set_logo(root):
    """The Changeling logo as the window's icon. customtkinter puts its own in at about 200 ms, so this is later."""
    ico, png = os.path.join(HERE, "logo.ico"), os.path.join(HERE, "logo.png")

    def apply():
        try:
            if os.name == "nt" and os.path.exists(ico):
                root.iconbitmap(ico)
            elif os.path.exists(png):
                root._logo_icon = tk.PhotoImage(file=png)
                root.iconphoto(True, root._logo_icon)
        except tk.TclError:
            pass
    root.after(300, apply)


class Camera:
    """The webcam (or --source: a photo or a video, looped) on its own thread; .frame is the newest picture."""

    def __init__(self, index, source=None):
        self.index, self.source = index, source
        self.frame = None
        self.error = ""
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="camera").start()

    def stop(self):
        self._running = False
        time.sleep(0.15)

    def _loop(self):
        if self.source and os.path.splitext(self.source)[1].lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".jfif"):
            still = read_bgr(self.source)
            while self._running:
                self.frame = still
                time.sleep(0.05)
            return
        cap = cv2.VideoCapture(self.source) if self.source else \
            cv2.VideoCapture(self.index, cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY)
        if not cap.isOpened():
            self.error = "No camera found." if not self.source else f"Can't open {self.source}."
            self._running = False
            return
        self.error = ""
        while self._running:
            ok, frame = cap.read()
            if not ok:
                if self.source:                       # a video: from the start again
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                self.error = "The camera stopped giving pictures."
                break
            self.frame = frame if self.source else cv2.flip(frame, 1)
            if self.source:
                time.sleep(1 / 30)
        cap.release()
        self._running = False


class Window:
    def __init__(self, args):
        self.args = args
        self.camera = Camera(args.camera, args.source)
        self.you = None               # the snapshot (a path in made/)
        self.new_you = None           # what the Changeling made of it (a path in made/)
        self.live = None              # CopyCat Realtime, while it runs
        self.make_proc = None
        self.countdown = 0
        self.state = {"busy": False, "done": 0, "total": 0, "stage": "", "t0": 0.0, "message": "", "detected": ""}
        os.makedirs(MADE, exist_ok=True)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme(os.path.join(HERE, "theme.json"))
        self.root = ctk.CTk()
        set_logo(self.root)
        self.root.title(NAME)
        self.root.geometry("1280x800")
        self.root.minsize(1000, 640)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self._build()
        self._keys()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.camera.start()
        self._check_parts()
        self.root.after(30, self.show)
        self.root.after(200, self.watch)

    # ---- the window
    def _build(self):
        stage = ctk.CTkFrame(self.root, corner_radius=12)
        stage.grid(row=0, column=0, sticky="nsew", padx=(14, 7), pady=14)
        stage.grid_columnconfigure(0, weight=1)
        stage.grid_rowconfigure(0, weight=1)
        self.view = tk.Label(stage, bg="#16161a", bd=0, fg="gray60", font=("Segoe UI", 13))
        self.view.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.view_size = (900, 600)
        self.view.bind("<Configure>", lambda e: setattr(self, "view_size", (max(e.width, 64), max(e.height, 36))))
        strip = ctk.CTkFrame(stage, fg_color="transparent")
        strip.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.thumbs = {}
        for key, text in (("you", "YOU"), ("new", "THE NEW YOU")):
            box = ctk.CTkFrame(strip, fg_color="transparent")
            box.pack(side="left", padx=(0, 14))
            ctk.CTkLabel(box, text=text, text_color="gray50", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
            label = ctk.CTkLabel(box, text="-", width=120, height=120, fg_color="#16161a", corner_radius=8)
            label.pack()
            self.thumbs[key] = label
        self.thumbs["new"].bind("<Button-1>", lambda e: self.new_you and self._open_file(self.new_you))
        self.hint = ctk.CTkLabel(strip, text="", text_color="gray60", wraplength=520, justify="left")
        self.hint.pack(side="left", padx=8, anchor="s", pady=(0, 6))

        side = ctk.CTkScrollableFrame(self.root, width=300, corner_radius=12)
        side.grid(row=0, column=1, sticky="ns", padx=(7, 14), pady=14)
        logo = os.path.join(HERE, "logo.png")
        if os.path.exists(logo):
            ctk.CTkLabel(side, image=ctk.CTkImage(Image.open(logo), size=(56, 56)), text="").pack(anchor="w", padx=12, pady=(10, 0))
        ctk.CTkLabel(side, text="CHANGELING", text_color="gray55",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=12, pady=(12, 0))
        ctk.CTkLabel(side, text=f"{APP} Realtime", font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=PINK).pack(anchor="w", padx=12)
        ctk.CTkLabel(side, text=TAGLINES.get(APP, ""), text_color="gray60", wraplength=270,
                     justify="left").pack(anchor="w", padx=12)

        self._section(side, "1 · You")
        row = ctk.CTkFrame(side, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        self.snap_btn = ctk.CTkButton(row, text="Snapshot  (Space)", command=self.snapshot)
        self.snap_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(row, text="Photo ...", width=80, command=self.pick_photo).pack(side="left")
        ctk.CTkLabel(side, text="Look at the camera, face lit from the front, no glasses if you can.",
                     text_color="gray55", wraplength=270, justify="left").pack(anchor="w", padx=12)

        self._section(side, "2 · The change")
        self._options(side)
        ctk.CTkLabel(side, text="Quality", text_color="gray70").pack(anchor="w", padx=12, pady=(8, 0))
        self.quality = ctk.CTkSegmentedButton(side, values=list(QUALITY))
        self.quality.set("Balanced")
        self.quality.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(side, text="Balanced and Best learn your face first, so the new you still looks like you "
                     "(about 1 and 3 minutes). Fast takes seconds.", text_color="gray55", wraplength=270,
                     justify="left").pack(anchor="w", padx=12)
        self.make_btn = ctk.CTkButton(side, text="Make the new you  (Enter)", height=40,
                                      font=ctk.CTkFont(size=14, weight="bold"), command=self.make)
        self.make_btn.pack(fill="x", padx=12, pady=(12, 4))
        self.bar = ctk.CTkProgressBar(side, mode="determinate")
        self.bar.set(0)
        self.bar.pack(fill="x", padx=12, pady=(4, 2))
        self.status = ctk.CTkLabel(side, text="", text_color="gray65", wraplength=270, justify="left")
        self.status.pack(anchor="w", padx=12)
        ctk.CTkLabel(side, text="Made before", text_color="gray70").pack(anchor="w", padx=12, pady=(8, 0))
        self.made_pick = ctk.CTkOptionMenu(side, values=["-"], command=self.pick_made)
        self.made_pick.pack(fill="x", padx=12, pady=4)
        self._list_made()

        self._section(side, "3 · Live")
        self.skin = self._slider(side, "Persona's skin", 0, 100, 70)
        ctk.CTkLabel(side, text="The new you's skin worn too: its tone and fine detail (wrinkles, freckles). Your "
                     "neck and ears keep yours, so lower it if the jaw line shows.", text_color="gray55",
                     wraplength=270, justify="left").pack(anchor="w", padx=12)
        ctk.CTkLabel(side, text="Voice", text_color="gray70").pack(anchor="w", padx=12)
        self.voice = ctk.CTkSegmentedButton(side, values=["off", "female", "male"])
        self.voice.set("off")
        self.voice.pack(fill="x", padx=12, pady=4)
        self.echo = ctk.BooleanVar(value=echo_installed())
        self.echo_sw = ctk.CTkSwitch(side, text="Echo: trained voices", variable=self.echo)
        self.echo_sw.pack(anchor="w", padx=12, pady=3)
        if not echo_installed():
            self.echo_sw.configure(state="disabled", text="Echo: not installed")
        self.live_btn = ctk.CTkButton(side, text="Go live  (L)", height=42, font=ctk.CTkFont(size=15, weight="bold"),
                                      command=self.go_live)
        self.live_btn.pack(fill="x", padx=12, pady=(12, 4))
        self.live_note = ctk.CTkLabel(side, text="Opens Changeling CopyCat Realtime wearing the new you: out to the "
                                      "call through OBS Virtual Camera. Close it to come back here.",
                                      text_color="gray55", wraplength=270, justify="left")
        self.live_note.pack(anchor="w", padx=12)

        foot = ctk.CTkFrame(side, fg_color="transparent")
        foot.pack(fill="x", padx=12, pady=(18, 6))
        links = ctk.CTkFrame(foot, fg_color="transparent")
        links.pack(anchor="w")
        for text, url in (("GitHub", GITHUB), ("Ko-fi", KOFI)):
            link = ctk.CTkLabel(links, text=text, text_color=("#c2186b", "#f29cc0"), cursor="hand2")
            link.pack(side="left", padx=(0, 14))
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        ctk.CTkLabel(foot, text="© Cursed Entertainment 2026", text_color="gray45").pack(anchor="w")

    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text.upper(), text_color="gray50",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=12, pady=(16, 1))

    def _slider(self, parent, text, lo, hi, value, step=5, fmt="{}%"):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(6, 0))
        ctk.CTkLabel(row, text=text).pack(side="left")
        shown = ctk.CTkLabel(row, text=fmt.format(value), text_color="gray60")
        shown.pack(side="right")
        s = ctk.CTkSlider(parent, from_=lo, to=hi, number_of_steps=(hi - lo) // step,
                          command=lambda v: shown.configure(text=fmt.format(int(v))))
        s.set(value)
        s.pack(fill="x", padx=12, pady=(0, 4))
        return s

    def _segmented(self, parent, label, values, value):
        if label:
            ctk.CTkLabel(parent, text=label, text_color="gray70").pack(anchor="w", padx=12, pady=(6, 0))
        seg = ctk.CTkSegmentedButton(parent, values=values)
        seg.set(value)
        seg.pack(fill="x", padx=12, pady=4)
        return seg

    def _options(self, side):
        """Each Changeling's own choices (the same as in its window)."""
        if APP == "Tiresias":
            self.direction = self._segmented(side, "", ["Auto", "To female", "To male"], "Auto")
            self.strength = self._slider(side, "Strength", 25, 200, 100)
        elif APP == "Chronos":
            self.age = self._slider(side, "Age", -100, 100, 50, fmt="{:+d}")
            ctk.CTkLabel(side, text="Below 0 younger, above 0 older.", text_color="gray55").pack(anchor="w", padx=12)
            self.keep_gender = self._segmented(side, "Keep gender", list(GENDERS), "Auto")
        elif APP == "Natio":
            self.towards = self._segmented(side, "Towards", ["African", "European", "East Asian"], "European")
            self.strength = self._slider(side, "Strength", 20, 150, 100)
            self.keep_gender = self._segmented(side, "Keep gender", list(GENDERS), "Auto")

    def _option_args(self):
        """(command-line options for the Changeling's main.py, a short name for the file)"""
        if APP == "Tiresias":
            to = {"Auto": "auto", "To female": "female", "To male": "male"}[self.direction.get()]
            return ["--to", to, "--strength", f"{self.strength.get() / 100:.2f}"], to
        if APP == "Chronos":
            age = int(self.age.get())
            return ["--age", f"{age / 100:.2f}", "--keep-gender", GENDERS[self.keep_gender.get()]], \
                ("older" if age >= 0 else "younger") + f"{abs(age)}"
        towards = self.towards.get().lower().replace(" ", "_")
        return ["--towards", towards, "--strength", f"{self.strength.get() / 100:.2f}",
                "--keep-gender", GENDERS[self.keep_gender.get()]], towards

    def _keys(self):
        def unless_typing(f):
            return lambda e: None if isinstance(e.widget, (tk.Entry, ctk.CTkEntry)) else f()
        self.root.bind("<space>", unless_typing(self.snapshot))
        self.root.bind("<Return>", unless_typing(self.make))
        self.root.bind("<KeyPress-l>", unless_typing(self.go_live))
        self.root.bind("<Escape>", lambda e: self.quit())

    def _check_parts(self):
        missing = []
        if app_dir(APP) is None:
            missing.append(f"Changeling {APP}")
        elif app_python() is None:
            missing.append(f"Changeling {APP}'s environment (run its run.bat once)")
        if copycat_dir() is None:
            missing.append("Changeling CopyCat Realtime")
        if missing:
            self.status.configure(text="Not found: " + ", ".join(missing) + ". Put them next to this folder "
                                  "(Changeling Studio's fetch.bat does it), or run this repo's run.bat.")
            self.make_btn.configure(state="disabled")
            self.live_btn.configure(state="disabled")

    # ---- you
    def snapshot(self):
        if self.live is not None or self.countdown:
            return
        if self.camera.frame is None:
            self.status.configure(text=self.camera.error or "No picture from the camera yet.")
            return
        self.countdown = 3
        self.root.after(1000, self._tick)

    def _tick(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.root.after(1000, self._tick)
            return
        frame = self.camera.frame
        if frame is None:
            return
        path = os.path.join(MADE, time.strftime("you_%Y-%m-%d_%H%M%S.jpg"))
        write_bgr(path, frame)
        self._set_you(path)

    def pick_photo(self):
        path = filedialog.askopenfilename(title="A photo of you", filetypes=IMAGE_TYPES)
        if path:
            self._set_you(path)

    def _set_you(self, path):
        self.you = path
        self._thumb("you", path)
        self.status.configure(text="Now: Make the new you.")

    def _thumb(self, key, path):
        img = read_bgr(path) if path else None
        if img is None:
            self.thumbs[key].configure(image=None, text="-")
            return
        h, w = img.shape[:2]
        s = min(h, w)
        crop = img[(h - s) // 2:(h + s) // 2, (w - s) // 2:(w + s) // 2]
        pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        self.thumbs[key].configure(image=ctk.CTkImage(pil, size=(120, 120)), text="")

    # ---- the new you
    def make(self):
        if self.state["busy"] or self.live is not None or self.make_btn.cget("state") == "disabled":
            return
        if not self.you:
            self.status.configure(text="First a snapshot of you (Space), or a photo.")
            return
        options, short = self._option_args()
        out = os.path.join(MADE, time.strftime(f"{APP.lower()}_{short}_%Y-%m-%d_%H%M%S.jpg"))
        cmd = [app_python(), "-u", "main.py", self.you, "-o", out, "--quality", QUALITY[self.quality.get()], *options]
        self.state.update(busy=True, done=0, total=0, stage="Loading the models", t0=time.monotonic(), message="",
                          detected="")
        self.make_btn.configure(state="disabled")
        self.bar.set(0)
        threading.Thread(target=self._make, args=(cmd, out), daemon=True, name="make").start()

    def _make(self, cmd, out):
        tail = []
        try:
            self.make_proc = subprocess.Popen(cmd, cwd=app_dir(APP), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            line = b""
            while True:
                ch = self.make_proc.stdout.read(1)
                if not ch:
                    break
                if ch not in b"\r\n":
                    line += ch
                    continue
                text = line.decode("utf-8", "replace").strip()
                line = b""
                if not text:
                    continue
                tail = (tail + [text])[-6:]
                m = re.search(r"(\d+)/(\d+)\s+loss", text)
                if m:
                    self.state.update(done=int(m.group(1)), total=int(m.group(2)), stage="Learning your face")
                m = re.search(r"detected (\w+) -> (\w+)", text)
                if m:
                    self.state["detected"] = m.group(2)
            ok = self.make_proc.wait() == 0 and os.path.exists(out)
            self.state["message"] = "" if ok else ("It didn't work: " + (tail[-1] if tail else "no output"))
            if ok:
                if "_auto_" in out and self.state["detected"]:     # name it by what Auto chose
                    named = out.replace("_auto_", f"_{self.state['detected']}_")
                    os.replace(out, named)
                    out = named
                self.new_you = out
        except Exception as e:  # noqa: BLE001 - shown in the window
            self.state["message"] = f"It didn't work: {e}"
        self.make_proc = None
        self.state["busy"] = False
        self.state["finished"] = True

    def watch(self):
        st = self.state
        if st["busy"]:
            spent = time.monotonic() - st["t0"]
            if st["total"]:
                self.bar.set(st["done"] / st["total"])
                left = spent / max(st["done"], 1) * (st["total"] - st["done"])
                self.status.configure(text=f"{st['stage']}: {st['done']}/{st['total']}, about {int(left)} s left")
            else:
                self.bar.set(min(0.95, spent / 60) if self.quality.get() == "Fast" else 0)
                self.status.configure(text=f"{st['stage']} ... {int(spent)} s")
        elif st.pop("finished", False):
            self.make_btn.configure(state="normal")
            if st["message"]:
                self.bar.set(0)
                self.status.configure(text=st["message"])
            else:
                self.bar.set(1)
                self.status.configure(text=f"Done in {int(time.monotonic() - st['t0'])} s. Now: Go live (L).")
                self._thumb("new", self.new_you)
                if APP == "Tiresias" and st["detected"] in ("female", "male"):
                    self.voice.set(st["detected"])      # the voice to go with it
                self._list_made()
        if self.live is not None and self.live.poll() is not None:
            self.live = None
            self.live_btn.configure(state="normal", text="Go live  (L)")
            self.camera.start()
        self.root.after(200, self.watch)

    def _list_made(self):
        made = sorted((f for f in os.listdir(MADE) if f.startswith(APP.lower() + "_")), reverse=True)
        self.made_pick.configure(values=made or ["-"])
        self.made_pick.set(os.path.basename(self.new_you) if self.new_you else (made[0] if made else "-"))
        if self.new_you is None and made:
            self.pick_made(made[0])

    def pick_made(self, name):
        path = os.path.join(MADE, name)
        if os.path.exists(path):
            self.new_you = path
            self._thumb("new", path)

    # ---- live
    def go_live(self):
        if self.live is not None or self.live_btn.cget("state") == "disabled":
            return
        if not self.new_you:
            self.status.configure(text="First make the new you.")
            return
        folder = copycat_dir()
        py = _python(folder, "venv")
        cmd = [py if os.path.exists(py) else sys.executable, "app.py", "--persona", self.new_you,
               "--camera", str(self.args.camera), "--voice", self.voice.get(), "--skin", str(int(self.skin.get()))]
        if self.args.source:
            cmd += ["--source", self.args.source]
        if self.echo.get():
            cmd.append("--echo")
        self.camera.stop()                      # CopyCat Realtime needs the camera
        self.live = subprocess.Popen(cmd, cwd=folder)
        self.live_btn.configure(state="disabled", text="Live: close CopyCat Realtime to come back")

    # ---- the picture
    def show(self):
        if self.live is not None:
            frame = read_bgr(self.new_you) if self.new_you else None
            note = "Live in Changeling CopyCat Realtime"
        else:
            frame = self.camera.frame
            note = self.camera.error or ("" if frame is not None else "Waiting for the camera ...")
        w, h = self.view_size
        if frame is not None:
            ih, iw = frame.shape[:2]
            k = min(w / iw, h / ih)
            small = cv2.resize(frame, (max(int(iw * k), 1), max(int(ih * k), 1)), interpolation=cv2.INTER_AREA)
            if self.countdown:
                cy, cx = small.shape[0] // 2, small.shape[1] // 2
                cv2.putText(small, str(self.countdown), (cx - 40, cy + 40), cv2.FONT_HERSHEY_SIMPLEX, 4,
                            (138, 64, 224), 10, cv2.LINE_AA)
            photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)))
            self.view.configure(image=photo, text="")
            self.view.image = photo
        else:
            self.view.configure(image="", text=note)
            self.view.image = None
        self.hint.configure(text=note if frame is not None and self.live is not None else "")
        self.root.after(33, self.show)

    def _open_file(self, path):
        if os.name == "nt":
            os.startfile(path)  # noqa: S606 - the user's own picture

    def quit(self):
        self.camera.stop()
        if self.make_proc is not None:
            self.make_proc.kill()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    ap = argparse.ArgumentParser(description=f"{NAME}: one snapshot of you, changed by Changeling {APP}, "
                                 "worn live by Changeling CopyCat Realtime.")
    ap.add_argument("--camera", type=int, default=0, help="which webcam (default 0)")
    ap.add_argument("--source", help="a photo or video instead of the webcam (for trying it out)")
    Window(ap.parse_args()).run()


if __name__ == "__main__":
    main()
