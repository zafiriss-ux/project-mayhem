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

__version__ = "5.7.0"
__kernel_version__ = "5.7.0"  # Expected titan.__version__
