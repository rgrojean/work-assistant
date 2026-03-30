#!/usr/bin/env python3
"""Simple Mac recording app with tkinter UI."""

import os
import threading
import time
from datetime import datetime, timedelta

import tkinter as tk
from tkinter import ttk

import numpy as np
import sounddevice as sd
import soundfile as sf


RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")
SAMPLE_RATE = 44100
CHANNELS = 1


class RecorderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Recording Studio")
        self.root.resizable(False, False)

        # State
        self.is_recording = False
        self.is_paused = False
        self.start_time = None
        self.paused_duration = timedelta()
        self.pause_start = None
        self.audio_chunks = []
        self.stream = None
        self.pulse_visible = True

        self._build_ui()
        self._update_timer()
        self._pulse_indicator()

    def _build_ui(self):
        self.root.configure(bg="#1e1e1e")
        main = tk.Frame(self.root, bg="#1e1e1e", padx=30, pady=20)
        main.pack(fill="both", expand=True)

        # --- Status indicator ---
        status_frame = tk.Frame(main, bg="#1e1e1e")
        status_frame.pack(pady=(0, 15))

        self.status_dot = tk.Canvas(
            status_frame, width=18, height=18, bg="#1e1e1e", highlightthickness=0
        )
        self.status_dot.pack(side="left", padx=(0, 8))
        self._draw_dot("#555555")

        self.status_label = tk.Label(
            status_frame,
            text="Off",
            font=("Helvetica Neue", 22, "bold"),
            fg="#aaaaaa",
            bg="#1e1e1e",
        )
        self.status_label.pack(side="left")

        # --- Timer ---
        self.timer_label = tk.Label(
            main,
            text="00:00:00",
            font=("SF Mono", 40),
            fg="#ffffff",
            bg="#1e1e1e",
        )
        self.timer_label.pack(pady=(0, 20))

        # --- Category radio buttons ---
        cat_frame = tk.Frame(main, bg="#1e1e1e")
        cat_frame.pack(pady=(0, 20))

        self.category = tk.StringVar(value="customer_call")
        categories = [
            ("Customer call", "customer_call"),
            ("Internal prep", "internal_prep"),
            ("1-1", "one_on_one"),
        ]
        for label, value in categories:
            rb = tk.Radiobutton(
                cat_frame,
                text=label,
                variable=self.category,
                value=value,
                font=("Helvetica Neue", 14),
                fg="#cccccc",
                bg="#1e1e1e",
                selectcolor="#333333",
                activebackground="#1e1e1e",
                activeforeground="#ffffff",
                highlightthickness=0,
            )
            rb.pack(anchor="w", pady=2)

        # --- Buttons ---
        btn_frame = tk.Frame(main, bg="#1e1e1e")
        btn_frame.pack(pady=(0, 5))

        btn_style = {
            "font": ("Helvetica Neue", 14, "bold"),
            "width": 10,
            "height": 1,
            "relief": "flat",
            "cursor": "hand2",
            "bd": 0,
        }

        self.start_btn = tk.Button(
            btn_frame,
            text="Start",
            command=self._on_start,
            bg="#e74c3c",
            fg="#ffffff",
            activebackground="#c0392b",
            activeforeground="#ffffff",
            **btn_style,
        )
        self.start_btn.pack(side="left", padx=5)

        self.pause_btn = tk.Button(
            btn_frame,
            text="Pause",
            command=self._on_pause,
            bg="#555555",
            fg="#999999",
            state="disabled",
            activebackground="#666666",
            activeforeground="#ffffff",
            **btn_style,
        )
        self.pause_btn.pack(side="left", padx=5)

        self.stop_btn = tk.Button(
            btn_frame,
            text="Stop",
            command=self._on_stop,
            bg="#555555",
            fg="#999999",
            state="disabled",
            activebackground="#666666",
            activeforeground="#ffffff",
            **btn_style,
        )
        self.stop_btn.pack(side="left", padx=5)

    def _draw_dot(self, color):
        self.status_dot.delete("all")
        self.status_dot.create_oval(2, 2, 16, 16, fill=color, outline=color)

    # --- Recording controls ---

    def _on_start(self):
        self.is_recording = True
        self.is_paused = False
        self.start_time = datetime.now()
        self.paused_duration = timedelta()
        self.pause_start = None
        self.audio_chunks = []

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=self._audio_callback,
        )
        self.stream.start()

        self.status_label.config(text="On Air", fg="#e74c3c")
        self.start_btn.config(state="disabled", bg="#555555", fg="#999999")
        self.pause_btn.config(state="normal", bg="#f39c12", fg="#ffffff")
        self.stop_btn.config(state="normal", bg="#e74c3c", fg="#ffffff")

    def _on_pause(self):
        if not self.is_recording:
            return

        if not self.is_paused:
            # Pause
            self.is_paused = True
            self.pause_start = datetime.now()
            self.status_label.config(text="Paused", fg="#f39c12")
            self.pause_btn.config(text="Resume")
        else:
            # Resume
            self.is_paused = False
            if self.pause_start:
                self.paused_duration += datetime.now() - self.pause_start
                self.pause_start = None
            self.status_label.config(text="On Air", fg="#e74c3c")
            self.pause_btn.config(text="Pause")

    def _on_stop(self):
        if not self.is_recording:
            return

        self.is_recording = False
        self.is_paused = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        # Capture data for background save
        chunks = self.audio_chunks
        self.audio_chunks = []
        category = self.category.get()
        timestamp = datetime.now()

        # Save in background so user can start next recording immediately
        threading.Thread(
            target=self._save_recording,
            args=(chunks, category, timestamp),
            daemon=True,
        ).start()

        # Reset UI
        self.start_time = None
        self.paused_duration = timedelta()
        self.pause_start = None
        self.status_label.config(text="Off", fg="#aaaaaa")
        self.timer_label.config(text="00:00:00")
        self.start_btn.config(state="normal", bg="#e74c3c", fg="#ffffff")
        self.pause_btn.config(
            state="disabled", text="Pause", bg="#555555", fg="#999999"
        )
        self.stop_btn.config(state="disabled", bg="#555555", fg="#999999")

    # --- Audio ---

    def _audio_callback(self, indata, frames, time_info, status):
        if not self.is_paused:
            self.audio_chunks.append(indata.copy())

    def _save_recording(self, chunks, category, timestamp):
        if not chunks:
            return

        date_folder = timestamp.strftime("%m-%d-%y")
        folder = os.path.join(RECORDINGS_DIR, date_folder)
        os.makedirs(folder, exist_ok=True)

        time_str = timestamp.strftime("%H%M%S")
        filename = f"{category}_{time_str}.wav"
        filepath = os.path.join(folder, filename)

        audio_data = np.concatenate(chunks, axis=0)
        sf.write(filepath, audio_data, SAMPLE_RATE)
        print(f"Saved: {filepath}")

    # --- Timer & pulse ---

    def _update_timer(self):
        if self.is_recording and self.start_time:
            elapsed = datetime.now() - self.start_time - self.paused_duration
            if self.is_paused and self.pause_start:
                elapsed -= datetime.now() - self.pause_start
            total_seconds = max(0, int(elapsed.total_seconds()))
            h, remainder = divmod(total_seconds, 3600)
            m, s = divmod(remainder, 60)
            self.timer_label.config(text=f"{h:02d}:{m:02d}:{s:02d}")
        self.root.after(200, self._update_timer)

    def _pulse_indicator(self):
        if self.is_recording and not self.is_paused:
            self.pulse_visible = not self.pulse_visible
            color = "#e74c3c" if self.pulse_visible else "#1e1e1e"
            self._draw_dot(color)
        elif self.is_recording and self.is_paused:
            self._draw_dot("#f39c12")
        else:
            self._draw_dot("#555555")
        self.root.after(500, self._pulse_indicator)


def main():
    root = tk.Tk()
    root.geometry("380x320")
    RecorderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
