#!/usr/bin/env python3
"""Simple Mac recording app with a browser-based UI."""

import logging
import os
import json
import threading
import webbrowser
from datetime import datetime, timedelta

import numpy as np
import sounddevice as sd
import soundfile as sf
from flask import Flask, render_template_string, jsonify, request

RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")
SAMPLE_RATE = 44100
CHANNELS = 1

app = Flask(__name__)

# ---- Recording state ----
state = {
    "status": "off",  # off, recording, paused
    "start_time": None,
    "paused_duration": timedelta(),
    "pause_start": None,
    "audio_chunks": [],
    "stream": None,
    "category": "customer_call",
}
state_lock = threading.Lock()


def audio_callback(indata, frames, time_info, status):
    with state_lock:
        if state["status"] == "recording":
            state["audio_chunks"].append(indata.copy())


def save_recording(chunks, category, timestamp):
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


# ---- API routes ----

@app.route("/api/status")
def get_status():
    with state_lock:
        elapsed = 0
        if state["start_time"]:
            e = datetime.now() - state["start_time"] - state["paused_duration"]
            if state["status"] == "paused" and state["pause_start"]:
                e -= datetime.now() - state["pause_start"]
            elapsed = max(0, e.total_seconds())
        return jsonify(status=state["status"], elapsed=elapsed, category=state["category"])


@app.route("/api/start", methods=["POST"])
def start_recording():
    with state_lock:
        if state["status"] != "off":
            return jsonify(error="Already recording"), 400
        cat = request.json.get("category", "customer_call") if request.json else "customer_call"
        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32", callback=audio_callback,
            )
            stream.start()
        except Exception as e:
            return jsonify(error=f"Could not start recording: {e}"), 500
        state["category"] = cat
        state["stream"] = stream
        state["audio_chunks"] = []
        state["paused_duration"] = timedelta()
        state["pause_start"] = None
        state["start_time"] = datetime.now()
        state["status"] = "recording"
    return jsonify(ok=True)


@app.route("/api/pause", methods=["POST"])
def pause_recording():
    with state_lock:
        if state["status"] == "recording":
            state["status"] = "paused"
            state["pause_start"] = datetime.now()
        elif state["status"] == "paused":
            if state["pause_start"]:
                state["paused_duration"] += datetime.now() - state["pause_start"]
                state["pause_start"] = None
            state["status"] = "recording"
        else:
            return jsonify(error="Not recording"), 400
    return jsonify(ok=True)


@app.route("/api/stop", methods=["POST"])
def stop_recording():
    with state_lock:
        if state["status"] == "off":
            return jsonify(error="Not recording"), 400
        if state["stream"]:
            state["stream"].stop()
            state["stream"].close()
            state["stream"] = None
        chunks = state["audio_chunks"]
        category = state["category"]
        state["audio_chunks"] = []
        state["status"] = "off"
        state["start_time"] = None
        state["paused_duration"] = timedelta()
        state["pause_start"] = None

    timestamp = datetime.now()
    threading.Thread(target=save_recording, args=(chunks, category, timestamp), daemon=True).start()
    return jsonify(ok=True)


# ---- UI ----

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recording Studio</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif;
    background: #1a1a1a; color: #fff;
    display: flex; justify-content: center; align-items: center;
    min-height: 100vh;
  }
  .card {
    background: #242424; border-radius: 20px; padding: 40px 48px;
    text-align: center; min-width: 360px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }

  /* Status */
  .status { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 8px; }
  .dot {
    width: 14px; height: 14px; border-radius: 50%; background: #555;
    transition: background 0.3s;
  }
  .dot.on { background: #e74c3c; animation: pulse 1s ease-in-out infinite; }
  .dot.paused { background: #f39c12; animation: none; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.2; } }
  .status-text { font-size: 22px; font-weight: 700; color: #888; }
  .status-text.on { color: #e74c3c; }
  .status-text.paused { color: #f39c12; }

  /* Timer */
  .timer {
    font-size: 52px; font-weight: 300; letter-spacing: 2px;
    font-variant-numeric: tabular-nums;
    margin: 16px 0 28px; color: #fff;
    font-family: "SF Mono", "Menlo", monospace;
  }

  /* Categories */
  .categories { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; margin: 0 auto 28px; width: fit-content; }
  .categories label {
    font-size: 15px; color: #bbb; cursor: pointer;
    display: flex; align-items: center; gap: 8px;
  }
  .categories input[type="radio"] { accent-color: #e74c3c; width: 16px; height: 16px; }

  /* Buttons */
  .buttons { display: flex; gap: 10px; justify-content: center; }
  button {
    font-size: 15px; font-weight: 600; padding: 10px 28px;
    border: none; border-radius: 10px; cursor: pointer;
    transition: background 0.2s, opacity 0.2s;
    min-width: 100px;
  }
  button:active { transform: scale(0.97); }
  .btn-start { background: #e74c3c; color: #fff; }
  .btn-start:hover { background: #c0392b; }
  .btn-pause { background: #f39c12; color: #fff; }
  .btn-pause:hover { background: #d68910; }
  .btn-stop { background: #555; color: #fff; }
  .btn-stop:hover { background: #666; }
  button:disabled { opacity: 0.3; cursor: default; pointer-events: none; }
</style>
</head>
<body>
<div class="card">
  <div class="status">
    <div class="dot" id="dot"></div>
    <div class="status-text" id="statusText">Off</div>
  </div>
  <div class="timer" id="timer">00:00:00</div>
  <div class="categories">
    <label><input type="radio" name="cat" value="customer_call" checked> Customer call</label>
    <label><input type="radio" name="cat" value="internal_prep"> Internal prep</label>
    <label><input type="radio" name="cat" value="one_on_one"> 1-1</label>
  </div>
  <div class="buttons">
    <button class="btn-start" id="btnStart" onclick="doStart()">Start</button>
    <button class="btn-pause" id="btnPause" onclick="doPause()" disabled>Pause</button>
    <button class="btn-stop" id="btnStop" onclick="doStop()" disabled>Stop</button>
  </div>
</div>
<script>
  let polling = null;

  function getCategory() {
    return document.querySelector('input[name="cat"]:checked').value;
  }

  async function doStart() {
    const r = await fetch('/api/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({category: getCategory()})});
    if (!r.ok) { const d = await r.json(); alert(d.error || 'Failed to start recording'); }
  }
  async function doPause() {
    await fetch('/api/pause', {method:'POST'});
  }
  async function doStop() {
    await fetch('/api/stop', {method:'POST'});
  }

  function fmt(sec) {
    const h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60), s = Math.floor(sec%60);
    return [h,m,s].map(v => String(v).padStart(2,'0')).join(':');
  }

  async function poll() {
    try {
      const r = await fetch('/api/status');
      const d = await r.json();
      const dot = document.getElementById('dot');
      const st = document.getElementById('statusText');
      const timer = document.getElementById('timer');

      dot.className = 'dot' + (d.status === 'recording' ? ' on' : d.status === 'paused' ? ' paused' : '');
      st.className = 'status-text' + (d.status === 'recording' ? ' on' : d.status === 'paused' ? ' paused' : '');
      st.textContent = d.status === 'recording' ? 'On Air' : d.status === 'paused' ? 'Paused' : 'Off';
      timer.textContent = fmt(d.elapsed);

      document.getElementById('btnStart').disabled = d.status !== 'off';
      document.getElementById('btnPause').disabled = d.status === 'off';
      document.getElementById('btnPause').textContent = d.status === 'paused' ? 'Resume' : 'Pause';
      document.getElementById('btnStop').disabled = d.status === 'off';

      // Select the right category radio
      const radio = document.querySelector(`input[name="cat"][value="${d.category}"]`);
      if (radio) radio.checked = true;
    } catch(e) {}
  }

  function startPolling() {
    if (!polling) polling = setInterval(poll, 200);
  }
  startPolling();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


def main():
    # Suppress per-request logs (GET /api/status every 200ms is noisy)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    port = 5111
    print(f"Recording Studio running at http://localhost:{port}")
    webbrowser.open(f"http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
