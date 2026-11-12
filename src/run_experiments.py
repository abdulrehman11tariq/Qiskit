"""Reproduce every number and figure in the report:

    python -m src.run_experiments

Takes a few minutes on a laptop. Everything is seeded, so reruns give the
same output. Writes PNG figures and results.json into results/.
"""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")                      # render to files, no window needed
import matplotlib.pyplot as plt
from qiskit import QuantumCircuit

from .instance import make_instance, simulate_served
from .formulation import index_to_bits, qubo_matrix, to_ising, default_scale
from .baseline import brute_force, greedy_top_k, describe
from .qaoa import (run_qaoa, sample_counts, noisy_counts, dicke_circuit,
                   cost_layer, xy_mixer_layer)
from .evaluate import problem, metrics, counts_to_probs

LAMBDAS = [0, 0.002, 0.005, 0.01, 0.02, 0.05]   # risk weights for the frontier
LAM = 0.005                                      # headline setting
BLUE, RED, GREY, GREEN = "#1f6fb4", "#d1495b", "#c8c8c8", "#2a9d8f"
METHODS = [("penalty", "mean", "Standard QAOA\n(penalty)"),
           ("xy", "mean", "Dicke + XY mixer"),
           ("xy", "cvar", "Dicke + XY mixer\n+ CVaR")]


def names_of(x, inst):
    return [n for n, v in zip(inst.names, x) if v]


def method_comparison(inst, out):
    """Experiment A: three QAOA variants at depths 1-3 on the same problem."""
    prob = problem(inst.mu, inst.sigma, LAM, inst.k)
    rows = []
    for method, objective, label in METHODS:
        for p in (1, 2, 3):
            res = run_qaoa(inst.mu, inst.sigma, LAM, inst.k, method, p, objective)
            m = metrics(res.probs, prob)
            rows.append({"method": label.replace("\n", " "), "p": p,
                         **{key: m[key] for key in ("feasible_rate", "approx_ratio",
                                                    "p_optimum", "amplification", "pick_rank")}})
            print(f"  {rows[-1]['method']:<32} p={p}  feasible={m['feasible_rate']:.2f}  "
                  f"ratio={m['approx_ratio']:.3f}  P(opt)={m['p_optimum']:.3f}")
    out["methods"] = rows

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    panels = [("feasible_rate", "Valid plans (exactly k sites)"),
              ("approx_ratio", "Approximation ratio"),
              ("p_optimum", "Probability of the exact optimum")]
    width = 0.25
    for ax, (key, title) in zip(axes, panels):
        for j, p in enumerate((1, 2, 3)):
            vals = [r[key] for r in rows if r["p"] == p]
            ax.bar(np.arange(3) + (j - 1) * width, vals, width, label=f"p = {p}",
                   color=[GREY, "#7fb2dc", BLUE][j])
        ax.set_xticks(range(3), [m[2] for m in METHODS], fontsize=8)
        ax.set_title(title, fontsize=10)
    axes[2].axhline(1 / prob["feasible"].sum(), ls="--", c=RED, lw=1)
    axes[2].text(-0.4, 1 / prob["feasible"].sum() + 0.003, "random guess", color=RED, fontsize=8)
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig("results/methods.png", dpi=150)
    plt.close(fig)


def frontier(inst, out):
    """Experiment B: sweep the risk weight; compare quantum picks with the
    exact frontier and test every plan on fresh flood seasons."""
    _, _, _, _, fresh = simulate_served(20000, np.random.default_rng(999))
    bad_season = lambda x: float(np.percentile(fresh @ x, 5))   # 5th percentile
    greedy = greedy_top_k(inst.mu, inst.k)
    g_mean, g_std = describe(greedy, inst.mu, inst.sigma)
    rows = [{"plan": "greedy top-k", "lam": None, "sites": names_of(greedy, inst),
             "expected": g_mean, "std": g_std, "bad_season": bad_season(greedy)}]
    quantum_pts, exact_pts = [], []
    for lam in LAMBDAS:
        prob = problem(inst.mu, inst.sigma, lam, inst.k)
        x_exact = index_to_bits(prob["optimum"], inst.n)
        res = run_qaoa(inst.mu, inst.sigma, lam, inst.k, "xy", 3, "cvar")
        m = metrics(res.probs, prob)
        x_q = index_to_bits(m["pick"], inst.n)
        for tag, x in (("exact", x_exact), ("quantum", x_q)):
            mean, std = describe(x, inst.mu, inst.sigma)
            (exact_pts if tag == "exact" else quantum_pts).append((std, mean))
            rows.append({"plan": tag, "lam": lam, "sites": names_of(x, inst),
                         "expected": mean, "std": std, "bad_season": bad_season(x),
                         **({"rank": m["pick_rank"], "p_optimum": m["p_optimum"]}
                            if tag == "quantum" else {})})
        print(f"  lam={lam:<6} quantum pick is rank {m['pick_rank']} of "
              f"{prob['feasible'].sum()}  P(opt)={m['p_optimum']:.3f}")
    out["frontier"] = rows

    everything = [describe(x, inst.mu, inst.sigma)
                  for _, x in brute_force(inst.mu, inst.sigma, 0, inst.k)]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.scatter([s for _, s in everything], [m for m, _ in everything], s=8, c=GREY,
               label="all 210 valid plans")
    ax.plot(*zip(*exact_pts), "o-", c=BLUE, label="exact optimum (brute force)")
    ax.scatter(*zip(*quantum_pts), marker="*", s=220, facecolors="none",
               edgecolors=GREEN, linewidths=1.6, zorder=3, label="quantum (QAOA) pick")
    ax.scatter([g_std], [g_mean], marker="X", s=110, c=RED, zorder=4, label="greedy top-k")
    ax.set_xlabel("Risk: std. dev. of people served (thousands)")
    ax.set_ylabel("Expected people served (thousands)")
    ax.set_title("Coverage vs. flood risk")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig("results/frontier.png", dpi=150)
    plt.close(fig)


def noise_and_distribution(inst, out):
    """Experiment C: what the trained circuit outputs, ideally and with noise."""
    prob = problem(inst.mu, inst.sigma, LAM, inst.k)
    res = run_qaoa(inst.mu, inst.sigma, LAM, inst.k, "xy", 3, "cvar")

    # --- outcome distribution from 2048 ideal shots -----------------------
    probs = counts_to_probs(sample_counts(res), inst.n)
    top = np.argsort(probs)[::-1][:12]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    colours = [GREEN if b == prob["optimum"] else BLUE for b in top]
    ax.bar(range(len(top)), probs[top], color=colours)
    ax.set_xticks(range(len(top)), [f"#{(prob['sorted'] < prob['costs'][b] - 1e-9).sum() + 1}"
                                    for b in top], fontsize=8)
    ax.axhline(1 / prob["feasible"].sum(), ls="--", c=RED, lw=1, label="random guess")
    ax.set_xlabel("12 most-measured plans, labelled by their true rank (#1 = exact optimum, green)")
    ax.set_ylabel("Measured probability")
    ax.set_title("What the quantum circuit outputs (2048 shots, p = 3)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig("results/distribution.png", dpi=150)
    plt.close(fig)

    # --- depolarising noise sweep ----------------------------------------
    rows = []
    for err in (0.0, 0.001, 0.003, 0.01):
        if err == 0:
            counts, cx, depth = sample_counts(res), None, None
        else:
            counts, cx, depth = noisy_counts(res, err)
        m = metrics(counts_to_probs(counts, inst.n), prob)
        rows.append({"cx_error": err, "feasible_rate": m["feasible_rate"],
                     "p_optimum": m["p_optimum"], "pick_rank": m["pick_rank"],
                     "cx_gates": cx, "depth": depth})
        print(f"  CX error {err:<6} valid shots={m['feasible_rate']:.2f}  "
              f"P(opt)={m['p_optimum']:.3f}  pick rank={m['pick_rank']}")
    out["noise"] = rows
    fig, ax = plt.subplots(figsize=(6, 3.8))
    labels = [f"{r['cx_error']:.1%}" for r in rows]
    ax.plot(labels, [r["feasible_rate"] for r in rows], "o-", c=BLUE, label="valid shots (exactly k sites)")
    ax.plot(labels, [r["p_optimum"] for r in rows], "s-", c=GREEN, label="P(exact optimum)")
    ax.set_xlabel("Two-qubit gate error rate")
    ax.set_ylim(0, 1.05)
    ax.set_title(f"Effect of hardware noise ({rows[-1]['cx_gates']} CX gates)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig("results/noise.png", dpi=150)
    plt.close(fig)


def circuit_figure(inst):
    """One QAOA layer drawn with the Dicke preparation collapsed into a box."""
    q, c = qubo_matrix(inst.mu, inst.sigma, LAM)
    ham, _ = to_ising(q / default_scale(inst.mu, inst.sigma, LAM), 0)
    qc = QuantumCircuit(inst.n)
    qc.append(dicke_circuit(inst.n, inst.k).to_gate(label="Dicke state\n(k of n)"), range(inst.n))
    qc.barrier()
    cost_layer(qc, ham, 0.4)                  # example angles, for the picture only
    qc.barrier()
    xy_mixer_layer(qc, 0.6)
    fig = qc.draw("mpl", fold=60, scale=0.55)
    fig.savefig("results/circuit.png", dpi=130, bbox_inches="tight")
    plt.close(fig)


def main():
    inst = make_instance()
    out = {"instance": {"sites": inst.names, "k": inst.k, "lam": LAM}}
    print("A. method comparison");            method_comparison(inst, out)
    print("B. coverage-risk frontier");       frontier(inst, out)
    print("C. sampling and noise");           noise_and_distribution(inst, out)
    circuit_figure(inst)
    with open("results/results.json", "w") as f:
        json.dump(out, f, indent=2, default=float)
    print("saved figures and results.json in results/")


if __name__ == "__main__":
    main()
