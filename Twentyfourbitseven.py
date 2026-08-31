"""
24bit7 - command-line interface.

All the logic lives in engine.py; this file is just the console front end.
It passes `print` as the progress reporter and console prompts as the
callbacks, so the engine stays free of input()/print() and can be driven
by a GUI in exactly the same way.
"""

import engine




def main():
    print("--- 24bit7 ---")
    print("1: Create Playlist of Similar Artists")
    print("2: Play Artist's Top Tracks")
    print("3: Show This Record's Credits")
    choice = input("\nEnter choice (1, 2 or 3): ").strip()

    if choice == "1":
        engine.create_similar_playlist(report=print)
    elif choice == "2":
        engine.play_top_n(report=print)
    elif choice == "3":
        engine.explore_credits(report=print)
    else:
        print("Invalid choice. Please enter 1, 2 or 3.")


if __name__ == "__main__":
    main()