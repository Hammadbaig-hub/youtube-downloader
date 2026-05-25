"""
gui.py — Tkinter desktop GUI for YouTube Downloader.

Runs the download in a background thread and communicates progress back to
the main thread through a queue, so the UI stays responsive at all times.

Launch with:  python gui.py
"""

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from downloader import DOWNLOAD_DIR, QUALITY_OPTIONS, VideoDownloader

# ── Window constants ──────────────────────────────────────────────────────────
TITLE       = "YouTube Downloader"
WIN_WIDTH   = 600
PAD         = 14          # outer padding
INNER_PAD   = 10          # LabelFrame inner padding
POLL_MS     = 100         # queue poll interval


class App(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title(TITLE)
        self.resizable(True, False)
        self.minsize(WIN_WIDTH, 0)
        self.configure(padx=PAD, pady=PAD)

        self._apply_theme()

        # ── State ────────────────────────────────────────────────────────────
        self._queue:         queue.Queue      = queue.Queue()
        self._cancel_event:  threading.Event  = threading.Event()
        self._dl_thread:     threading.Thread | None = None

        # ── Tk variables ─────────────────────────────────────────────────────
        self._url_var      = tk.StringVar()
        self._quality_var  = tk.StringVar()
        self._folder_var   = tk.StringVar(value=str(DOWNLOAD_DIR.resolve()))
        self._playlist_var = tk.BooleanVar(value=False)
        self._title_var    = tk.StringVar(value="Ready.")
        self._stats_var    = tk.StringVar(value="")

        self._build_ui()
        self._poll()           # kick off the queue-polling loop

    # ─────────────────────────────────────────────────────────────────────────
    # Theme / style
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_theme(self) -> None:
        style = ttk.Style(self)
        # Prefer platform-native themes for a polished look
        for candidate in ("vista", "winnative", "aqua", "clam", "alt"):
            if candidate in style.theme_names():
                style.theme_use(candidate)
                break

        style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))
        style.configure("TLabelframe.Label", font=("Segoe UI", 9, "bold"))

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_settings()
        self._build_progress()
        self._build_buttons()

    def _build_settings(self) -> None:
        frame = ttk.LabelFrame(self, text=" Settings ", padding=INNER_PAD)
        frame.pack(fill="x", pady=(0, PAD))
        frame.columnconfigure(1, weight=1)

        lbl_opts = {"sticky": "w", "padx": (0, 10), "pady": 4}
        row = 0

        # ── URL ──────────────────────────────────────────────────────────────
        ttk.Label(frame, text="YouTube URL").grid(row=row, column=0, **lbl_opts)
        url_row = ttk.Frame(frame)
        url_row.grid(row=row, column=1, sticky="ew", pady=4)
        url_row.columnconfigure(0, weight=1)

        self._url_entry = ttk.Entry(url_row, textvariable=self._url_var)
        self._url_entry.grid(row=0, column=0, sticky="ew")
        self._url_entry.bind("<Return>", lambda _: self._start_download())

        ttk.Button(url_row, text="Paste", width=7,
                   command=self._paste_url).grid(row=0, column=1, padx=(6, 0))
        row += 1

        # ── Quality ───────────────────────────────────────────────────────────
        ttk.Label(frame, text="Quality").grid(row=row, column=0, **lbl_opts)
        quality_names = [v["name"] for v in QUALITY_OPTIONS.values()]
        self._quality_cb = ttk.Combobox(
            frame, textvariable=self._quality_var,
            values=quality_names, state="readonly", width=36,
        )
        self._quality_cb.current(0)
        self._quality_cb.grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        # ── Playlist checkbox ─────────────────────────────────────────────────
        ttk.Label(frame, text="").grid(row=row, column=0)   # spacer
        ttk.Checkbutton(
            frame, text="Download full playlist (if URL is a playlist)",
            variable=self._playlist_var,
        ).grid(row=row, column=1, sticky="w", pady=(0, 4))
        row += 1

        # ── Save folder ───────────────────────────────────────────────────────
        ttk.Label(frame, text="Save to").grid(row=row, column=0, **lbl_opts)
        folder_row = ttk.Frame(frame)
        folder_row.grid(row=row, column=1, sticky="ew", pady=4)
        folder_row.columnconfigure(0, weight=1)

        ttk.Entry(folder_row, textvariable=self._folder_var,
                  state="readonly").grid(row=0, column=0, sticky="ew")
        ttk.Button(folder_row, text="Browse", width=7,
                   command=self._browse).grid(row=0, column=1, padx=(6, 0))

    def _build_progress(self) -> None:
        frame = ttk.LabelFrame(self, text=" Progress ", padding=INNER_PAD)
        frame.pack(fill="x", pady=(0, PAD))

        # Progress bar + percentage label on the same row
        bar_row = ttk.Frame(frame)
        bar_row.pack(fill="x")
        bar_row.columnconfigure(0, weight=1)

        self._bar = ttk.Progressbar(bar_row, mode="determinate", maximum=100)
        self._bar.grid(row=0, column=0, sticky="ew")

        self._pct_lbl = ttk.Label(bar_row, text="  0 %", width=7, anchor="e")
        self._pct_lbl.grid(row=0, column=1, padx=(8, 0))

        # Title / activity line
        ttk.Label(frame, textvariable=self._title_var,
                  foreground="#444444").pack(anchor="w", pady=(8, 2))

        # Speed / ETA / size line
        ttk.Label(frame, textvariable=self._stats_var,
                  foreground="#0078d4").pack(anchor="w")

    def _build_buttons(self) -> None:
        row = ttk.Frame(self)
        row.pack(pady=(4, 0))

        self._dl_btn = ttk.Button(
            row, text="  Download  ", style="Accent.TButton",
            command=self._start_download, width=16,
        )
        self._dl_btn.grid(row=0, column=0, padx=6)

        self._cancel_btn = ttk.Button(
            row, text="Cancel", command=self._cancel,
            width=10, state="disabled",
        )
        self._cancel_btn.grid(row=0, column=1, padx=6)

    # ─────────────────────────────────────────────────────────────────────────
    # User actions
    # ─────────────────────────────────────────────────────────────────────────

    def _paste_url(self) -> None:
        try:
            self._url_var.set(self.clipboard_get().strip())
            self._url_entry.icursor("end")
        except tk.TclError:
            pass

    def _browse(self) -> None:
        path = filedialog.askdirectory(
            initialdir=self._folder_var.get(),
            title="Choose download folder",
        )
        if path:
            self._folder_var.set(path)

    def _start_download(self) -> None:
        url = self._url_var.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Please paste or type a YouTube URL first.")
            return

        # Map combobox display name → quality key ("1"–"6")
        selected = self._quality_var.get()
        quality_key = next(k for k, v in QUALITY_OPTIONS.items() if v["name"] == selected)
        output_dir  = Path(self._folder_var.get())
        is_playlist = self._playlist_var.get()

        self._cancel_event.clear()
        self._set_state("downloading")
        self._reset_progress("Fetching video information…")

        self._dl_thread = threading.Thread(
            target=self._worker,
            args=(url, quality_key, output_dir, is_playlist),
            daemon=True,
        )
        self._dl_thread.start()

    def _cancel(self) -> None:
        self._cancel_event.set()
        self._cancel_btn.configure(state="disabled")
        self._title_var.set("Cancelling…")

    # ─────────────────────────────────────────────────────────────────────────
    # Background download worker  (runs on a daemon thread)
    # ─────────────────────────────────────────────────────────────────────────

    def _worker(
        self,
        url: str,
        quality_key: str,
        output_dir: Path,
        is_playlist: bool,
    ) -> None:
        dl = VideoDownloader()

        def hook(d: dict) -> None:
            # Raising inside a yt-dlp hook aborts the download cleanly.
            if self._cancel_event.is_set():
                raise Exception("Cancelled by user")

            status = d.get("status")

            if status == "downloading":
                self._queue.put({
                    "type":       "progress",
                    "downloaded": d.get("downloaded_bytes") or 0,
                    "total":      d.get("total_bytes") or d.get("total_bytes_estimate") or 0,
                    "speed":      d.get("speed") or 0,
                    "eta":        d.get("eta") or 0,
                    "title":      d.get("info_dict", {}).get("title", ""),
                })
            elif status == "finished":
                self._queue.put({"type": "processing"})

        try:
            saved = dl.download(
                url,
                quality_key,
                is_playlist=is_playlist,
                progress_callback=hook,
                output_dir=output_dir,
            )
            self._queue.put({"type": "done", "files": saved, "folder": str(output_dir)})

        except Exception as exc:
            if self._cancel_event.is_set():
                self._queue.put({"type": "cancelled"})
            else:
                self._queue.put({"type": "error", "message": str(exc)})

    # ─────────────────────────────────────────────────────────────────────────
    # Queue polling  (runs on the main/GUI thread via after())
    # ─────────────────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        try:
            while True:
                self._dispatch(self._queue.get_nowait())
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll)

    def _dispatch(self, msg: dict) -> None:
        kind = msg["type"]

        if kind == "progress":
            self._on_progress(msg)

        elif kind == "processing":
            self._title_var.set("Merging / converting with FFmpeg…")
            self._stats_var.set("Please wait — this may take a moment.")

        elif kind == "done":
            files  = msg.get("files", [])
            folder = msg.get("folder", "")
            self._bar.configure(mode="determinate", value=100)
            self._pct_lbl.configure(text=" 100 %")
            self._title_var.set(f"Done!  {len(files)} file(s) saved.")
            self._stats_var.set(folder)
            self._set_state("idle")
            self._show_done(files, folder)

        elif kind == "cancelled":
            self._reset_progress("Download cancelled.")
            self._set_state("idle")

        elif kind == "error":
            self._title_var.set("Error")
            self._stats_var.set("")
            self._set_state("idle")
            messagebox.showerror("Download Error", msg["message"])

    # ─────────────────────────────────────────────────────────────────────────
    # Progress display helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_progress(self, msg: dict) -> None:
        downloaded = msg["downloaded"]
        total      = msg["total"]
        speed      = msg["speed"]
        eta        = msg["eta"]
        title      = msg.get("title", "")

        # Progress bar
        if total:
            pct = min(downloaded / total * 100, 100)
            if self._bar["mode"] != "determinate":
                self._bar.configure(mode="determinate")
            self._bar.configure(value=pct)
            self._pct_lbl.configure(text=f"{pct:4.0f} %")
        else:
            # Unknown total — bounce the bar
            if self._bar["mode"] != "indeterminate":
                self._bar.configure(mode="indeterminate")
            self._bar.step(5)
            self._pct_lbl.configure(text="   … %")

        # Title line
        if title:
            short = (title[:62] + "…") if len(title) > 62 else title
            self._title_var.set(f'Downloading: "{short}"')

        # Stats line: speed / ETA / size
        speed_s = f"{speed / 1_048_576:.1f} MB/s"  if speed else "—"
        eta_s   = f"{eta // 60}:{eta % 60:02d}"     if eta   else "—"
        if total:
            size_s = f"{downloaded / 1_048_576:.1f} / {total / 1_048_576:.1f} MB"
        else:
            size_s = f"{downloaded / 1_048_576:.1f} MB downloaded"

        self._stats_var.set(f"Speed: {speed_s}   •   ETA: {eta_s}   •   {size_s}")

    def _show_done(self, files: list[str], folder: str) -> None:
        if not files:
            messagebox.showinfo(
                "Download Complete",
                f"Download finished.\nCheck your folder:\n{folder}",
            )
            return

        names  = "\n".join(f"  • {Path(f).name}" for f in files[:8])
        suffix = f"\n  … and {len(files) - 8} more" if len(files) > 8 else ""
        messagebox.showinfo(
            "Download Complete",
            f"Saved to:\n{folder}\n\n{names}{suffix}",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # State helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _set_state(self, state: str) -> None:
        if state == "downloading":
            self._dl_btn.configure(state="disabled")
            self._cancel_btn.configure(state="normal")
            self._url_entry.configure(state="disabled")
            self._quality_cb.configure(state="disabled")
        else:
            self._dl_btn.configure(state="normal")
            self._cancel_btn.configure(state="disabled")
            self._url_entry.configure(state="normal")
            self._quality_cb.configure(state="readonly")

    def _reset_progress(self, status: str = "Ready.") -> None:
        self._bar.configure(mode="determinate", value=0)
        self._pct_lbl.configure(text="  0 %")
        self._title_var.set(status)
        self._stats_var.set("")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
