"""Evolve a No Thanks! player with a simple genetic algorithm.

Run:   python no_thanks_evolve.py
Result: best_weights.json  (load it with GeneticPlayer.from_file, see bottom of this file)

How it works
------------
* A "genome" is a list of weights. GeneticPlayer turns the game situation into a few numbers
  (features), multiplies them by the weights, and TAKES the card if the total is above zero.
* Fitness = how much better than its opponents a genome scores over many games.
* Each generation the best genomes are kept, and the rest of the population is refilled with
  mutated crossovers of good genomes. Over time the weights improve.

Only the standard library is used. The game rules come from no_thanks.py.
"""
import argparse
import json
import random

from no_thanks import Player, RandomPlayer, Community, START_TOKENS

FEATURE_NAMES = ["bias", "card cost", "pot", "tokens", "cost*tokens", "pot*tokens"]


# ----------------------------------------------------------------------
# headless game
# ----------------------------------------------------------------------
def run_game(players, seed):
    """Play one full game with no printing or input. Returns each player's final score."""
    random.seed(seed)                       # same seed -> same deck and starting seat
    for p in players:
        p.tokens, p.cards = START_TOKENS, []

    deck = list(range(3, 36))
    random.shuffle(deck)
    deck = deck[9:]                         # 9 cards removed unseen
    community = Community()
    current = random.randrange(len(players))

    while deck:
        community.card = deck.pop()
        while players[current].play_turn(community) == "pass":
            current = (current + 1) % len(players)
        # the player who took the card starts the next round

    return [p.score() for p in players]


# ----------------------------------------------------------------------
# players
# ----------------------------------------------------------------------
def card_cost(player, card):
    """How much taking this card changes the player's score (runs are taken into account)."""
    before = player.score()
    player.cards.append(card)
    after = player.score()
    player.cards.pop()
    return after - before


class HeuristicPlayer(Player):
    """Hand-written baseline: take if the card is cheap enough once the pot is subtracted."""

    def __init__(self, name, threshold=10):
        super().__init__(name)
        self.threshold = threshold

    def decide(self, community):
        net_cost = card_cost(self, community.card) - community.pot
        return "take" if net_cost <= self.threshold else "pass"


class GeneticPlayer(Player):
    """Decides with a weighted sum of features. The weights are what evolution tunes."""

    def __init__(self, name, weights):
        super().__init__(name)
        self.weights = weights

    def features(self, community):
        cost = card_cost(self, community.card) / 35
        pot = community.pot / 10
        tokens = self.tokens / START_TOKENS
        return [1.0, cost, pot, tokens, cost * tokens, pot * tokens]

    def decide(self, community):
        z = sum(w * x for w, x in zip(self.weights, self.features(community)))
        return "take" if z > 0 else "pass"

    @classmethod
    def from_file(cls, name, path="best_weights.json"):
        with open(path) as f:
            return cls(name, json.load(f)["weights"])


# ----------------------------------------------------------------------
# fitness + evolution
# ----------------------------------------------------------------------
def evaluate(genome, pool, games, base_seed):
    """Average score margin over `pool` opponents (higher = better). Same seeds for everyone."""
    me = GeneticPlayer("candidate", genome)
    total = 0.0
    for i in range(games):
        seed = base_seed + i
        opponents = random.Random(seed).sample(pool, 2)
        scores = run_game([me] + opponents, seed)
        total += (scores[1] + scores[2]) / 2 - scores[0]
    return total / games


def tournament(scored, rng, k=3):
    """Pick k random genomes and return the fittest of them."""
    return max(rng.sample(scored, k), key=lambda t: t[0])[1]


def evolve(pop_size, generations, games, seed):
    rng = random.Random(seed)
    n = len(FEATURE_NAMES)
    population = [[rng.gauss(0, 1) for _ in range(n)] for _ in range(pop_size)]
    champions = []                          # best genome of every generation

    for gen in range(generations):
        hall = [GeneticPlayer(f"Champion {i}", g) for i, g in enumerate(champions[-5:])]
        pool = [RandomPlayer("Random A"), RandomPlayer("Random B"),
                HeuristicPlayer("Heuristic")] + hall
        base_seed = 1_000_000 + gen * 10_000          # fresh decks every generation

        scored = sorted(((evaluate(g, pool, games, base_seed), g) for g in population),
                        key=lambda t: t[0], reverse=True)
        best_fit, best = scored[0]
        mean_fit = sum(f for f, _ in scored) / len(scored)
        champions.append(best)
        print(f"gen {gen + 1:3d}/{generations}  best margin {best_fit:+6.2f}  mean {mean_fit:+6.2f}")

        elites = [g for _, g in scored[:max(2, pop_size // 5)]]
        sigma = 0.5 * (1 - gen / generations) + 0.05  # mutations shrink over time
        children = []
        while len(elites) + len(children) < pop_size:
            a, b = tournament(scored, rng), tournament(scored, rng)
            child = [x if rng.random() < 0.5 else y for x, y in zip(a, b)]            # crossover
            child = [w + rng.gauss(0, sigma) if rng.random() < 0.3 else w for w in child]  # mutation
            children.append(child)
        population = elites + children

    # Pick the final winner by re-testing recent champions on fresh decks (less luck than one generation).
    print("\nChoosing the final champion...")
    pool = [RandomPlayer("Random A"), RandomPlayer("Random B"), HeuristicPlayer("Heuristic")]
    finalists = champions[-10:]
    results = [(evaluate(g, pool, games * 5, 5_000_000), g) for g in finalists]
    return max(results, key=lambda t: t[0])[1]


# ----------------------------------------------------------------------
# reporting
# ----------------------------------------------------------------------
def report(label, me, make_opponents, games=2000, base_seed=9_000_000):
    """Mean score and win rate of `me` against fresh opponents on decks never used in training."""
    my_total = opp_total = wins = 0
    for i in range(games):
        scores = run_game([me] + make_opponents(), base_seed + i)
        my_total += scores[0]
        opp_total += (scores[1] + scores[2]) / 2
        wins += scores[0] <= min(scores[1:])      # ties count as a win
    print(f"  {label:<26} your score {my_total / games:6.1f}  vs {opp_total / games:6.1f}"
          f"   win rate {100 * wins / games:5.1f}%")


def full_report(genome):
    print("\nResults on 2000 unseen games (lowest score wins; a random 3-player game is ~33% wins):")
    print("Reference points:")
    report("Random vs 2 Random", RandomPlayer("R"), lambda: [RandomPlayer("a"), RandomPlayer("b")])
    report("Heuristic vs 2 Random", HeuristicPlayer("H"), lambda: [RandomPlayer("a"), RandomPlayer("b")])
    print("Evolved player:")
    me = GeneticPlayer("Evolved", genome)
    report("vs 2 Random", me, lambda: [RandomPlayer("a"), RandomPlayer("b")])
    report("vs 2 Heuristic", me, lambda: [HeuristicPlayer("a"), HeuristicPlayer("b")])
    report("vs Random + Heuristic", me, lambda: [RandomPlayer("a"), HeuristicPlayer("b")])


def main():
    parser = argparse.ArgumentParser(description="Evolve a No Thanks! player")
    parser.add_argument("--pop", type=int, default=30, help="population size")
    parser.add_argument("--generations", type=int, default=25)
    parser.add_argument("--games", type=int, default=150, help="games per genome per generation")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="best_weights.json")
    args = parser.parse_args()

    best = evolve(args.pop, args.generations, args.games, args.seed)

    print("\nBest weights:")
    for name, w in zip(FEATURE_NAMES, best):
        print(f"  {name:<12} {w:+.3f}")
    with open(args.out, "w") as f:
        json.dump({"features": FEATURE_NAMES, "weights": best}, f, indent=2)
    print(f"Saved to {args.out}")

    full_report(best)


if __name__ == "__main__":
    main()

# ----------------------------------------------------------------------
# Using the result in the GUI or server (no other changes needed):
#
#   from no_thanks_evolve import GeneticPlayer
#   bot = GeneticPlayer.from_file("Evolved Bot", "best_weights.json")
#   self.players = [GUIPlayer("You"), bot, RandomPlayer("Bot 2")]
# ----------------------------------------------------------------------