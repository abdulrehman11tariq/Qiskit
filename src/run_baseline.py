"""Run stages 1-3:  python -m src.run_baseline"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .instance import make_instance, save_instance, simulate_served
from .baseline import brute_force, greedy_top_k, describe, exact_frontier

LAMBDAS = [0, 0.002, 0.005, 0.01, 0.02, 0.05]


def names_of(x, inst):
    return ", ".join(n for n, v in zip(inst.names, x) if v)


def main():
    inst = make_instance()
    save_instance(inst, "data/instance.json")
    print(f"{inst.n} candidate sites, stock k={inst.k} "
          f"({len(brute_force(inst.mu, inst.sigma, 0, inst.k))} feasible selections)\n")

    g = greedy_top_k(inst.mu, inst.k)
    frontier = exact_frontier(inst.mu, inst.sigma, inst.k, LAMBDAS)

    # out-of-sample check on fresh flood seasons the optimiser never saw
    _, _, _, _, fresh = simulate_served(20000, np.random.default_rng(999))

    def oos(x):
        t = fresh @ x
        return t.mean(), np.percentile(t, 5)

    print(f"{'plan':<14}{'expected':>9}{'std':>7}{'worst 5%':>10}  sites")
    m, s = describe(g, inst.mu, inst.sigma)
    print(f"{'greedy top-k':<14}{m:>9.1f}{s:>7.1f}{oos(g)[1]:>10.1f}  {names_of(g, inst)}")
    for r in frontier:
        label = f"exact lam={r['lam']:g}"
        print(f"{label:<14}{r['mean']:>9.1f}{r['std']:>7.1f}{oos(r['x'])[1]:>10.1f}  "
              f"{names_of(r['x'], inst)}")
    print("\n(people in thousands; 'worst 5%' = served in the 5th-percentile "
          "season, 20,000 fresh simulated seasons)")

    allsel = [describe(x, inst.mu, inst.sigma) for _, x in brute_force(inst.mu, inst.sigma, 0, inst.k)]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.scatter([s for _, s in allsel], [m for m, _ in allsel], s=8, c="#c8c8c8",
               label="all feasible selections")
    ax.plot([r["std"] for r in frontier], [r["mean"] for r in frontier], "o-",
            c="#1f6fb4", label="exact optimum as risk weight grows")
    ax.scatter([s], [m], marker="X", s=110, c="#d1495b", zorder=3, label="greedy top-k")
    ax.set_xlabel("Risk: std. dev. of people served (thousands)")
    ax.set_ylabel("Expected people served (thousands)")
    ax.set_title("Coverage vs. flood risk - exact reference")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig("results/frontier_exact.png", dpi=150)
    print("saved data/instance.json, results/frontier_exact.png")


if __name__ == "__main__":
    main()
