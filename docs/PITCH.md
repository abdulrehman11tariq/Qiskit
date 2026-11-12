# 3-minute pitch script

| Time | Screen | Say |
|---|---|---|
| 0:00–0:25 | App headline | "Before every monsoon, relief agencies choose where to store supplies. The obvious choice is the sites that reach the most people. The problem: those sites share river basins, and a flood cuts off a whole basin at once." |
| 0:25–0:55 | Caution slider fully left, then *Balanced* | "With the slider on *maximise reach* we get the obvious plan: two basins, 90,000 people reached in a bad year. On *balanced*, stock spreads over four basins. We give up 7% in a normal year and reach 51% more people in a bad one." |
| 0:55–1:20 | README formulation | "This is two competing objectives: expected reach minus caution times risk. Risk is a covariance matrix, so the problem is quadratic in yes/no variables. That is exactly the form a quantum cost Hamiltonian takes: one site, one qubit; one correlation, one two-qubit gate." |
| 1:20–1:55 | *Under the hood* tab | "Standard QAOA handles the budget with a penalty and wastes shots on invalid plans. We build the budget into the circuit: a Dicke state starts us on only the 210 valid plans, and an XY mixer swaps sites without ever changing how many are chosen. Every shot is valid." |
| 1:55–2:25 | `results/methods.png` | "Against brute force: the penalty version finds the optimum no better than guessing. Ours measures it 21 times more often than a random guess, and the final pick matched the exact optimum at all six caution levels." |
| 2:25–2:50 | Noise button | "We are honest about limits. This is a simulator. At a 1% gate error only a quarter of shots stay valid, and at ten sites a laptop needs no quantum computer." |
| 2:50–3:00 | App headline | "What we show is a correct, verified quantum formulation of a real planning trade-off, in a tool a planner can actually use." |

## Likely questions

- **Why not a penalty term?** It needs a tuned weight and half the shots at p = 1 are invalid; the XY mixer makes the constraint exact at no qubit cost.
- **Is there quantum advantage?** No, and we do not claim it. 210 plans is trivially classical.
- **Why CVaR?** We only keep the best measured plans, so optimising the best tail matches how the output is used. It doubled P(optimum) at p = 3.
- **How do you know the Hamiltonian is right?** A unit test compares it with the classical cost on all 1,024 bitstrings.
- **Why top-5 shortlist?** One measurement is noisy; scoring five candidates classically is cheap. We report P(optimum) separately so the shortlist does not hide weak circuits.
- **Is the data real?** Site names are; capacities and flood odds are synthetic and labelled as such.
- **What would hardware need?** Roughly 10× lower two-qubit error, or a shallower Dicke preparation plus symmetry-based error mitigation.
