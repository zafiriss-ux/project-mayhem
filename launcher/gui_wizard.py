"""
TITAN Launcher — Tkinter GUI Setup Wizard

Graphical first-run setup for beginners.
Replaces console prompts with user-friendly forms.

Workflow:
  1. WelcomeFrame: Logo + version + "Continue" button
  2. ProgressFrame: Pre-flight checks (Python, disk, data dir) with progress bar
  3. CredentialsFrame: Form for Garmin, Telegram, OpenAI API keys
  4. SuccessFrame: "Setup Complete! Start TITAN" button

Requirements:
  - tkinter (bundled with Python 3.11+)
  - ttk for modern widgets (also bundled)
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Optional

from launcher import __version__
from launcher.validator import validate_environment
from launcher.wizard import write_env, validate_garmin_username, validate_telegram_token, validate_openai_key


# ══════════════════════════════════════════════════════════════════════════════
# Main Wizard Window
# ══════════════════════════════════════════════════════════════════════════════

class WizardWindow:
    """
    Main Tkinter window manager for setup wizard.

    Manages frame transitions: Welcome → Progress → Credentials → Success
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"TITAN Setup Wizard v{__version__}")
        self.root.geometry("600x500")
        self.root.resizable(False, False)

        # Data storage
        self.config: Dict[str, str] = {}
        self.validation_passed = False

        # Current frame
        self.current_frame: Optional[tk.Frame] = None

        # Start with welcome screen
        self.show_welcome()

    def switch_frame(self, frame_class, **kwargs):
        """Switch to a different frame."""
        if self.current_frame:
            self.current_frame.destroy()
        self.current_frame = frame_class(self.root, self, **kwargs)
        self.current_frame.pack(fill=tk.BOTH, expand=True)

    def show_welcome(self):
        """Show welcome screen."""
        self.switch_frame(WelcomeFrame)

    def show_progress(self):
        """Show pre-flight check progress."""
        self.switch_frame(ProgressFrame)

    def show_credentials(self):
        """Show credentials input form."""
        self.switch_frame(CredentialsFrame)

    def show_success(self):
        """Show success screen."""
        self.switch_frame(SuccessFrame)

    def on_complete(self):
        """Called when wizard completes successfully."""
        self.root.quit()


# ══════════════════════════════════════════════════════════════════════════════
# Welcome Frame
# ══════════════════════════════════════════════════════════════════════════════

class WelcomeFrame(ttk.Frame):
    """Welcome screen with logo and Continue button."""

    def __init__(self, parent, wizard: WizardWindow):
        super().__init__(parent)
        self.wizard = wizard

        # Header
        header = ttk.Label(
            self,
            text="🏃 TITAN OS",
            font=("Arial", 32, "bold"),
            foreground="#2E86AB"
        )
        header.pack(pady=(60, 10))

        version = ttk.Label(
            self,
            text=f"Version {__version__}",
            font=("Arial", 12),
            foreground="#555"
        )
        version.pack()

        subtitle = ttk.Label(
            self,
            text="Closed-Loop Sovereign Training Intelligence",
            font=("Arial", 14, "italic"),
            foreground="#777"
        )
        subtitle.pack(pady=(5, 40))

        # Welcome message
        welcome_text = (
            "Welcome to TITAN Setup Wizard!\n\n"
            "This wizard will guide you through the initial setup:\n"
            "  • Environment validation (Python, disk space)\n"
            "  • Garmin Connect credentials\n"
            "  • Telegram bot configuration\n"
            "  • Optional API keys (OpenAI, Weather)\n\n"
            "Setup takes about 2 minutes."
        )
        message = ttk.Label(
            self,
            text=welcome_text,
            font=("Arial", 11),
            justify=tk.CENTER,
            foreground="#333"
        )
        message.pack(pady=20)

        # Continue button
        btn = ttk.Button(
            self,
            text="Continue →",
            command=self.on_continue,
            width=20
        )
        btn.pack(pady=30)

    def on_continue(self):
        """Switch to progress frame."""
        self.wizard.show_progress()


# ══════════════════════════════════════════════════════════════════════════════
# Progress Frame (Pre-flight Checks)
# ══════════════════════════════════════════════════════════════════════════════

class ProgressFrame(ttk.Frame):
    """Pre-flight checks with progress bar."""

    def __init__(self, parent, wizard: WizardWindow):
        super().__init__(parent)
        self.wizard = wizard

        # Header
        header = ttk.Label(
            self,
            text="Running Pre-flight Checks",
            font=("Arial", 18, "bold")
        )
        header.pack(pady=(40, 20))

        # Status label
        self.status_label = ttk.Label(
            self,
            text="Checking Python version...",
            font=("Arial", 11)
        )
        self.status_label.pack(pady=10)

        # Progress bar
        self.progress = ttk.Progressbar(
            self,
            length=400,
            mode='determinate'
        )
        self.progress.pack(pady=20)

        # Results text
        self.results_text = tk.Text(
            self,
            height=10,
            width=60,
            font=("Courier", 10),
            state=tk.DISABLED
        )
        self.results_text.pack(pady=10)

        # Start checks automatically
        self.after(500, self.run_checks)

    def log(self, message: str):
        """Append message to results text."""
        self.results_text.config(state=tk.NORMAL)
        self.results_text.insert(tk.END, message + "\n")
        self.results_text.see(tk.END)
        self.results_text.config(state=tk.DISABLED)
        self.update_idletasks()

    def run_checks(self):
        """Run all pre-flight checks."""
        success, errors = validate_environment()

        self.progress['value'] = 100
        self.update_idletasks()

        if success:
            self.status_label.config(text="✅ All checks passed!", foreground="green")
            self.log("\n✅ Environment validation complete.")
            self.wizard.validation_passed = True
            self.after(1000, self.on_complete)
        else:
            self.status_label.config(text="❌ Validation failed", foreground="red")
            self.log("\n❌ Pre-flight checks failed:\n")
            for error in errors:
                self.log(f"  • {error.message}")
                if error.remediation:
                    self.log(f"    → {error.remediation}")
            messagebox.showerror(
                "Validation Failed",
                "Cannot proceed with setup. Fix the issues above and try again."
            )
            self.after(2000, sys.exit)

    def on_complete(self):
        """Move to credentials frame."""
        self.wizard.show_credentials()


# ══════════════════════════════════════════════════════════════════════════════
# Credentials Frame
# ══════════════════════════════════════════════════════════════════════════════

class CredentialsFrame(ttk.Frame):
    """Credentials input form."""

    def __init__(self, parent, wizard: WizardWindow):
        super().__init__(parent)
        self.wizard = wizard

        # Scrollable canvas (in case form is too long)
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Header
        header = ttk.Label(
            scrollable_frame,
            text="Enter Your Credentials",
            font=("Arial", 18, "bold")
        )
        header.grid(row=0, column=0, columnspan=2, pady=(20, 30))

        # Garmin section
        self.add_section_header(scrollable_frame, 1, "Garmin Connect")
        self.garmin_user = self.add_field(
            scrollable_frame, 2, "Username or Email:", validate_garmin_username
        )
        self.garmin_pass = self.add_field(
            scrollable_frame, 3, "Password:", show="*"
        )

        # Telegram section
        self.add_section_header(scrollable_frame, 4, "Telegram Bot")
        self.add_help(scrollable_frame, 5, "Create bot with @BotFather. Get token from BotFather message.")
        self.telegram_token = self.add_field(
            scrollable_frame, 6, "Bot Token:", validate_telegram_token
        )
        self.telegram_chat = self.add_field(
            scrollable_frame, 7, "Chat ID:", placeholder="123456789"
        )

        # OpenAI section (optional)
        self.add_section_header(scrollable_frame, 8, "OpenAI API (Optional)")
        self.add_help(scrollable_frame, 9, "For GPT-4 coaching narratives. Leave blank to skip.")
        self.openai_key = self.add_field(
            scrollable_frame, 10, "API Key:", placeholder="sk-...", optional=True, validator=validate_openai_key
        )

        # Weather API section (optional)
        self.add_section_header(scrollable_frame, 11, "Weather API (Optional)")
        self.add_help(scrollable_frame, 12, "OpenWeatherMap or similar. Leave blank to skip.")
        self.weather_key = self.add_field(
            scrollable_frame, 13, "API Key:", optional=True
        )

        # Submit button
        submit_btn = ttk.Button(
            scrollable_frame,
            text="Save & Continue",
            command=self.on_submit,
            width=25
        )
        submit_btn.grid(row=14, column=0, columnspan=2, pady=30)

    def add_section_header(self, parent, row, text):
        """Add section header label."""
        lbl = ttk.Label(
            parent,
            text=text,
            font=("Arial", 13, "bold"),
            foreground="#2E86AB"
        )
        lbl.grid(row=row, column=0, columnspan=2, sticky="w", padx=20, pady=(15, 5))

    def add_help(self, parent, row, text):
        """Add help text."""
        lbl = ttk.Label(
            parent,
            text=text,
            font=("Arial", 9, "italic"),
            foreground="#666",
            wraplength=500
        )
        lbl.grid(row=row, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 5))

    def add_field(self, parent, row, label, validator=None, show=None, placeholder="", optional=False):
        """Add input field with label."""
        lbl = ttk.Label(parent, text=label, font=("Arial", 11))
        lbl.grid(row=row, column=0, sticky="w", padx=20, pady=5)

        entry = ttk.Entry(parent, width=40, show=show)
        entry.grid(row=row, column=1, sticky="w", padx=10, pady=5)

        if placeholder:
            entry.insert(0, placeholder)
            entry.config(foreground="gray")
            entry.bind("<FocusIn>", lambda e: self.clear_placeholder(entry, placeholder))

        # Store validator
        entry.validator = validator
        entry.optional = optional

        return entry

    @staticmethod
    def clear_placeholder(entry, placeholder):
        """Clear placeholder text on focus."""
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(foreground="black")

    def on_submit(self):
        """Validate and save credentials."""
        config = {}

        # Garmin (required)
        garmin_user = self.garmin_user.get().strip()
        garmin_pass = self.garmin_pass.get().strip()
        if not garmin_user or not garmin_pass:
            messagebox.showerror("Error", "Garmin credentials are required.")
            return
        if hasattr(self.garmin_user, 'validator') and self.garmin_user.validator:
            if not self.garmin_user.validator(garmin_user):
                messagebox.showerror("Error", "Invalid Garmin username format.")
                return
        config['GARMIN_USERNAME'] = garmin_user
        config['GARMIN_PASSWORD'] = garmin_pass

        # Telegram (required)
        telegram_token = self.telegram_token.get().strip()
        telegram_chat = self.telegram_chat.get().strip()
        if not telegram_token or not telegram_chat:
            messagebox.showerror("Error", "Telegram bot token and chat ID are required.")
            return
        if hasattr(self.telegram_token, 'validator') and self.telegram_token.validator:
            if not self.telegram_token.validator(telegram_token):
                messagebox.showerror("Error", "Invalid Telegram bot token format.")
                return
        config['TELEGRAM_BOT_TOKEN'] = telegram_token
        config['TELEGRAM_CHAT_ID'] = telegram_chat

        # OpenAI (optional)
        openai_key = self.openai_key.get().strip()
        if openai_key and openai_key != "sk-...":
            if hasattr(self.openai_key, 'validator') and self.openai_key.validator:
                if not self.openai_key.validator(openai_key):
                    messagebox.showerror("Error", "Invalid OpenAI API key format (must start with sk-).")
                    return
            config['OPENAI_API_KEY'] = openai_key

        # Weather (optional)
        weather_key = self.weather_key.get().strip()
        if weather_key:
            config['WEATHER_API_KEY'] = weather_key

        # Save to .env
        try:
            write_env(config)
            self.wizard.config = config
            self.wizard.show_success()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration:\n{e}")


# ══════════════════════════════════════════════════════════════════════════════
# Success Frame
# ══════════════════════════════════════════════════════════════════════════════

class SuccessFrame(ttk.Frame):
    """Success screen with Start TITAN button."""

    def __init__(self, parent, wizard: WizardWindow):
        super().__init__(parent)
        self.wizard = wizard

        # Success icon
        icon = ttk.Label(
            self,
            text="✅",
            font=("Arial", 72)
        )
        icon.pack(pady=(60, 20))

        # Success message
        header = ttk.Label(
            self,
            text="Setup Complete!",
            font=("Arial", 24, "bold"),
            foreground="green"
        )
        header.pack(pady=10)

        message = ttk.Label(
            self,
            text=(
                "TITAN is configured and ready to run.\n\n"
                "Your credentials are saved securely.\n"
                "Database will be created on first run."
            ),
            font=("Arial", 12),
            justify=tk.CENTER
        )
        message.pack(pady=20)

        # Button frame for horizontal layout
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=20)

        # Start button
        start_btn = ttk.Button(
            btn_frame,
            text="Start TITAN",
            command=self.on_start,
            width=20
        )
        start_btn.grid(row=0, column=0, padx=10)

        # Diagnostics button (optional — for troubleshooting)
        diag_btn = ttk.Button(
            btn_frame,
            text="📊 Diagnostics",
            command=self.on_diagnostics,
            width=20
        )
        diag_btn.grid(row=0, column=1, padx=10)

    def on_start(self):
        """Close wizard and proceed to kernel."""
        self.wizard.on_complete()

    def on_diagnostics(self):
        """Show diagnostics dialog with path info + open logs folder."""
        import subprocess
        import platform

        # Get diagnostics info
        from launcher.paths import get_path_info
        from launcher.validator import get_data_directory

        path_info = get_path_info()
        data_dir = get_data_directory()
        logs_dir = data_dir / 'logs'

        # Build message
        msg = "TITAN Diagnostics\n" + "="*50 + "\n\n"
        msg += f"Frozen mode: {'Yes (TITAN.exe)' if path_info['frozen'] else 'No (Python script)'}\n"
        msg += f"Executable: {path_info['sys.executable']}\n"
        msg += f"Bundle dir: {path_info['bundle_dir']}\n"
        msg += f"Data directory: {data_dir}\n"
        msg += f"Logs directory: {logs_dir}\n\n"

        if logs_dir.exists():
            msg += "Click OK to open logs folder."
        else:
            msg += "Logs folder will be created on first run."

        # Show dialog
        messagebox.showinfo("Diagnostics", msg)

        # Open logs folder if it exists
        if logs_dir.exists():
            try:
                if platform.system() == 'Windows':
                    subprocess.run(['explorer', str(logs_dir)])
                elif platform.system() == 'Darwin':  # macOS
                    subprocess.run(['open', str(logs_dir)])
                else:  # Linux
                    subprocess.run(['xdg-open', str(logs_dir)])
            except Exception:
                # Best effort — don't crash if file explorer fails
                pass


# ══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════════════════

def run_gui_wizard() -> bool:
    """
    Run Tkinter GUI wizard.

    Returns:
        True if setup completed successfully, False if cancelled/failed
    """
    try:
        root = tk.Tk()
        WizardWindow(root)
        root.mainloop()
        return True
    except KeyboardInterrupt:
        return False
    except Exception as e:
        messagebox.showerror("Error", f"Wizard failed:\n{e}")
        return False


if __name__ == '__main__':
    run_gui_wizard()
