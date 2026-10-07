import os
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from airflow.app import main

if __name__ == "__main__":
    main()
