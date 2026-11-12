"""Stage 5 - score quantum output against the exact answer."""
import numpy as np
from .formulation import qubo_matrix
from .qaoa import all_costs


def problem(mu, sigma, lam, k):
    """Everything needed to judge a result: the true cost of every bitstring,
    which ones select exactly k sites, and the exact best / worst of those."""
    n = len(mu)
    q, const = qubo_matrix(mu, sigma, lam)
    costs = all_costs(q, const, n)
    weight = np.array([bin(b).count("1") for b in range(2 ** n)])
    feasible = weight == k
    feasible_costs = np.sort(costs[feasible])
    return {"n": n, "k": k, "costs": costs, "feasible": feasible,
            "optimum": int(np.argmin(np.where(feasible, costs, np.inf))),
            "best": float(feasible_costs[0]), "worst": float(feasible_costs[-1]),
            "sorted": feasible_costs}


def counts_to_probs(counts, n):
    """{bitstring: count} from a sampler -> probability vector of length 2^n."""
    probs = np.zeros(2 ** n)
    for bitstring, c in counts.items():
        probs[int(bitstring, 2)] += c     # int(..., 2) honours Qiskit bit order
    return probs / probs.sum()


def rank_of(index, prob):
    """1 = the exact optimum, 2 = second-best feasible selection, ..."""
    return int((prob["sorted"] < prob["costs"][index] - 1e-9).sum()) + 1


def shortlist(probs, prob, size=5):
    """The `size` most likely feasible selections, i.e. what the quantum
    computer proposes. A classical check then scores this handful exactly."""
    masked = np.where(prob["feasible"], probs, -1.0)
    top = np.argsort(masked)[::-1][:size]
    return [int(b) for b in top if masked[b] > 0]


def metrics(probs, prob, shortlist_size=5):
    """Standard QAOA quality numbers for one outcome distribution."""
    feas = prob["feasible"]
    p_feasible = float(probs[feas].sum())
    # expected cost of the outcomes that respect the k-sites rule
    mean_cost = float(probs[feas] @ prob["costs"][feas] / p_feasible) if p_feasible else np.nan
    short = shortlist(probs, prob, shortlist_size)
    pick = min(short, key=lambda b: prob["costs"][b]) if short else None
    uniform = 1 / feas.sum()               # chance of a blind feasible guess
    return {
        "feasible_rate": p_feasible,
        "approx_ratio": (prob["worst"] - mean_cost) / (prob["worst"] - prob["best"]),
        "p_optimum": float(probs[prob["optimum"]]),
        "amplification": float(probs[prob["optimum"]] / uniform),
        "shortlist": short,
        "pick": pick,
        "pick_rank": rank_of(pick, prob) if pick is not None else None,
        "pick_gap": (float((prob["costs"][pick] - prob["best"]) / abs(prob["best"]))
                     if pick is not None else None),
    }
