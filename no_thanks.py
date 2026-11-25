import random
from abc import ABC, abstractmethod

NUM_PLAYERS = 3
START_TOKENS = 11


class Community:
    def __init__(self):
        self.card = None
        self.pot = 0

    def update_pot(self):
        self.pot += 1

    def reset_pot(self):
        """Empty the pot and return its contents."""
        pay_out = self.pot
        self.pot = 0
        return pay_out


class Player(ABC):
    """General player. Subclasses only have to say HOW they decide."""

    def __init__(self, name):
        self.name = name
        self.tokens = START_TOKENS
        self.cards = []

    @abstractmethod
    def decide(self, community):
        """Return 'pass' or 'take'. Each subclass implements this differently."""

    def play_turn(self, community):
        """Shared game rules: same for every kind of player."""
        action = self.decide(community)
        if action == "pass" and self.tokens > 0:
            self.tokens -= 1
            community.update_pot()
            return "pass"
        # taking (or forced to take because out of tokens)
        self.cards.append(community.card)
        self.tokens += community.reset_pot()
        return "take"

    def score(self):
        """Lowest wins. Only the lowest card of a run counts; each token is -1."""
        cards = sorted(self.cards)
        total = 0
        for i, c in enumerate(cards):
            if i == 0 or c != cards[i - 1] + 1:
                total += c
        return total - self.tokens


class HumanPlayer(Player):
    """Decides using keyboard input."""

    def decide(self, community):
        print(f"[Card: {community.card} | Pot: {community.pot}]")
        if self.tokens == 0:
            print(f"{self.name} has no tokens and must take the card.")
            return "take"
        while True:
            act = input(f"{self.name} (tokens: {self.tokens}) - pass or take? ").strip().lower()
            if act in ("pass", "take"):
                return act
            print("Please type 'pass' or 'take'.")


class RandomPlayer(Player):
    """Computer player that picks pass or take at random."""

    def decide(self, community):
        return random.choice(["pass", "take"])


def cycle(players, community, starting_player):
    """Go round the table until someone takes the card. Returns that player's index."""
    current = starting_player
    while True:
        if players[current].play_turn(community) == "take":
            return current
        current = (current + 1) % len(players)


def main():
    deck = list(range(3, 36))
    random.shuffle(deck)
    deck = deck[9:]  # 9 cards removed unseen

    players = [HumanPlayer(f"Player {i}") for i in range(NUM_PLAYERS)]
    community = Community()

    cp = 0
    while deck:
        community.card = deck.pop()
        print(f"\n--- New card drawn | Cards left in deck: {len(deck)} ---")
        cp = cycle(players, community, cp)  # taker starts the next round

    print("\nFinal scores (lowest wins):")
    for p in sorted(players, key=lambda p: p.score()):
        print(f"{p.name}: {p.score()}  cards={sorted(p.cards)} tokens={p.tokens}")


if __name__ == "__main__":
    main()