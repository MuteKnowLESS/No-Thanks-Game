# No Thanks!

A Python version of the card game *No Thanks!* with a terminal mode, a single-player GUI and online multiplayer.
Cards 3-35 are used, 9 are removed unseen, and each player starts with 11 tokens (3-5 players).
Lowest score wins: only the lowest card in each run counts, and each token is worth -1.

## Files

| File | Purpose |
|------|---------|
| `no_thanks.py` | Core game classes (`Player`, `HumanPlayer`, `RandomPlayer`, `Community`) and a terminal game |
| `no_thanks_gui.py` | Single-player tkinter GUI against two bots |
| `no_thanks_server.py` | Multiplayer server (the host runs this) |
| `no_thanks_client.py` | Multiplayer tkinter client (everyone runs this) |

## Setup

No third-party packages are required (see `requirements.txt`).

```
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```
python no_thanks.py          # terminal game
python no_thanks_gui.py      # single-player GUI
python no_thanks_server.py   # host: start the server (default port 5555)
python no_thanks_client.py   # everyone: join with host address, port and a name
```

The first player to join is the host and presses Start. Bots fill empty seats up to 3 players.

## Playing over the internet

The server has no password or encryption, so use a private network such as Tailscale
(share the host's machine with friends) or only run a public tunnel while you are playing.
