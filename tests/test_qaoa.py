import numpy as np
from math import comb
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
from src.qaoa import dicke_circuit, xy_mixer_layer, cvar


def weights(n):
    """Number of ones in every n-bit basis state index."""
    return np.array([bin(b).count("1") for b in range(2 ** n)])


def test_dicke_state_is_uniform_over_exactly_k_ones():
    for n, k in [(4, 2), (5, 1), (6, 3), (8, 7), (10, 4)]:
        amps = Statevector(dicke_circuit(n, k)).data
        w = weights(n)
        assert np.allclose(amps[w == k], 1 / np.sqrt(comb(n, k)))   # equal amplitudes
        assert np.allclose(amps[w != k], 0)                          # nothing else


def test_xy_mixer_never_changes_the_number_of_selected_sites():
    n, k = 6, 2
    qc = dicke_circuit(n, k)
    for beta in (0.3, 1.1, 2.0):
        xy_mixer_layer(qc, beta)
    probs = Statevector(qc).probabilities()
    assert np.isclose(probs[weights(n) == k].sum(), 1.0)


def test_cvar_is_mean_of_best_tail():
    probs, costs = np.array([0.5, 0.3, 0.2]), np.array([3.0, 1.0, 2.0])
    assert np.isclose(cvar(probs, costs, 1.0), probs @ costs)       # alpha=1 -> plain mean
    assert np.isclose(cvar(probs, costs, 0.3), 1.0)                 # best 30% all cost 1
    assert np.isclose(cvar(probs, costs, 0.4), (0.3 * 1 + 0.1 * 2) / 0.4)
