import numpy as np
from src.instance import make_instance
from src.formulation import (qubo_matrix, cost, to_ising, index_to_bits,
                             bits_to_string, string_to_bits)
from src.baseline import brute_force, greedy_top_k


def test_ising_matches_cost_on_every_bitstring():
    inst = make_instance(n_scenarios=300)
    for penalty in (0.0, 3.0):
        q, c = qubo_matrix(inst.mu, inst.sigma, lam=0.02, k=inst.k, penalty=penalty)
        op, offset = to_ising(q, c)
        diag = np.real(np.diag(op.to_matrix()))
        for b in range(2 ** inst.n):
            assert np.isclose(diag[b] + offset, cost(index_to_bits(b, inst.n), q, c))


def test_penalty_is_zero_exactly_on_feasible_selections():
    inst = make_instance(n_scenarios=300)
    q0, c0 = qubo_matrix(inst.mu, inst.sigma, 0.02)
    q1, c1 = qubo_matrix(inst.mu, inst.sigma, 0.02, k=inst.k, penalty=5.0)
    for b in range(2 ** inst.n):
        x = index_to_bits(b, inst.n)
        extra = cost(x, q1, c1) - cost(x, q0, c0)
        assert np.isclose(extra, 5.0 * (x.sum() - inst.k) ** 2)


def test_bitstring_round_trip():
    x = np.array([1, 0, 0, 1, 0])
    assert bits_to_string(x) == "01001"
    assert (string_to_bits(bits_to_string(x)) == x).all()


def test_brute_force_respects_k_and_beats_greedy():
    inst = make_instance(n_scenarios=300)
    results = brute_force(inst.mu, inst.sigma, 0.02, inst.k)
    assert all(x.sum() == inst.k for _, x in results)
    q, c = qubo_matrix(inst.mu, inst.sigma, 0.02)
    assert results[0][0] <= cost(greedy_top_k(inst.mu, inst.k), q, c) + 1e-9
