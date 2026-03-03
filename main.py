#!/usr/bin/env python3
"""
TITAN v51 – root-level launcher.

Usage (from project root):
    python main.py
"""
import os
import sys

# Ensure the project root is on sys.path so `titan` resolves as a package.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from titan.main import main

if __name__ == "__main__":
    main()
