"""
24bit7 - command-line interface.

All the logic lives in engine.py; this file is just the console front end.
It passes `print` as the progress reporter and console prompts as the
callbacks, so the engine stays free of input()/print() and can be driven
by a GUI in exactly the same way.
"""

import engine


def ask_producer():
    return input("\nBuild a playlist from this record's producer? (y/N): ").strip().lower() == "y"


def console_chooser(names, what):
    """Asks which of several names to use; returns a 0-based index."""
    for i, name in enumerate(names, 1):
        print(f"    {i}: {name}")
    while True:
        raw = input(f"  Which one? (1-{len(names)}) [1]: ").strip()
        if raw == "":
            return 0
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(names):
                return idx
        except ValueError:
            pass
        print(f"  Please enter a number from 1 to {len(names)}.")


def main():
    print("--- 24bit7 ---")
    print("1: Create Playlist of Similar Artists")
    print("2: Play Artist's Top Tracks")
    print("3: Show This Record's Credits (with optional producer playlist)")
    choice = input("\nEnter choice (1, 2 or 3): ").strip()

    if choice == "1":
        engine.create_similar_playlist(report=print)
    elif choice == "2":
        engine.play_top_n(report=print)
    elif choice == "3":
        engine.explore_credits(report=print, ask_producer=ask_producer, chooser=console_chooser)
    else:
        print("Invalid choice. Please enter 1, 2 or 3.")


if __name__ == "__main__":
    main()