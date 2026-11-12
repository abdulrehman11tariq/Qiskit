"""Stage 2 - objective, QUBO and Ising Hamiltonian.

Decision variable x_i = 1 if site i is stocked.

    maximise   mu.x  -  lam * x.Sigma.x      (expected people served - risk)
    subject to sum(x) = K

We MINIMISE cost(x) = -(mu.x) + lam * x.Sigma.x, divided by a constant
`scale` so coefficients are O(1) for the QAOA optimiser.

Bit convention (Qiskit little-endian): site i <-> qubit i <-> the i-th
character FROM THE RIGHT of a measured bitstring.
"""
import numpy as np
from qiskit.quantum_info import SparsePauliOp


def qubo_matrix(mu, sigma, lam, k=None, penalty=0.0):
    """Upper-triangular Q and constant c with cost(x) = x^T Q x + c.

    If penalty > 0, adds penalty * (sum(x) - k)^2 (needed only for the
    standard X-mixer QAOA; the XY-mixer version keeps sum(x) = k exactly).
    """
    n = len(mu)
    q = np.zeros((n, n))
    for i in range(n):
        q[i, i] = -mu[i] + lam * sigma[i, i]
        for j in range(i + 1, n):
            q[i, j] = 2 * lam * sigma[i, j]
    const = 0.0
    if penalty:
        # A(sum x - k)^2 = A[(1-2k) sum x_i + 2 sum_{i<j} x_i x_j + k^2]
        q[np.diag_indices(n)] += penalty * (1 - 2 * k)
        q[np.triu_indices(n, 1)] += 2 * penalty
        const = penalty * k * k
    return q, const


def default_scale(mu, sigma, lam):
    q, _ = qubo_matrix(mu, sigma, lam)
    return float(np.abs(q).max())


def cost(x, q, const=0.0):
    x = np.asarray(x, dtype=float)
    return float(x @ q @ x + const)


def to_ising(q, const=0.0):
    """Substitute x_i = (1 - z_i)/2. Returns (SparsePauliOp, offset) with
    cost(x) = <z|H|z> + offset for every computational basis state."""
    n = q.shape[0]
    h = np.zeros(n)
    terms = []
    offset = const
    for i in range(n):
        offset += q[i, i] / 2
        h[i] -= q[i, i] / 2
        for j in range(i + 1, n):
            if q[i, j] == 0:
                continue
            offset += q[i, j] / 4
            h[i] -= q[i, j] / 4
            h[j] -= q[i, j] / 4
            terms.append(("ZZ", [i, j], q[i, j] / 4))
    terms += [("Z", [i], h[i]) for i in range(n) if h[i] != 0]
    # terms are unique and non-zero by construction, so no simplification is needed
    return SparsePauliOp.from_sparse_list(terms, num_qubits=n), offset


def index_to_bits(b, n):
    """Basis-state index -> x vector, x[i] = bit of qubit i."""
    return np.array([(b >> i) & 1 for i in range(n)])


def bits_to_string(x):
    """x vector -> Qiskit bitstring (qubit 0 on the right)."""
    return "".join(str(int(v)) for v in reversed(x))


def string_to_bits(s):
    return np.array([int(c) for c in reversed(s)])
