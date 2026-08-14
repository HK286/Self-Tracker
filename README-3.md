# Self Tracker 🎯
A self-tracking productivity app — timer, analytics, rewards, and a schedule optimizer that learns your peak focus hours from your own data.

Built to run **entirely on-device**, no cloud, no accounts, no external dependencies — just Python's standard library. Designed and tested for **Pydroid 3 / QPython 3L on Android**, but runs anywhere Python 3 + tkinter is available (Windows, macOS, Linux too).

## ✨ Features

- **📋 Task & Schedule Manager** — log tasks with a category and a planned time slot
- **⏱ Live Session Timer** — start/stop tracking, every session is saved to a local SQLite database
- **🏆 Reward System** — earn points per minute tracked, deep-work bonuses for 25+ minute sessions, level progression, streaks, and unlockable badges
- **📊 Analytics Dashboard** — hand-drawn bar charts (no matplotlib needed) showing your last 7 days and time-by-category breakdown
- **🧭 Schedule Optimizer** — mines your own session history to find which hours of the day you actually focus best in, and suggests where to slot your hardest tasks

## 🖼 Screenshots
> _Add screenshots here after your first run — drag images into this section on GitHub, e.g._
> `![Home tab](screenshots/home.png)`

## 🚀 Getting Started

### On Android (Pydroid 3 / QPython 3L)
1. Install [Pydroid 3](https://play.google.com/store/apps/details?id=ru.iiec.pydroid3) from the Play Store (or QPython 3L as an alternative)
2. Download `self_tracker.py` from this repo
3. Open it in the app and press ▶ — no pip installs required, it's stdlib-only
4. A `self_tracker.db` file is created automatically on first run to store your data

### On Desktop (Windows / macOS / Linux)
```bash
git clone https://github.com/<your-username>/self-tracker.git
cd self-tracker
python3 self_tracker.py
```
Requires Python 3.7+. Tkinter ships with most Python installs; on Linux you may need `sudo apt install python3-tk`.

## 🗂 How it works

| Tab | Purpose |
|---|---|
| **Home** | Points, level progress, streak, badges, reward log |
| **Tasks** | Add/complete/delete tasks with category + planned time |
| **Timer** | Start/stop a live session, optionally attached to a task |
| **Stats** | 7-day trend + category breakdown, drawn on a plain `tk.Canvas` |
| **Optimizer** | Ranks your hours of day by average session length to surface your real peak-focus windows |

All data lives in a single local SQLite file (`self_tracker.db`) next to the script — easy to back up, inspect with any SQLite browser, or wipe by deleting the file.

## ⚙️ Design notes

- **Plain `tkinter` only — no `ttk`.** Themed widgets (`ttk.Notebook`, `ttk.Style`, `ttk.Combobox`) can crash at the native Tcl/Tk layer on some Android Python IDEs before Python's own error handling can catch it. This app uses a hand-rolled tab bar and plain widgets instead for maximum compatibility.
- **No external dependencies.** Charts are drawn manually on `tk.Canvas` rather than using `matplotlib`, so there's nothing to `pip install`.
- **Crash-safe startup.** If something does go wrong on launch, the app writes a full traceback to `self_tracker_crash_log.txt` and shows it in a popup, instead of failing silently.

## 🗺 Roadmap ideas
- [ ] Export session history to CSV
- [ ] Weekly summary notifications
- [ ] Customizable point/level formulas
- [ ] Dark/light theme toggle

## 📄 License
MIT — see [LICENSE](LICENSE).

## 🙌 Contributing
Issues and PRs welcome. This is a personal productivity tool shared in case it's useful to others studying, working, or building their own habit-tracking system.
