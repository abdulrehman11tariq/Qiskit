"""Stage 1 - synthetic flood-relief instance.

Ten candidate warehouse sites in four river basins. A flood season is one
"scenario": each basin either has a severe flood or not, and a site in a
flooded basin is likely to be cut off. Stock at a cut-off site serves nobody.

All numbers are SYNTHETIC and only shaped to be plausible; real use would
replace `SITES` and the scenario generator with historical flood records.
"""
from dataclasses import dataclass
import json
import numpy as np

# name, basin, people the stock can serve (thousands), P(cut off | basin floods),
# latitude, longitude (approximate city centres, used only for the map)
SITES = [
    ("Nowshera",     "Kabul",        95, 0.85, 34.02, 71.98),
    ("Charsadda",    "Kabul",        90, 0.80, 34.15, 71.74),
    ("Sukkur",       "Lower Indus", 100, 0.75, 27.71, 68.85),
    ("Larkana",      "Lower Indus",  92, 0.80, 27.56, 68.21),
    ("Dadu",         "Lower Indus",  88, 0.85, 26.73, 67.78),
    ("Rajanpur",     "Mid Indus",    80, 0.80, 29.10, 70.33),
    ("D.G. Khan",    "Mid Indus",    76, 0.70, 30.05, 70.64),
    ("Muzaffargarh", "Chenab",       72, 0.70, 30.07, 71.19),
    ("Jhang",        "Chenab",       66, 0.60, 31.27, 72.32),
    ("Multan",       "Chenab",       60, 0.25, 30.20, 71.47),
]
# P(severe flood this season) per basin
BASIN_FLOOD_PROB = {"Kabul": 0.30, "Lower Indus": 0.35, "Mid Indus": 0.30, "Chenab": 0.25}
BACKGROUND_CUTOFF = 0.03  # road washout etc. even when the basin does not flood


@dataclass
class Instance:
    names: list
    basins: list
    capacity: np.ndarray   # (n,)   thousands of people
    coords: np.ndarray     # (n, 2) latitude, longitude
    served: np.ndarray     # (S, n) people served per scenario, thousands
    mu: np.ndarray         # (n,)   expected people served
    sigma: np.ndarray      # (n, n) covariance of people served
    k: int                 # number of sites to stock

    @property
    def n(self):
        return len(self.names)


def simulate_served(n_scenarios, rng, flood_prob=None):
    """Simulate flood seasons. Returns (names, basins, capacity, coords,
    served) where served[s, i] = people site i serves in season s.
    `flood_prob` optionally overrides BASIN_FLOOD_PROB (basin -> probability)."""
    flood_prob = {**BASIN_FLOOD_PROB, **(flood_prob or {})}
    names = [s[0] for s in SITES]
    basins = [s[1] for s in SITES]
    cap = np.array([s[2] for s in SITES], dtype=float)
    p_cut = np.array([s[3] for s in SITES])
    coords = np.array([s[4:6] for s in SITES])
    basin_names = list(flood_prob)
    # one coin flip per basin per season: does this basin flood severely?
    flood = rng.random((n_scenarios, len(basin_names))) < np.array(
        [flood_prob[b] for b in basin_names])
    site_basin = np.array([basin_names.index(b) for b in basins])
    in_flood = flood[:, site_basin]                       # (S, n)
    # a site is cut off with high probability if its basin floods, else rarely
    p = np.where(in_flood, p_cut, BACKGROUND_CUTOFF)
    cut_off = rng.random(p.shape) < p
    return names, basins, cap, coords, cap * (~cut_off)   # cut off -> serves 0


def make_instance(k=4, n_scenarios=2000, seed=7, flood_prob=None):
    """Build the optimisation input: simulate seasons, then summarise them as
    mu (average reach per site) and sigma (how sites' reach moves together)."""
    rng = np.random.default_rng(seed)
    names, basins, cap, coords, served = simulate_served(n_scenarios, rng, flood_prob)
    return Instance(names, basins, cap, coords, served,
                    served.mean(axis=0), np.cov(served, rowvar=False), k)


def save_instance(inst, path):
    with open(path, "w") as f:
        json.dump({"names": inst.names, "basins": inst.basins, "k": inst.k,
                   "capacity": inst.capacity.tolist(),
                   "mu": inst.mu.round(4).tolist(),
                   "sigma": inst.sigma.round(4).tolist()}, f, indent=2)
