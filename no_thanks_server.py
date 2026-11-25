"""No Thanks! multiplayer server.

Run this on ONE computer (the host):   python no_thanks_server.py
Everyone (including the host) then joins with no_thanks_client.py.

The server owns the game. Clients only send "pass" / "take" and receive the
state they are allowed to see (opponents' tokens stay hidden until the end).
Game rules come from no_thanks.py, so they exist in only one place.
"""
import argparse
import json
import random
import socket
import threading

from no_thanks import Community, Player, RandomPlayer

MIN_PLAYERS = 3   # bots fill empty seats up to this number
MAX_PLAYERS = 5   # 11 tokens each is correct for 3-5 players
BOT_DELAY = 0.9   # seconds before a bot moves, so humans can follow


class NetPlayer(Player):
    """A human on the network. The server stores their chosen action here."""

    def __init__(self, name):
        super().__init__(name)
        self.next_action = "pass"

    def decide(self, community):
        return self.next_action


def unique_name(name, taken):
    base = (name or "Player").strip()[:16] or "Player"
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base} {n}"
        n += 1
    return candidate


class Client:
    def __init__(self, sock):
        self.sock = sock
        self.file = sock.makefile("r", encoding="utf-8")
        self.name = None
        self.player = None

    def send(self, msg):
        try:
            self.sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        except OSError:
            pass  # the reader thread will notice the dead connection

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Server:
    def __init__(self):
        self.lock = threading.RLock()
        self.listener = None
        self.reset()

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------
    def reset(self):
        self.clients = []          # joined humans, in join order (first = host)
        self.phase = "lobby"       # lobby | playing | over
        self.players = []
        self.deck = []
        self.community = Community()
        self.current = 0

    def state_for(self, client):
        if self.phase == "lobby":
            plist = [{"name": c.name, "tokens": None, "cards": [], "score": None, "bot": False}
                     for c in self.clients]
            you = self.clients.index(client)
        else:
            over = self.phase == "over"
            plist = [{
                "name": p.name,
                "tokens": p.tokens if (over or p is client.player) else None,
                "cards": sorted(p.cards),
                "score": p.score() if over else None,
                "bot": isinstance(p, RandomPlayer),
            } for p in self.players]
            you = self.players.index(client.player)
        return {
            "type": "state",
            "phase": self.phase,
            "players": plist,
            "you": you,
            "card": self.community.card,
            "pot": self.community.pot,
            "deck_left": len(self.deck),
            "current": self.current if self.phase == "playing" else -1,
            "host": self.clients[0].name if self.clients else None,
        }

    def broadcast_state(self):
        for c in list(self.clients):
            c.send(self.state_for(c))

    def log(self, text):
        print(text)
        for c in list(self.clients):
            c.send({"type": "log", "text": text})

    # ------------------------------------------------------------------
    # game flow
    # ------------------------------------------------------------------
    def start_game(self):
        self.players = []
        for c in self.clients:
            c.player = NetPlayer(c.name)
            self.players.append(c.player)
        n = 1
        while len(self.players) < MIN_PLAYERS:
            name = unique_name(f"Bot {n}", [p.name for p in self.players])
            self.players.append(RandomPlayer(name))
            n += 1

        deck = list(range(3, 36))
        random.shuffle(deck)
        self.deck = deck[9:]   # 9 cards removed unseen
        self.community = Community()
        self.current = random.randrange(len(self.players))
        self.phase = "playing"
        self.log("--- New game started ---")
        self.draw_card()
        self.broadcast_state()
        self.schedule_bot()

    def draw_card(self):
        self.community.card = self.deck.pop()
        self.log(f"New card: {self.community.card} ({len(self.deck)} left in deck)")

    def take_turn(self, player, action=None):
        card, pot = self.community.card, self.community.pot
        if isinstance(player, NetPlayer):
            player.next_action = action
        result = player.play_turn(self.community)   # rules live in no_thanks.py

        if result == "pass":
            self.log(f"{player.name} passed.")
            self.current = (self.current + 1) % len(self.players)
        else:
            extra = f" and {pot} token(s)" if pot else ""
            self.log(f"{player.name} took {card}{extra}.")
            if self.deck:
                self.draw_card()   # the taker starts the next round
            else:
                self.end_game()
                return
        self.broadcast_state()
        self.schedule_bot()

    def end_game(self):
        self.phase = "over"
        self.community.card = None
        self.log("=== Game over! Final scores (lowest wins) ===")
        for p in sorted(self.players, key=lambda p: p.score()):
            self.log(f"  {p.name}: {p.score()}")
        self.broadcast_state()

    def schedule_bot(self):
        if self.phase == "playing" and isinstance(self.players[self.current], RandomPlayer):
            t = threading.Timer(BOT_DELAY, self.bot_move, args=(self.players[self.current],))
            t.daemon = True
            t.start()

    def bot_move(self, bot):
        with self.lock:
            if self.phase != "playing" or not self.players or self.players[self.current] is not bot:
                return
            self.take_turn(bot)

    # ------------------------------------------------------------------
    # client handling
    # ------------------------------------------------------------------
    def handle(self, client, msg):
        with self.lock:
            kind = msg.get("type")

            if kind == "join":
                if client.name is not None:
                    return
                if self.phase != "lobby":
                    client.send({"type": "error", "text": "A game is already in progress. Try again later."})
                    client.close()
                    return
                if len(self.clients) >= MAX_PLAYERS:
                    client.send({"type": "error", "text": f"The game is full ({MAX_PLAYERS} players)."})
                    client.close()
                    return
                client.name = unique_name(msg.get("name"), [c.name for c in self.clients])
                self.clients.append(client)
                self.log(f"{client.name} joined.")
                self.broadcast_state()

            elif client not in self.clients:
                return

            elif kind == "start":
                if client is self.clients[0] and self.phase in ("lobby", "over"):
                    self.start_game()

            elif kind == "action":
                action = msg.get("action")
                if (self.phase == "playing" and action in ("pass", "take")
                        and client.player is self.players[self.current]):
                    self.take_turn(client.player, action)

    def disconnect(self, client):
        with self.lock:
            client.close()
            if client not in self.clients:
                return
            self.clients.remove(client)
            self.log(f"{client.name} left.")

            if self.phase == "playing" and client.player in self.players:
                # a bot takes over their seat, keeping tokens and cards
                old = client.player
                bot = RandomPlayer(old.name + " (bot)")
                bot.tokens, bot.cards = old.tokens, old.cards
                self.players[self.players.index(old)] = bot

            if not self.clients:
                self.reset()
                print("All players left - back to the lobby.")
                return
            self.broadcast_state()
            self.schedule_bot()

    def serve_client(self, client):
        try:
            for line in client.file:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if isinstance(msg, dict):
                    self.handle(client, msg)
        except (OSError, ValueError):
            pass
        finally:
            self.disconnect(client)

    # ------------------------------------------------------------------
    # networking
    # ------------------------------------------------------------------
    def bind(self, host, port):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind((host, port))
        self.listener.listen()
        return self.listener.getsockname()[1]

    def serve_forever(self):
        while True:
            sock, addr = self.listener.accept()
            print(f"Connection from {addr[0]}")
            client = Client(sock)
            threading.Thread(target=self.serve_client, args=(client,), daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="No Thanks! multiplayer server")
    parser.add_argument("--host", default="0.0.0.0", help="address to listen on")
    parser.add_argument("--port", type=int, default=5555, help="TCP port (default 5555)")
    args = parser.parse_args()

    server = Server()
    port = server.bind(args.host, args.port)
    print(f"No Thanks! server listening on port {port}. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
