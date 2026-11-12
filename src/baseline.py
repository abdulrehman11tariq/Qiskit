"""Stage 3 - exact and greedy classical references."""
from itertools import combinations
import numpy as np
from .formulation import qubo_matrix, cost


def selection(n, chosen):
    x = np.zeros(n, dtype=int)
    x[list(chosen)] = 1
    return x


def brute_force(mu, sigma, lam, k):
    """Check every way of choosing k sites. Returns all (cost, x) sorted
    best-first, so callers can read off the optimum and the worst case."""
    n = len(mu)
    q, c = qubo_matrix(mu, sigma, lam)
    results = [(cost(selection(n, s), q, c), selection(n, s))
               for s in combinations(range(n), k)]
    results.sort(key=lambda t: t[0])
    return results


def greedy_top_k(mu, k):
    """Naive planner: stock the k sites with the highest expected reach,
    ignoring that neighbouring sites flood together."""
    return selection(len(mu), np.argsort(mu)[::-1][:k])


def describe(x, mu, sigma):
    """(expected people served, standard deviation) for a selection."""
    x = np.asarray(x, dtype=float)
    return float(mu @ x), float(np.sqrt(x @ sigma @ x))


def exact_frontier(mu, sigma, k, lambdas):
    rows = []
    for lam in lambdas:
        _, x = brute_force(mu, sigma, lam, k)[0]
        mean, std = describe(x, mu, sigma)
        rows.append({"lam": float(lam), "x": x, "mean": mean, "std": std})
    return rows
