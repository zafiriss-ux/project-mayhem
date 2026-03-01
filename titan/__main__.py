"""
titan/__main__.py – package entry point for ``python -m titan``.

Delegates to titan.main.main() which initialises all engines,
registers Telegram callbacks, starts background threads and
launches the interactive menu.
"""

from titan.main import main

if __name__ == "__main__":
    main()
