"""Stage 4 - the quantum component (QAOA in Qiskit).

Two circuit families are built here:

* "penalty"  - textbook QAOA. Starts in the uniform superposition of ALL
               2^n bitstrings, uses an X mixer, and discourages selections
               with the wrong number of sites through a penalty term.
* "xy"       - constraint-preserving QAOA (Quantum Alternating Operator
               Ansatz). Starts in a Dicke state (equal superposition of the
               selections with EXACTLY k sites) and uses an XY mixer, which
               swaps a 1 and a 0 between two qubits and therefore can never
               change how many sites are selected.

Both can be trained on the mean cost or on CVaR (mean of the best alpha
fraction of outcomes).
"""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize
from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector
from qiskit.circuit.library import RYGate, XXPlusYYGate
from qiskit import transpile
from qiskit.primitives import StatevectorSampler
from qiskit.quantum_info import Statevector
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error

from .formulation import qubo_matrix, to_ising, default_scale

PENALTY = 2.0     # penalty weight, in units of the largest (scaled) coefficient
CVAR_ALPHA = 0.10  # CVaR keeps the best 10% of the probability mass


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------
def dicke_circuit(n, k):
    """Prepare the Dicke state |D_n^k>: every n-bit string with exactly k
    ones, all with the same amplitude.

    Deterministic construction of Baertschi & Eidenbenz (2019). Start with
    the k ones packed on the highest qubits, then apply "split & cyclic
    shift" blocks that spread each one over the remaining qubits with exactly
    the right probability. Uses O(n*k) gates and no ancilla qubits.
    """
    qc = QuantumCircuit(n, name=f"Dicke({n},{k})")
    qc.x(range(n - k, n))                      # |0..0 1..1> : k ones on top
    for l in range(n, 1, -1):                  # block acts on the first l qubits
        kk = min(k, l - 1)                     # ones that can still move down
        last = l - 1                           # 0-based index of qubit "l"
        # (i) two-qubit split: |01> -> sqrt(1/l)|01> + sqrt((l-1)/l)|10>
        a = last - 1
        qc.cx(a, last)
        qc.cry(2 * np.arccos(np.sqrt(1 / l)), last, a)
        qc.cx(a, last)
        # (ii) three-qubit splits for the 2nd..kk-th one in the block
        for i in range(2, kk + 1):
            t = last - i                       # qubit the one may move to
            qc.cx(t, last)
            ccry = RYGate(2 * np.arccos(np.sqrt(i / l))).control(2, annotated=False)
            qc.append(ccry, [last, t + 1, t])  # two controls, then target
            qc.cx(t, last)
    return qc


def cost_layer(qc, hamiltonian, gamma):
    """Append exp(-i * gamma * H) for a Hamiltonian made of Z and ZZ terms.
    Z -> RZ rotation, ZZ -> RZZ rotation (both take angle 2*gamma*coeff)."""
    for pauli, coeff in zip(hamiltonian.paulis, hamiltonian.coeffs):
        qubits = [q for q in range(hamiltonian.num_qubits) if pauli.z[q]]
        angle = 2 * gamma * float(np.real(coeff))
        if len(qubits) == 1:
            qc.rz(angle, qubits[0])
        elif len(qubits) == 2:
            qc.rzz(angle, qubits[0], qubits[1])


def xy_mixer_layer(qc, beta):
    """Ring of XX+YY rotations. Each one partially swaps |01> and |10> on a
    neighbouring pair, so the number of selected sites is conserved."""
    n = qc.num_qubits
    pairs = [(i, i + 1) for i in range(0, n - 1, 2)]      # even bonds
    pairs += [(i, i + 1) for i in range(1, n - 1, 2)]     # odd bonds
    if n > 2:
        pairs.append((n - 1, 0))                          # close the ring
    for a, b in pairs:
        qc.append(XXPlusYYGate(2 * beta), [a, b])


def build_circuit(hamiltonian, k, p, method):
    """Return (circuit, gammas, betas) with p alternating cost/mixer layers."""
    n = hamiltonian.num_qubits
    gammas, betas = ParameterVector("gamma", p), ParameterVector("beta", p)
    qc = QuantumCircuit(n)
    if method == "xy":
        qc.compose(dicke_circuit(n, k), inplace=True)     # feasible start
    else:
        qc.h(range(n))                                    # all 2^n strings
    for layer in range(p):
        cost_layer(qc, hamiltonian, gammas[layer])
        if method == "xy":
            xy_mixer_layer(qc, betas[layer])
        else:
            qc.rx(2 * betas[layer], range(n))             # standard X mixer
    return qc, gammas, betas


# --------------------------------------------------------------------------
# Training
# --------------------------------------------------------------------------
def all_costs(q, const, n):
    """Cost of every bitstring; entry b uses bit i of b as x_i (the same
    ordering Qiskit uses for statevector indices)."""
    bits = (np.arange(2 ** n)[:, None] >> np.arange(n)) & 1
    return np.einsum("bi,ij,bj->b", bits, q, bits) + const


def cvar(probs, costs, alpha):
    """Mean cost of the best `alpha` fraction of the outcome distribution."""
    order = np.argsort(costs)
    p_sorted, c_sorted = probs[order], costs[order]
    cum = np.cumsum(p_sorted)
    take = np.clip(alpha - (cum - p_sorted), 0, p_sorted)  # mass taken per state
    return float(take @ c_sorted / alpha)


@dataclass
class QAOAResult:
    method: str            # "penalty" or "xy"
    p: int                 # number of QAOA layers
    objective: str         # "mean" or "cvar"
    params: np.ndarray     # optimal [gammas..., betas...]
    probs: np.ndarray      # final probability of each of the 2^n bitstrings
    circuit: QuantumCircuit  # bound (parameter-free) circuit, no measurements
    evaluations: int       # how many circuits the optimiser simulated


def interpolate(params, p):
    """INTERP warm start: stretch the optimal depth-p angles to depth p+1."""
    out = []
    for vec in (params[:p], params[p:]):
        new = [(i / p) * (vec[i - 1] if i > 0 else 0)
               + ((p - i) / p) * (vec[i] if i < p else 0) for i in range(p + 1)]
        out.extend(new)
    return np.array(out)


def run_qaoa(mu, sigma, lam, k, method="xy", p=2, objective="mean", maxiter=150):
    """Train QAOA on an exact statevector simulation and return the result.

    Depth is grown one layer at a time: depth 1 starts from a coarse grid
    scan, each deeper circuit starts from the interpolated previous optimum.
    """
    n = len(mu)
    scale = default_scale(mu, sigma, lam)      # makes coefficients O(1)
    penalty = PENALTY * scale if method == "penalty" else 0.0
    q, const = qubo_matrix(mu, sigma, lam, k=k, penalty=penalty)
    hamiltonian, _ = to_ising(q / scale, const / scale)
    costs = all_costs(q, const, n) / scale     # what the optimiser minimises
    evals = 0

    def make_loss(depth):
        qc, gammas, betas = build_circuit(hamiltonian, k, depth, method)

        def probabilities(theta):
            bound = qc.assign_parameters(
                {**dict(zip(gammas, theta[:depth])), **dict(zip(betas, theta[depth:]))})
            return Statevector(bound).probabilities(), bound

        def loss(theta):
            nonlocal evals
            evals += 1
            probs, _ = probabilities(theta)
            if objective == "cvar":
                return cvar(probs, costs, CVAR_ALPHA)
            return float(probs @ costs)
        return loss, probabilities

    # depth 1: coarse grid, then local refinement
    loss, probabilities = make_loss(1)
    # the penalty term makes coefficients larger, so the useful gamma range shrinks
    span = 1.5 / max(1.0, float(np.abs(hamiltonian.coeffs).max()))
    grid = [(g, b) for g in np.linspace(-span, span, 11) for b in np.linspace(0.1, 1.5, 6)]
    theta = np.array(min(grid, key=lambda t: loss(np.array(t))))
    theta = minimize(loss, theta, method="COBYLA", options={"maxiter": maxiter}).x
    # deeper circuits: warm start from the previous depth
    for depth in range(2, p + 1):
        loss, probabilities = make_loss(depth)
        theta = minimize(loss, interpolate(theta, depth - 1), method="COBYLA",
                         options={"maxiter": maxiter}).x
    probs, bound = probabilities(theta)
    return QAOAResult(method, p, objective, theta, probs, bound, evals)


# --------------------------------------------------------------------------
# Measuring the trained circuit
# --------------------------------------------------------------------------
def sample_counts(result, shots=2048, seed=1):
    """Measure the trained circuit `shots` times on an ideal (noise-free)
    simulator. Returns {bitstring: count}; qubit 0 is the rightmost bit."""
    measured = result.circuit.copy()
    measured.measure_all()
    job = StatevectorSampler(seed=seed).run([measured], shots=shots)
    return job.result()[0].data.meas.get_counts()


BASIS_GATES = ["cx", "rz", "sx", "x"]  # typical superconducting-hardware gate set


def noisy_counts(result, two_qubit_error=0.01, shots=2048, seed=1):
    """Measure the trained circuit on a noisy simulator.

    Every CX gate suffers depolarising noise with probability
    `two_qubit_error`; single-qubit gates get a tenth of that. Returns
    (counts, number_of_cx_gates, circuit_depth) after compiling the circuit
    to hardware-style gates.
    """
    noise = NoiseModel()
    noise.add_all_qubit_quantum_error(depolarizing_error(two_qubit_error, 2), ["cx"])
    noise.add_all_qubit_quantum_error(depolarizing_error(two_qubit_error / 10, 1), ["sx", "x"])
    measured = result.circuit.copy()
    measured.measure_all()
    compiled = transpile(measured, basis_gates=BASIS_GATES, optimization_level=1,
                         seed_transpiler=seed)
    backend = AerSimulator(noise_model=noise, seed_simulator=seed)
    counts = backend.run(compiled, shots=shots).result().get_counts()
    return counts, compiled.count_ops().get("cx", 0), compiled.depth()
