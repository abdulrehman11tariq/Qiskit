"""Solver entry points used by the app.

The app runs these inside one long-lived helper process (src/worker.py),
so all Qiskit work happens on that process's main thread.

Everything returned here is plain data (numbers and numpy arrays), so it can
travel between processes and be cached safely.
"""
from .instance import make_instance
from .qaoa import run_qaoa, sample_counts, noisy_counts
from .evaluate import counts_to_probs

# trained circuits kept inside the worker, so the noise simulation can reuse
# them without retraining; key = (k, lam, flood_items, depth)
_TRAINED = {}


def _train(k, lam, flood_items, depth):
    """Train (or fetch) the constraint-preserving QAOA for these settings."""
    key = (k, lam, flood_items, depth)
    if key not in _TRAINED:
        inst = make_instance(k=k, flood_prob=dict(flood_items))
        _TRAINED[key] = run_qaoa(inst.mu, inst.sigma, lam, k,
                                 method="xy", p=depth, objective="cvar")
    return _TRAINED[key]


def plan(k, lam, flood_items, depth):
    """Train the circuit, measure it 2,048 times on an ideal simulator.
    Returns (measured probability of every bitstring, circuit statistics)."""
    res = _train(k, lam, flood_items, depth)
    n = res.circuit.num_qubits
    probs = counts_to_probs(sample_counts(res), n)
    stats = {"qubits": n, "gates": res.circuit.size(),
             "depth": res.circuit.depth(), "evaluations": res.evaluations}
    return probs, stats


def noisy_plan(k, lam, flood_items, depth, error):
    """Measure the same trained circuit on a noisy simulated device.
    Returns (measured probabilities, number of CX gates after compiling)."""
    res = _train(k, lam, flood_items, depth)
    counts, cx, _ = noisy_counts(res, error)
    return counts_to_probs(counts, res.circuit.num_qubits), cx
