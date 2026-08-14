"""
SELF TRACKER — Productivity, Time-Saver & Schedule Optimizer
================================================================
A single-file, stdlib-only Python app built for Pydroid 3 (Android).

IMPORTANT: This version uses PLAIN tkinter only — NO ttk widgets.
  On some Android/Pydroid 3 builds, ttk (Notebook, Style, Combobox)
  crashes the native Tcl/Tk layer instantly, before Python's own
  try/except can even catch it — which looks like the app just
  "bouncing back" to the code screen with zero error message.
  Plain tk widgets (Button, Frame, Label, OptionMenu, Listbox) avoid
  that layer entirely and are rock solid on Pydroid 3.

FEATURES
  1. Task & Schedule Manager   — add tasks with a category + planned slot
  2. Live Session Timer        — Start/Stop, logs real duration to SQLite
  3. Reward System             — points, levels, streaks, badges
  4. Analytics Dashboard       — hand-drawn Canvas bar charts
  5. Schedule Optimizer        — mines your history for your most
                                  productive hours of day

HOW TO RUN ON PYDROID 3
  Paste this file into Pydroid 3 and press ▶. That's it — no pip
  installs needed. A database file `self_tracker.db` is created
  automatically the first time you run it.

Author: you. License: MIT. Publish freely on GitHub.
"""

import sqlite3
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta
import os
import sys
import traceback


def _resolve_db_path():
    """Pick a writable folder for the database. Falls back gracefully
    if the script's own folder isn't writable (common on Android)."""
    candidates = []
    try:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass
    candidates.append(os.getcwd())
    candidates.append(os.path.expanduser("~"))
    candidates.append("/storage/emulated/0")

    for folder in candidates:
        try:
            test_path = os.path.join(folder, ".write_test_tmp")
            with open(test_path, "w") as f:
                f.write("ok")
            os.remove(test_path)
            return os.path.join(folder, "self_tracker.db")
        except Exception:
            continue
    return ":memory:"


DB_PATH = _resolve_db_path()

# ----------------------------------------------------------------------
# DATABASE LAYER
# ----------------------------------------------------------------------

class DB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            planned_start TEXT,
            planned_minutes INTEGER,
            created_at TEXT NOT NULL,
            done INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            category TEXT NOT NULL,
            start_ts TEXT NOT NULL,
            end_ts TEXT NOT NULL,
            duration_min REAL NOT NULL,
            date TEXT NOT NULL,
            hour INTEGER NOT NULL,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS rewards(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            points INTEGER NOT NULL,
            reason TEXT NOT NULL,
            date TEXT NOT NULL
        )""")
        self.conn.commit()

    def add_task(self, name, category, planned_start, planned_minutes):
        self.conn.execute(
            "INSERT INTO tasks(name,category,planned_start,planned_minutes,created_at) VALUES(?,?,?,?,?)",
            (name, category, planned_start, planned_minutes, datetime.now().isoformat())
        )
        self.conn.commit()

    def list_tasks(self, include_done=True):
        q = "SELECT id,name,category,planned_start,planned_minutes,done FROM tasks"
        if not include_done:
            q += " WHERE done=0"
        q += " ORDER BY done ASC, id DESC"
        return self.conn.execute(q).fetchall()

    def mark_done(self, task_id):
        self.conn.execute("UPDATE tasks SET done=1 WHERE id=?", (task_id,))
        self.conn.commit()

    def delete_task(self, task_id):
        self.conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        self.conn.commit()

    def log_session(self, task_id, category, start_dt, end_dt):
        duration = (end_dt - start_dt).total_seconds() / 60.0
        self.conn.execute(
            "INSERT INTO sessions(task_id,category,start_ts,end_ts,duration_min,date,hour) VALUES(?,?,?,?,?,?,?)",
            (task_id, category, start_dt.isoformat(), end_dt.isoformat(),
             round(duration, 2), start_dt.strftime("%Y-%m-%d"), start_dt.hour)
        )
        self.conn.commit()
        return duration

    def sessions_last_n_days(self, n=7):
        since = (datetime.now() - timedelta(days=n - 1)).strftime("%Y-%m-%d")
        return self.conn.execute(
            "SELECT date,duration_min FROM sessions WHERE date>=? ORDER BY date", (since,)
        ).fetchall()

    def minutes_by_category(self, n=30):
        since = (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")
        return self.conn.execute(
            "SELECT category, SUM(duration_min) FROM sessions WHERE date>=? GROUP BY category ORDER BY 2 DESC",
            (since,)
        ).fetchall()

    def minutes_by_hour(self, n=30):
        since = (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")
        return self.conn.execute(
            "SELECT hour, SUM(duration_min), COUNT(*) FROM sessions WHERE date>=? GROUP BY hour ORDER BY 2 DESC",
            (since,)
        ).fetchall()

    def total_minutes(self):
        r = self.conn.execute("SELECT SUM(duration_min) FROM sessions").fetchone()[0]
        return r or 0

    def distinct_active_days(self):
        rows = self.conn.execute("SELECT DISTINCT date FROM sessions ORDER BY date DESC").fetchall()
        return [r[0] for r in rows]

    def add_points(self, points, reason):
        self.conn.execute(
            "INSERT INTO rewards(points,reason,date) VALUES(?,?,?)",
            (points, reason, datetime.now().isoformat())
        )
        self.conn.commit()

    def total_points(self):
        r = self.conn.execute("SELECT SUM(points) FROM rewards").fetchone()[0]
        return r or 0

    def recent_rewards(self, limit=8):
        return self.conn.execute(
            "SELECT points,reason,date FROM rewards ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


# ----------------------------------------------------------------------
# REWARD / STREAK ENGINE
# ----------------------------------------------------------------------

LEVEL_STEP = 500

def compute_level(points):
    level = points // LEVEL_STEP + 1
    into_level = points % LEVEL_STEP
    return int(level), int(into_level), LEVEL_STEP

def compute_streak(active_days):
    if not active_days:
        return 0
    days = set(active_days)
    streak = 0
    cursor = datetime.now().date()
    if cursor.strftime("%Y-%m-%d") not in days:
        cursor = cursor - timedelta(days=1)
    while cursor.strftime("%Y-%m-%d") in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak

def badges_for(points, streak, total_minutes):
    b = []
    if total_minutes >= 60: b.append("First Hour")
    if total_minutes >= 600: b.append("10-Hour Club")
    if total_minutes >= 3000: b.append("50-Hour Grinder")
    if streak >= 3: b.append("3-Day Streak")
    if streak >= 7: b.append("7-Day Streak")
    if streak >= 30: b.append("30-Day Streak")
    if points >= 1000: b.append("1000-Point Club")
    return b or ["Start a session to earn your first badge!"]


# ----------------------------------------------------------------------
# MAIN APP — plain tkinter only, no ttk
# ----------------------------------------------------------------------

BG = "#101418"
FG = "#e8eef2"
PANEL = "#1b2126"
ACCENT = "#00d0a4"
ACCENT2 = "#ff9f43"

class SelfTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Self Tracker")
        self.geometry("420x700")
        self.configure(bg=BG)

        self.db = DB()
        self.active_task = None
        self.session_start = None
        self.timer_job = None

        self._build_tabs()
        self.refresh_all()

    # ---------------- custom tab bar (replaces ttk.Notebook) ----------------
    def _build_tabs(self):
        bar = tk.Frame(self, bg=PANEL)
        bar.pack(fill="x")

        self.tab_names = ["Home", "Tasks", "Timer", "Stats", "Optimizer"]
        self.tab_buttons = {}
        self.tab_frames = {}
        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True)

        for name in self.tab_names:
            btn = tk.Button(bar, text=name, bg=PANEL, fg=FG, relief="flat",
                             font=("Roboto", 10, "bold"),
                             command=lambda n=name: self.show_tab(n))
            btn.pack(side="left", fill="x", expand=True, ipady=8)
            self.tab_buttons[name] = btn

            frame = tk.Frame(container, bg=BG)
            self.tab_frames[name] = frame

        self._build_home(self.tab_frames["Home"])
        self._build_tasks(self.tab_frames["Tasks"])
        self._build_timer(self.tab_frames["Timer"])
        self._build_stats(self.tab_frames["Stats"])
        self._build_optimizer(self.tab_frames["Optimizer"])

        self.show_tab("Home")

    def show_tab(self, name):
        for n, f in self.tab_frames.items():
            f.pack_forget()
            self.tab_buttons[n].config(bg=PANEL, fg=FG)
        self.tab_frames[name].pack(fill="both", expand=True)
        self.tab_buttons[name].config(bg=ACCENT, fg="#0a0a0a")
        if name == "Stats":
            self.refresh_stats()

    # ---------------- HOME ----------------
    def _build_home(self, root):
        tk.Label(root, text="Your Progress", bg=BG, fg=ACCENT,
                 font=("Roboto", 16, "bold")).pack(pady=(16, 4))
        self.lbl_points = tk.Label(root, text="Points: 0", bg=BG, fg=FG)
        self.lbl_points.pack(pady=2)
        self.lbl_level = tk.Label(root, text="Level 1", bg=BG, fg=FG)
        self.lbl_level.pack(pady=2)
        self.level_bar = tk.Canvas(root, width=340, height=18, bg=PANEL, highlightthickness=0)
        self.level_bar.pack(pady=6)
        self.lbl_streak = tk.Label(root, text="Streak: 0 days", bg=BG, fg=FG)
        self.lbl_streak.pack(pady=2)
        self.lbl_total = tk.Label(root, text="Total tracked: 0 min", bg=BG, fg=FG)
        self.lbl_total.pack(pady=2)

        tk.Label(root, text="Badges", bg=BG, fg=ACCENT,
                 font=("Roboto", 14, "bold")).pack(pady=(20, 4))
        self.badges_box = tk.Text(root, width=40, height=6, bg=PANEL, fg=FG,
                                   relief="flat", wrap="word")
        self.badges_box.pack(pady=4)
        self.badges_box.configure(state="disabled")

        tk.Label(root, text="Recent Rewards", bg=BG, fg=ACCENT,
                 font=("Roboto", 14, "bold")).pack(pady=(20, 4))
        self.rewards_box = tk.Text(root, width=40, height=6, bg=PANEL, fg=FG,
                                    relief="flat", wrap="word")
        self.rewards_box.pack(pady=4)
        self.rewards_box.configure(state="disabled")

    # ---------------- TASKS ----------------
    def _build_tasks(self, root):
        form = tk.Frame(root, bg=BG); form.pack(fill="x", padx=12, pady=10)

        tk.Label(form, text="Task name", bg=BG, fg=FG).pack(anchor="w")
        self.e_name = tk.Entry(form, bg=PANEL, fg=FG, insertbackground=FG)
        self.e_name.pack(fill="x")

        tk.Label(form, text="Category (e.g. GATE-DA, Project, Revision)", bg=BG, fg=FG).pack(anchor="w", pady=(8, 0))
        self.e_cat = tk.Entry(form, bg=PANEL, fg=FG, insertbackground=FG)
        self.e_cat.pack(fill="x")

        tk.Label(form, text="Planned time (HH:MM, 24h) — optional", bg=BG, fg=FG).pack(anchor="w", pady=(8, 0))
        self.e_time = tk.Entry(form, bg=PANEL, fg=FG, insertbackground=FG)
        self.e_time.pack(fill="x")

        tk.Label(form, text="Planned duration (minutes)", bg=BG, fg=FG).pack(anchor="w", pady=(8, 0))
        self.e_dur = tk.Entry(form, bg=PANEL, fg=FG, insertbackground=FG)
        self.e_dur.pack(fill="x")

        tk.Button(form, text="+ Add Task", bg=ACCENT, fg="#0a0a0a",
                  font=("Roboto", 11, "bold"), command=self.add_task).pack(fill="x", pady=10)

        list_frame = tk.Frame(root, bg=BG); list_frame.pack(fill="both", expand=True, padx=12)
        self.task_listbox = tk.Listbox(list_frame, bg=PANEL, fg=FG,
                                        selectbackground=ACCENT, font=("Roboto", 10),
                                        activestyle="none")
        self.task_listbox.pack(fill="both", expand=True, side="left")
        sb = tk.Scrollbar(list_frame, command=self.task_listbox.yview)
        sb.pack(side="right", fill="y")
        self.task_listbox.config(yscrollcommand=sb.set)

        btns = tk.Frame(root, bg=BG); btns.pack(fill="x", padx=12, pady=8)
        tk.Button(btns, text="Mark Done", bg=PANEL, fg=FG,
                  command=self.complete_task).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(btns, text="Delete", bg=PANEL, fg=FG,
                  command=self.remove_task).pack(side="left", expand=True, fill="x", padx=2)

    def add_task(self):
        name = self.e_name.get().strip()
        cat = self.e_cat.get().strip() or "General"
        time_str = self.e_time.get().strip()
        try:
            dur = int(self.e_dur.get().strip()) if self.e_dur.get().strip() else None
        except ValueError:
            messagebox.showerror("Invalid", "Duration must be a number of minutes.")
            return
        if not name:
            messagebox.showerror("Invalid", "Task name is required.")
            return
        self.db.add_task(name, cat, time_str, dur)
        self.e_name.delete(0, "end"); self.e_cat.delete(0, "end")
        self.e_time.delete(0, "end"); self.e_dur.delete(0, "end")
        self.refresh_tasks()
        self.refresh_timer_dropdown()

    def _selected_task_id(self):
        sel = self.task_listbox.curselection()
        if not sel:
            return None
        return self._task_ids[sel[0]]

    def complete_task(self):
        tid = self._selected_task_id()
        if tid is None:
            return
        self.db.mark_done(tid)
        self.db.add_points(20, "Completed a scheduled task")
        self.refresh_all()

    def remove_task(self):
        tid = self._selected_task_id()
        if tid is None:
            return
        self.db.delete_task(tid)
        self.refresh_tasks()
        self.refresh_timer_dropdown()

    def refresh_tasks(self):
        self.task_listbox.delete(0, "end")
        self._task_ids = []
        for row in self.db.list_tasks():
            tid, name, cat, ptime, pdur, done = row
            mark = "[x]" if done else "[ ]"
            label = f"{mark} [{cat}] {name}"
            if ptime:
                label += f"  @ {ptime}"
            if pdur:
                label += f"  ({pdur}m)"
            self.task_listbox.insert("end", label)
            self._task_ids.append(tid)

    # ---------------- TIMER ----------------
    def _build_timer(self, root):
        tk.Label(root, text="Live Session", bg=BG, fg=ACCENT,
                 font=("Roboto", 16, "bold")).pack(pady=(16, 8))
        tk.Label(root, text="Attach to task (optional):", bg=BG, fg=FG).pack(anchor="w", padx=12)

        self.timer_task_var = tk.StringVar(self)
        self.timer_task_var.set("(none)")
        self.timer_dropdown = tk.OptionMenu(root, self.timer_task_var, "(none)")
        self.timer_dropdown.config(bg=PANEL, fg=FG, highlightthickness=0)
        self.timer_dropdown.pack(fill="x", padx=12, pady=4)

        tk.Label(root, text="Or type a free category:", bg=BG, fg=FG).pack(anchor="w", padx=12, pady=(8, 0))
        self.e_free_cat = tk.Entry(root, bg=PANEL, fg=FG, insertbackground=FG)
        self.e_free_cat.pack(fill="x", padx=12)

        self.lbl_clock = tk.Label(root, text="00:00:00", font=("Roboto", 40, "bold"),
                                   bg=BG, fg=ACCENT)
        self.lbl_clock.pack(pady=30)

        btnrow = tk.Frame(root, bg=BG); btnrow.pack()
        self.btn_start = tk.Button(btnrow, text="Start", bg=ACCENT, fg="#0a0a0a",
                                    font=("Roboto", 11, "bold"), command=self.start_session)
        self.btn_start.pack(side="left", padx=6)
        self.btn_stop = tk.Button(btnrow, text="Stop & Save", bg=PANEL, fg=FG,
                                   font=("Roboto", 11, "bold"), state="disabled",
                                   command=self.stop_session)
        self.btn_stop.pack(side="left", padx=6)

        self.lbl_timer_status = tk.Label(root, text="No active session", bg=BG, fg=FG)
        self.lbl_timer_status.pack(pady=10)

    def refresh_timer_dropdown(self):
        tasks = self.db.list_tasks(include_done=False)
        self._timer_task_map = {f"[{c}] {n}": (tid, c) for tid, n, c, *_ in tasks}
        menu = self.timer_dropdown["menu"]
        menu.delete(0, "end")
        menu.add_command(label="(none)", command=lambda: self.timer_task_var.set("(none)"))
        for label in self._timer_task_map:
            menu.add_command(label=label, command=lambda l=label: self.timer_task_var.set(l))
        if self.timer_task_var.get() not in self._timer_task_map and self.timer_task_var.get() != "(none)":
            self.timer_task_var.set("(none)")

    def start_session(self):
        if self.session_start is not None:
            return
        chosen = self.timer_task_var.get()
        free_cat = self.e_free_cat.get().strip()
        if chosen in getattr(self, "_timer_task_map", {}):
            tid, cat = self._timer_task_map[chosen]
        elif free_cat:
            tid, cat = None, free_cat
        else:
            tid, cat = None, "General"
        self.active_task = (tid, cat)
        self.session_start = datetime.now()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal", bg=ACCENT2)
        self.lbl_timer_status.config(text=f"Tracking: {cat}")
        self._tick()

    def _tick(self):
        if self.session_start is None:
            return
        elapsed = datetime.now() - self.session_start
        total_s = int(elapsed.total_seconds())
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        self.lbl_clock.config(text=f"{h:02d}:{m:02d}:{s:02d}")
        self.timer_job = self.after(1000, self._tick)

    def stop_session(self):
        if self.session_start is None:
            return
        end = datetime.now()
        tid, cat = self.active_task
        duration = self.db.log_session(tid, cat, self.session_start, end)
        if self.timer_job:
            self.after_cancel(self.timer_job)
            self.timer_job = None
        self.session_start = None
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled", bg=PANEL)
        self.lbl_clock.config(text="00:00:00")

        pts = max(1, round(duration))
        bonus = 15 if duration >= 25 else 0
        self.db.add_points(pts + bonus, f"{round(duration)} min on {cat}")
        msg = f"Saved {round(duration)} min on '{cat}'. +{pts} pts"
        if bonus:
            msg += f" (+{bonus} deep-work bonus!)"
        self.lbl_timer_status.config(text=msg)
        self.refresh_all()

    # ---------------- ANALYTICS ----------------
    def _build_stats(self, root):
        tk.Label(root, text="Last 7 Days (minutes/day)", bg=BG, fg=ACCENT,
                 font=("Roboto", 14, "bold")).pack(pady=(12, 2))
        self.chart7 = tk.Canvas(root, width=380, height=180, bg=PANEL, highlightthickness=0)
        self.chart7.pack(pady=6)

        tk.Label(root, text="Time by Category (last 30 days)", bg=BG, fg=ACCENT,
                 font=("Roboto", 14, "bold")).pack(pady=(16, 2))
        self.chart_cat = tk.Canvas(root, width=380, height=200, bg=PANEL, highlightthickness=0)
        self.chart_cat.pack(pady=6)

        tk.Button(root, text="Refresh Charts", bg=PANEL, fg=FG,
                  command=self.refresh_stats).pack(pady=10)

    def draw_bar_chart(self, canvas, labels, values, color):
        canvas.delete("all")
        w = int(canvas["width"]); h = int(canvas["height"])
        pad = 30
        if not values or max(values) == 0:
            canvas.create_text(w // 2, h // 2, text="No data yet - start a session!", fill="#7a8791")
            return
        max_v = max(values)
        n = len(values)
        bar_w = (w - 2 * pad) / max(n, 1)
        for i, (lab, val) in enumerate(zip(labels, values)):
            bar_h = (val / max_v) * (h - 2 * pad) if max_v else 0
            x0 = pad + i * bar_w + 4
            x1 = pad + (i + 1) * bar_w - 4
            y1 = h - pad
            y0 = y1 - bar_h
            canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
            canvas.create_text((x0 + x1) / 2, y1 + 12, text=str(lab)[:8], fill="#c7d1d9", font=("Roboto", 8))
            canvas.create_text((x0 + x1) / 2, y0 - 8, text=f"{val:.0f}", fill=FG, font=("Roboto", 8))

    def refresh_stats(self):
        rows = self.db.sessions_last_n_days(7)
        by_day = {}
        for date, dur in rows:
            by_day[date] = by_day.get(date, 0) + dur
        days = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
        labels = [d[5:] for d in days]
        values = [round(by_day.get(d, 0), 1) for d in days]
        self.draw_bar_chart(self.chart7, labels, values, ACCENT)

        cats = self.db.minutes_by_category(30)
        clabels = [c[0] for c in cats][:6]
        cvalues = [round(c[1], 1) for c in cats][:6]
        self.draw_bar_chart(self.chart_cat, clabels, cvalues, ACCENT2)

    # ---------------- OPTIMIZER ----------------
    def _build_optimizer(self, root):
        tk.Label(root, text="Where's Your Peak Focus Time?", bg=BG, fg=ACCENT,
                 font=("Roboto", 16, "bold")).pack(pady=(16, 6))
        tk.Label(root, text="Mined from your own logged sessions (last 30 days).",
                 bg=BG, fg=FG, wraplength=340, justify="left").pack(padx=12, pady=(0, 10))
        self.opt_box = tk.Text(root, width=42, height=14, bg=PANEL, fg=FG,
                                relief="flat", wrap="word")
        self.opt_box.pack(padx=12, pady=6)
        self.opt_box.configure(state="disabled")
        tk.Button(root, text="Analyze & Suggest Schedule", bg=ACCENT, fg="#0a0a0a",
                  font=("Roboto", 11, "bold"), command=self.run_optimizer).pack(pady=10)

    def run_optimizer(self):
        rows = self.db.minutes_by_hour(30)
        self.opt_box.configure(state="normal")
        self.opt_box.delete("1.0", "end")
        if not rows:
            self.opt_box.insert("end", "Not enough data yet.\n\nLog at least a few timer "
                                        "sessions across different times of day, then come "
                                        "back - the optimizer needs history to find your "
                                        "patterns.")
            self.opt_box.configure(state="disabled")
            return

        scored = []
        for hour, total, count in rows:
            avg = total / count if count else 0
            scored.append((hour, total, count, avg))
        scored.sort(key=lambda r: r[3], reverse=True)

        top = scored[:3]
        self.opt_box.insert("end", "Your top focus windows:\n\n")
        for hour, total, count, avg in top:
            slot = f"{hour:02d}:00-{(hour+1)%24:02d}:00"
            self.opt_box.insert("end", f"  - {slot}  -  avg {avg:.0f} min/session "
                                        f"({count} sessions logged)\n")

        weakest = sorted(scored, key=lambda r: r[3])[:2]
        self.opt_box.insert("end", "\nWeaker windows (short sessions / distractions):\n\n")
        for hour, total, count, avg in weakest:
            slot = f"{hour:02d}:00-{(hour+1)%24:02d}:00"
            self.opt_box.insert("end", f"  - {slot}  -  avg {avg:.0f} min/session\n")

        self.opt_box.insert("end", "\nSuggestion: schedule your hardest / highest-priority "
                                    "tasks (e.g. GATE DA problem-solving) inside your top "
                                    "focus windows, and reserve weaker windows for light "
                                    "review, admin, or breaks.")
        self.opt_box.configure(state="disabled")

    # ---------------- GLOBAL REFRESH ----------------
    def refresh_all(self):
        self.refresh_tasks()
        self.refresh_timer_dropdown()
        self.refresh_dash()

    def refresh_dash(self):
        points = self.db.total_points()
        level, into_level, step = compute_level(points)
        streak = compute_streak(self.db.distinct_active_days())
        total_min = self.db.total_minutes()

        self.lbl_points.config(text=f"Points: {points}")
        self.lbl_level.config(text=f"Level {level}  ({into_level}/{step} to next)")
        self.lbl_streak.config(text=f"Streak: {streak} day{'s' if streak != 1 else ''}")
        self.lbl_total.config(text=f"Total tracked: {total_min:.0f} min ({total_min/60:.1f} h)")

        self.level_bar.delete("all")
        frac = into_level / step
        self.level_bar.create_rectangle(0, 0, 340, 18, fill=PANEL, outline="")
        self.level_bar.create_rectangle(0, 0, 340 * frac, 18, fill=ACCENT, outline="")

        self.badges_box.configure(state="normal")
        self.badges_box.delete("1.0", "end")
        for b in badges_for(points, streak, total_min):
            self.badges_box.insert("end", f"{b}\n")
        self.badges_box.configure(state="disabled")

        self.rewards_box.configure(state="normal")
        self.rewards_box.delete("1.0", "end")
        for pts, reason, date in self.db.recent_rewards():
            ts = date[:16].replace("T", " ")
            self.rewards_box.insert("end", f"+{pts}  {reason}  ({ts})\n")
        self.rewards_box.configure(state="disabled")


def _write_crash_log(exc_text):
    for folder in (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd(),
                   os.getcwd(), os.path.expanduser("~")):
        try:
            path = os.path.join(folder, "self_tracker_crash_log.txt")
            with open(path, "w") as f:
                f.write(exc_text)
            return path
        except Exception:
            continue
    return None


if __name__ == "__main__":
    try:
        app = SelfTrackerApp()
        app.mainloop()
    except Exception:
        err_text = traceback.format_exc()
        log_path = _write_crash_log(err_text)
        try:
            err_root = tk.Tk()
            err_root.title("Self Tracker crashed")
            err_root.geometry("380x400")
            tk.Label(err_root, text="The app hit an error on startup:",
                     font=("Roboto", 12, "bold")).pack(pady=(10, 4))
            box = tk.Text(err_root, wrap="word")
            box.insert("1.0", err_text)
            if log_path:
                box.insert("end", f"\n\n(Also saved to: {log_path})")
            box.pack(fill="both", expand=True, padx=8, pady=8)
            err_root.mainloop()
        except Exception:
            print("SELF TRACKER CRASHED:\n" + err_text)
            sys.exit(1)
