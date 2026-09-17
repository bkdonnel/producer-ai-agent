#!/usr/bin/env python3
"""
Phase 0 sanity check: confirm AbletonOSC is running inside Live and
responding over OSC.

Usage:
    1. Open Ableton Live.
    2. Preferences -> Link/Tempo/MIDI -> Control Surface -> select "AbletonOSC".
    3. Run this script (from the repo root):
         ./.venv/bin/python scripts/verify_osc_connection.py

It reads the current tempo, nudges it up by 1 BPM, reads it back to confirm
the change landed, then restores the original tempo.
"""

from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

ABLETON_IP = "127.0.0.1"
SEND_PORT = 11000    # this script -> AbletonOSC
RECEIVE_PORT = 11001  # AbletonOSC -> this script
TIMEOUT_SECONDS = 5


def get_tempo(client: SimpleUDPClient) -> float:
    result = {}

    def handle_tempo(address, *args):
        result["tempo"] = args[0]

    dispatcher = Dispatcher()
    dispatcher.map("/live/song/get/tempo", handle_tempo)

    server = BlockingOSCUDPServer((ABLETON_IP, RECEIVE_PORT), dispatcher)
    server.timeout = TIMEOUT_SECONDS

    client.send_message("/live/song/get/tempo", [])
    server.handle_request()
    server.server_close()

    if "tempo" not in result:
        raise TimeoutError(
            f"No reply from AbletonOSC within {TIMEOUT_SECONDS}s. "
            "Is Live open with AbletonOSC selected as the Control Surface?"
        )
    return result["tempo"]


def main():
    client = SimpleUDPClient(ABLETON_IP, SEND_PORT)

    print("Reading current tempo...")
    original_tempo = get_tempo(client)
    print(f"  -> {original_tempo} BPM")

    nudged = round(original_tempo, 2) + 1
    print(f"Setting tempo to {nudged} BPM...")
    client.send_message("/live/song/set/tempo", [nudged])

    confirmed = get_tempo(client)
    print(f"  -> Live now reports {confirmed} BPM")

    print(f"Restoring original tempo ({original_tempo} BPM)...")
    client.send_message("/live/song/set/tempo", [original_tempo])

    if abs(confirmed - nudged) < 0.01:
        print("\nSUCCESS: AbletonOSC is installed and responding.")
    else:
        print("\nWARNING: tempo didn't change as expected — check Live's Control Surface setting.")


if __name__ == "__main__":
    main()
