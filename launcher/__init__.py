"""
TITAN Launcher — Distribution Layer

Beginner-friendly one-click launcher for TITAN OS.
Handles environment validation, first-run setup, and kernel orchestration.

Architecture Boundary:
  Launcher (this layer)  → UX, validation, packaging
  Kernel (titan/)        → Science, orchestration, training logic

The launcher never performs training computations.
The kernel never prints setup instructions.
"""

# One version for launcher and kernel, from pyproject.toml (AGENTS RE-01).
from titan import __version__  # noqa: E402, F401
