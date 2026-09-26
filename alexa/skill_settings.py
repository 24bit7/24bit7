"""
needle drop - your settings, kept apart from the skill's code.

In the Alexa console's Code tab, create a file called skill_settings.py next to
lambda_function.py, paste this in and fill in the two values. Keep this file
out of screen recordings and never commit your real values to GitHub: the copy
in the 24bit7 repo holds placeholders only.
"""

# Your Tailscale Funnel address, e.g. https://desktop-abc123.tailxxxx.ts.net
BIT7_URL = "https://YOUR-PC.YOUR-TAILNET.ts.net"

# The key from 24bit7's Settings > Voice (Show, or the Copy button).
BIT7_KEY = "PASTE-YOUR-KEY-HERE"

# Optional: a sound from the Alexa Skills Kit Sound Library, e.g. "soundbank://soundlibrary/....".
# Leave it empty and Alexa says "Ready" and "You got it" instead of chiming.
CHIME = ""
