"""
MiniTeensy Synth Controller v2.0
Full hardware-style GUI controller with bidirectional serial + MIDI.
- Reads encoder data from Teensy over serial
- Sends MIDI CC/notes to synth (Teensy) and forwards external MIDI
- Displays LCD messages from Teensy
- Patch change buttons send program change and show new patch name
"""

import tkinter as tk
from tkinter import ttk
import threading
import queue
import time
import math

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("pyserial not found - serial disabled")

try:
    import mido
    MIDI_AVAILABLE = True
except ImportError:
    MIDI_AVAILABLE = False
    print("mido not found - running in demo mode")

# ─── COLOR PALETTE (same as original) ─────────────────────────────────────────
BG          = "#0d0d0f"
PANEL       = "#13141a"
PANEL2      = "#1a1b24"
ACCENT      = "#e8ff47"       # Lime yellow
ACCENT2     = "#ff6b35"       # Orange
ACCENT3     = "#47b8ff"       # Cyan
TEXT        = "#e8e8e8"
TEXT_DIM    = "#5a5a6e"
KNOB_BG     = "#1e1f2a"
KNOB_TRACK  = "#2a2b38"
KNOB_FILL   = "#e8ff47"
LED_OFF     = "#1a1a22"
LED_ON      = "#e8ff47"
LCD_BG      = "#0a1a0a"
LCD_TEXT    = "#33ff66"
LCD_DIM     = "#0f3018"
RED         = "#ff4757"
GREEN       = "#2ed573"
BORDER      = "#252636"

# ─── PARAMETER DEFINITIONS (same as original) ─────────────────────────────────
PARAMS = [
    ("Osc1 Range",      14,  53, "stepped", ["32'","16'","8'","4'","2'","LO"]),
    ("Osc2 Range",      15,  53, "stepped", ["32'","16'","8'","4'","2'","LO"]),
    ("Osc3 Range",      16,  53, "stepped", ["32'","16'","8'","4'","2'","LO"]),
    ("Osc2 Fine",       17,  64, "knob",    (-1200, 1200)),
    ("Osc3 Fine",       18,  64, "knob",    (-1200, 1200)),
    ("Osc1 Wave",       19,  53, "stepped", ["Tri","Shark","Saw","W.Pulse","M.Pulse","N.Pulse"]),
    ("Osc2 Wave",       20,  53, "stepped", ["Tri","Shark","Saw","W.Pulse","M.Pulse","N.Pulse"]),
    ("Osc3 Wave",       21,  53, "stepped", ["Tri","Tri","Saw","W.Pulse","M.Pulse","N.Pulse"]),
    ("Volume 1",        22, 101, "knob",    (0, 127)),
    ("Volume 2",        23, 101, "knob",    (0, 127)),
    ("Volume 3",        24, 101, "knob",    (0, 127)),
    ("Cutoff",          25, 127, "knob",    (0, 127)),
    ("Resonance",       26,   0, "knob",    (0, 127)),
    ("Filt Attack",     27,   0, "knob",    (0, 127)),
    ("Filt Decay",      28,  20, "knob",    (0, 127)),
    ("Filt Sustain",    29, 127, "knob",    (0, 127)),
    ("Noise Vol",       30,   0, "knob",    (0, 127)),
    ("Amp Attack",      31,   0, "knob",    (0, 127)),
    ("Amp Sustain",     32, 127, "knob",    (0, 127)),
    ("Amp Decay",       33,  13, "knob",    (0, 127)),
    ("Osc1 Fine",       34,  64, "knob",    (-1200, 1200)),
    ("Filt Strength",   35,  64, "knob",    (0, 127)),
    ("LFO Rate",        36,  32, "knob",    (0, 127)),
    ("LFO Depth",       37,   0, "knob",    (0, 127)),
    ("LFO Toggle",      38,   0, "toggle",  ["Off", "On"]),
    ("LFO Target",      39,  64, "stepped", ["Pitch","Filter","Amp"]),
    ("Play Mode",       40,  64, "stepped", ["Mono","Poly","Legato"]),
    ("Glide Time",      41,   0, "knob",    (0, 127)),
    ("Noise Type",      42,   0, "toggle",  ["White","Pink"]),
    ("Macro Mode",      43,   0, "toggle",  ["Off", "On"]),
    ("MIDI Channel",    44,   0, "stepped", ["Omni","1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16"]),
]

NOTE_NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
def note_to_name(note): return f"{NOTE_NAMES[note % 12]}{note // 12 - 1}"

# ─── KNOB, STEPPED, TOGGLE WIDGETS (slightly modified for external updates) ──
class Knob(tk.Canvas):
    def __init__(self, parent, label, cc, value=64, on_change=None, size=56, **kwargs):
        super().__init__(parent, width=size, height=size+20, bg=PANEL, highlightthickness=0, **kwargs)
        self.label = label
        self.cc = cc
        self.value = value
        self.on_change = on_change
        self.size = size
        self.dragging = False
        self.last_y = 0
        self._draw()
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<MouseWheel>", self._on_scroll)
        self.bind("<Button-4>", lambda e: self._change(1))
        self.bind("<Button-5>", lambda e: self._change(-1))

    def _draw(self):
        self.delete("all")
        s = self.size
        cx, cy = s//2, s//2
        r = s//2 - 4
        self.create_oval(cx-r, cy-r, cx+r, cy+r, fill=KNOB_TRACK, outline=BORDER, width=1)
        self.create_arc(cx-r+3, cy-r+3, cx+r-3, cy+r-3,
                        start=-225, extent=270, style="arc", outline=BORDER, width=2)
        angle_range = 270
        angle = -225 + (self.value / 127) * angle_range
        self.create_arc(cx-r+3, cy-r+3, cx+r-3, cy+r-3,
                        start=-225, extent=(self.value/127)*270,
                        style="arc", outline=KNOB_FILL, width=2)
        rad = math.radians(angle)
        ix = cx + (r-7) * math.cos(rad)
        iy = cy - (r-7) * math.sin(rad)
        self.create_line(cx, cy, ix, iy, fill=KNOB_FILL, width=2, capstyle="round")
        self.create_oval(cx-3, cy-3, cx+3, cy+3, fill=KNOB_BG, outline=KNOB_FILL, width=1)
        short = self.label[:8]
        self.create_text(s//2, s+10, text=short, fill=TEXT_DIM, font=("Courier", 7), anchor="center")
        self.create_text(s//2, s+2, text="", fill=ACCENT, font=("Courier", 6), anchor="center", tags="val")

    def set_value(self, v, send=True):
        self.value = max(0, min(127, int(v)))
        self._draw()
        if send and self.on_change:
            self.on_change(self.cc, self.value)

    def _on_press(self, e): self.dragging, self.last_y = True, e.y
    def _on_drag(self, e):
        if self.dragging:
            self._change(self.last_y - e.y)
            self.last_y = e.y
    def _on_release(self, e): self.dragging = False
    def _on_scroll(self, e): self._change(1 if e.delta > 0 else -1)
    def _change(self, delta): self.set_value(self.value + delta)


class SteppedControl(tk.Frame):
    def __init__(self, parent, label, cc, options, value=0, on_change=None, **kwargs):
        super().__init__(parent, bg=PANEL, **kwargs)
        self.label_text = label
        self.cc = cc
        self.options = options
        self.n = len(options)
        self.step = max(0, min(self.n-1, int(value / 127 * (self.n-1) + 0.5)))
        self.on_change = on_change
        tk.Label(self, text=label[:10], bg=PANEL, fg=TEXT_DIM, font=("Courier", 7)).pack()
        btn_frame = tk.Frame(self, bg=PANEL)
        btn_frame.pack()
        tk.Button(btn_frame, text="◀", bg=PANEL2, fg=ACCENT, relief="flat",
                  font=("Courier", 8), width=2, command=self._prev,
                  activebackground=BORDER, activeforeground=ACCENT).pack(side="left")
        self.val_label = tk.Label(btn_frame, text=options[self.step], bg=PANEL2,
                                   fg=ACCENT, font=("Courier", 8, "bold"), width=8,
                                   relief="flat", pady=2)
        self.val_label.pack(side="left", padx=1)
        tk.Button(btn_frame, text="▶", bg=PANEL2, fg=ACCENT, relief="flat",
                  font=("Courier", 8), width=2, command=self._next,
                  activebackground=BORDER, activeforeground=ACCENT).pack(side="left")

    def _prev(self): self.step = max(0, self.step - 1); self._update()
    def _next(self): self.step = min(self.n-1, self.step + 1); self._update()
    def _update(self):
        self.val_label.config(text=self.options[self.step])
        midi_val = int(self.step / max(1, self.n-1) * 127)
        if self.on_change: self.on_change(self.cc, midi_val)

    def set_step_external(self, midi_val):   # for serial updates
        self.step = max(0, min(self.n-1, int(midi_val / 127 * (self.n-1) + 0.5)))
        self.val_label.config(text=self.options[self.step])


class ToggleBtn(tk.Frame):
    def __init__(self, parent, label, cc, options, value=0, on_change=None, **kwargs):
        super().__init__(parent, bg=PANEL, **kwargs)
        self.cc = cc
        self.on_change = on_change
        self.state = value > 63
        self.options = options
        tk.Label(self, text=label[:10], bg=PANEL, fg=TEXT_DIM, font=("Courier", 7)).pack()
        self.btn = tk.Button(self, text=options[int(self.state)],
                              bg=LED_ON if self.state else LED_OFF,
                              fg=BG if self.state else TEXT_DIM,
                              font=("Courier", 8, "bold"), width=8, relief="flat",
                              command=self._toggle, activebackground=ACCENT)
        self.btn.pack(pady=1)

    def _toggle(self):
        self.state = not self.state
        self.btn.config(text=self.options[int(self.state)],
                         bg=LED_ON if self.state else LED_OFF,
                         fg=BG if self.state else TEXT_DIM)
        if self.on_change: self.on_change(self.cc, 127 if self.state else 0)

    def set_state_external(self, state):   # for serial updates
        self.state = state
        self.btn.config(text=self.options[int(self.state)],
                         bg=LED_ON if self.state else LED_OFF,
                         fg=BG if self.state else TEXT_DIM)


# ─── LCD DISPLAY (unchanged) ──────────────────────────────────────────────────
class LCDDisplay(tk.Canvas):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, width=280, height=70, bg=LCD_BG,
                         highlightthickness=2, highlightbackground=BORDER, **kwargs)
        self.line1 = "MiniTeensy Synth"
        self.line2 = "  6-Voice Poly  "
        self._draw()

    def update_text(self, l1, l2=""):
        self.line1 = l1[:16].ljust(16)
        self.line2 = l2[:16].ljust(16)
        self._draw()

    def _draw(self):
        self.delete("all")
        for y in range(0, 70, 4): self.create_line(0, y, 280, y, fill=LCD_DIM, width=1)
        self.create_text(14, 18, text=self.line1, fill=LCD_TEXT, font=("Courier", 14, "bold"), anchor="w")
        self.create_text(14, 48, text=self.line2, fill=LCD_TEXT, font=("Courier", 14, "bold"), anchor="w")
        cur_x = 14 + len(self.line1.rstrip()) * 8.4 + 2
        self.create_rectangle(cur_x, 6, cur_x+6, 28, fill=LCD_TEXT, outline="")


# ─── PIANO KEYBOARD (unchanged) ───────────────────────────────────────────────
class PianoKeyboard(tk.Canvas):
    def __init__(self, parent, on_note_on=None, on_note_off=None, start_note=36, octaves=4, **kwargs):
        self.white_w = 28; self.white_h = 90; self.black_w = 18; self.black_h = 58
        self.start_note = start_note; self.octaves = octaves
        self.on_note_on = on_note_on; self.on_note_off = on_note_off
        total_whites = octaves * 7
        w = total_whites * self.white_w
        super().__init__(parent, width=w, height=self.white_h + 2, bg=BG, highlightthickness=0, **kwargs)
        self.pressed = {}
        self._build_keys()
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<B1-Motion>", self._motion)

    def _build_keys(self):
        self.white_keys = []; self.black_keys = []
        black_offsets = {1:17, 3:45, 6:73, 8:101, 10:129}
        wi = 0
        for oct in range(self.octaves):
            for semi in range(12):
                note = self.start_note + oct*12 + semi
                if semi not in [1,3,6,8,10]:
                    x = wi * self.white_w
                    self.white_keys.append((note, x, 0, x+self.white_w-1, self.white_h))
                    wi += 1
        wi = 0
        for oct in range(self.octaves):
            base_x = oct * 7 * self.white_w
            for semi, off in black_offsets.items():
                note = self.start_note + oct*12 + semi
                x = base_x + off
                self.black_keys.append((note, x, 0, x+self.black_w, self.black_h))
        self._draw_all()

    def _draw_all(self):
        self.delete("all")
        for note, x1, y1, x2, y2 in self.white_keys:
            color = ACCENT if note in self.pressed else "white"
            self.create_rectangle(x1, y1, x2, y2, fill=color, outline="#555", width=1)
        for note, x1, y1, x2, y2 in self.black_keys:
            color = ACCENT2 if note in self.pressed else "#1a1a1a"
            self.create_rectangle(x1, y1, x2, y2, fill=color, outline="#000", width=1)

    def _get_note_at(self, x, y):
        for note, x1, y1, x2, y2 in self.black_keys:
            if x1 <= x <= x2 and y1 <= y <= y2: return note
        for note, x1, y1, x2, y2 in self.white_keys:
            if x1 <= x <= x2 and y1 <= y <= y2: return note
        return None

    def _press(self, e):
        note = self._get_note_at(e.x, e.y)
        if note and note not in self.pressed:
            self.pressed[note] = True; self._draw_all()
            if self.on_note_on: self.on_note_on(note, 100)

    def _release(self, e):
        for note in list(self.pressed.keys()): del self.pressed[note]; self.on_note_off(note)
        self._draw_all()

    def _motion(self, e):
        note = self._get_note_at(e.x, e.y)
        current = list(self.pressed.keys())
        for n in current:
            if n != note: del self.pressed[n]; self.on_note_off(n)
        if note and note not in self.pressed:
            self.pressed[note] = True; self._draw_all()
            if self.on_note_on: self.on_note_on(note, 100)

    def note_on_external(self, note): self.pressed[note] = True; self._draw_all()
    def note_off_external(self, note):
        if note in self.pressed: del self.pressed[note]; self._draw_all()


# ─── MIDI LOG (unchanged) ─────────────────────────────────────────────────────
class MidiLog(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=PANEL, **kwargs)
        tk.Label(self, text="MIDI MONITOR", bg=PANEL, fg=ACCENT,
                 font=("Courier", 9, "bold")).pack(anchor="w", padx=6, pady=(4,0))
        self.text = tk.Text(self, height=8, bg=BG, fg=GREEN,
                            font=("Courier", 8), relief="flat", state="disabled",
                            insertbackground=GREEN, wrap="word")
        self.text.pack(fill="both", expand=True, padx=4, pady=4)
        sb = tk.Scrollbar(self, command=self.text.yview, bg=PANEL)
        self.text.config(yscrollcommand=sb.set)

    def log(self, msg, color=None):
        self.text.config(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.text.insert("end", f"[{ts}] {msg}\n")
        self.text.see("end")
        if self.text.index("end-1c").split(".")[0] > "200":
            self.text.delete("1.0", "50.0")
        self.text.config(state="disabled")


# ─── SERIAL READER THREAD ─────────────────────────────────────────────────────
class SerialReader(threading.Thread):
    def __init__(self, port, baudrate, queue, log_callback):
        super().__init__(daemon=True)
        self.port = port
        self.baudrate = baudrate
        self.queue = queue
        self.log = log_callback
        self.ser = None
        self.running = True

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.5)
            self.log(f"Serial connected: {self.port}")
            while self.running:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    self.queue.put(line)
        except Exception as e:
            self.log(f"Serial error: {e}")
        finally:
            if self.ser and self.ser.is_open:
                self.ser.close()

    def stop(self):
        self.running = False
        if self.ser:
            self.ser.close()


# ─── MAIN APPLICATION ─────────────────────────────────────────────────────────
class MiniTeensyController(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MiniTeensy Synth Controller")
        self.configure(bg=BG)
        self.resizable(True, True)

        # MIDI attributes
        self.midi_out = None
        self.midi_in = None
        self.channel = 0
        self.velocity = 100
        self.octave_shift = 0
        self.held_notes = {}

        # Serial attributes
        self.serial_reader = None
        self.serial_queue = queue.Queue()
        self.serial_port = None

        # Parameter storage
        self.param_widgets = {}   # cc -> widget
        self.param_values = {p[1]: p[2] for p in PARAMS}

        self._build_ui()
        self._refresh_ports()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<KeyPress>", self._key_press)
        self.bind("<KeyRelease>", self._key_release)

        # Start polling serial queue
        self.after(100, self._process_serial_queue)

        # LCD boot
        self.after(500, lambda: self.lcd.update_text("MiniTeensy Synth", "  6-Voice Poly  "))
        self.after(2000, lambda: self.lcd.update_text("Connect serial", "& MIDI ports"))

    # ─── UI BUILDING ───────────────────────────────────────────────────────────
    def _build_ui(self):
        # Top bar (MIDI + serial)
        top = tk.Frame(self, bg=PANEL, height=70)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)

        # Logo
        tk.Label(top, text="MINI", bg=PANEL, fg=ACCENT,
                 font=("Courier", 22, "bold")).pack(side="left", padx=(16,0))
        tk.Label(top, text="TEENSY", bg=PANEL, fg=TEXT,
                 font=("Courier", 22, "bold")).pack(side="left")
        tk.Label(top, text=" CONTROLLER", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier", 14)).pack(side="left")

        # MIDI frame (right side)
        midi_frame = tk.Frame(top, bg=PANEL)
        midi_frame.pack(side="right", padx=12)

        tk.Label(midi_frame, text="MIDI OUT", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier", 8)).grid(row=0, column=0, padx=4, sticky="e")
        self.out_var = tk.StringVar(value="-- Select --")
        self.out_menu = ttk.Combobox(midi_frame, textvariable=self.out_var,
                                      width=22, state="readonly", font=("Courier", 8))
        self.out_menu.grid(row=0, column=1, padx=2)
        self.out_menu.bind("<<ComboboxSelected>>", self._connect_out)

        tk.Label(midi_frame, text="MIDI IN", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier", 8)).grid(row=1, column=0, padx=4, sticky="e")
        self.in_var = tk.StringVar(value="-- Select --")
        self.in_menu = ttk.Combobox(midi_frame, textvariable=self.in_var,
                                     width=22, state="readonly", font=("Courier", 8))
        self.in_menu.grid(row=1, column=1, padx=2)
        self.in_menu.bind("<<ComboboxSelected>>", self._connect_in)

        tk.Button(midi_frame, text="⟳", bg=ACCENT, fg=BG, relief="flat",
                  font=("Courier", 10, "bold"), command=self._refresh_ports,
                  activebackground=ACCENT2).grid(row=0, column=2, rowspan=2, padx=4)

        # Serial frame (left of MIDI)
        serial_frame = tk.Frame(top, bg=PANEL)
        serial_frame.pack(side="right", padx=12)

        tk.Label(serial_frame, text="SERIAL", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier", 8)).grid(row=0, column=0, padx=4, sticky="e")
        self.serial_var = tk.StringVar(value="-- Select --")
        self.serial_menu = ttk.Combobox(serial_frame, textvariable=self.serial_var,
                                        width=22, state="readonly", font=("Courier", 8))
        self.serial_menu.grid(row=0, column=1, padx=2)
        tk.Button(serial_frame, text="Connect", bg=ACCENT3, fg=BG, relief="flat",
                  font=("Courier", 8, "bold"), command=self._toggle_serial,
                  width=8).grid(row=0, column=2, padx=2)

        # Connection indicator
        self.conn_indicator = tk.Label(top, text="●", bg=PANEL, fg=RED,
                                        font=("Courier", 14))
        self.conn_indicator.pack(side="right", padx=4)

        # ─── MAIN CONTENT (same as original, but with added patch buttons) ───
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=6, pady=4)

        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="both", expand=True)

        # LCD row with patch buttons
        lcd_row = tk.Frame(left, bg=PANEL, pady=6)
        lcd_row.pack(fill="x", pady=(0,4))

        lcd_inner = tk.Frame(lcd_row, bg=PANEL)
        lcd_inner.pack(side="left", padx=12)
        tk.Label(lcd_inner, text="LCD DISPLAY", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier", 7)).pack(anchor="w")
        self.lcd = LCDDisplay(lcd_inner)
        self.lcd.pack()

        # Patch buttons
        patch_frame = tk.Frame(lcd_row, bg=PANEL)
        patch_frame.pack(side="left", padx=12, pady=4)
        tk.Label(patch_frame, text="PATCH", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier", 7)).pack(anchor="w")
        btn_patch_prev = tk.Button(patch_frame, text="◀ PREV", bg=PANEL2, fg=ACCENT,
                                   relief="flat", font=("Courier", 9, "bold"),
                                   command=lambda: self._change_patch(-1))
        btn_patch_prev.pack(side="left", padx=2)
        self.patch_label = tk.Label(patch_frame, text="0", bg=PANEL2, fg=ACCENT,
                                     font=("Courier", 12, "bold"), width=4)
        self.patch_label.pack(side="left", padx=2)
        btn_patch_next = tk.Button(patch_frame, text="NEXT ▶", bg=PANEL2, fg=ACCENT,
                                   relief="flat", font=("Courier", 9, "bold"),
                                   command=lambda: self._change_patch(1))
        btn_patch_next.pack(side="left", padx=2)

        # Velocity & octave (same)
        vc_frame = tk.Frame(lcd_row, bg=PANEL)
        vc_frame.pack(side="left", padx=12)
        tk.Label(vc_frame, text="VELOCITY", bg=PANEL, fg=TEXT_DIM, font=("Courier", 7)).pack()
        self.vel_var = tk.IntVar(value=100)
        vel_scale = tk.Scale(vc_frame, from_=127, to=1, variable=self.vel_var,
                              orient="vertical", bg=PANEL, fg=ACCENT, troughcolor=KNOB_TRACK,
                              highlightthickness=0, sliderlength=12, length=60, width=14,
                              relief="flat", showvalue=False,
                              command=lambda v: self.vel_label.config(text=str(int(float(v)))))
        vel_scale.pack()
        self.vel_label = tk.Label(vc_frame, text="100", bg=PANEL, fg=ACCENT, font=("Courier", 8))
        self.vel_label.pack()

        oct_frame = tk.Frame(lcd_row, bg=PANEL)
        oct_frame.pack(side="left", padx=6)
        tk.Label(oct_frame, text="OCTAVE", bg=PANEL, fg=TEXT_DIM, font=("Courier", 7)).pack()
        self.oct_label = tk.Label(oct_frame, text="+0", bg=PANEL2, fg=ACCENT,
                                    font=("Courier", 12, "bold"), width=4, pady=4)
        self.oct_label.pack(pady=2)
        tk.Button(oct_frame, text="▲", bg=PANEL2, fg=ACCENT, relief="flat",
                  font=("Courier", 9), command=lambda: self._shift_octave(1)).pack()
        tk.Button(oct_frame, text="▼", bg=PANEL2, fg=ACCENT, relief="flat",
                  font=("Courier", 9), command=lambda: self._shift_octave(-1)).pack()

        # MIDI Channel (same)
        ch_frame = tk.Frame(lcd_row, bg=PANEL)
        ch_frame.pack(side="left", padx=8)
        tk.Label(ch_frame, text="MIDI CH", bg=PANEL, fg=TEXT_DIM, font=("Courier", 7)).pack()
        self.ch_var = tk.IntVar(value=1)
        ch_spin = tk.Spinbox(ch_frame, from_=1, to=16, textvariable=self.ch_var,
                              width=4, bg=PANEL2, fg=ACCENT, buttonbackground=PANEL2,
                              font=("Courier", 11, "bold"), relief="flat",
                              command=lambda: setattr(self, 'channel', self.ch_var.get()-1))
        ch_spin.pack(pady=2)

        # ─── SCROLLABLE PARAMETER SECTIONS ──────────────────────────────
        scroll_container = tk.Frame(left, bg=BG)
        scroll_container.pack(fill="both", expand=True)

        # Canvas + scrollbar
        self._params_canvas = tk.Canvas(scroll_container, bg=BG, highlightthickness=0)
        v_scroll = tk.Scrollbar(scroll_container, orient="vertical",
                                command=self._params_canvas.yview,
                                bg=PANEL, troughcolor=BG)
        self._params_canvas.configure(yscrollcommand=v_scroll.set)

        v_scroll.pack(side="right", fill="y")
        self._params_canvas.pack(side="left", fill="both", expand=True)

        # Inner frame that holds all the sections
        params_outer = tk.Frame(self._params_canvas, bg=BG)
        self._params_canvas_window = self._params_canvas.create_window(
            (0, 0), window=params_outer, anchor="nw")

        # Resize the scroll region when content changes
        def _on_params_frame_configure(event):
            self._params_canvas.configure(
                scrollregion=self._params_canvas.bbox("all"))
        params_outer.bind("<Configure>", _on_params_frame_configure)

        # Make canvas width follow its container
        def _on_canvas_configure(event):
            self._params_canvas.itemconfig(
                self._params_canvas_window, width=event.width)
        self._params_canvas.bind("<Configure>", _on_canvas_configure)

        # Bind mouse-wheel scroll (Windows + Linux)
        def _on_mousewheel(event):
            if event.num == 4:
                self._params_canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self._params_canvas.yview_scroll(1, "units")
            else:
                self._params_canvas.yview_scroll(
                    int(-1 * (event.delta / 120)), "units")

        self._params_canvas.bind("<MouseWheel>", _on_mousewheel)
        self._params_canvas.bind("<Button-4>", _on_mousewheel)
        self._params_canvas.bind("<Button-5>", _on_mousewheel)
        params_outer.bind("<MouseWheel>", _on_mousewheel)
        params_outer.bind("<Button-4>", _on_mousewheel)
        params_outer.bind("<Button-5>", _on_mousewheel)

        sections = [
            ("OSCILLATORS",  PARAMS[0:8]),
            ("MIXER",        PARAMS[8:11] + [PARAMS[16]] + [PARAMS[28]]),
            ("FILTER",       PARAMS[11:16] + [PARAMS[21]]),
            ("AMPLIFIER",    PARAMS[17:20]),
            ("LFO",          PARAMS[22:26]),
            ("MODULATION",   PARAMS[3:5] + [PARAMS[20]]),
            ("PLAY",         PARAMS[26:28] + [PARAMS[29]] + [PARAMS[30]]),
        ]

        for sec_name, params in sections:
            sec_frame = tk.Frame(params_outer, bg=PANEL, padx=6, pady=4)
            sec_frame.pack(fill="x", pady=2)
            tk.Label(sec_frame, text=f"── {sec_name} ──", bg=PANEL, fg=ACCENT,
                     font=("Courier", 8, "bold")).pack(anchor="w")
            knobs_row = tk.Frame(sec_frame, bg=PANEL)
            knobs_row.pack(anchor="w")
            for p in params:
                name, cc, default, ptype, opts = p
                if ptype == "knob":
                    w = Knob(knobs_row, name, cc, value=default,
                             on_change=self._on_param_change, size=52)
                elif ptype == "stepped":
                    w = SteppedControl(knobs_row, name, cc, opts,
                                       value=default, on_change=self._on_param_change)
                elif ptype == "toggle":
                    w = ToggleBtn(knobs_row, name, cc, opts,
                                  value=default, on_change=self._on_param_change)
                else:
                    w = None
                if w:
                    w.pack(side="left", padx=4, pady=2)
                    self.param_widgets[cc] = w
                    # Propagate scroll events from child widgets to the canvas
                    for child in [w] + w.winfo_children():
                        child.bind("<MouseWheel>", _on_mousewheel, add="+")
                        child.bind("<Button-4>", _on_mousewheel, add="+")
                        child.bind("<Button-5>", _on_mousewheel, add="+")

        # Piano
        piano_frame = tk.Frame(left, bg=BG, pady=4)
        piano_frame.pack(fill="x")
        tk.Label(piano_frame, text="KEYBOARD  [Z-M = white keys C3-B3 | S,D,G,H,J = black]  [Z/X = octave]",
                 bg=BG, fg=TEXT_DIM, font=("Courier", 7)).pack(anchor="w", padx=6)
        self.piano = PianoKeyboard(piano_frame,
                                    on_note_on=self._piano_note_on,
                                    on_note_off=self._piano_note_off,
                                    start_note=36, octaves=4)
        self.piano.pack(padx=6, pady=2)

        # Right column: MIDI log + wheels
        right = tk.Frame(main, bg=PANEL, width=260)
        right.pack(side="right", fill="y", padx=(4,0))
        right.pack_propagate(False)

        self.midi_log = MidiLog(right)
        self.midi_log.pack(fill="both", expand=True, pady=4)

        wheel_frame = tk.Frame(right, bg=PANEL, pady=4)
        wheel_frame.pack(fill="x", padx=4)
        tk.Label(wheel_frame, text="PITCH BEND", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier", 7)).grid(row=0, column=0)
        tk.Label(wheel_frame, text="MOD WHEEL", bg=PANEL, fg=TEXT_DIM,
                 font=("Courier", 7)).grid(row=0, column=1, padx=8)

        self.pb_var = tk.IntVar(value=64)
        pb_scale = tk.Scale(wheel_frame, from_=127, to=0, variable=self.pb_var,
                             orient="vertical", bg=PANEL, fg=ACCENT3, troughcolor=KNOB_TRACK,
                             highlightthickness=0, sliderlength=16, length=100, width=20,
                             relief="flat", showvalue=True,
                             command=self._send_pitch_bend)
        pb_scale.grid(row=1, column=0, padx=8)

        self.mw_var = tk.IntVar(value=0)
        mw_scale = tk.Scale(wheel_frame, from_=127, to=0, variable=self.mw_var,
                             orient="vertical", bg=PANEL, fg=ACCENT2, troughcolor=KNOB_TRACK,
                             highlightthickness=0, sliderlength=16, length=100, width=20,
                             relief="flat", showvalue=True,
                             command=self._send_mod_wheel)
        mw_scale.grid(row=1, column=1, padx=8)

        tk.Button(wheel_frame, text="Reset PB", bg=PANEL2, fg=TEXT_DIM,
                  font=("Courier", 7), relief="flat",
                  command=lambda: [self.pb_var.set(64), self._send_pitch_bend(64)]).grid(row=2, column=0)

        # Status bar
        self.status_var = tk.StringVar(value="Ready. Select serial & MIDI ports.")
        status = tk.Label(self, textvariable=self.status_var, bg=PANEL2, fg=TEXT_DIM,
                          font=("Courier", 8), anchor="w", pady=3)
        status.pack(fill="x", side="bottom", padx=0)

    # ─── SERIAL HANDLING ──────────────────────────────────────────────────────
    def _toggle_serial(self):
        if self.serial_reader and self.serial_reader.is_alive():
            self._disconnect_serial()
        else:
            self._connect_serial()

    def _connect_serial(self):
        port = self.serial_var.get()
        if not SERIAL_AVAILABLE or port in ("-- Select --", "No ports found"):
            self.midi_log.log("No valid serial port selected")
            return
        try:
            # Get list of ports to verify
            ports = [p.device for p in serial.tools.list_ports.comports()]
            if port not in ports:
                self.midi_log.log(f"Port {port} not available")
                return
            self.serial_reader = SerialReader(port, 115200, self.serial_queue, self.midi_log.log)
            self.serial_reader.start()
            self.serial_menu.config(state="disabled")
            self.serial_var.set(port)
            self.status_var.set(f"Serial: {port}")
            # Request full param dump from Teensy so GUI syncs
            self.after(500, self._request_serial_dump)
        except Exception as e:
            self.midi_log.log(f"Serial connect error: {e}")

    def _disconnect_serial(self):
        if self.serial_reader:
            self.serial_reader.stop()
            self.serial_reader = None
            self.serial_menu.config(state="readonly")
            self.midi_log.log("Serial disconnected")
            self.status_var.set("Serial disconnected")

    def _request_serial_dump(self):
        """Ask Teensy to send all current parameter values."""
        if self.serial_reader and self.serial_reader.ser and self.serial_reader.ser.is_open:
            try:
                self.serial_reader.ser.write(b"DUMP\n")
                self.midi_log.log("Sent DUMP — syncing params from Teensy...")
            except Exception as e:
                self.midi_log.log(f"DUMP send error: {e}")

    def _process_serial_queue(self):
        """Called periodically to handle incoming serial messages."""
        try:
            while True:
                line = self.serial_queue.get_nowait()
                self._parse_serial_line(line)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_serial_queue)

    def _parse_serial_line(self, line):
        """Parse messages from Teensy. Expected formats:
           ENC <cc> <value>      (value 0-127)
           LCD <line1> | <line2> (two lines separated by '|')
           PATCH <name>           (set patch name on line1)
        """
        parts = line.strip().split()
        if not parts:
            return
        cmd = parts[0].upper()
        if cmd == "ENC" and len(parts) >= 3:
            try:
                cc = int(parts[1])
                val = int(parts[2])
                val = max(0, min(127, val))
                self._set_parameter_from_serial(cc, val)
            except ValueError:
                pass
        elif cmd == "LCD" and len(parts) >= 2:
            # everything after LCD is the line; could contain '|'
            rest = line[4:].strip()
            if '|' in rest:
                l1, l2 = rest.split('|', 1)
                self.lcd.update_text(l1.strip(), l2.strip())
            else:
                self.lcd.update_text(rest, "")
        elif cmd == "PATCH" and len(parts) >= 2:
            patch_name = ' '.join(parts[1:])
            self.lcd.update_text(patch_name, "")
            # Optionally update patch number if name contains number
        else:
            self.midi_log.log(f"Serial: {line}")

    def _set_parameter_from_serial(self, cc, value):
        """Update GUI and send MIDI CC when encoder changed on Teensy."""
        if cc not in self.param_widgets:
            return
        w = self.param_widgets[cc]
        # Update widget without triggering its own callback
        if isinstance(w, Knob):
            w.set_value(value, send=False)
        elif isinstance(w, SteppedControl):
            w.set_step_external(value)
        elif isinstance(w, ToggleBtn):
            w.set_state_external(value > 63)
        # Send MIDI CC
        self._send_cc(cc, value)
        # Log
        name = next((p[0] for p in PARAMS if p[1] == cc), f"CC{cc}")
        self.midi_log.log(f"Serial ENC {cc}: {name} = {value}")
        self.param_values[cc] = value

    def _send_cc(self, cc, value):
        ch = self.ch_var.get() - 1
        if MIDI_AVAILABLE and self.midi_out:
            try:
                self.midi_out.send(mido.Message("control_change", channel=ch, control=cc, value=value))
            except Exception as e:
                self.midi_log.log(f"MIDI send error: {e}")

    def _send_serial_set(self, cc, value):
        """Send SET <paramIndex> <value> to Teensy over serial."""
        if not (self.serial_reader and self.serial_reader.is_alive()):
            return
        # Find paramIndex from CC (CC = paramIndex + 14)
        param_idx = cc - 14
        if 0 <= param_idx <= 30 and self.serial_reader.ser and self.serial_reader.ser.is_open:
            try:
                cmd = f"SET {param_idx} {value}\n"
                self.serial_reader.ser.write(cmd.encode('utf-8'))
            except Exception as e:
                self.midi_log.log(f"Serial write error: {e}")

    # ─── MIDI PORT MANAGEMENT (unchanged) ─────────────────────────────────────
    def _refresh_ports(self):
        if not MIDI_AVAILABLE:
            self.midi_log.log("mido not available - demo mode")
            return
        try:
            outs = mido.get_output_names()
            ins  = mido.get_input_names()
            self.out_menu["values"] = outs or ["No ports found"]
            self.in_menu["values"]  = ins  or ["No ports found"]
            self.midi_log.log(f"Found {len(outs)} OUT, {len(ins)} IN ports")
        except Exception as e:
            self.midi_log.log(f"Port scan error: {e}")

        if SERIAL_AVAILABLE:
            try:
                ports = [p.device for p in serial.tools.list_ports.comports()]
                self.serial_menu["values"] = ports or ["No ports found"]
            except Exception as e:
                self.serial_menu["values"] = ["Error scanning"]

    def _connect_out(self, e=None):
        port = self.out_var.get()
        if not MIDI_AVAILABLE or port in ("-- Select --", "No ports found"):
            return
        try:
            if self.midi_out:
                self.midi_out.close()
            self.midi_out = mido.open_output(port)
            self.midi_log.log(f"OUT connected: {port}")
            self.status_var.set(f"MIDI OUT: {port}")
            self._update_indicator()
        except Exception as ex:
            self.midi_log.log(f"OUT error: {ex}")

    def _connect_in(self, e=None):
        port = self.in_var.get()
        if not MIDI_AVAILABLE or port in ("-- Select --", "No ports found"):
            return
        try:
            if self.midi_in:
                self.midi_in.close()
            self.midi_in = mido.open_input(port, callback=self._midi_in_callback)
            self.midi_log.log(f"IN connected: {port}")
            self._update_indicator()
        except Exception as ex:
            self.midi_log.log(f"IN error: {ex}")

    def _update_indicator(self):
        connected = (self.midi_out is not None)
        self.conn_indicator.config(fg=GREEN if connected else RED)

    # ─── MIDI SEND / RECEIVE ──────────────────────────────────────────────────
    def _on_param_change(self, cc, value):
        """Called when a GUI knob/button is moved."""
        self.param_values[cc] = value
        self._send_cc(cc, value)
        self._send_serial_set(cc, value)  # Also send to Teensy over serial
        name = next((p[0] for p in PARAMS if p[1] == cc), f"CC{cc}")
        self.lcd.update_text(name[:16], self._format_value(cc, value))
        self.midi_log.log(f"GUI CC {cc:3d} ({name[:12]}) = {value}")

    def _format_value(self, cc, val):
        p = next((p for p in PARAMS if p[1] == cc), None)
        if not p: return str(val)
        if p[3] == "stepped":
            opts = p[4]
            idx = int(val / 127 * (len(opts)-1) + 0.5)
            return opts[min(idx, len(opts)-1)]
        if p[3] == "toggle":
            return p[4][1 if val > 63 else 0]
        return str(val)

    def _piano_note_on(self, note, vel):
        actual_note = note + self.octave_shift * 12
        actual_note = max(0, min(127, actual_note))
        ch = self.ch_var.get() - 1
        v  = self.vel_var.get()
        self._send(mido.Message("note_on", channel=ch, note=actual_note, velocity=v))
        self.midi_log.log(f"NOTE ON  {note_to_name(actual_note)} ({actual_note}) vel={v}")
        self.lcd.update_text(f"Note: {note_to_name(actual_note)}", f"Vel: {v}  Ch:{ch+1}")

    def _piano_note_off(self, note):
        actual_note = note + self.octave_shift * 12
        actual_note = max(0, min(127, actual_note))
        ch = self.ch_var.get() - 1
        self._send(mido.Message("note_off", channel=ch, note=actual_note, velocity=0))

    def _send_pitch_bend(self, val):
        ch = self.ch_var.get() - 1
        mapped = int((int(val) / 127) * 16383)
        self._send(mido.Message("pitchwheel", channel=ch, pitch=mapped - 8192))

    def _send_mod_wheel(self, val):
        ch = self.ch_var.get() - 1
        self._send(mido.Message("control_change", channel=ch, control=1, value=int(val)))

    def _send(self, msg):
        if self.midi_out and MIDI_AVAILABLE:
            try:
                self.midi_out.send(msg)
            except Exception as e:
                self.midi_log.log(f"Send error: {e}")

    def _midi_in_callback(self, msg):
        """Forward incoming MIDI to synth and update GUI."""
        self.after(0, lambda: self._process_midi_in(msg))

    def _process_midi_in(self, msg):
        # Forward to synth
        if self.midi_out and MIDI_AVAILABLE:
            try:
                self.midi_out.send(msg)
            except Exception as e:
                self.midi_log.log(f"Forward error: {e}")

        # Update GUI for relevant messages
        t = msg.type
        if t == "note_on":
            self.midi_log.log(f"IN NOTE ON  {note_to_name(msg.note)} vel={msg.velocity}")
            self.piano.note_on_external(msg.note)
        elif t == "note_off":
            self.midi_log.log(f"IN NOTE OFF {note_to_name(msg.note)}")
            self.piano.note_off_external(msg.note)
        elif t == "control_change":
            self.midi_log.log(f"IN CC {msg.control:3d} = {msg.value}")
            if msg.control in self.param_widgets:
                w = self.param_widgets[msg.control]
                if isinstance(w, Knob):
                    w.set_value(msg.value, send=False)
                elif isinstance(w, SteppedControl):
                    w.set_step_external(msg.value)
                elif isinstance(w, ToggleBtn):
                    w.set_state_external(msg.value > 63)
        elif t == "program_change":
            self.midi_log.log(f"IN PROGRAM {msg.program}")
            self.patch_label.config(text=str(msg.program+1))
        else:
            self.midi_log.log(f"IN {msg}")

    # ─── PATCH CHANGE ─────────────────────────────────────────────────────────
    def _change_patch(self, delta):
        """Send program change (patch up/down)."""
        current = int(self.patch_label.cget("text"))
        new = max(1, min(128, current + delta))
        self.patch_label.config(text=str(new))
        ch = self.ch_var.get() - 1
        prog = new - 1
        if MIDI_AVAILABLE and self.midi_out:
            self._send(mido.Message("program_change", channel=ch, program=prog))
        # Also trigger preset load on Teensy via serial (0-based index)
        if self.serial_reader and self.serial_reader.ser and self.serial_reader.ser.is_open:
            try:
                self.serial_reader.ser.write(f"PRESET {prog}\n".encode('utf-8'))
            except Exception as e:
                self.midi_log.log(f"Serial PRESET error: {e}")
        self.midi_log.log(f"Program change: {prog+1}")

    # ─── KEYBOARD SHORTCUTS (unchanged) ───────────────────────────────────────
    KEY_MAP = {
        'z': 0, 's': 1, 'x': 2, 'd': 3, 'c': 4, 'v': 5,
        'g': 6, 'b': 7, 'h': 8, 'n': 9, 'j': 10, 'm': 11,
        'q': 12, '2': 13, 'w': 14, '3': 15, 'e': 16, 'r': 17,
        '5': 18, 't': 19, '6': 20, 'y': 21, '7': 22, 'u': 23,
    }

    def _key_press(self, e):
        k = e.keysym.lower()
        if k == 'z' and e.state & 0x1: self._shift_octave(-1); return
        if k == 'x' and e.state & 0x1: self._shift_octave(1); return
        if k in self.KEY_MAP and k not in self.held_notes:
            base = 60 + self.octave_shift * 12
            note = base + self.KEY_MAP[k]
            self.held_notes[k] = note
            self._piano_note_on(note - self.octave_shift * 12, self.vel_var.get())
            self.piano.note_on_external(note - self.octave_shift * 12)

    def _key_release(self, e):
        k = e.keysym.lower()
        if k in self.held_notes:
            note = self.held_notes.pop(k)
            self._piano_note_off(note - self.octave_shift * 12)
            self.piano.note_off_external(note - self.octave_shift * 12)

    def _shift_octave(self, delta):
        self.octave_shift = max(-3, min(3, self.octave_shift + delta))
        label = f"+{self.octave_shift}" if self.octave_shift >= 0 else str(self.octave_shift)
        self.oct_label.config(text=label)
        self.midi_log.log(f"Octave: {label}")

    # ─── ALL NOTES OFF / PANIC / INIT ─────────────────────────────────────────
    def _all_notes_off(self):
        ch = self.ch_var.get() - 1
        for n in range(128):
            self._send(mido.Message("note_off", channel=ch, note=n, velocity=0))
        self.piano.pressed.clear(); self.piano._draw_all()
        self.midi_log.log("All notes off")
        self.lcd.update_text("All Notes Off", "")

    def _panic(self):
        for ch in range(16):
            self._send(mido.Message("control_change", channel=ch, control=123, value=0))
        self.piano.pressed.clear(); self.piano._draw_all()
        self.midi_log.log("PANIC - All channels cleared")
        self.lcd.update_text("** PANIC **", "All Notes Off")

    def _send_init(self):
        ch = self.ch_var.get() - 1
        for cc, val in self.param_values.items():
            self._send(mido.Message("control_change", channel=ch, control=cc, value=val))
            self._send_serial_set(cc, val)
            time.sleep(0.005)
        self.midi_log.log("Init patch sent to synth")
        self.lcd.update_text("Init Sent!", "All params set")

    # ─── CLEANUP ──────────────────────────────────────────────────────────────
    def _on_close(self):
        self._all_notes_off()
        if self.midi_out:
            self.midi_out.close()
        if self.midi_in:
            self.midi_in.close()
        self._disconnect_serial()
        self.destroy()


if __name__ == "__main__":
    app = MiniTeensyController()
    app.mainloop()