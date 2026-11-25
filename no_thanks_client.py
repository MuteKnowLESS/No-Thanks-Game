"""No Thanks! multiplayer client (tkinter).

Run:  python no_thanks_client.py
Enter the host's address, port and your name, then Connect.
The first person to join is the host and presses Start when everyone is in.
"""
import json
import queue
import socket
import threading
import tkinter as tk


class NoThanksClient:
    def __init__(self, root):
        self.root = root
        root.title("No Thanks! (online)")
        root.resizable(False, False)

        self.sock = None
        self.inbox = queue.Queue()
        self.panel_names = None
        self.panels = []

        self.build_connect_frame()
        self.build_game_frame()
        self.show_connect()
        root.after(100, self.poll)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def build_connect_frame(self):
        f = self.connect_frame = tk.Frame(self.root, padx=30, pady=20)
        tk.Label(f, text="No Thanks!", font=("Helvetica", 24, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 15))

        self.host_var = tk.StringVar(value="localhost")
        self.port_var = tk.StringVar(value="5555")
        self.name_var = tk.StringVar(value="Player")
        for row, (label, var) in enumerate([("Host address", self.host_var),
                                            ("Port", self.port_var),
                                            ("Your name", self.name_var)], start=1):
            tk.Label(f, text=label).grid(row=row, column=0, sticky="e", padx=5, pady=3)
            tk.Entry(f, textvariable=var, width=24).grid(row=row, column=1, pady=3)

        tk.Button(f, text="Connect", width=16, command=self.connect).grid(
            row=4, column=0, columnspan=2, pady=12)
        self.connect_msg = tk.Label(f, text="", fg="red", wraplength=260)
        self.connect_msg.grid(row=5, column=0, columnspan=2)

    def build_game_frame(self):
        f = self.game_frame = tk.Frame(self.root)

        top = tk.Frame(f, padx=10, pady=10)
        top.pack(fill="x")
        self.card_label = tk.Label(top, text="-", font=("Helvetica", 48, "bold"),
                                   width=4, relief="ridge", bd=4, bg="white")
        self.card_label.pack(side="left", padx=(0, 20))
        info = tk.Frame(top)
        info.pack(side="left")
        self.pot_label = tk.Label(info, text="Pot: 0", font=("Helvetica", 18))
        self.pot_label.pack(anchor="w")
        self.deck_label = tk.Label(info, text="Cards left: 0", font=("Helvetica", 12))
        self.deck_label.pack(anchor="w")

        self.players_frame = tk.Frame(f, padx=10)
        self.players_frame.pack(fill="x")

        buttons = tk.Frame(f, pady=10)
        buttons.pack()
        self.pass_btn = tk.Button(buttons, text="Pass (pay 1 token)", width=18,
                                  state="disabled", command=lambda: self.act("pass"))
        self.pass_btn.pack(side="left", padx=5)
        self.take_btn = tk.Button(buttons, text="Take card + pot", width=18,
                                  state="disabled", command=lambda: self.act("take"))
        self.take_btn.pack(side="left", padx=5)
        self.start_btn = tk.Button(buttons, text="Start game", width=18,
                                   state="disabled", command=self.start)
        self.start_btn.pack(side="left", padx=(20, 5))

        self.status = tk.Label(f, text="", font=("Helvetica", 12, "bold"))
        self.status.pack()
        self.log = tk.Text(f, height=8, width=64, state="disabled")
        self.log.pack(padx=10, pady=(5, 10))

    def show_connect(self):
        self.game_frame.pack_forget()
        self.connect_frame.pack()

    def show_game(self):
        self.connect_frame.pack_forget()
        self.game_frame.pack()

    # ------------------------------------------------------------------
    # networking
    # ------------------------------------------------------------------
    def connect(self):
        host = self.host_var.get().strip()
        name = self.name_var.get().strip() or "Player"
        try:
            port = int(self.port_var.get())
            sock = socket.create_connection((host, port), timeout=5)
        except ValueError:
            self.connect_msg.config(text="Port must be a number.")
            return
        except OSError as e:
            self.connect_msg.config(text=f"Could not connect: {e}")
            return
        sock.settimeout(None)

        self.sock = sock
        self.panel_names = None
        self.clear_log()
        self.connect_msg.config(text="")
        threading.Thread(target=self.reader, args=(sock,), daemon=True).start()
        self.send({"type": "join", "name": name})
        self.show_game()

    def reader(self, sock):
        """Background thread: turn incoming lines into queue messages."""
        try:
            for line in sock.makefile("r", encoding="utf-8"):
                try:
                    self.inbox.put(json.loads(line))
                except ValueError:
                    pass
        except (OSError, ValueError):
            pass
        self.inbox.put({"type": "closed", "sock": sock})

    def send(self, msg):
        if self.sock is None:
            return
        try:
            self.sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        except OSError:
            self.disconnect("Connection lost.")

    def disconnect(self, reason):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        self.connect_msg.config(text=reason)
        self.show_connect()

    def poll(self):
        """Runs on the GUI thread every 100 ms and handles queued messages."""
        try:
            while True:
                self.handle_message(self.inbox.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def handle_message(self, msg):
        kind = msg.get("type")
        if kind == "state":
            self.render(msg)
        elif kind == "log":
            self.write_log(msg["text"])
        elif kind == "error":
            self.disconnect(msg.get("text", "Error"))
        elif kind == "closed":
            if msg.get("sock") is self.sock:   # ignore stale connections
                self.disconnect("Disconnected from the server.")

    # ------------------------------------------------------------------
    # user actions
    # ------------------------------------------------------------------
    def act(self, action):
        self.pass_btn.config(state="disabled")
        self.take_btn.config(state="disabled")
        self.send({"type": "action", "action": action})

    def start(self):
        self.send({"type": "start"})

    # ------------------------------------------------------------------
    # display
    # ------------------------------------------------------------------
    def build_panels(self, players):
        for child in self.players_frame.winfo_children():
            child.destroy()
        self.panels = []
        for _ in players:
            frame = tk.Frame(self.players_frame, bd=2, relief="groove", padx=8, pady=6)
            frame.pack(side="left", fill="both", expand=True, padx=4)
            name = tk.Label(frame, font=("Helvetica", 14, "bold"))
            name.pack()
            tokens = tk.Label(frame)
            tokens.pack()
            cards = tk.Label(frame, wraplength=150, justify="center")
            cards.pack()
            score = tk.Label(frame, fg="gray30")
            score.pack()
            self.panels.append((frame, name, tokens, cards, score))

    def render(self, state):
        players, you, phase, cur = state["players"], state["you"], state["phase"], state["current"]

        names = tuple((p["name"], p["bot"]) for p in players)
        if names != self.panel_names:
            self.build_panels(players)
            self.panel_names = names

        card = state["card"]
        self.card_label.config(text="-" if card is None else str(card))
        self.pot_label.config(text=f"Pot: {state['pot']}")
        self.deck_label.config(text=f"Cards left: {state['deck_left']}")

        default_bg = self.root.cget("bg")
        for i, (p, panel) in enumerate(zip(players, self.panels)):
            frame, name, tokens, cards, score = panel
            label = p["name"] + (" (you)" if i == you else "") + (" [bot]" if p["bot"] else "")
            name.config(text=label)
            tokens.config(text="Tokens: ?" if p["tokens"] is None else f"Tokens: {p['tokens']}")
            cards.config(text=" ".join(map(str, p["cards"])) or "(no cards)")
            score.config(text="" if p["score"] is None else f"Score: {p['score']}")
            bg = "#fff3b0" if i == cur else default_bg
            for w in (frame, name, tokens, cards, score):
                w.config(bg=bg)

        me = players[you]
        my_turn = phase == "playing" and cur == you
        self.take_btn.config(state="normal" if my_turn else "disabled")
        self.pass_btn.config(state="normal" if my_turn and me["tokens"] != 0 else "disabled")

        is_host = state["host"] == me["name"]
        if phase in ("lobby", "over") and is_host:
            self.start_btn.config(state="normal",
                                  text="Start game" if phase == "lobby" else "Play again")
        else:
            self.start_btn.config(state="disabled",
                                  text="Start game" if phase == "lobby" else "Play again")

        if phase == "lobby":
            if is_host:
                self.status.config(text="You are the host. Press Start when everyone has joined "
                                        "(bots fill empty seats up to 3).")
            else:
                self.status.config(text=f"Waiting for {state['host']} to start the game...")
        elif phase == "playing":
            if my_turn:
                self.status.config(text="Your turn!")
            else:
                self.status.config(text=f"Waiting for {players[cur]['name']}...")
        else:
            winner = min(players, key=lambda p: p["score"])
            self.status.config(text=f"Game over - {winner['name']} wins!")

    def write_log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    NoThanksClient(root)
    root.mainloop()
