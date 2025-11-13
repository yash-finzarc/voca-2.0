from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox
import os
from dotenv import load_dotenv

from src.voca.config import Config
from src.voca.orchestrator import VocaOrchestrator
from src.voca.twilio_voice import TwilioCallManager
from src.voca.twilio_config import get_twilio_config


class VocaApp:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        self.root = tk.Tk()
        self.root.title("Voca - AI Voice Assistant with Twilio")
        self.root.geometry("1000x700")

        self.log_text = None
        self.phone_entry = None
        self.call_status_label = None
        self.twilio_manager = None
        self.country_var = None
        self.country_combo = None
        self.country_code_label = None
        self.phone_format_label = None
        self._status_refresh_job = None
        self._status_refresh_interval_ms = 25000

        self.orchestrator = VocaOrchestrator(on_log=self.append_log)
        
        # Initialize Twilio manager if configured
        config = get_twilio_config()
        if config.validate():
            self.twilio_manager = TwilioCallManager(self.orchestrator)
        else:
            self.append_log("WARNING: Twilio not configured. Please set up environment variables.")

        self._build_ui()

    def get_country_codes(self):
        """Get dictionary of country codes for phone number input."""
        return {
            "United States (+1)": "+1",
            "Canada (+1)": "+1", 
            "United Kingdom (+44)": "+44",
            "India (+91)": "+91",
            "Australia (+61)": "+61",
            "Germany (+49)": "+49",
            "France (+33)": "+33",
            "Japan (+81)": "+81",
            "China (+86)": "+86",
            "Brazil (+55)": "+55",
            "Mexico (+52)": "+52",
            "Russia (+7)": "+7",
            "South Korea (+82)": "+82",
            "Italy (+39)": "+39",
            "Spain (+34)": "+34",
            "Netherlands (+31)": "+31",
            "Sweden (+46)": "+46",
            "Norway (+47)": "+47",
            "Denmark (+45)": "+45",
            "Finland (+358)": "+358",
            "Poland (+48)": "+48",
            "Turkey (+90)": "+90",
            "South Africa (+27)": "+27",
            "Egypt (+20)": "+20",
            "Nigeria (+234)": "+234",
            "Kenya (+254)": "+254",
            "Israel (+972)": "+972",
            "Saudi Arabia (+966)": "+966",
            "UAE (+971)": "+971",
            "Singapore (+65)": "+65",
            "Malaysia (+60)": "+60",
            "Thailand (+66)": "+66",
            "Philippines (+63)": "+63",
            "Indonesia (+62)": "+62",
            "Vietnam (+84)": "+84",
            "Argentina (+54)": "+54",
            "Chile (+56)": "+56",
            "Colombia (+57)": "+57",
            "Peru (+51)": "+51",
            "Venezuela (+58)": "+58"
        }

    def on_country_selected(self, event=None):
        """Handle country selection change."""
        if self.country_var and self.country_code_label:
            country_name = self.country_var.get()
            country_codes = self.get_country_codes()
            country_code = country_codes.get(country_name, "+1")
            self.country_code_label.config(text=country_code)
            # Update phone format display
            self.update_phone_format()

    def get_full_phone_number(self):
        """Get the complete phone number with country code."""
        if not self.phone_entry or not self.country_code_label:
            return ""
        
        phone_number = self.phone_entry.get().strip()
        country_code = self.country_code_label.cget("text")
        
        if not phone_number:
            return ""
        
        # Remove any existing country code from phone number
        if phone_number.startswith("+"):
            phone_number = phone_number[1:]
        elif phone_number.startswith(country_code[1:]):  # Remove country code without +
            phone_number = phone_number[len(country_code[1:]):]
        
        return f"{country_code}{phone_number}"

    def update_phone_format(self, event=None):
        """Update the phone format display."""
        if self.phone_format_label:
            full_number = self.get_full_phone_number()
            if full_number:
                self.phone_format_label.config(text=f"Will call: {full_number}")
            else:
                self.phone_format_label.config(text="")

    def _build_ui(self):
        frm = ttk.Frame(self.root)
        frm.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create notebook for tabs
        notebook = ttk.Notebook(frm)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Local Voice Tab
        local_frame = ttk.Frame(notebook)
        notebook.add(local_frame, text="Local Voice")
        
        # Twilio Calls Tab
        twilio_frame = ttk.Frame(notebook)
        notebook.add(twilio_frame, text="Twilio Calls")
        
        # Build local voice controls
        self._build_local_voice_ui(local_frame)
        
        # Build Twilio controls
        self._build_twilio_ui(twilio_frame)
        
        # Status bar
        status_frame = ttk.Frame(frm)
        status_frame.pack(fill=tk.X, pady=5)
        self.call_status_label = ttk.Label(status_frame, text="Ready")
        self.call_status_label.pack(side=tk.LEFT)
        
        # Logs
        log_lbl = ttk.Label(frm, text="Logs")
        log_lbl.pack(anchor=tk.W)
        self.log_text = tk.Text(frm, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True)
    
    def _build_local_voice_ui(self, parent):
        """Build local voice interface."""
        # Controls
        ctrl_row = ttk.Frame(parent)
        ctrl_row.pack(fill=tk.X, pady=5)
        ttk.Button(ctrl_row, text="Start Continuous Call", command=self.start_continuous_call).pack(side=tk.LEFT, padx=6)
        ttk.Button(ctrl_row, text="Stop", command=self.stop_continuous_call).pack(side=tk.LEFT, padx=6)
        ttk.Button(ctrl_row, text="One Minute Test", command=self.start_one_minute_call).pack(side=tk.LEFT, padx=6)
    
    def _build_twilio_ui(self, parent):
        """Build Twilio call interface."""
        if not self.twilio_manager:
            ttk.Label(parent, text="Twilio not configured. Please set up environment variables.", 
                     foreground="red").pack(pady=20)
            return
        
        # Phone number input with country code selection
        phone_frame = ttk.Frame(parent)
        phone_frame.pack(fill=tk.X, pady=5)
        
        # Country code selection
        country_frame = ttk.Frame(phone_frame)
        country_frame.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(country_frame, text="Country:").pack(side=tk.LEFT)
        
        self.country_var = tk.StringVar(value="United States (+1)")
        self.country_combo = ttk.Combobox(country_frame, textvariable=self.country_var, 
                                        values=list(self.get_country_codes().keys()), 
                                        state="readonly", width=20)
        self.country_combo.pack(side=tk.LEFT, padx=5)
        self.country_combo.bind("<<ComboboxSelected>>", self.on_country_selected)
        
        # Phone number input
        phone_input_frame = ttk.Frame(phone_frame)
        phone_input_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(phone_input_frame, text="Phone:").pack(side=tk.LEFT)
        
        self.country_code_label = ttk.Label(phone_input_frame, text="+1")
        self.country_code_label.pack(side=tk.LEFT, padx=2)
        
        self.phone_entry = ttk.Entry(phone_input_frame, width=15)
        self.phone_entry.pack(side=tk.LEFT, padx=2)
        self.phone_entry.insert(0, "5854604655")  # Default number without country code
        
        # Show full phone number format
        self.phone_format_label = ttk.Label(phone_frame, text="", foreground="gray")
        self.phone_format_label.pack(side=tk.LEFT, padx=10)
        
        # Update phone format display when phone number changes
        self.phone_entry.bind("<KeyRelease>", self.update_phone_format)
        
        # Call controls
        call_frame = ttk.Frame(parent)
        call_frame.pack(fill=tk.X, pady=5)
        ttk.Button(call_frame, text="Start Twilio Server", command=self.start_twilio_server).pack(side=tk.LEFT, padx=6)
        ttk.Button(call_frame, text="Make Call", command=self.make_twilio_call).pack(side=tk.LEFT, padx=6)
        ttk.Button(call_frame, text="Hang Up All", command=self.hangup_all_calls).pack(side=tk.LEFT, padx=6)
        ttk.Button(call_frame, text="Refresh Status", command=lambda: self.refresh_call_status(schedule_next=True, reset_timer=True)).pack(side=tk.LEFT, padx=6)
        
        # Call status
        status_frame = ttk.LabelFrame(parent, text="Call Status")
        status_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.twilio_status_text = tk.Text(status_frame, height=10)
        self.twilio_status_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.twilio_status_text.insert(tk.END, "Call status will auto-refresh every 25 seconds.\nClick 'Refresh Status' to update immediately.\n")
        
        # Kick off the auto-refresh loop
        self.refresh_call_status(schedule_next=True, reset_timer=False)

    def append_log(self, msg: str):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def start_one_minute_call(self):
        def _worker():
            try:
                self.orchestrator.run_one_minute_interaction(duration_sec=30)
            except Exception as e:
                self.append_log(f"Call failed: {e}")
        threading.Thread(target=_worker, daemon=True).start()

    def start_continuous_call(self):
        def _worker():
            try:
                self.orchestrator.run_continuous_vad_loop()
            except Exception as e:
                self.append_log(f"Call failed: {e}")
        threading.Thread(target=_worker, daemon=True).start()

    def stop_continuous_call(self):
        setattr(self.orchestrator, "_vad_stop", True)
    
    def start_twilio_server(self):
        """Start the Twilio webhook server."""
        if not self.twilio_manager:
            messagebox.showerror("Error", "Twilio not configured")
            return
        
        def _worker():
            try:
                self.twilio_manager.start()
                self.append_log("Twilio server started successfully")
                self.call_status_label.config(text="Twilio Server Running")
            except Exception as e:
                self.append_log(f"Failed to start Twilio server: {e}")
                messagebox.showerror("Error", f"Failed to start Twilio server: {e}")
        
        threading.Thread(target=_worker, daemon=True).start()
    
    def make_twilio_call(self):
        """Make an outbound call using Twilio."""
        if not self.twilio_manager:
            messagebox.showerror("Error", "Twilio not configured")
            return
        
        phone_number = self.get_full_phone_number()
        if not phone_number:
            messagebox.showerror("Error", "Please enter a phone number")
            return
        
        def _worker():
            try:
                call_sid = self.twilio_manager.make_call(phone_number)
                if call_sid:
                    self.append_log(f"Call initiated to {phone_number}, SID: {call_sid}")
                    if self.call_status_label:
                        self.call_status_label.config(text=f"Calling {phone_number}")
                else:
                    self.append_log(f"Failed to initiate call to {phone_number}")
                    messagebox.showerror("Error", "Failed to make call")
            except Exception as e:
                self.append_log(f"Call error: {e}")
                messagebox.showerror("Error", f"Call failed: {e}")
        
        threading.Thread(target=_worker, daemon=True).start()
    
    def hangup_all_calls(self):
        """Hang up all active calls."""
        if not self.twilio_manager:
            messagebox.showerror("Error", "Twilio not configured")
            return
        
        try:
            self.twilio_manager.hangup_all_calls()
            self.append_log("All calls hung up")
            self.call_status_label.config(text="All calls ended")
        except Exception as e:
            self.append_log(f"Error hanging up calls: {e}")
            messagebox.showerror("Error", f"Failed to hang up calls: {e}")
    
    def refresh_call_status(self, schedule_next: bool = True, reset_timer: bool = False):
        """Refresh the call status display, optionally scheduling the next refresh."""
        if not self.twilio_manager:
            return

        if reset_timer and self._status_refresh_job:
            self.root.after_cancel(self._status_refresh_job)
            self._status_refresh_job = None

        def _worker():
            try:
                status = self.twilio_manager.get_call_status()
                breakdown = self.twilio_manager.fetch_call_history(limit=15)
            except Exception as exc:
                self.root.after(0, lambda: self._update_status_text_error(exc, schedule_next))
                return

            def _update():
                lines = []
                lines.append(f"Models ready: {'Yes' if status.get('models_ready') else 'No'}")
                lines.append(f"Active calls (internal): {status.get('active_calls', 0)}")
                lines.append("")
                lines.append("Call Breakdown (last fetch):")

                sections = [
                    ("ongoing", "Active / In Progress"),
                    ("declined", "Declined / Failed"),
                    ("completed", "Completed"),
                    ("others", "Other Statuses"),
                ]

                for key, title in sections:
                    entries = breakdown.get(key, [])
                    lines.append(f"{title} ({len(entries)})")
                    if entries:
                        for call in entries[:5]:
                            start_time = call.get("start_time") or "Unknown"
                            status_text = call.get("status", "unknown")
                            duration = call.get("duration_human") or "-"
                            to_number = call.get("to_number") or call.get("from_number") or "Unknown number"
                            lines.append(f"  • {status_text} | {to_number}")
                            lines.append(f"    Started: {start_time} | Duration: {duration}")
                    else:
                        lines.append("  • No calls")
                    lines.append("")

                self.twilio_status_text.delete(1.0, tk.END)
                self.twilio_status_text.insert(tk.END, "\n".join(lines))

                if schedule_next:
                    self._status_refresh_job = self.root.after(
                        self._status_refresh_interval_ms,
                        self.refresh_call_status,
                    )

            self.root.after(0, _update)

        threading.Thread(target=_worker, daemon=True).start()

    def _update_status_text_error(self, error: Exception, schedule_next: bool):
        self.twilio_status_text.delete(1.0, tk.END)
        self.twilio_status_text.insert(tk.END, f"Error fetching call status: {error}\n")
        if schedule_next:
            self._status_refresh_job = self.root.after(
                self._status_refresh_interval_ms,
                self.refresh_call_status,
            )

    def run(self):
        self.root.mainloop()


