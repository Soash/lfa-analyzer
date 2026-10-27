import os
import csv
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import numpy as np
import matplotlib.pyplot as plt

MAX_DISPLAY_HEIGHT = 750


def open_grayscale_array(path):
    """Open any image (8-bit, 16-bit TIFF, RGB, PNG, etc.) and return a
    float64 single-channel array at FULL source precision, regardless of
    file extension."""
    pil_raw = Image.open(path)
    pil_raw.load()
    if pil_raw.mode in ("I", "I;16", "I;16B", "I;16L", "F"):
        measure_img = pil_raw
    else:
        measure_img = pil_raw.convert("L")
    return np.asarray(measure_img).astype(np.float64)


def compute_base_scale(img_height, max_height=MAX_DISPLAY_HEIGHT):
    return max_height / img_height if img_height > max_height else 1.0


def box_blur(arr, radius):
    """Fast separable box blur (moving average) using a cumulative-sum
    trick, so it stays fast even at large radii with no extra dependencies."""
    if radius <= 0:
        return arr.copy()
    k = 2 * radius + 1
    padded = np.pad(arr, ((radius, radius), (radius, radius)), mode='edge')
    csum = np.cumsum(padded, axis=1)
    csum = np.pad(csum, ((0, 0), (1, 0)), mode='constant')
    h_blur = (csum[:, k:] - csum[:, :-k]) / k
    csum2 = np.cumsum(h_blur, axis=0)
    csum2 = np.pad(csum2, ((1, 0), (0, 0)), mode='constant')
    v_blur = (csum2[k:, :] - csum2[:-k, :]) / k
    return v_blur


def extract_channel_array(pil_img, channel):
    """Return a float64 single-channel array from a PIL image, honoring the
    requested channel for COLOR images (this feeds into real measurement,
    not just the preview - picking the channel with the best band contrast
    is a legitimate quantification choice, not a cosmetic trick)."""
    if pil_img.mode in ("I", "I;16", "I;16B", "I;16L", "F"):
        return np.asarray(pil_img).astype(np.float64)
    if pil_img.mode in ("RGB", "RGBA") and channel in ("Red", "Green", "Blue"):
        rgb = np.asarray(pil_img.convert("RGB")).astype(np.float64)
        idx = {"Red": 0, "Green": 1, "Blue": 2}[channel]
        return rgb[:, :, idx]
    return np.asarray(pil_img.convert("L")).astype(np.float64)

def build_display_image(raw_arr, enhance, invert, bg_radius, saturated_pct):
    """Build an 8-bit PIL image for on-screen display ONLY. raw_arr (the real
    measurement data) is never modified - this returns a new array every time."""
    arr = raw_arr.astype(np.float64).copy()

    if enhance:
        if bg_radius > 0:
            blurred = box_blur(arr, bg_radius)
            arr = arr - blurred + np.mean(arr)  # flatten uneven baseline/illumination

        tail = max(0.0, saturated_pct) / 100.0 / 2.0  # split between both tails, like ImageJ
        lo = np.percentile(arr, tail * 100)
        hi = np.percentile(arr, 100 - tail * 100)
        if hi > lo:
            arr = np.clip((arr - lo) / (hi - lo), 0, 1) * 255.0
        else:
            arr = np.zeros_like(arr)
    else:
        lo, hi = arr.min(), arr.max()
        if hi > lo:
            arr = (arr - lo) / (hi - lo) * 255.0
        else:
            arr = np.zeros_like(arr)

    if invert:
        arr = 255.0 - arr

    return Image.fromarray(arr.astype(np.uint8), mode="L")


class LFAAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Interactive LFA Strip Analyzer")

        # --- Multi-image state ---
        self.image_paths = []          # list of loaded file paths, in load order
        self.image_configs = {}        # path -> dict of box settings for that image
        self.current_index = -1
        self.current_path = None

        # --- Per-image data (for the currently displayed image) ---
        self.raw_data = None            # full-precision numpy array (float64), current image
        self.base_pil_image = None      # 8-bit PIL image, current image, display only
        self.display_image = None
        self.base_scale_factor = 1.0
        self.user_zoom = 1.0
        self.scale_factor = 1.0

        self.x_offset = 0
        self.y_offset = 0

        self.drag_data = {"start_y": 0, "start_control_y": 0, "dragging": False}

        self.csv_path = None

        # --- Configurable Variables (reflect the CURRENTLY DISPLAYED image) ---
        self.box_h = tk.IntVar(value=10)
        self.dist_t2 = tk.IntVar(value=52)
        self.dist_t1 = tk.IntVar(value=122)
        self.dist_bg = tk.IntVar(value=85)
        self.control_y = tk.IntVar(value=251)

        self.use_median = tk.BooleanVar(value=False)

        # --- Channel selection (affects real measurement, per-image but same choice for all) ---
        self.channel_var = tk.StringVar(value="Luminance")

        # --- Preview-only enhancement (NEVER affects raw_data / measurements / CSV) ---
        self.enhance_preview = tk.BooleanVar(value=False)
        self.invert_preview = tk.BooleanVar(value=False)
        self.bg_flatten_radius = tk.IntVar(value=25)
        self.saturated_pct = tk.DoubleVar(value=0.35)

        self.current_pil_raw = None  # full-precision PIL image for the currently shown path (pre-channel-split)


        self._suspend_trace = False  # guards against feedback loops while restoring a config
        for var in (self.box_h, self.dist_t2, self.dist_t1, self.dist_bg, self.control_y):
            var.trace_add("write", self._on_slider_change)

        # --- UI Layout ---
        self.left_frame = tk.Frame(root, bg="gray")
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.left_frame.grid_rowconfigure(1, weight=1)
        self.left_frame.grid_columnconfigure(0, weight=1)

        self.status_label = tk.Label(self.left_frame, text="No images loaded.", font=("Arial", 10, "bold"),
                                      anchor=tk.W, bg="gray", fg="white")
        self.status_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))

        self.v_scroll = tk.Scrollbar(self.left_frame, orient=tk.VERTICAL)
        self.v_scroll.grid(row=1, column=1, sticky="ns")
        self.h_scroll = tk.Scrollbar(self.left_frame, orient=tk.HORIZONTAL)
        self.h_scroll.grid(row=2, column=0, sticky="ew")

        self.canvas = tk.Canvas(self.left_frame, bg="gray", cursor="cross", highlightthickness=0,
                                 yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.canvas.grid(row=1, column=0, sticky="nsew")

        self.canvas.bind("<Configure>", self.center_content)

        self.v_scroll.config(command=self.canvas.yview)
        self.h_scroll.config(command=self.canvas.xview)

        # Prev / Next navigation, under the canvas
        nav_frame = tk.Frame(self.left_frame, bg="gray")
        nav_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        tk.Button(nav_frame, text="<< Prev", command=self.show_prev, width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(nav_frame, text="Next >>", command=self.show_next, width=12).pack(side=tk.LEFT, padx=5)

        # ======================================================================
        # SCROLLABLE RIGHT FRAME (Controls)
        # ======================================================================
        self.right_container = tk.Frame(root, width=380)
        self.right_container.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        self.right_container.pack_propagate(False) # Keep width fixed

        self.right_canvas = tk.Canvas(self.right_container, highlightthickness=0)
        self.right_scrollbar = tk.Scrollbar(self.right_container, orient=tk.VERTICAL, command=self.right_canvas.yview)
        
        # This is the actual frame where all widgets will go
        self.right_frame = tk.Frame(self.right_canvas)
        
        # Configure scroll region when internal frame resizes
        self.right_frame.bind(
            "<Configure>",
            lambda e: self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all"))
        )

        # Add the inner frame to the canvas
        self.right_canvas.create_window((0, 0), window=self.right_frame, anchor="nw", tags="right_inner")

        # Make the inner frame dynamically expand to match the canvas width
        self.right_canvas.bind(
            "<Configure>",
            lambda e: self.right_canvas.itemconfig("right_inner", width=e.width)
        )

        self.right_canvas.configure(yscrollcommand=self.right_scrollbar.set)
        
        self.right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind mouse wheel to right panel for scrolling (Windows and MacOS)
        def _on_mousewheel(event):
            self.right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.right_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        # ======================================================================


        tk.Button(self.right_frame, text="1. Load Image(s)", command=self.load_images, width=29,
                  font=("Arial", 12, "bold")).pack(pady=(10, 5))

        # --- Channel selection (feeds real measurement) ---
        channel_frame = tk.Frame(self.right_frame)
        channel_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(channel_frame, text="Measure channel:", font=("Arial", 9, "bold")).pack(anchor=tk.W)
        channel_menu = tk.OptionMenu(channel_frame, self.channel_var,
                                      "Luminance", "Red", "Green", "Blue",
                                      command=lambda _=None: self.on_channel_change())
        channel_menu.pack(fill=tk.X)
        tk.Label(channel_frame, text="(ignored for images that are already single-channel grayscale)",
                 font=("Arial", 7), fg="gray", wraplength=310, justify=tk.LEFT).pack(anchor=tk.W)

        # --- Preview-only enhancement (cosmetic; never affects measurements/CSV) ---
        preview_frame = tk.LabelFrame(self.right_frame, text="Preview enhancement (display only)",
                                       font=("Arial", 9, "bold"))
        preview_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Checkbutton(preview_frame, text="Enhance faint bands (background-flatten + contrast stretch)",
                       variable=self.enhance_preview, command=self.refresh_display,
                       wraplength=300, justify=tk.LEFT).pack(anchor=tk.W)
        tk.Checkbutton(preview_frame, text="Invert preview", variable=self.invert_preview,
                       command=self.refresh_display).pack(anchor=tk.W)

        bg_row = tk.Frame(preview_frame)
        bg_row.pack(fill=tk.X, pady=2)
        tk.Label(bg_row, text="Background-flatten radius:").pack(anchor=tk.W)
        tk.Scale(bg_row, from_=0, to=150, orient=tk.HORIZONTAL, variable=self.bg_flatten_radius,
                 command=lambda _=None: self.refresh_display()).pack(fill=tk.X)

        sat_row = tk.Frame(preview_frame)
        sat_row.pack(fill=tk.X, pady=2)
        tk.Label(sat_row, text="Saturated pixels % (contrast stretch):").pack(anchor=tk.W)
        tk.Scale(sat_row, from_=0.0, to=5.0, resolution=0.05, orient=tk.HORIZONTAL,
                 variable=self.saturated_pct, command=lambda _=None: self.refresh_display()).pack(fill=tk.X)


        # --- Loaded images list ---
        tk.Label(self.right_frame, text="Loaded images (click to jump):", font=("Arial", 9, "bold")).pack(
            anchor=tk.W, pady=(5, 2))
        list_frame = tk.Frame(self.right_frame)
        list_frame.pack(fill=tk.X, pady=(0, 10))
        list_scroll = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.image_listbox = tk.Listbox(list_frame, height=5, yscrollcommand=list_scroll.set, exportselection=False)
        self.image_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        list_scroll.config(command=self.image_listbox.yview)
        self.image_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)

        # --- Zoom Controls ---
        zoom_frame = tk.Frame(self.right_frame)
        zoom_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Button(zoom_frame, text="Zoom In (+)", command=self.zoom_in, font=("Arial", 10, "bold"),
                  bg="#e0e0e0").pack(side=tk.LEFT, expand=True, padx=2)
        tk.Button(zoom_frame, text="Zoom Out (-)", command=self.zoom_out, font=("Arial", 10, "bold"),
                  bg="#e0e0e0").pack(side=tk.RIGHT, expand=True, padx=2)

        # --- Save/Load Controls ---
        config_frame = tk.Frame(self.right_frame)
        config_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Button(config_frame, text="Save Config", command=self.save_config, width=13).pack(side=tk.LEFT, expand=True)
        tk.Button(config_frame, text="Load Config", command=self.load_config, width=13).pack(side=tk.RIGHT, expand=True)

        tk.Label(self.right_frame, text="Box Settings (applies to CURRENT image only):",
                 font=("Arial", 10, "bold"), wraplength=320, justify=tk.LEFT).pack(anchor=tk.W, pady=(5, 5))

        self.create_control("Global Y Position (Control)", self.control_y, 0, 3000)
        self.create_control("Common Box Height", self.box_h, 5, 100)
        self.create_control("Distance: Control to T2", self.dist_t2, -500, 500)
        self.create_control("Distance: Control to T1", self.dist_t1, -800, 800)
        self.create_control("Distance: Control to Background", self.dist_bg, -800, 800)

        tk.Frame(self.right_frame, height=10).pack()
        legend_frame = tk.Frame(self.right_frame)
        legend_frame.pack(anchor=tk.W, pady=4)
        legend_frame.grid_columnconfigure(0, weight=1)
        legend_frame.grid_columnconfigure(1, weight=1)
        tk.Label(legend_frame, text="Blue: Control", fg="blue", font=("Arial", 9, "bold")).grid(
            row=0, column=0, sticky=tk.W, padx=(0, 15), pady=2)
        tk.Label(legend_frame, text="Green: T2", fg="green", font=("Arial", 9, "bold")).grid(
            row=0, column=1, sticky=tk.W, pady=2)
        tk.Label(legend_frame, text="Red: T1", fg="red", font=("Arial", 9, "bold")).grid(
            row=1, column=0, sticky=tk.W, padx=(0, 15), pady=2)
        tk.Label(legend_frame, text="Orange: Background", fg="#cc7a00", font=("Arial", 9, "bold")).grid(
            row=1, column=1, sticky=tk.W, pady=2)

        tk.Frame(self.right_frame, height=10).pack()
        tk.Checkbutton(self.right_frame, text="Use median instead of mean",
                       variable=self.use_median, wraplength=300, justify=tk.LEFT).pack(anchor=tk.W, pady=2)

        tk.Frame(self.right_frame, height=10).pack()
        tk.Button(self.right_frame, text="2. Analyze CURRENT Image + Save to CSV", command=self.analyze_current,
                  width=29, font=("Arial", 11, "bold"), bg="lightblue").pack(pady=(10, 5))
        tk.Button(self.right_frame, text="3. Analyze ALL Loaded Images + Compare", command=self.analyze_all,
                  width=29, font=("Arial", 11, "bold"), bg="#c8f2c8").pack(pady=(0, 10))
        tk.Button(self.right_frame, text="Choose CSV output file...", command=self.choose_csv_path,
                  width=29).pack(pady=(0, 5))

        self.csv_label = tk.Label(self.right_frame, text="CSV: (not set - will ask on first save)",
                                   font=("Arial", 8), fg="gray", wraplength=320, justify=tk.CENTER)
        self.csv_label.pack(anchor=tk.CENTER, pady=(0, 20)) # Added extra bottom padding

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    def create_control(self, label_text, variable, from_val, to_val):
        frame = tk.Frame(self.right_frame)
        frame.pack(fill=tk.X, pady=4)
        tk.Label(frame, text=label_text).pack(anchor=tk.W)

        spinbox = tk.Spinbox(frame, from_=from_val, to=to_val, textvariable=variable, width=6, font=("Arial", 10))
        spinbox.pack(side=tk.RIGHT, padx=5)

        scale = tk.Scale(frame, from_=from_val, to=to_val, orient=tk.HORIZONTAL, variable=variable, showvalue=False)
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ---------------- Per-image config helpers ----------------

    def _get_current_slider_config(self):
        return {
            "box_h": self.box_h.get(),
            "dist_t2": self.dist_t2.get(),
            "dist_t1": self.dist_t1.get(),
            "dist_bg": self.dist_bg.get(),
            "control_y": self.control_y.get(),
        }

    def _apply_slider_config(self, cfg):
        self._suspend_trace = True
        self.box_h.set(cfg["box_h"])
        self.dist_t2.set(cfg["dist_t2"])
        self.dist_t1.set(cfg["dist_t1"])
        self.dist_bg.set(cfg["dist_bg"])
        self.control_y.set(cfg["control_y"])
        self._suspend_trace = False
        self.redraw_boxes()

    def _on_slider_change(self, *args):
        if self._suspend_trace:
            return
        # keep this image's stored config in sync as the user tweaks sliders
        if self.current_path is not None:
            self.image_configs[self.current_path] = self._get_current_slider_config()
        self.redraw_boxes()

    # ---------------- Dynamic Centering Logic ----------------

    def center_content(self, event=None):
        if not self.display_image:
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        iw = self.display_image.width()
        ih = self.display_image.height()

        self.x_offset = max(0, (cw - iw) // 2)
        self.y_offset = max(0, (ch - ih) // 2)

        self.canvas.coords("img", self.x_offset, self.y_offset)
        self.redraw_boxes()

    # ---------------- Zoom Functionality ----------------

    def zoom_in(self):
        if self.base_pil_image:
            self.user_zoom += 0.25
            self.update_display()

    def zoom_out(self):
        if self.base_pil_image and self.user_zoom > 0.5:
            self.user_zoom -= 0.25
            self.update_display()

    def update_display(self):
        new_w = int(self.base_pil_image.width * self.user_zoom)
        new_h = int(self.base_pil_image.height * self.user_zoom)
        self.scale_factor = self.base_scale_factor * self.user_zoom

        resized_img = self.base_pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.display_image = ImageTk.PhotoImage(resized_img)

        self.canvas.config(scrollregion=(0, 0, new_w, new_h))
        self.canvas.delete("img")

        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.display_image, tags="img")
        self.canvas.tag_lower("img")

        self.root.update_idletasks()
        self.center_content()

    # ---------------- Config Management (JSON template, unrelated to per-image memory) ----------------

    def save_config(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if filepath:
            import json
            try:
                with open(filepath, 'w') as f:
                    json.dump(self._get_current_slider_config(), f, indent=4)
                messagebox.showinfo("Success", "Configuration saved successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Could not save file:\n{e}")

    def load_config(self):
        filepath = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if filepath:
            import json
            try:
                with open(filepath, 'r') as f:
                    config = json.load(f)
                defaults = self._get_current_slider_config()
                for k in defaults:
                    defaults[k] = config.get(k, defaults[k])
                self._apply_slider_config(defaults)
                if self.current_path is not None:
                    self.image_configs[self.current_path] = defaults
            except Exception as e:
                messagebox.showerror("Error", f"Could not load file:\n{e}")

    # ---------------- Multi-image loading & navigation ----------------

    def load_images(self):
        file_paths = filedialog.askopenfilenames(
            filetypes=[("Images", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp"), ("All files", "*.*")]
        )
        if not file_paths:
            return

        was_empty = len(self.image_paths) == 0
        default_cfg = self._get_current_slider_config()

        added = 0
        for p in file_paths:
            if p not in self.image_paths:
                self.image_paths.append(p)
                self.image_configs[p] = dict(default_cfg)  # each new image starts from current settings
                self.image_listbox.insert(tk.END, os.path.basename(p))
                added += 1

        if added == 0:
            return

        if was_empty:
            self.show_image_at_index(0)
        else:
            self._update_status_label()

    def on_listbox_select(self, event):
        sel = self.image_listbox.curselection()
        if sel:
            self.show_image_at_index(sel[0])

    def show_prev(self):
        if self.current_index > 0:
            self.show_image_at_index(self.current_index - 1)

    def show_next(self):
        if self.current_index < len(self.image_paths) - 1:
            self.show_image_at_index(self.current_index + 1)

    def show_image_at_index(self, idx):
        if idx < 0 or idx >= len(self.image_paths):
            return

        # persist whatever the user has set for the image we're leaving
        if self.current_path is not None:
            self.image_configs[self.current_path] = self._get_current_slider_config()

        path = self.image_paths[idx]
        try:
            pil_raw = Image.open(path)
            pil_raw.load()
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image:\n{path}\n\n{e}")
            return

        self.current_index = idx
        self.current_path = path
        self.current_pil_raw = pil_raw
        self.raw_data = extract_channel_array(pil_raw, self.channel_var.get())

        self._rebuild_display_image()
        self.user_zoom = 1.0
        self.update_display()

        # restore this image's own box configuration
        cfg = self.image_configs.get(path, self._get_current_slider_config())
        self._apply_slider_config(cfg)

        self.image_listbox.selection_clear(0, tk.END)
        self.image_listbox.selection_set(idx)
        self.image_listbox.see(idx)
        self._update_status_label()

    def on_channel_change(self):
        """Re-derive raw_data (and therefore what gets measured) for the
        currently shown image using the newly selected channel."""
        if self.current_pil_raw is None:
            return
        self.raw_data = extract_channel_array(self.current_pil_raw, self.channel_var.get())
        self._rebuild_display_image()
        self.update_display()

    def _rebuild_display_image(self):
        """Build the 8-bit PIL image used for on-screen display, applying the
        preview-only enhancement pipeline. self.raw_data (used for all real
        measurements) is never modified here."""
        disp_img = build_display_image(
            self.raw_data,
            enhance=self.enhance_preview.get(),
            invert=self.invert_preview.get(),
            bg_radius=self.bg_flatten_radius.get(),
            saturated_pct=self.saturated_pct.get(),
        )

        if disp_img.height > MAX_DISPLAY_HEIGHT:
            self.base_scale_factor = compute_base_scale(disp_img.height)
            new_width = int(disp_img.width * self.base_scale_factor)
            self.base_pil_image = disp_img.resize((new_width, MAX_DISPLAY_HEIGHT), Image.Resampling.LANCZOS)
        else:
            self.base_scale_factor = 1.0
            self.base_pil_image = disp_img

    def refresh_display(self):
        """Called when a preview-only control changes; rebuilds the display
        image at the current zoom without touching raw_data or box config."""
        if self.raw_data is None:
            return
        self._rebuild_display_image()
        self.update_display()

    def _update_status_label(self):
        if self.current_index >= 0 and self.image_paths:
            name = os.path.basename(self.image_paths[self.current_index])
            self.status_label.config(
                text=f"Image {self.current_index + 1} of {len(self.image_paths)}: {name}")
        else:
            self.status_label.config(text="No images loaded.")

    def redraw_boxes(self, *args):
        if not self.display_image:
            return

        z = self.user_zoom
        h = int(self.box_h.get() * z)
        dt2 = int(self.dist_t2.get() * z)
        dt1 = int(self.dist_t1.get() * z)
        dbg = int(self.dist_bg.get() * z)

        y1 = self.y_offset + int(self.control_y.get() * z)
        x1 = self.x_offset + 1
        x2 = self.x_offset + self.display_image.width() - 2

        self.canvas.delete("band")
        self.canvas.create_rectangle(x1, y1, x2, y1 + h, outline="blue", width=1, tags=("band", "top_band"))
        self.canvas.create_rectangle(x1, y1 + dt2, x2, y1 + dt2 + h, outline="green", width=1, tags=("band", "mid_band"))
        self.canvas.create_rectangle(x1, y1 + dt1, x2, y1 + dt1 + h, outline="red", width=1, tags=("band", "bot_band"))
        self.canvas.create_rectangle(x1, y1 + dbg, x2, y1 + dbg + h, outline="orange", width=1, tags=("band", "bg_band"))

    # ---------------- Mouse Dragging Logic ----------------

    def on_press(self, event):
        items = self.canvas.find_withtag("current")
        if items and "band" in self.canvas.gettags(items[0]):
            self.drag_data["dragging"] = True
            self.drag_data["start_y"] = self.canvas.canvasy(event.y)
            self.drag_data["start_control_y"] = self.control_y.get()

    def on_drag(self, event):
        if self.drag_data["dragging"]:
            current_y = self.canvas.canvasy(event.y)
            dy = current_y - self.drag_data["start_y"]
            base_dy = int(dy / self.user_zoom)

            new_y = self.drag_data["start_control_y"] + base_dy
            self.control_y.set(max(0, new_y))

    def on_release(self, event):
        self.drag_data["dragging"] = False

    # ---------------- CSV output ----------------

    def choose_csv_path(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if filepath:
            self.csv_path = filepath
            self.csv_label.config(text=f"CSV: {filepath}")

    def _ensure_csv_path(self):
        if self.csv_path is None:
            filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
            if not filepath:
                return False
            self.csv_path = filepath
            self.csv_label.config(text=f"CSV: {filepath}")
        return True

    def append_rows_to_csv(self, rows):
        if not rows:
            return
        if not self._ensure_csv_path():
            return

        file_exists = os.path.isfile(self.csv_path)
        write_header = (not file_exists) or os.path.getsize(self.csv_path) == 0

        try:
            with open(self.csv_path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                if write_header:
                    writer.writeheader()
                for row in rows:
                    writer.writerow(row)
        except Exception as e:
            messagebox.showerror("Error", f"Could not write to CSV:\n{e}")

    # ---------------- Core measurement (works on any array + config, no canvas needed) ----------------

    def _measure_from_config(self, arr, cfg):
        """Given a full-precision array and a box config (in zoom=1 display
        pixel units), return the 4 raw ROI values in ORIGINAL image coords."""
        img_h = arr.shape[0]
        img_w = arr.shape[1]
        base_scale = compute_base_scale(img_h)

        def to_orig(v):
            return v / base_scale

        box_h_o = max(1, int(round(to_orig(cfg["box_h"]))))
        control_y_o = int(round(to_orig(cfg["control_y"])))
        dt2_o = int(round(to_orig(cfg["dist_t2"])))
        dt1_o = int(round(to_orig(cfg["dist_t1"])))
        dbg_o = int(round(to_orig(cfg["dist_bg"])))

        stat_func = np.median if self.use_median.get() else np.mean

        def region_value(y_start):
            y1 = max(0, y_start)
            y2 = min(img_h, y_start + box_h_o)
            if y2 <= y1:
                return 0.0
            crop = arr[y1:y2, 0:img_w]
            return float(stat_func(crop))

        control_raw = region_value(control_y_o)
        t2_raw = region_value(control_y_o + dt2_o)
        t1_raw = region_value(control_y_o + dt1_o)
        bg_raw = region_value(control_y_o + dbg_o)
        return control_raw, t1_raw, t2_raw, bg_raw

    def _compute_row(self, filename, control_raw, t1_raw, t2_raw, bg_raw, cfg):
        # raw color/grayscale photo: bands are darker than background
        control_net = bg_raw - control_raw
        t1_net = bg_raw - t1_raw
        t2_net = bg_raw - t2_raw

        tc1_ratio = (t1_net / control_net) if control_net != 0 else float("nan")
        tc2_ratio = (t2_net / control_net) if control_net != 0 else float("nan")

        row = {
            "filename": filename,
            "stat_used": "median" if self.use_median.get() else "mean",
            "control_raw": control_raw,
            "t1_raw": t1_raw,
            "t2_raw": t2_raw,
            "background_raw": bg_raw,
            "control_net": control_net,
            "t1_net": t1_net,
            "t2_net": t2_net,
            "t1_c_ratio": tc1_ratio,
            "t2_c_ratio": tc2_ratio,
            "control_y": cfg["control_y"],
            "box_h": cfg["box_h"],
            "dist_t2": cfg["dist_t2"],
            "dist_t1": cfg["dist_t1"],
            "dist_bg": cfg["dist_bg"],
        }
        return row, control_net, t1_net, t2_net, tc1_ratio, tc2_ratio

    # ---------------- Analyze CURRENT image ----------------

    def analyze_current(self):
        if self.raw_data is None:
            messagebox.showerror("Error", "Please load an image first!")
            return

        if self.current_path is not None:
            self.image_configs[self.current_path] = self._get_current_slider_config()
        cfg = self._get_current_slider_config()

        control_raw, t1_raw, t2_raw, bg_raw = self._measure_from_config(self.raw_data, cfg)
        filename = os.path.basename(self.current_path) if self.current_path else "unknown"
        row, control_net, t1_net, t2_net, tc1, tc2 = self._compute_row(
            filename, control_raw, t1_raw, t2_raw, bg_raw, cfg)

        self._plot_single(filename, control_net, t1_net, t2_net, tc1, tc2)
        self.append_rows_to_csv([row])
        messagebox.showinfo("Saved", f"Results for '{filename}' appended to:\n{self.csv_path}")

    def _plot_single(self, filename, control_net, t1_net, t2_net, tc1, tc2):
        labels = ['Control', 'T2', 'T1']
        net_values = [control_net, t2_net, t1_net]
        colors = ['blue', 'green', 'red']

        fig, axes = plt.subplots(1, 2, figsize=(11, 5))

        bars = axes[0].bar(labels, net_values, color=colors)
        axes[0].set_ylabel("Net Signal Intensity (background-subtracted)")
        axes[0].set_title(f"Band Intensities\n{filename}")
        for bar in bars:
            yval = bar.get_height()
            axes[0].text(bar.get_x() + bar.get_width() / 2, yval, f"{yval:.1f}",
                         ha='center', va='bottom', fontweight='bold')

        ratio_labels = ['T1 / Control', 'T2 / Control']
        ratio_values = [tc1, tc2]
        bars2 = axes[1].bar(ratio_labels, ratio_values, color=['red', 'green'])
        axes[1].set_ylabel("T / C Ratio")
        axes[1].set_title("Test-to-Control Ratio")
        for bar in bars2:
            yval = bar.get_height()
            axes[1].text(bar.get_x() + bar.get_width() / 2, yval, f"{yval:.4f}",
                         ha='center', va='bottom', fontweight='bold')

        plt.tight_layout()
        plt.show()

    # ---------------- Analyze ALL loaded images ----------------

    def analyze_all(self):
        if not self.image_paths:
            messagebox.showerror("Error", "Load at least one image first!")
            return

        # make sure the image currently on screen has its latest tweaks saved
        if self.current_path is not None:
            self.image_configs[self.current_path] = self._get_current_slider_config()

        rows = []
        filenames = []
        controls, t1s, t2s, tc1s, tc2s = [], [], [], [], []

        for path in self.image_paths:
            try:
                pil_img = Image.open(path)
                pil_img.load()
                arr = extract_channel_array(pil_img, self.channel_var.get())
            except Exception as e:
                messagebox.showwarning("Skipped", f"Could not open {os.path.basename(path)}:\n{e}")
                continue

            cfg = self.image_configs.get(path, self._get_current_slider_config())
            control_raw, t1_raw, t2_raw, bg_raw = self._measure_from_config(arr, cfg)
            filename = os.path.basename(path)
            row, control_net, t1_net, t2_net, tc1, tc2 = self._compute_row(
                filename, control_raw, t1_raw, t2_raw, bg_raw, cfg)

            rows.append(row)
            filenames.append(filename)
            controls.append(control_net)
            t1s.append(t1_net)
            t2s.append(t2_net)
            tc1s.append(tc1)
            tc2s.append(tc2)

        if not rows:
            return

        self.append_rows_to_csv(rows)
        self._plot_comparison(filenames, controls, t1s, t2s, tc1s, tc2s)
        messagebox.showinfo("Saved", f"Results for {len(rows)} image(s) appended to:\n{self.csv_path}")

    def _plot_comparison(self, filenames, controls, t1s, t2s, tc1s, tc2s):
        n = len(filenames)
        x = np.arange(n)
        width = 0.25

        fig, axes = plt.subplots(2, 1, figsize=(max(8, n * 1.6), 9))

        axes[0].bar(x - width, controls, width, label='Control', color='blue')
        axes[0].bar(x, t2s, width, label='T2', color='green')
        axes[0].bar(x + width, t1s, width, label='T1', color='red')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(filenames, rotation=20, ha='right')
        axes[0].set_ylabel("Net Signal Intensity")
        axes[0].set_title("Band Intensity Comparison Across Images")
        axes[0].legend()

        axes[1].bar(x - width / 2, tc1s, width, label='T1 / Control', color='red')
        axes[1].bar(x + width / 2, tc2s, width, label='T2 / Control', color='green')
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(filenames, rotation=20, ha='right')
        axes[1].set_ylabel("T / C Ratio")
        axes[1].set_title("Test-to-Control Ratio Comparison")
        axes[1].legend()

        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    root = tk.Tk()
    app = LFAAnalyzerApp(root)
    root.mainloop()
    
    
    
    