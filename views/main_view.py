import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
import threading
import logging
import webbrowser
import json

# Modular Configurations & Services
import config
from services import satellite_service, arduino_service

class MainView:
    def __init__(self, root):
        self.root = root
        self.root.title(config.WINDOW_TITLE)
        self.root.geometry(config.WINDOW_GEOMETRY)
        self.root.configure(bg=config.COLOR_BG)
        
        # Load local database name mappings
        self.satellite_db = satellite_service.load_satellite_data(config.DB_FILENAME)
        self.satellite_names = list(self.satellite_db.keys())
        
        # Create Core Frame
        self.main_frame = ttk.Frame(root, padding="15")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Set Grid layout sizing logic
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=1)
        
        # Autocomplete dropdown configuration state
        self.suggestion_listbox = None
        
        self.build_ui()
        self.setup_bindings()
        
        # Automatically discover active Arduino ports at startup
        self.auto_verify_ports()

    def build_ui(self):
        # Header Label
        header_lbl = ttk.Label(
            self.main_frame, 
            text="Satellite Arduino Exporter", 
            font=(config.FONT_FAMILY, 14, "bold")
        )
        header_lbl.grid(row=0, column=0, columnspan=2, pady=(0, 15))
        
        # Row 1: Satellite Name Input
        lbl_sat = ttk.Label(self.main_frame, text="Satellite Name:", font=(config.FONT_FAMILY, 10, "bold"))
        lbl_sat.grid(row=1, column=0, sticky="w", pady=2)
        
        self.entry_sat = ttk.Entry(self.main_frame, font=(config.FONT_FAMILY, 11))
        self.entry_sat.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        # Row 2: Arduino Port Input
        lbl_port = ttk.Label(self.main_frame, text="Arduino Port (e.g., COM3 or /dev/ttyACM0):", font=(config.FONT_FAMILY, 10, "bold"))
        lbl_port.grid(row=3, column=0, sticky="w", pady=2)
        
        self.entry_port = ttk.Entry(self.main_frame, font=(config.FONT_FAMILY, 11))
        self.entry_port.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        # Row 3: Baud Rate Input
        lbl_baud = ttk.Label(self.main_frame, text="Baud Rate:", font=(config.FONT_FAMILY, 10, "bold"))
        lbl_baud.grid(row=5, column=0, sticky="w", pady=2)
        
        self.entry_baud = ttk.Entry(self.main_frame, font=(config.FONT_FAMILY, 11))
        self.entry_baud.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.entry_baud.insert(0, "9600")
        
        # Row 4: Board Search Description filter
        lbl_desc = ttk.Label(self.main_frame, text="Arduino Board Description (for startup scan filter):", font=(config.FONT_FAMILY, 10, "bold"))
        lbl_desc.grid(row=7, column=0, sticky="w", pady=2)
        
        self.entry_desc = ttk.Entry(self.main_frame, font=(config.FONT_FAMILY, 11))
        self.entry_desc.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        self.entry_desc.insert(0, "Arduino")
        
        # Row 5: Action submission trigger button
        self.btn_fetch = ttk.Button(self.main_frame, text="Fetch & Send Data", command=self.on_fetch_clicked)
        self.btn_fetch.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        
        # Row 6: Log Console Box
        lbl_log = ttk.Label(self.main_frame, text="System Log Console:", font=(config.FONT_FAMILY, 9, "bold"))
        lbl_log.grid(row=10, column=0, sticky="w", pady=2)
        
        self.txt_log = ScrolledText(self.main_frame, height=8, wrap=tk.WORD, font=(config.FONT_MONO, 9))
        self.txt_log.grid(row=11, column=0, columnspan=2, sticky="nsew", pady=2)
        self.txt_log.tag_config("error", foreground=config.COLOR_ERROR)
        self.txt_log.tag_config("success", foreground=config.COLOR_SUCCESS)
        self.txt_log.tag_config("info", foreground="blue")
        
        self.main_frame.rowconfigure(11, weight=1)
        
        # Floating Listbox for autocomplete popup recommendations
        self.suggestion_listbox = tk.Listbox(
            self.main_frame, 
            width=50, 
            height=5, 
            relief="solid", 
            borderwidth=1,
            highlightbackground="#cccccc"
        )

    def setup_bindings(self):
        self.entry_sat.bind("<FocusIn>", self.on_entry_click)
        self.entry_sat.bind("<KeyRelease>", self.on_entry_change)
        self.suggestion_listbox.bind("<ButtonRelease-1>", self.on_suggestion_select)

    def log_message(self, message, tag=None):
        """Appends status lines dynamically in a thread-safe manner."""
        self.root.after(0, self._safe_log_append, message, tag)

    def _safe_log_append(self, message, tag):
        self.txt_log.insert(tk.END, message + "\n", tag)
        self.txt_log.see(tk.END)

    def clear_logs(self):
        self.txt_log.delete("1.0", tk.END)

    # Autocomplete dropdown handlers
    def on_entry_click(self, event):
        self.render_suggestions()

    def on_entry_change(self, event):
        self.render_suggestions()

    def render_suggestions(self):
        user_input = self.entry_sat.get()
        self.suggestion_listbox.delete(0, tk.END)
        
        # If the input matches exactly a name, do not show recommendations
        if user_input in self.satellite_names:
            self.suggestion_listbox.place_forget()
            return
            
        matched_names = [name for name in self.satellite_names if user_input.lower() in name.lower()]
        
        if matched_names:
            # Anchor suggestion coordinates directly relative to input box
            pos_x = self.entry_sat.winfo_x()
            pos_y = self.entry_sat.winfo_y()
            offset_y = self.entry_sat.winfo_height()
            
            self.suggestion_listbox.config(height=min(len(matched_names), 5))
            for name in matched_names:
                self.suggestion_listbox.insert(tk.END, name)
                
            self.suggestion_listbox.place(x=pos_x, y=pos_y + offset_y)
            self.suggestion_listbox.lift()
        else:
            self.suggestion_listbox.place_forget()

    def on_suggestion_select(self, event):
        try:
            selection_tuple = self.suggestion_listbox.curselection()
            if selection_tuple:
                selected_name = self.suggestion_listbox.get(selection_tuple)
                self.entry_sat.delete(0, tk.END)
                self.entry_sat.insert(0, selected_name)
        except Exception as e:
            logging.error(f"Failed to fetch selected list choice: {str(e)}")
        finally:
            self.suggestion_listbox.place_forget()

    # Port discoverer
    def auto_verify_ports(self):
        filter_str = self.entry_desc.get().strip()
        self.log_message("Scanning interface ports for Arduino devices...", "info")
        ports = arduino_service.find_arduino_ports(filter_str)
        if ports:
            self.log_message("Compatible hardware port(s) detected:", "success")
            for p in ports:
                self.log_message(f" -> {p}", "success")
            # Automatically populate top match if input is currently empty
            if not self.entry_port.get():
                self.entry_port.insert(0, ports[0])
        else:
            self.log_message("No default Arduino ports detected matching criteria.", "error")

    # Flow coordinator
    def on_fetch_clicked(self):
        sat_name = self.entry_sat.get().strip()
        port = self.entry_port.get().strip()
        baud_str = self.entry_baud.get().strip()
        
        if not all([sat_name, port, baud_str]):
            self.log_message("Error: Name, Port, and Baud rate are required fields.", "error")
            return
            
        try:
            baud_rate = int(baud_str)
        except ValueError:
            self.log_message("Error: Baud rate must be a valid integer.", "error")
            return
            
        self.clear_logs()
        
        # Display the external browser portal
        self.display_web_browser()
        
        # Run process asynchronous runner to prevent main loop hangs
        worker_thread = threading.Thread(
            target=self.transfer_process_worker,
            args=(sat_name, port, baud_rate),
            daemon=True
        )
        worker_thread.start()

    def display_web_browser(self):
        """Opens N2YO website and renders a non-blocking confirmation dialog."""
        web_window = tk.Toplevel(self.root)
        web_window.title("N2YO Portal")
        web_window.geometry("350x120")
        
        info_lbl = ttk.Label(
            web_window, 
            text="Launching N2YO.com tracker portal\nin your default web browser...",
            justify="center",
            font=(config.FONT_FAMILY, 10)
        )
        info_lbl.pack(pady=20)
        
        try:
            webbrowser.open("https://www.n2yo.com/")
        except Exception as e:
            self.log_message(f"Browser Launch notice: {str(e)}", "error")

    def transfer_process_worker(self, sat_name, port, baud_rate):
        """Asynchronous execution step thread."""
        sat_id = satellite_service.get_satellite_id(sat_name, self.satellite_db)
        if not sat_id:
            self.log_message(f"Error: Satellite '{sat_name}' is not registered in index catalog.", "error")
            return
            
        self.log_message(f"Retrieving parameters for '{sat_name}' (ID: {sat_id})...")
        
        # 1. Network API pull
        try:
            tle_str = satellite_service.fetch_tle_data(
                sat_id, 
                config.N2YO_API_KEY, 
                config.MAX_RETRIES, 
                config.TIMEOUT
            )
            self.log_message("Satellite TLE block retrieved.", "success")
        except Exception as e:
            self.log_message(f"Pipeline Interrupted: {str(e)}", "error")
            return
            
        # 2. Computational mechanics step
        try:
            orbital_data = satellite_service.calculate_orbital_data(sat_name, tle_str)
            self.log_message("Orbital tracking factors successfully derived.", "success")
        except Exception as e:
            self.log_message(f"Math calculation failed: {str(e)}", "error")
            return
            
        # 3. Save local JSON document capture
        filename = f"{sat_name}.json"
        try:
            with open(filename, "w") as outfile:
                json.dump(orbital_data, outfile, indent=4)
            self.log_message(f"Wrote calculated elements data to '{filename}' locally.", "success")
        except Exception as e:
            self.log_message(f"Local file write warning: {str(e)}", "error")
            
        # 4. Microcontroller Serial transfer
        self.log_message(f"Verifying serial link status on {port}...")
        try:
            arduino_service.send_data_to_arduino(port, baud_rate, orbital_data)
            self.log_message("Transmission verified. Data written successfully to microcontroller.", "success")
        except Exception as e:
            self.log_message(f"Data transfer failed: {str(e)}", "error")
            return
            
        self.log_message("Operation complete.", "info")