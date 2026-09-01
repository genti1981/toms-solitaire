#!/usr/bin/env python3
"""
Tom's Solitaire — pure Python / tkinter, no external dependencies.

Rules implemented:
  - Standard 52-card deck, 7 tableau columns, 4 foundations, stock + waste.
  - Draw 1 or draw 3 from stock (toggle in the menu). Empty stock recycles waste.
  - Tableau builds down in alternating colours; only a King (or a valid run
    ending appropriately) may fill an empty column.
  - Foundations build up by suit from Ace to King.
  - Drag-and-drop to move cards (single card or a valid run from the tableau).
  - Double-click a card to auto-send it to a foundation if legal.
  - Win detection when all four foundations reach the King.

Run:  python3 solitaire.py
"""

import json
import math
import os
import random
import threading
import time
import urllib.request
import tkinter as tk
from tkinter import messagebox, simpledialog

STATE_FILE = os.path.join(os.path.expanduser("~"), ".toms_solitaire.json")

# --- Online leaderboard (optional) -----------------------------------------
# To let a few people share a scoreboard, create ONE GitHub gist that contains
# a file named  scores.json  whose contents are exactly:  []
# Paste that gist's id into LEADERBOARD_GIST_ID below. To let the game WRITE
# new scores (not just read them), also paste a GitHub token that has the
# "gist" scope into LEADERBOARD_TOKEN. Everyone who should share the board uses
# the SAME two values. Leave GIST_ID empty to keep scores on this computer only.
LEADERBOARD_GIST_ID = "8108dcf542649202ed899c86f4bd72c0"
LEADERBOARD_TOKEN = "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"
LEADERBOARD_FILENAME = "scores.json"

# --- Online updates (optional) ---------------------------------------------
# Publish the game in a public GitHub repo containing solitaire.py, the cards/
# folder, and a small file version.json (see the README notes). Put the repo
# here as "owner/name". The game reads version.json, and when its "version" is
# higher than VERSION below it offers to download the listed files. Leave
# UPDATE_REPO empty to turn the update check off.
VERSION = "1.0.0"
UPDATE_REPO = ""          # e.g. "genti1981/toms-solitaire"
UPDATE_BRANCH = "main"

# --- Version / auto-update (optional) ---------------------------------------
GAME_VERSION = "1.0.0"
# Point this at a raw manifest.json in your GitHub repo to enable
# "Check for updates". Leave it empty to disable updating. Example:
#   https://raw.githubusercontent.com/genti1981/toms-solitaire/main/manifest.json
# manifest.json looks like:
#   {
#     "version": "1.1.0",
#     "notes": "Short summary of what changed",
#     "base": "https://raw.githubusercontent.com/genti1981/toms-solitaire/main/",
#     "files": ["solitaire.py", "cards/AS.png", "cards/back.png"]
#   }
# On update the listed files are downloaded from <base>+<file> and replace the
# local copies; bump "version" above the installed one to offer an update.
UPDATE_MANIFEST_URL = ""

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

SUITS = ["\u2660", "\u2665", "\u2666", "\u2663"]  # spades, hearts, diamonds, clubs
RED_SUITS = {"\u2665", "\u2666"}
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
RANK_VALUE = {r: i + 1 for i, r in enumerate(RANKS)}  # A=1 ... K=13

# Albanian corner letters: As, Fant, Damë, Mbret. Number ranks keep their digits.
RANK_LABEL = {"A": "A", "J": "F", "Q": "D", "K": "M"}

# Positions of pips on number cards, as (x, y) fractions of the inner face.
# y > 0.5 pips are drawn upside-down, as on real cards.
_xL, _xC, _xR = 0.30, 0.50, 0.70
PIP_LAYOUT = {
    2: [(_xC, 0.18), (_xC, 0.82)],
    3: [(_xC, 0.18), (_xC, 0.50), (_xC, 0.82)],
    4: [(_xL, 0.18), (_xR, 0.18), (_xL, 0.82), (_xR, 0.82)],
    5: [(_xL, 0.18), (_xR, 0.18), (_xC, 0.50), (_xL, 0.82), (_xR, 0.82)],
    6: [(_xL, 0.18), (_xR, 0.18), (_xL, 0.50), (_xR, 0.50), (_xL, 0.82), (_xR, 0.82)],
    7: [(_xL, 0.18), (_xR, 0.18), (_xC, 0.34), (_xL, 0.50), (_xR, 0.50),
        (_xL, 0.82), (_xR, 0.82)],
    8: [(_xL, 0.18), (_xR, 0.18), (_xC, 0.34), (_xL, 0.50), (_xR, 0.50),
        (_xC, 0.66), (_xL, 0.82), (_xR, 0.82)],
    9: [(_xL, 0.16), (_xR, 0.16), (_xL, 0.38), (_xR, 0.38), (_xC, 0.50),
        (_xL, 0.62), (_xR, 0.62), (_xL, 0.84), (_xR, 0.84)],
    10: [(_xL, 0.16), (_xR, 0.16), (_xC, 0.30), (_xL, 0.38), (_xR, 0.38),
         (_xL, 0.62), (_xR, 0.62), (_xC, 0.70), (_xL, 0.84), (_xR, 0.84)],
}


class Card:
    __slots__ = ("suit", "rank", "face_up")

    def __init__(self, suit, rank):
        self.suit = suit
        self.rank = rank
        self.face_up = False

    @property
    def is_red(self):
        return self.suit in RED_SUITS

    @property
    def value(self):
        return RANK_VALUE[self.rank]

    def __repr__(self):
        return f"{self.rank}{self.suit}"


def make_deck():
    deck = [Card(s, r) for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

CARD_W = 90
CARD_H = 130
GAP_X = 44
GAP_Y = 30
FAN_Y = 26          # vertical offset between fanned tableau cards
MARGIN = 24
TOP_Y = MARGIN
TABLEAU_Y = TOP_Y + CARD_H + GAP_Y

BG = "#0b6623"       # felt green
CARD_BG = "#faf3e0"
CARD_BORDER = "#c9a227"
CARD_BACK = "#25507a"
CARD_BACK_2 = "#3a6ea5"
EMPTY_OUTLINE = "#0a5a1e"
HIGHLIGHT = "#ffd54a"

GRAVITY = 1.3          # win-animation card bounce
BOUNCE_DAMPING = 0.78


def col_x(i):
    return MARGIN + i * (CARD_W + GAP_X)


# The game's emblem: a gold roundel bearing a "T", used for the window icon
# and drawn on every card back so the deck and the app share one look.
ICON_BLUE = "#25507a"
ICON_GOLD = "#ffd54a"
ICON_DARK = "#10331d"


def make_app_icon(size=64):
    """Build the 'T' emblem as a tk.PhotoImage, drawn pixel-by-pixel."""
    img = tk.PhotoImage(width=size, height=size)
    cx = cy = (size - 1) / 2.0
    rad = size * 0.30
    border = max(2, int(size * 0.06))
    stem_hw = size * 0.055
    bar_hw = size * 0.17
    t_top = cy - size * 0.17
    t_bar_bottom = cy - size * 0.06
    t_bottom = cy + size * 0.17

    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            if x < border or x >= size - border or y < border or y >= size - border:
                row.append(ICON_GOLD)                       # outer frame
                continue
            colour = ICON_BLUE
            if (x - cx) ** 2 + (y - cy) ** 2 <= rad * rad:
                colour = ICON_GOLD                          # roundel
                in_t = (abs(x - cx) <= stem_hw and t_top <= y <= t_bottom) or \
                       (abs(x - cx) <= bar_hw and t_top <= y <= t_bar_bottom)
                if in_t:
                    colour = ICON_DARK                      # the "T"
            row.append(colour)
        rows.append("{" + " ".join(row) + "}")
    img.put(" ".join(rows))
    return img


# ---------------------------------------------------------------------------
# Online leaderboard (a shared GitHub gist holding a JSON list of scores)
# ---------------------------------------------------------------------------

class Leaderboard:
    """Reads/writes a shared scores list in a GitHub gist. All network work
    happens on a daemon thread; results come back through on_update(entries),
    which the caller marshals onto the Tk main thread."""

    API = "https://api.github.com/gists/"

    def __init__(self, gist_id, token, on_update):
        self.gist_id = gist_id
        self.token = token
        self.on_update = on_update

    @property
    def enabled(self):
        return bool(self.gist_id)

    def _headers(self):
        h = {"Accept": "application/vnd.github+json",
             "User-Agent": "toms-solitaire"}
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        return h

    def _read(self):
        req = urllib.request.Request(self.API + self.gist_id, headers=self._headers())
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.load(resp)
        content = data["files"][LEADERBOARD_FILENAME]["content"]
        return json.loads(content) if content.strip() else []

    @staticmethod
    def _prune(entries):
        # keep each player's best entry per mode, then the top 25 overall
        best = {}
        for e in entries:
            key = (e.get("name", "?"), e.get("mode", "standard"))
            if key not in best or e.get("score", 0) > best[key].get("score", 0):
                best[key] = e
        pruned = sorted(best.values(), key=lambda e: e.get("score", 0), reverse=True)
        return pruned[:25]

    def fetch_async(self):
        if not self.enabled:
            self.on_update(None)
            return
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        try:
            self.on_update(self._read())
        except Exception:
            self.on_update(None)

    def submit_async(self, entry):
        if not self.enabled:
            self.on_update(None)
            return
        threading.Thread(target=self._submit_worker, args=(entry,), daemon=True).start()

    def _submit_worker(self, entry):
        try:
            entries = self._read()
        except Exception:
            entries = []
        entries.append(entry)
        entries = self._prune(entries)
        try:
            body = json.dumps({"files": {LEADERBOARD_FILENAME:
                              {"content": json.dumps(entries, indent=2)}}}).encode()
            req = urllib.request.Request(
                self.API + self.gist_id, data=body, method="PATCH",
                headers={**self._headers(), "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8):
                pass
        except Exception:
            pass  # offline or no write token — keep the local copy regardless
        self.on_update(entries)


def version_tuple(v):
    out = []
    for part in str(v).split("."):
        try:
            out.append(int(part))
        except ValueError:
            out.append(0)
    out = (out + [0, 0, 0, 0])[:4]   # pad so "1.0" and "1.0.0" compare equal
    return tuple(out)


class Updater:
    """Checks a public GitHub repo for a newer version and downloads the
    listed files. All network work runs on a daemon thread; results are
    delivered through callbacks the caller marshals onto the Tk main thread."""

    def __init__(self, repo, branch, on_result):
        self.repo = repo
        self.branch = branch
        self.on_result = on_result

    @property
    def enabled(self):
        return bool(self.repo)

    def _raw(self, path):
        return (f"https://raw.githubusercontent.com/{self.repo}/"
                f"{self.branch}/{path}?t={int(time.time())}")

    def check_async(self):
        if not self.enabled:
            self.on_result({"error": "disabled"})
            return
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self):
        try:
            req = urllib.request.Request(self._raw("version.json"),
                                         headers={"User-Agent": "toms-solitaire"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                self.on_result({"info": json.load(resp)})
        except Exception as exc:
            self.on_result({"error": str(exc)})

    def download_async(self, files, done):
        threading.Thread(target=self._download_worker,
                         args=(files, done), daemon=True).start()

    def _download_worker(self, files, done):
        here = os.path.dirname(os.path.abspath(__file__))
        try:
            # fetch everything first; only touch disk once all succeed, so a
            # failed download can never leave a half-written solitaire.py
            blobs = {}
            for rel in files:
                req = urllib.request.Request(self._raw(rel),
                                             headers={"User-Agent": "toms-solitaire"})
                with urllib.request.urlopen(req, timeout=25) as resp:
                    blobs[rel] = resp.read()
            for rel, data in blobs.items():
                dest = os.path.join(here, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(dest) or here, exist_ok=True)
                tmp = dest + ".new"
                with open(tmp, "wb") as fh:
                    fh.write(data)
                os.replace(tmp, dest)      # atomic swap into place
            done(True, None)
        except Exception as exc:
            done(False, str(exc))


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

class Solitaire:
    def __init__(self, root):
        self.root = root
        self.root.title("Tom's Solitaire")
        self.draw_three = False

        # window / taskbar icon (also drawn on every card back)
        try:
            self.icon = make_app_icon(64)
            self.root.iconphoto(True, self.icon)
        except Exception:
            self.icon = None

        # optional illustrated faces for A/J/Q/K, loaded from a cards/ folder
        self.card_images, self.full_images = self._load_card_images()

        width = MARGIN * 2 + 7 * CARD_W + 6 * GAP_X
        height = TABLEAU_Y + CARD_H + 19 * FAN_Y + MARGIN
        self.W, self.H = width, height
        self.canvas = tk.Canvas(root, width=width, height=height,
                                bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # persistent state (name, best score, Vegas bankroll, local scores)
        self.state = self._load_state()
        self.vegas = bool(self.state.get("vegas", False))

        # Drag state
        self.drag_cards = []       # list of Card objects being dragged
        self.drag_source = None    # ("tableau", col) or ("waste", None)
        self.drag_items = []       # canvas item ids for the floating cards
        self.drag_offset = (0, 0)
        self.dragging_ids = set()  # cards currently lifted (hidden from board)

        # Undo (single level)
        self.undo_state = None

        # Score / timing state
        self.score = 0
        self.hand = 0             # this deal's net in Vegas dollars
        self.moves = 0
        self.passes = 0          # stock recycles used (capped in Vegas)
        self.start_time = None
        self._clock_job = None
        self._anim_job = None
        self.anim_running = False

        # leaderboard (online if configured, otherwise local only)
        self.lb_entries = None
        self.lb_window = None
        self.leaderboard = Leaderboard(LEADERBOARD_GIST_ID, LEADERBOARD_TOKEN,
                                       self._on_leaderboard_update)

        # online updates (optional)
        self.updater = Updater(UPDATE_REPO, UPDATE_BRANCH, self._on_update_result)
        self._update_manual = False
        self.update_window = None

        self._build_menu()
        self.player_name = self._ensure_player_name()
        self._bind_game_handlers()
        self.new_game()

        # quiet check on startup — only pops up if a newer version exists
        if self.updater.enabled:
            self.root.after(1500, lambda: self.check_updates(manual=False))

    # -- input binding ------------------------------------------------------

    def _bind_game_handlers(self):
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", self.on_double)

    def _unbind_game_handlers(self):
        for seq in ("<ButtonPress-1>", "<B1-Motion>",
                    "<ButtonRelease-1>", "<Double-Button-1>"):
            self.canvas.unbind(seq)

    # -- persistent state ---------------------------------------------------

    def _load_state(self):
        defaults = {"name": "", "best": 0, "bankroll": 0,
                    "vegas": False, "local_scores": []}
        try:
            with open(STATE_FILE, "r") as fh:
                data = json.load(fh)
            defaults.update({k: data[k] for k in defaults if k in data})
        except Exception:
            pass
        return defaults

    def _save_state(self):
        try:
            with open(STATE_FILE, "w") as fh:
                json.dump(self.state, fh, indent=2)
        except Exception:
            pass  # persistence is best-effort, never crash the game over it

    @property
    def best(self):
        return self.state.get("best", 0)

    @best.setter
    def best(self, value):
        self.state["best"] = value

    # -- player name --------------------------------------------------------

    def _ensure_player_name(self):
        name = self.state.get("name", "").strip()
        if name:
            keep = messagebox.askyesno(
                "Mirë se erdhe",
                f"Mirë se erdhe, {name}!\n\nTë vazhdosh si \u201c{name}\u201d?")
            if keep:
                return name
        return self._prompt_name(name)

    def _prompt_name(self, current=""):
        answer = simpledialog.askstring(
            "Emri i lojtarit", "Shkruaj emrin tënd:",
            parent=self.root, initialvalue=current)
        name = (answer or "").strip() or current or "Player"
        self.state["name"] = name
        self._save_state()
        return name

    def _change_name(self):
        self.player_name = self._prompt_name(self.player_name)
        self.render()

    # -- leaderboard --------------------------------------------------------

    def _on_leaderboard_update(self, entries):
        # called from a worker thread — bounce onto the Tk main thread
        self.root.after(0, lambda: self._apply_leaderboard(entries))

    def _apply_leaderboard(self, entries):
        if entries is not None:
            self.lb_entries = entries
        if self.lb_window is not None and self.lb_window.winfo_exists():
            self._render_leaderboard()

    def _record_score(self, mode, value):
        entry = {"name": self.player_name, "mode": mode, "score": value,
                 "date": time.strftime("%Y-%m-%d"),
                 "seconds": self._elapsed()}
        # always keep a local copy so a single machine still has a board
        local = self.state.setdefault("local_scores", [])
        local.append(entry)
        self.state["local_scores"] = Leaderboard._prune(local)
        self._save_state()
        # push to the shared board if one is configured
        self.leaderboard.submit_async(entry)

    def show_leaderboard(self):
        if self.lb_window is not None and self.lb_window.winfo_exists():
            self.lb_window.lift()
            return
        win = tk.Toplevel(self.root)
        win.title("Tabela e rezultateve")
        win.configure(bg="#10331d")
        win.resizable(False, False)
        self.lb_window = win
        self._lb_body = tk.Frame(win, bg="#10331d")
        self._lb_body.pack(padx=16, pady=14)
        # show what we have, then refresh from the network
        if self.lb_entries is None:
            self.lb_entries = list(self.state.get("local_scores", []))
        self._render_leaderboard(loading=self.leaderboard.enabled)
        if self.leaderboard.enabled:
            self.leaderboard.fetch_async()

    def _render_leaderboard(self, loading=False):
        for w in self._lb_body.winfo_children():
            w.destroy()
        title = ("Tabela e rezultateve" if self.leaderboard.enabled
                 else "Tabela e rezultateve (në këtë kompjuter)")
        tk.Label(self._lb_body, text=title, bg="#10331d", fg=HIGHLIGHT,
                 font=("Helvetica", 16, "bold")).pack(anchor="w")
        entries = self.lb_entries or []
        for mode, heading in (("standard", "Standard (pikë)"),
                              ("vegas", "Vegas (dollarë)")):
            rows = sorted([e for e in entries if e.get("mode") == mode],
                          key=lambda e: e.get("score", 0), reverse=True)[:10]
            if not rows:
                continue
            tk.Label(self._lb_body, text=heading, bg="#10331d", fg="#cfe8d4",
                     font=("Helvetica", 12, "bold")).pack(anchor="w", pady=(10, 2))
            for i, e in enumerate(rows, 1):
                v = e.get("score", 0)
                shown = (f"-${abs(v)}" if v < 0 else f"${v}") if mode == "vegas" else str(v)
                line = f"{i:>2}. {e.get('name','?')[:16]:<16} {shown:>8}   {e.get('date','')}"
                tk.Label(self._lb_body, text=line, bg="#10331d", fg="#ffffff",
                         font=("Courier", 11)).pack(anchor="w")
        if loading:
            tk.Label(self._lb_body, text="Po përditësohet nga interneti\u2026",
                     bg="#10331d", fg="#9ccbaa",
                     font=("Helvetica", 10, "italic")).pack(anchor="w", pady=(10, 0))
        elif not entries:
            tk.Label(self._lb_body, text="Ende asnjë rezultat — fito një lojë!",
                     bg="#10331d", fg="#9ccbaa",
                     font=("Helvetica", 11)).pack(anchor="w", pady=(8, 0))

    # -- about --------------------------------------------------------------

    def show_about(self):
        win = tk.Toplevel(self.root)
        win.title("Rreth Tom's Solitaire")
        win.configure(bg="#10331d")
        win.resizable(False, False)
        frame = tk.Frame(win, bg="#10331d")
        frame.pack(padx=24, pady=20)
        if self.icon is not None:
            tk.Label(frame, image=self.icon, bg="#10331d").pack()
        tk.Label(frame, text="Tom's Solitaire", bg="#10331d", fg=HIGHLIGHT,
                 font=("Georgia", 20, "bold")).pack(pady=(8, 2))
        tk.Label(frame, text=f"Klondike \u2014 versioni {VERSION}",
                 bg="#10331d", fg="#cfe8d4", font=("Helvetica", 11)).pack()
        # Dedication, in Albanian
        dedication = ("Dizajni i kësaj loje i kushtohet kolegut tonë\n"
                      "Ing. Tomorr Spahiu, në shenjë respekti për punën e tij.")
        tk.Label(frame, text=dedication, bg="#10331d", fg="#ffffff",
                 font=("Georgia", 12, "italic"), justify="center",
                 wraplength=360).pack(pady=(16, 4))
        tk.Button(frame, text="Mbyll", command=win.destroy).pack(pady=(14, 0))

    # -- updates ------------------------------------------------------------

    def check_updates(self, manual=True):
        self._update_manual = manual
        if not self.updater.enabled:
            if manual:
                messagebox.showinfo(
                    "Përditësime",
                    "Përditësimet nuk janë konfiguruar.\n\n"
                    "Vendos emrin e depozitës në UPDATE_REPO brenda solitaire.py.")
            return
        self.updater.check_async()

    def _on_update_result(self, res):
        self.root.after(0, lambda: self._apply_update_result(res))

    def _apply_update_result(self, res):
        if "error" in res:
            if self._update_manual and res["error"] != "disabled":
                messagebox.showwarning(
                    "Përditësime", "Nuk u arrit të kontrollohej për përditësime.")
            return
        info = res.get("info", {})
        latest = info.get("version", "0")
        if version_tuple(latest) > version_tuple(VERSION):
            self._show_update_window(info)
        elif self._update_manual:
            messagebox.showinfo(
                "Përditësime", f"Je i përditësuar (versioni {VERSION}).")

    def _show_update_window(self, info):
        if self.update_window is not None and self.update_window.winfo_exists():
            self.update_window.lift()
            return
        latest = info.get("version", "?")
        notes = info.get("notes", "")
        files = info.get("files", ["solitaire.py"])

        win = tk.Toplevel(self.root)
        win.title("Përditësim i disponueshëm")
        win.configure(bg="#10331d")
        win.resizable(False, False)
        self.update_window = win
        frame = tk.Frame(win, bg="#10331d")
        frame.pack(padx=22, pady=18)
        tk.Label(frame, text="Përditësim i disponueshëm", bg="#10331d",
                 fg=HIGHLIGHT, font=("Georgia", 16, "bold")).pack(anchor="w")
        tk.Label(frame, text=f"Version i ri {latest}  (ke {VERSION})",
                 bg="#10331d", fg="#cfe8d4", font=("Helvetica", 11)).pack(
                     anchor="w", pady=(2, 8))
        if notes:
            tk.Label(frame, text=notes, bg="#10331d", fg="#ffffff",
                     font=("Helvetica", 10), justify="left",
                     wraplength=360).pack(anchor="w")
        self._update_status = tk.Label(frame, text="", bg="#10331d",
                                       fg="#9ccbaa", font=("Helvetica", 10, "italic"))
        self._update_status.pack(anchor="w", pady=(10, 0))
        btns = tk.Frame(frame, bg="#10331d")
        btns.pack(anchor="e", pady=(14, 0))
        self._update_btn = tk.Button(
            btns, text="Përditëso tani",
            command=lambda: self._start_download(files))
        self._update_btn.pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Më vonë", command=win.destroy).pack(side="right")

    def _start_download(self, files):
        self._update_btn.config(state="disabled")
        self._update_status.config(text="Po shkarkohet\u2026")
        self.updater.download_async(
            files, lambda ok, err: self.root.after(0,
                lambda: self._on_download_done(ok, err)))

    def _on_download_done(self, ok, err):
        if ok:
            if self.update_window is not None and self.update_window.winfo_exists():
                self.update_window.destroy()
            messagebox.showinfo(
                "Përditësime",
                "U përditësua me sukses.\nMbylle dhe rihap lojën "
                "për të parë ndryshimet.")
        else:
            self._update_status.config(
                text="Shkarkimi dështoi. Provo më vonë.", fg="#e6a0a0")
            self._update_btn.config(state="normal")

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        game = tk.Menu(menubar, tearoff=0)
        game.add_command(label="Lojë e re", command=self.new_game, accelerator="F2")
        game.add_command(label="Zhbëj", command=self._undo, accelerator="Ctrl+Z")
        self.draw_var = tk.BooleanVar(value=self.draw_three)
        game.add_checkbutton(label="Tërhiq nga tri", variable=self.draw_var,
                             command=self._toggle_draw)
        self.vegas_var = tk.BooleanVar(value=self.vegas)
        game.add_checkbutton(label="Vlerësim Vegas", variable=self.vegas_var,
                             command=self._toggle_vegas)
        game.add_command(label="Rivendos bankën Vegas", command=self._reset_bankroll)
        game.add_separator()
        game.add_command(label="Ndrysho emrin\u2026", command=self._change_name)
        game.add_command(label="Tabela e rezultateve\u2026",
                         command=self.show_leaderboard)
        game.add_separator()
        game.add_command(label="Dil", command=self.root.quit)
        menubar.add_cascade(label="Loja", menu=game)

        helpm = tk.Menu(menubar, tearoff=0)
        helpm.add_command(label="Kontrollo për përditësime\u2026",
                          command=lambda: self.check_updates(manual=True))
        helpm.add_command(label="Rreth lojës\u2026", command=self.show_about)
        menubar.add_cascade(label="Ndihmë", menu=helpm)

        self.root.config(menu=menubar)
        self.root.bind("<F2>", lambda e: self.new_game())
        self.root.bind("<Control-z>", lambda e: self._undo())

    def _toggle_draw(self):
        self.draw_three = self.draw_var.get()

    def _toggle_vegas(self):
        self.vegas = self.vegas_var.get()
        self.state["vegas"] = self.vegas
        self._save_state()
        # scoring rules differ per mode, so start a fresh deal
        self.new_game()

    def _reset_bankroll(self):
        if messagebox.askyesno("Rivendos bankën",
                               "Ta kthej bankën Vegas në $0?"):
            self.state["bankroll"] = 0
            self._save_state()
            self.render()

    # -- setup --------------------------------------------------------------

    def new_game(self):
        # leave any win animation cleanly
        self.anim_running = False
        if self._anim_job:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None
        self._bind_game_handlers()
        self.root.unbind("<Key>")

        deck = make_deck()
        self.stock = []
        self.waste = []
        self.foundations = [[] for _ in range(4)]
        self.tableau = [[] for _ in range(7)]

        for col in range(7):
            for row in range(col + 1):
                card = deck.pop()
                card.face_up = (row == col)
                self.tableau[col].append(card)
        self.stock = deck  # remaining 24 cards, all face down
        for c in self.stock:
            c.face_up = False

        self.score = 0
        self.hand = 0
        self.moves = 0
        self.passes = 0
        self.undo_state = None
        self.dragging_ids = set()
        if self.vegas:
            # buy the deck for $52 (authentic Vegas); +$5 per foundation card
            self.hand = -52
            self.state["bankroll"] = self.state.get("bankroll", 0) - 52
            self._save_state()
        self.start_time = time.time()
        self._start_clock()
        self.render()

    # -- undo (single level) ------------------------------------------------

    def _clone_pile(self, pile):
        out = []
        for c in pile:
            d = Card(c.suit, c.rank)
            d.face_up = c.face_up
            out.append(d)
        return out

    def _push_undo(self):
        self.undo_state = {
            "stock": self._clone_pile(self.stock),
            "waste": self._clone_pile(self.waste),
            "foundations": [self._clone_pile(p) for p in self.foundations],
            "tableau": [self._clone_pile(p) for p in self.tableau],
            "score": self.score,
            "moves": self.moves,
            "hand": self.hand,
            "passes": self.passes,
            "bankroll": self.state.get("bankroll", 0),
        }

    def _undo(self):
        if not self.undo_state or self.anim_running:
            return
        s = self.undo_state
        self.stock = s["stock"]
        self.waste = s["waste"]
        self.foundations = s["foundations"]
        self.tableau = s["tableau"]
        self.score = s["score"]
        self.moves = s["moves"]
        self.hand = s["hand"]
        self.passes = s["passes"]
        self.state["bankroll"] = s["bankroll"]   # refund/restore Vegas money
        self._save_state()
        self.undo_state = None       # only one undo per move
        self.dragging_ids = set()
        self.render()

    # -- clock --------------------------------------------------------------

    def _start_clock(self):
        if self._clock_job:
            self.root.after_cancel(self._clock_job)
        self._tick_clock()

    def _tick_clock(self):
        if not self.anim_running:
            self._update_scoreboard()
        self._clock_job = self.root.after(1000, self._tick_clock)

    def _elapsed(self):
        return int(time.time() - self.start_time) if self.start_time else 0

    # -- rendering ----------------------------------------------------------

    def render(self):
        self.canvas.delete("all")
        self._draw_stock()
        self._draw_waste()
        self._draw_foundations()
        self._draw_tableau()
        self._update_scoreboard()

    def _update_scoreboard(self):
        self.canvas.delete("scoreboard")
        # a plaque filling the band between the (draw-three) waste fan and the
        # foundations, so the top row reads as an intentional element, not a gap
        waste_right = col_x(1) + 2 * 22 + CARD_W
        x0 = waste_right + 4
        x1 = col_x(3) - 4
        self._rounded_rect(x0, TOP_Y, x1 - x0, CARD_H, r=8,
                           fill="#0a4f1c", outline=ICON_GOLD, width=1,
                           tags="scoreboard")
        secs = self._elapsed()
        clock = f"{secs // 60}:{secs % 60:02d}"
        if self.vegas:
            lines = [
                ("Banka", self._money(self.state.get("bankroll", 0))),
                ("Dora", self._money(self.hand)),
                ("Koha", clock),
                ("Lëvizje", str(self.moves)),
            ]
        else:
            lines = [
                ("Pikët", str(self.score)),
                ("Rekordi", str(self.best)),
                ("Koha", clock),
                ("Lëvizje", str(self.moves)),
            ]
        y = TOP_Y + (CARD_H - len(lines) * 24) / 2 + 12
        for label, value in lines:
            self.canvas.create_text(x0 + 9, y, text=f"{label}:", anchor="w",
                                    fill="#e8f5e9", font=("Helvetica", 10),
                                    tags="scoreboard")
            self.canvas.create_text(x1 - 9, y, text=value, anchor="e",
                                    fill="#ffffff", font=("Helvetica", 11, "bold"),
                                    tags="scoreboard")
            y += 24

    @staticmethod
    def _money(v):
        return f"-${abs(v)}" if v < 0 else f"${v}"

    def _rounded_rect(self, x, y, w, h, r=10, **kw):
        pts = [
            x + r, y, x + w - r, y, x + w, y, x + w, y + r,
            x + w, y + h - r, x + w, y + h, x + w - r, y + h,
            x + r, y + h, x, y + h, x, y + h - r,
            x, y + r, x, y,
        ]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def _load_card_images(self):
        """Load card art from a cards/ folder next to this script.
        Returns (figures, full): 'figures' are centred illustrations for the
        court cards (drawn on the game's card with a rank index); 'full' are
        complete card images (the four aces and the back) drawn edge to edge.
        Anything missing falls back to code drawing, so a partial set works."""
        here = os.path.dirname(os.path.abspath(__file__))
        folder = os.path.join(here, "cards")
        suit_letter = {"\u2660": "S", "\u2665": "H", "\u2666": "D", "\u2663": "C"}
        figures, full = {}, {}
        if not os.path.isdir(folder):
            return figures, full

        def load(name):
            path = os.path.join(folder, name + ".png")
            if os.path.exists(path):
                try:
                    return tk.PhotoImage(file=path)
                except Exception:
                    return None
            return None

        back = load("back")
        if back is not None:
            full["back"] = back
        for suit, letter in suit_letter.items():
            ace = load("A" + letter)
            if ace is not None:
                full["A" + suit] = ace
            for rank in ("J", "Q", "K"):
                fig = load(rank + letter)
                if fig is not None:
                    figures[rank + suit] = fig
        return figures, full

    def _draw_card(self, card, x, y):
        if not card.face_up:
            self._draw_card_back(x, y)
            return

        # full-card art (aces) covers the whole card, index baked in
        full = self.full_images.get(card.rank + card.suit)
        if full is not None:
            self.canvas.create_image(x + CARD_W / 2, y + CARD_H / 2, image=full)
            return

        colour = "#c0392b" if card.is_red else "#1a1a1a"
        self._rounded_rect(x, y, CARD_W, CARD_H, fill=CARD_BG,
                           outline=CARD_BORDER, width=1)
        self._draw_corner_index(card, x, y, colour)

        fig = self.card_images.get(card.rank + card.suit)
        if fig is not None:                       # illustrated court figure
            self.canvas.create_image(x + CARD_W / 2, y + CARD_H / 2 + 6, image=fig)
        elif card.rank == "A":
            self._draw_ace(card, x, y, colour)
        elif card.rank in ("J", "Q", "K"):
            self._draw_court(card, x, y, colour)
        else:
            self._draw_pip_card(card, x, y, colour)

    def _draw_corner_index(self, card, x, y, colour):
        label = RANK_LABEL.get(card.rank, card.rank)
        f_rank = ("Helvetica", 12, "bold")
        f_suit = ("Helvetica", 11)
        # top-left, upright (centre-anchored, well inside the edge)
        self.canvas.create_text(x + 12, y + 14, text=label, fill=colour, font=f_rank)
        self.canvas.create_text(x + 12, y + 29, text=card.suit, fill=colour, font=f_suit)
        # bottom-right, rotated 180° like a real card
        self.canvas.create_text(x + CARD_W - 12, y + CARD_H - 14, text=label,
                                fill=colour, angle=180, font=f_rank)
        self.canvas.create_text(x + CARD_W - 12, y + CARD_H - 29, text=card.suit,
                                fill=colour, angle=180, font=f_suit)

    def _draw_pip_card(self, card, x, y, colour):
        n = card.value
        layout = PIP_LAYOUT.get(n, [(0.5, 0.5)])
        inset_l, inset_r = 0.20, 0.80        # keep pips clear of the corner index
        for xf, yf in layout:
            px = x + CARD_W * xf
            py = y + CARD_H * (0.13 + yf * 0.74)
            angle = 180 if yf > 0.5 else 0
            self.canvas.create_text(px, py, text=card.suit, fill=colour,
                                    angle=angle, font=("Helvetica", 20))

    def _draw_ace(self, card, x, y, colour):
        cx, cy = x + CARD_W / 2, y + CARD_H / 2
        # decorative double ring around one large central pip
        self.canvas.create_oval(cx - 26, cy - 26, cx + 26, cy + 26,
                                outline=colour, width=2)
        self.canvas.create_oval(cx - 21, cy - 21, cx + 21, cy + 21,
                                outline=colour, width=1)
        for a in range(8):                    # little flourish dots around the ring
            ang = a * math.pi / 4
            dx, dy = 33 * math.cos(ang), 33 * math.sin(ang)
            self.canvas.create_oval(cx + dx - 1.5, cy + dy - 1.5,
                                    cx + dx + 1.5, cy + dy + 1.5,
                                    fill=colour, outline="")
        self.canvas.create_text(cx, cy, text=card.suit, fill=colour,
                                font=("Helvetica", 30))

    def _draw_court(self, card, x, y, colour):
        cx = x + CARD_W / 2
        # inset frame + a dividing line, echoing a traditional court card
        self._rounded_rect(x + 8, y + 8, CARD_W - 16, CARD_H - 16, r=8,
                           fill="", outline=colour, width=1)
        gold = ICON_GOLD
        # top figure (upright) and bottom figure (mirrored through the centre)
        top_cy = y + CARD_H * 0.34
        bot_cy = y + CARD_H * 0.66
        self._draw_figure(card.rank, cx, top_cy, colour, gold, flip=False)
        self._draw_figure(card.rank, cx, bot_cy, colour, gold, flip=True)
        # small suit marks flanking the centre
        self.canvas.create_text(x + CARD_W * 0.30, y + CARD_H / 2, text=card.suit,
                                fill=colour, font=("Helvetica", 12))
        self.canvas.create_text(x + CARD_W * 0.70, y + CARD_H / 2, text=card.suit,
                                fill=colour, angle=180, font=("Helvetica", 12))

    def _draw_figure(self, rank, cx, cy, colour, gold, flip):
        """A small emblem per court card: crown (K), tiara (Q), plumed cap (J)."""
        s = -1 if flip else 1                 # vertical direction
        # a face medallion
        self.canvas.create_oval(cx - 15, cy - 15, cx + 15, cy + 15,
                                fill="#faf3e0", outline=colour, width=1)
        # tiny facial hint
        self.canvas.create_oval(cx - 6, cy - 6 * s, cx - 2, cy - 2 * s,
                                fill=colour, outline="")
        self.canvas.create_oval(cx + 2, cy - 6 * s, cx + 6, cy - 2 * s,
                                fill=colour, outline="")
        headwear_y = cy - 17 * s
        if rank == "K":
            pts = [cx - 16, headwear_y, cx - 16, headwear_y - 12 * s,
                   cx - 8, headwear_y - 4 * s, cx, headwear_y - 14 * s,
                   cx + 8, headwear_y - 4 * s, cx + 16, headwear_y - 12 * s,
                   cx + 16, headwear_y]
            self.canvas.create_polygon(pts, fill=gold, outline=colour, width=1)
            self.canvas.create_line(cx, headwear_y - 14 * s, cx, headwear_y - 20 * s,
                                    fill=gold, width=2)
            self.canvas.create_line(cx - 3, headwear_y - 17 * s,
                                    cx + 3, headwear_y - 17 * s, fill=gold, width=2)
        elif rank == "Q":
            pts = [cx - 15, headwear_y, cx - 10, headwear_y - 11 * s,
                   cx - 5, headwear_y - 4 * s, cx, headwear_y - 12 * s,
                   cx + 5, headwear_y - 4 * s, cx + 10, headwear_y - 11 * s,
                   cx + 15, headwear_y]
            self.canvas.create_polygon(pts, fill=gold, outline=colour, width=1)
            for gx in (-10, 0, 10):
                self.canvas.create_oval(cx + gx - 2, headwear_y - 12 * s - 2,
                                        cx + gx + 2, headwear_y - 12 * s + 2,
                                        fill=gold, outline=colour)
        else:  # Jack — plumed cap
            self.canvas.create_arc(cx - 15, headwear_y - 14 * s, cx + 15,
                                   headwear_y + 14 * s,
                                   start=0, extent=180 * s if s > 0 else 180,
                                   fill=gold, outline=colour, style="chord")
            self.canvas.create_line(cx + 10, headwear_y, cx + 20, headwear_y - 12 * s,
                                    fill=colour, width=2)

    def _draw_card_back(self, x, y):
        """Card back: illustrated image if provided, else the 'T' emblem."""
        back = self.full_images.get("back")
        if back is not None:
            self.canvas.create_image(x + CARD_W / 2, y + CARD_H / 2, image=back)
            return
        self._rounded_rect(x, y, CARD_W, CARD_H, fill=CARD_BACK,
                           outline="#0d2033", width=1)
        self._rounded_rect(x + 7, y + 7, CARD_W - 14, CARD_H - 14, r=8,
                           fill="", outline=ICON_GOLD, width=2)
        cx, cy = x + CARD_W / 2, y + CARD_H / 2
        r = CARD_W * 0.26
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                fill=ICON_GOLD, outline="#0d2033", width=1)
        self.canvas.create_text(cx, cy, text="T", fill=ICON_DARK,
                                font=("Georgia", int(r * 1.3), "bold"))
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            self.canvas.create_text(cx + dx * CARD_W * 0.32,
                                    cy + dy * CARD_H * 0.34,
                                    text="\u2660", fill=ICON_GOLD,
                                    font=("Helvetica", 10))

    def _draw_empty(self, x, y, label=""):
        self._rounded_rect(x, y, CARD_W, CARD_H, fill="",
                           outline=EMPTY_OUTLINE, width=2)
        if label:
            self.canvas.create_text(x + CARD_W / 2, y + CARD_H / 2,
                                    text=label, fill=EMPTY_OUTLINE,
                                    font=("Helvetica", 28))

    def _draw_stock(self):
        x, y = col_x(0), TOP_Y
        if self.stock:
            self._draw_card(self.stock[-1], x, y)  # face-down back
        else:
            self._draw_empty(x, y, "\u21ba")

    def _draw_waste(self):
        x, y = col_x(1), TOP_Y
        vis = [c for c in self.waste if id(c) not in self.dragging_ids]
        if vis:
            show = vis[-3:] if self.draw_three else vis[-1:]
            for i, card in enumerate(show):
                self._draw_card(card, x + i * 22, y)
        else:
            self._draw_empty(x, y)

    def _draw_foundations(self):
        for i in range(4):
            x, y = col_x(3 + i), TOP_Y
            vis = [c for c in self.foundations[i] if id(c) not in self.dragging_ids]
            if vis:
                self._draw_card(vis[-1], x, y)
            else:
                self._draw_empty(x, y, RANK_LABEL["A"])

    def _draw_tableau(self):
        for col in range(7):
            x = col_x(col)
            vis = [c for c in self.tableau[col] if id(c) not in self.dragging_ids]
            if not vis:
                self._draw_empty(x, TABLEAU_Y, RANK_LABEL["K"])
                continue
            y = TABLEAU_Y
            for card in vis:
                self._draw_card(card, x, y)
                y += FAN_Y

    # -- hit testing --------------------------------------------------------

    def _tableau_hit(self, px, py):
        """Return (col, index) of the topmost face-up card hit, else None."""
        for col in range(7):
            x = col_x(col)
            if not (x <= px <= x + CARD_W):
                continue
            pile = self.tableau[col]
            for idx in range(len(pile) - 1, -1, -1):
                cy = TABLEAU_Y + idx * FAN_Y
                # last card uses full height, others use the fan strip
                bottom = cy + (CARD_H if idx == len(pile) - 1 else FAN_Y)
                if cy <= py <= bottom and pile[idx].face_up:
                    return col, idx
        return None

    def _in_rect(self, px, py, x, y):
        return x <= px <= x + CARD_W and y <= py <= y + CARD_H

    def _waste_top_x(self):
        """X of the playable (top) waste card — it fans right in draw-three."""
        if not self.waste:
            return col_x(1)
        shown = min(3, len(self.waste)) if self.draw_three else 1
        return col_x(1) + (shown - 1) * 22

    # -- interaction --------------------------------------------------------

    def on_press(self, event):
        px, py = event.x, event.y

        # Stock click -> draw
        if self._in_rect(px, py, col_x(0), TOP_Y):
            self._draw_from_stock()
            return

        # Waste -> start dragging the top (playable) card
        wx = self._waste_top_x()
        if self.waste and self._in_rect(px, py, wx, TOP_Y):
            self._begin_drag([self.waste[-1]], ("waste", None), px, py,
                             wx, TOP_Y)
            return

        # Foundation -> drag its top card back into play
        for i in range(4):
            fx, fy = col_x(3 + i), TOP_Y
            if self.foundations[i] and self._in_rect(px, py, fx, fy):
                self._begin_drag([self.foundations[i][-1]], ("foundation", i),
                                 px, py, fx, fy)
                return

        # Tableau -> drag a run
        hit = self._tableau_hit(px, py)
        if hit:
            col, idx = hit
            run = self.tableau[col][idx:]
            if self._is_valid_run(run):
                x = col_x(col)
                y = TABLEAU_Y + idx * FAN_Y
                self._begin_drag(run, ("tableau", col), px, py, x, y)

    def _begin_drag(self, cards, source, px, py, x, y):
        self.drag_cards = cards
        self.drag_source = source
        self.drag_offset = (px - x, py - y)
        self.dragging_ids = {id(c) for c in cards}
        self.render()  # redraw the board with the lifted cards removed
        # draw floating copies on top
        for i, card in enumerate(cards):
            fy = y + i * FAN_Y
            self._draw_floating(card, x, fy)

    def _draw_floating(self, card, x, y):
        # store a group tag so we can move them together
        tag = f"drag"
        self._rounded_rect(x, y, CARD_W, CARD_H, fill=CARD_BG,
                           outline="#555", width=1, tags=tag)
        colour = "#c0392b" if card.is_red else "#1a1a1a"
        self.canvas.create_text(x + 10, y + 8, text=RANK_LABEL.get(card.rank, card.rank),
                                anchor="nw", fill=colour,
                                font=("Helvetica", 14, "bold"), tags=tag)
        self.canvas.create_text(x + 10, y + 30, text=card.suit, anchor="nw",
                                fill=colour, font=("Helvetica", 16), tags=tag)
        self.canvas.create_text(x + CARD_W / 2, y + CARD_H / 2, text=card.suit,
                                fill=colour, font=("Helvetica", 34), tags=tag)

    def on_drag(self, event):
        if not self.drag_cards:
            return
        # Reposition all floating items relative to the first press
        self.canvas.delete("drag")
        ox, oy = self.drag_offset
        x = event.x - ox
        y = event.y - oy
        for i, card in enumerate(self.drag_cards):
            self._draw_floating(card, x, y + i * FAN_Y)

    def on_release(self, event):
        if not self.drag_cards:
            return
        px, py = event.x, event.y
        placed = self._try_drop(px, py)
        self.canvas.delete("drag")
        self.drag_cards = []
        self.drag_source = None
        self.dragging_ids = set()
        if placed:
            self._flip_exposed()
            self.render()
            self._check_win()
        else:
            self.render()

    def on_double(self, event):
        """Auto-move a clicked card to a foundation if legal."""
        px, py = event.x, event.y
        # waste top
        if self.waste and self._in_rect(px, py, self._waste_top_x(), TOP_Y):
            if self._send_to_foundation(self.waste[-1], ("waste", None)):
                self._finish_auto()
            return
        hit = self._tableau_hit(px, py)
        if hit:
            col, idx = hit
            pile = self.tableau[col]
            if idx == len(pile) - 1:  # only the top card
                if self._send_to_foundation(pile[-1], ("tableau", col)):
                    self._finish_auto()

    def _finish_auto(self):
        self._flip_exposed()
        self.render()
        self._check_win()

    # -- rules --------------------------------------------------------------

    def _draw_from_stock(self):
        if not self.stock:
            if self.vegas:
                # draw-three allows one pass (no recycles); draw-one allows three
                max_recycles = 0 if self.draw_three else 2
                if self.passes >= max_recycles:
                    return  # out of passes — the stock stays empty
            self._push_undo()
            if self.vegas:
                self.passes += 1
            # recycle waste back into stock
            self.stock = list(reversed(self.waste))
            for c in self.stock:
                c.face_up = False
            self.waste = []
        else:
            self._push_undo()
            n = 3 if self.draw_three else 1
            for _ in range(min(n, len(self.stock))):
                card = self.stock.pop()
                card.face_up = True
                self.waste.append(card)
        self.render()

    def _is_valid_run(self, cards):
        """A run must be face-up, descending, alternating colours."""
        for c in cards:
            if not c.face_up:
                return False
        for a, b in zip(cards, cards[1:]):
            if a.value != b.value + 1 or a.is_red == b.is_red:
                return False
        return True

    def _can_place_on_tableau(self, moving_bottom, col):
        pile = self.tableau[col]
        if not pile:
            return moving_bottom.value == 13  # only a King on empty
        top = pile[-1]
        if not top.face_up:
            return False
        return top.value == moving_bottom.value + 1 and top.is_red != moving_bottom.is_red

    def _can_place_on_foundation(self, card, f_index):
        pile = self.foundations[f_index]
        if not pile:
            return card.value == 1  # Ace
        top = pile[-1]
        return top.suit == card.suit and card.value == top.value + 1

    def _try_drop(self, px, py):
        bottom = self.drag_cards[0]

        # Drop on a foundation (single card only)
        if len(self.drag_cards) == 1:
            for i in range(4):
                x, y = col_x(3 + i), TOP_Y
                if self._in_rect(px, py, x, y) and self._can_place_on_foundation(bottom, i):
                    self._push_undo()
                    src_kind = self.drag_source[0]
                    self._remove_from_source()
                    self.foundations[i].append(bottom)
                    self.moves += 1
                    if src_kind != "foundation":
                        self._foundation_gain()
                    return True

        # Drop on a tableau column
        for col in range(7):
            x = col_x(col)
            pile = self.tableau[col]
            top_y = TABLEAU_Y + max(len(pile) - 1, 0) * FAN_Y
            drop_bottom = top_y + CARD_H
            if x <= px <= x + CARD_W and TABLEAU_Y <= py <= drop_bottom + FAN_Y:
                if self._can_place_on_tableau(bottom, col):
                    self._push_undo()
                    src_kind = self.drag_source[0]
                    self._remove_from_source()
                    self.tableau[col].extend(self.drag_cards)
                    self.moves += 1
                    if src_kind == "waste" and not self.vegas:
                        self.score += 5
                    elif src_kind == "foundation":
                        self._foundation_loss()
                    return True
        return False

    def _remove_from_source(self):
        kind, col = self.drag_source
        n = len(self.drag_cards)
        if kind == "waste":
            self.waste = self.waste[:-1]
        elif kind == "tableau":
            self.tableau[col] = self.tableau[col][:-n]
        elif kind == "foundation":
            self.foundations[col] = self.foundations[col][:-1]

    def _send_to_foundation(self, card, source):
        for i in range(4):
            if self._can_place_on_foundation(card, i):
                self._push_undo()
                kind, col = source
                if kind == "waste":
                    self.waste.pop()
                elif kind == "tableau":
                    self.tableau[col].pop()
                self.foundations[i].append(card)
                self.moves += 1
                self._foundation_gain()
                return True
        return False

    def _foundation_gain(self):
        if self.vegas:
            self._add_money(5)
        else:
            self.score += 10

    def _foundation_loss(self):
        if self.vegas:
            self._add_money(-5)
        else:
            self.score = max(0, self.score - 10)

    def _add_money(self, delta):
        self.hand += delta
        self.state["bankroll"] = self.state.get("bankroll", 0) + delta
        self._save_state()

    def _flip_exposed(self):
        for pile in self.tableau:
            if pile and not pile[-1].face_up:
                pile[-1].face_up = True
                if not self.vegas:
                    self.score += 5

    def _check_win(self):
        if all(len(f) == 13 for f in self.foundations):
            self._win()

    # -- winning ------------------------------------------------------------

    def _win(self):
        if self._clock_job:
            self.root.after_cancel(self._clock_job)
            self._clock_job = None

        if self.vegas:
            self.new_best = False
            self._record_score("vegas", self.hand)
        else:
            elapsed = self._elapsed()
            time_bonus = max(0, 2000 - elapsed * 2)
            self.score += time_bonus
            self.new_best = self.score > self.best
            if self.new_best:
                self.best = self.score
                self._save_state()
            self._record_score("standard", self.score)

        self._start_win_animation()

    def _start_win_animation(self):
        self.anim_running = True
        self._unbind_game_handlers()
        self.canvas.bind("<Button-1>", lambda e: self.new_game())
        self.root.bind("<Key>", lambda e: self.new_game())

        # snapshot foundation piles to launch from, then clear the board
        self._fall_piles = [list(p) for p in self.foundations]
        self._launch_idx = -1
        self.fallers = []
        self.anim_frames = 0
        self.canvas.delete("all")
        self._animate()

    def _launch_next_faller(self):
        for _ in range(4):
            self._launch_idx = (self._launch_idx + 1) % 4
            pile = self._fall_piles[self._launch_idx]
            if pile:
                card = pile.pop()
                fx = col_x(3 + self._launch_idx)
                vx = random.choice([-1, 1]) * random.uniform(3.0, 7.0)
                self.fallers.append({
                    "card": card, "x": float(fx), "y": float(TOP_Y),
                    "vx": vx, "vy": random.uniform(-3.0, 1.0),
                })
                return

    def _piles_remaining(self):
        return any(self._fall_piles)

    def _animate(self):
        if not self.anim_running:
            return
        self.anim_frames += 1

        # launch a new card periodically until the foundations are empty
        if self.anim_frames % 4 == 1 and self._piles_remaining():
            self._launch_next_faller()

        alive = []
        for f in self.fallers:
            f["vy"] += GRAVITY
            f["x"] += f["vx"]
            f["y"] += f["vy"]
            floor = self.H - CARD_H
            if f["y"] >= floor:
                f["y"] = floor
                f["vy"] = -f["vy"] * BOUNCE_DAMPING
            # draw at new position — trails are intentional (no delete)
            self._draw_card(f["card"], int(f["x"]), int(f["y"]))
            if -CARD_W < f["x"] < self.W:
                alive.append(f)
        self.fallers = alive

        self._draw_win_banner()

        still_going = (self._piles_remaining() or self.fallers)
        if still_going and self.anim_frames < 1400:
            self._anim_job = self.root.after(30, self._animate)
        else:
            self._draw_win_banner()  # leave it up; click starts a new game

    def _draw_win_banner(self):
        self.canvas.delete("banner")
        cx, cy = self.W / 2, self.H / 2 - 30
        w, h = 520, 190
        self._rounded_rect(cx - w / 2, cy - h / 2, w, h, r=18,
                           fill="#10331d", outline=HIGHLIGHT, width=3,
                           tags="banner")
        self.canvas.create_text(cx, cy - 45, text=f"Lojë e mirë, {self.player_name}!",
                                fill=HIGHLIGHT, font=("Helvetica", 30, "bold"),
                                tags="banner")
        if self.vegas:
            subtitle = f"Kjo dorë: {self._money(self.hand)}   " \
                       f"Banka: {self._money(self.state.get('bankroll', 0))}"
        else:
            subtitle = f"Pikët {self.score}"
            if self.new_best:
                subtitle += "   \u2605 Rekord i ri!"
            else:
                subtitle += f"    (Rekordi {self.best})"
        self.canvas.create_text(cx, cy + 5, text=subtitle, fill="#ffffff",
                                font=("Helvetica", 16), tags="banner")
        secs = self._elapsed()
        self.canvas.create_text(cx, cy + 35,
                                text=f"Përfundoi për {secs // 60}:{secs % 60:02d}",
                                fill="#cfe8d4", font=("Helvetica", 12),
                                tags="banner")
        self.canvas.create_text(cx, cy + 68, text="Kliko kudo për një lojë të re",
                                fill="#9ccbaa", font=("Helvetica", 12, "italic"),
                                tags="banner")


def main():
    root = tk.Tk()
    Solitaire(root)
    root.mainloop()


if __name__ == "__main__":
    main()
