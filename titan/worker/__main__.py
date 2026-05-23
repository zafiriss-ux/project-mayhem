"""
Entrypoint for `python -m titan.worker`.
Called by Docker worker container CMD.
"""
from titan.worker import main

if __name__ == "__main__":
    main()
