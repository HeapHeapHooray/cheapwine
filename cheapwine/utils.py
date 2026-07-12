import sys
from rich.console import Console
from rich.theme import Theme

# Custom theme inspired by uv/modern CLI tools
theme = Theme({
    "info": "dim cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "accent": "bold bright_blue",
    "bold": "bold",
    "command": "bold magenta",
    "dim": "dim",
    "highlight": "bold bright_cyan",
    "subtle": "bright_black",
})

console = Console(theme=theme)
console_err = Console(stderr=True, theme=theme)

def print_step(action: str, message: str, emoji: str = "✨"):
    """Prints a styled step message in uv style, e.g. '✨ Initialized Wine prefix in 2.3s'."""
    console.print(f"[success]{emoji} {action:<12}[/success] [bold]{message}[/bold]")

def print_info(action: str, message: str, emoji: str = "ℹ️"):
    """Prints a styled info message, e.g. 'ℹ️ Running      notepad.exe'."""
    console.print(f"[accent]{emoji} {action:<12}[/accent] {message}")

def print_warning(message: str):
    """Prints a warning message."""
    console.print(f"[warning]⚠️  Warning:[/warning] {message}")

def print_error(message: str):
    """Prints an error message to stderr."""
    console_err.print(f"[error]❌ Error:[/error] {message}")
