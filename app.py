"""Flood Relief Stockpile Planner - interactive front end.

Run with:   streamlit run app.py

The page is written for a relief planner, not a physicist: pick a budget and
a caution level, press one button, get a plan. The quantum details live in
their own tab for anyone who wants to check the working.
"""
import numpy as np
import pandas as pd
import altair as alt
import pydeck as pdk
import streamlit as st

from src.instance import make_instance, simulate_served, BASIN_FLOOD_PROB
from src.formulation import index_to_bits
from src.baseline import greedy_top_k, describe
from src.qaoa import run_qaoa, sample_counts, noisy_counts
from src.evaluate import problem, metrics, counts_to_probs, rank_of

st.set_page_config(page_title="Flood Relief Stockpile Planner", page_icon="🌊", layout="wide")

# Plain-language caution levels -> risk weight (lambda) in the objective.
CAUTION = {"Maximise reach": 0.0, "Slightly cautious": 0.002, "Balanced": 0.005,
           "Cautious": 0.01, "Very cautious": 0.02}
# Plain-language effort levels -> number of QAOA layers (p).
EFFORT = {"Quick (1 layer)": 1, "Standard (2 layers)": 2, "Thorough (3 layers)": 3}
GREEN, GREY, RED, BLUE = "#2a9d8f", "#9aa0a6", "#d1495b", "#1f6fb4"
# map label offsets in pixels [right, down] for cities that sit close together
LABEL_OFFSET = {"Nowshera": [48, 6], "Charsadda": [-50, -6], "D.G. Khan": [-48, 0],
                "Muzaffargarh": [0, -22], "Multan": [36, 8], "Larkana": [-40, 0],
                "Sukkur": [36, 0], "Dadu": [0, 22]}


# --------------------------------------------------------------------------
# Cached computations (Streamlit re-runs this file on every click, so the
# slow steps are cached by their inputs)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def get_instance(k, flood_items):
    """Simulated flood seasons summarised as the optimisation input."""
    return make_instance(k=k, flood_prob=dict(flood_items))


@st.cache_data(show_spinner=False)
def get_fresh_seasons(flood_items):
    """20,000 new seasons the optimiser never saw, for honest stress tests."""
    return simulate_served(20000, np.random.default_rng(999), dict(flood_items))[4]


@st.cache_resource(show_spinner=False, max_entries=64)
def solve(k, lam, flood_items, depth):
    """Train the constraint-preserving QAOA and measure it 2048 times.

    cache_resource (not cache_data) on purpose: the result holds a Qiskit
    circuit, which must be kept as a live object rather than pickled."""
    inst = get_instance(k, flood_items)
    res = run_qaoa(inst.mu, inst.sigma, lam, k, method="xy", p=depth, objective="cvar")
    probs = counts_to_probs(sample_counts(res), inst.n)
    stats = {"qubits": res.circuit.num_qubits, "gates": res.circuit.size(),
             "depth": res.circuit.depth(), "evaluations": res.evaluations}
    return res, probs, stats


@st.cache_data(show_spinner=False)
def solve_noisy(k, lam, flood_items, depth, error):
    """Re-measure the same trained circuit on a noisy simulated device."""
    res, _, _ = solve(k, lam, flood_items, depth)
    counts, cx, _ = noisy_counts(res, error)
    return counts_to_probs(counts, res.circuit.num_qubits), cx


def people(thousands):
    """Format a 'thousands of people' number for humans: 255.5 -> 255,500."""
    return f"{thousands * 1000:,.0f}"


def plan_summary(x, inst, fresh):
    """Business numbers for one plan (x = 0/1 vector over sites)."""
    outcomes = fresh @ x                              # people reached, per season
    return {"sites": [n for n, v in zip(inst.names, x) if v],
            "basins": sorted({b for b, v in zip(inst.basins, x) if v}),
            "typical": describe(x, inst.mu, inst.sigma)[0],
            "bad_year": float(np.percentile(outcomes, 5)),
            # how often more than half of the stocked capacity is unreachable
            "half_lost": float((outcomes < 0.5 * (inst.capacity @ x)).mean()),
            "outcomes": outcomes}


# --------------------------------------------------------------------------
# Sidebar: the only inputs a planner has to touch
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Your decision")
    with st.form("controls"):
        k = st.slider("Warehouses you can afford to stock", 2, 6, 4,
                      help="Budget: how many of the 10 candidate sites get relief stock.")
        caution = st.select_slider(
            "How cautious should the plan be?", options=list(CAUTION), value="Balanced",
            help="Left: reach as many people as possible in an average year. "
                 "Right: accept a little less reach so one flood cannot wipe out most of the stock.")
        with st.expander("Flood outlook this season"):
            st.caption("Chance of a severe flood in each river basin.")
            flood = {b: st.slider(b, 0, 100, int(p * 100), 5, format="%d%%") / 100
                     for b, p in BASIN_FLOOD_PROB.items()}
        with st.expander("Quantum solver effort"):
            effort = st.radio("More layers = better answer, longer wait",
                              list(EFFORT), index=2, label_visibility="collapsed")
        st.form_submit_button("Find the best plan", type="primary", width="stretch")
    st.caption("Demo data is synthetic. See the *About* tab.")

lam, depth = CAUTION[caution], EFFORT[effort]
flood_items = tuple(sorted(flood.items()))            # hashable key for the cache

# --------------------------------------------------------------------------
# Solve
# --------------------------------------------------------------------------
inst = get_instance(k, flood_items)
fresh = get_fresh_seasons(flood_items)
with st.spinner("Running the quantum optimiser (about 10 seconds the first time)..."):
    res, probs, stats = solve(k, lam, flood_items, depth)

prob = problem(inst.mu, inst.sigma, lam, k)           # exact reference
m = metrics(probs, prob)                               # quantum quality numbers
x_quantum = index_to_bits(m["pick"], inst.n)           # the recommended plan
x_naive = greedy_top_k(inst.mu, k)                     # "biggest sites" plan
x_exact = index_to_bits(prob["optimum"], inst.n)       # proven best plan
quantum, naive, exact = (plan_summary(x, inst, fresh) for x in (x_quantum, x_naive, x_exact))
n_plans = int(prob["feasible"].sum())

# --------------------------------------------------------------------------
# Headline
# --------------------------------------------------------------------------
st.title("🌊 Flood Relief Stockpile Planner")
st.write("Decide **where to pre-position relief supplies before the monsoon**, so that "
         "a single flood cannot cut off most of your stock. The plan is found by a "
         "quantum optimisation algorithm and checked against every possible plan.")

st.subheader("Recommended: stock " + ", ".join(quantum["sites"]))
same_as_naive = quantum["sites"] == naive["sites"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("People reached, typical year", people(quantum["typical"]),
          None if same_as_naive else f"{(quantum['typical'] - naive['typical']) * 1000:+,.0f} vs biggest-sites plan",
          help="Average over simulated flood seasons.")
c2.metric("People reached, bad flood year", people(quantum["bad_year"]),
          None if same_as_naive else f"{(quantum['bad_year'] - naive['bad_year']) * 1000:+,.0f} vs biggest-sites plan",
          help="The 1-in-20 worst season, across 20,000 freshly simulated seasons.")
c3.metric("Chance over half the stock is cut off", f"{quantum['half_lost']:.0%}",
          None if same_as_naive else f"{(quantum['half_lost'] - naive['half_lost']) * 100:+.0f} pts",
          delta_color="inverse", help="Lower is better.")
c4.metric("River basins covered", f"{len(quantum['basins'])} of {len(BASIN_FLOOD_PROB)}",
          None if same_as_naive else f"{len(quantum['basins']) - len(naive['basins']):+d} vs biggest-sites plan")

if m["pick_rank"] == 1:
    st.success(f"✅ Verified: out of all {n_plans} possible plans, this is the best one "
               f"at the **{caution.lower()}** setting.")
else:
    st.warning(f"The quantum pick ranks #{m['pick_rank']} of {n_plans} possible plans "
               f"(within {m['pick_gap']:.1%} of the best). Try the *Thorough* solver effort.")

tab_plan, tab_compare, tab_quantum, tab_about = st.tabs(
    ["📍 The plan", "⚖️ Compare options", "⚛️ Under the hood", "ℹ️ About"])

# --------------------------------------------------------------------------
# Tab 1: map + reasons
# --------------------------------------------------------------------------
with tab_plan:
    left, right = st.columns([3, 2])
    sites = pd.DataFrame({
        "Site": inst.names, "River basin": inst.basins,
        "Can serve": [people(c) for c in inst.capacity],
        "Stock here?": ["Yes" if v else "No" for v in x_quantum],
        "lat": inst.coords[:, 0], "lon": inst.coords[:, 1],
        "colour": [[42, 157, 143] if v else [154, 160, 166] for v in x_quantum],
        "radius": [26000 if v else 14000 for v in x_quantum],
        # nudge labels of neighbouring cities apart so they stay readable
        "offset": [LABEL_OFFSET.get(n, [0, -22]) for n in inst.names]})
    with left:
        dots = pdk.Layer("ScatterplotLayer", sites, get_position="[lon, lat]",
                         get_fill_color="colour", get_radius="radius", pickable=True, opacity=0.85)
        labels = pdk.Layer("TextLayer", sites, get_position="[lon, lat]", get_text="Site",
                           get_size=13, get_color=[30, 30, 30], get_pixel_offset="offset")
        st.pydeck_chart(pdk.Deck(
            layers=[dots, labels], map_style="light",
            initial_view_state=pdk.ViewState(latitude=30.6, longitude=70.2, zoom=4.8), height=520,
            tooltip={"text": "{Site}\n{River basin} basin\nCan serve {Can serve}\nStock here? {Stock here?}"}))
        st.caption("🟢 stock here · ⚪ candidate site not chosen")
    with right:
        st.markdown("**Why this plan**")
        reasons = [f"It spreads stock across **{len(quantum['basins'])} river basins** "
                   f"({', '.join(quantum['basins'])}), so one flood cannot isolate everything."]
        if same_as_naive:
            reasons.append("At this caution level it is the same as simply stocking the "
                           "biggest sites. Move the caution slider right to protect against bad years.")
        else:
            reasons.append(f"In a bad flood year it still reaches **{people(quantum['bad_year'])}** "
                           f"people; the biggest-sites plan reaches {people(naive['bad_year'])}.")
            reasons.append(f"The price: **{people(naive['typical'] - quantum['typical'])}** fewer people "
                           f"in a typical year ({1 - quantum['typical'] / naive['typical']:.0%} less).")
        st.markdown("\n".join(f"- {r}" for r in reasons))
        st.dataframe(sites[["Site", "River basin", "Can serve", "Stock here?"]],
                     hide_index=True, width="stretch")

# --------------------------------------------------------------------------
# Tab 2: plan comparison + stress test
# --------------------------------------------------------------------------
with tab_compare:
    plans = {"Biggest sites (no risk view)": naive, "Quantum recommendation": quantum,
             "Proven best (checked all plans)": exact}
    st.dataframe(pd.DataFrame([{
        "Plan": name, "Stock at": ", ".join(p["sites"]),
        "Typical year": people(p["typical"]), "Bad flood year": people(p["bad_year"]),
        "Chance over half is cut off": f"{p['half_lost']:.0%}",
        "Basins": len(p["basins"])} for name, p in plans.items()]),
        hide_index=True, width="stretch")

    st.markdown("**Stress test: people reached across 20,000 simulated flood seasons**")
    bins = np.linspace(0, max(naive["outcomes"].max(), quantum["outcomes"].max()), 16)
    hist = pd.concat([pd.DataFrame({
        "People reached (thousands)": bins[:-1].round(0),
        "Share of seasons": np.histogram(p["outcomes"], bins)[0] / len(p["outcomes"]),
        "Plan": name}) for name, p in list(plans.items())[:2]])
    st.altair_chart(
        alt.Chart(hist).mark_bar(opacity=0.85).encode(
            x=alt.X("People reached (thousands):O"),
            y=alt.Y("Share of seasons:Q", axis=alt.Axis(format="%")),
            xOffset="Plan:N",
            color=alt.Color("Plan:N", scale=alt.Scale(range=[RED, GREEN]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=["Plan", "People reached (thousands)", alt.Tooltip("Share of seasons", format=".1%")]),
        width="stretch")
    st.caption("Read it left to right: bars on the left are disaster years where few people "
               "are reached. A good plan has small bars on the left.")

# --------------------------------------------------------------------------
# Tab 3: the quantum working, for technical reviewers
# --------------------------------------------------------------------------
with tab_quantum:
    st.markdown(
        f"Each candidate site is one **qubit** (1 = stock it). The circuit starts in a "
        f"**Dicke state**, an equal mix of all {n_plans} plans that use exactly {k} sites, "
        f"and alternates {depth} cost/**XY-mixer** layer(s). The XY mixer only swaps a "
        f"chosen site for an unchosen one, so the budget can never be violated. A classical "
        f"optimiser (COBYLA) tunes the {2 * depth} angles to minimise CVaR of the cost.")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Qubits", stats["qubits"])
    q2.metric("Gates / depth", f"{stats['gates']} / {stats['depth']}")
    q3.metric("Circuits simulated", stats["evaluations"])
    q4.metric("Shots measured", "2,048")
    q5, q6, q7, q8 = st.columns(4)
    q5.metric("Shots that respect the budget", f"{m['feasible_rate']:.0%}")
    q6.metric("Approximation ratio", f"{m['approx_ratio']:.2f}",
              help="1.00 = every shot is the optimum, 0 = every shot is the worst plan.")
    q7.metric("P(exact optimum)", f"{m['p_optimum']:.1%}")
    q8.metric("Boost over random guess", f"{m['amplification']:.0f}×",
              help=f"A blind guess hits the optimum with probability 1/{n_plans}.")

    top = np.argsort(probs)[::-1][:10]
    dist = pd.DataFrame({
        "Plan": [", ".join(n for n, v in zip(inst.names, index_to_bits(b, inst.n)) if v) for b in top],
        "True rank": [f"#{rank_of(int(b), prob)}" for b in top],
        "Measured probability": probs[top],
        "Kind": ["Exact optimum" if b == prob["optimum"] else "Other plan" for b in top]})
    bars = alt.Chart(dist).mark_bar().encode(
        x=alt.X("Measured probability:Q", axis=alt.Axis(format="%"), title="Measured probability"),
        y=alt.Y("Plan:N", sort="-x", title=None, axis=alt.Axis(labelLimit=330)),
        color=alt.Color("Kind:N", scale=alt.Scale(domain=["Exact optimum", "Other plan"],
                                                  range=[GREEN, BLUE]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["Plan", "True rank", alt.Tooltip("Measured probability", format=".1%")])
    guess = alt.Chart(pd.DataFrame({"x": [1 / n_plans]})).mark_rule(
        color=RED, strokeDash=[4, 4]).encode(x=alt.X("x:Q", title=None))
    st.markdown("**The 10 plans the quantum computer measured most often**")
    st.altair_chart(bars + guess, width="stretch")
    st.caption("Dashed red line: how often a random valid plan would appear. The quantum "
               "shortlist (top 5) is then scored exactly by a classical check, which picks the winner.")

    st.markdown("**What would real hardware noise do?**")
    error = st.select_slider("Two-qubit gate error rate", [0.001, 0.003, 0.01], value=0.003,
                             format_func=lambda e: f"{e:.1%}")
    if st.button("Simulate a noisy quantum device"):
        with st.spinner("Simulating noise..."):
            noisy_probs, cx = solve_noisy(k, lam, flood_items, depth, error)
        nm = metrics(noisy_probs, prob)
        n1, n2, n3 = st.columns(3)
        n1.metric("Shots that respect the budget", f"{nm['feasible_rate']:.0%}",
                  f"{(nm['feasible_rate'] - m['feasible_rate']) * 100:+.0f} pts")
        n2.metric("P(exact optimum)", f"{nm['p_optimum']:.1%}",
                  f"{(nm['p_optimum'] - m['p_optimum']) * 100:+.1f} pts")
        n3.metric("Rank of the pick after discarding invalid shots", f"#{nm['pick_rank']}")
        st.caption(f"The circuit compiles to {cx} CX gates. Noise breaks the budget guarantee, "
                   "so invalid shots are thrown away (post-selection).")

# --------------------------------------------------------------------------
# Tab 4: assumptions and limits, stated plainly
# --------------------------------------------------------------------------
with tab_about:
    st.markdown(f"""
**What the tool does.** It chooses {k} of 10 candidate warehouse sites to maximise
*expected people reached − caution × risk*, where risk is the variance of people reached
across simulated flood seasons. Sites in the same river basin tend to be cut off together,
which is exactly what the risk term penalises.

**What is real and what is not.**
- Site names and river basins are real places; capacities and flood odds are **synthetic**.
- A flood season is simulated as: each basin floods or not; sites in a flooded basin are
  probably cut off; a cut-off site serves nobody.
- Results are **verified against brute force** over all {n_plans} plans on every run.

**Honest limits.**
- At 10 sites a laptop solves this instantly, so there is **no quantum speed-up here**.
  The value is a correct, constraint-preserving quantum formulation that scales in qubits
  one-for-one with sites.
- The quantum circuit runs on a simulator. Under realistic noise many shots break the
  budget rule (see *Under the hood*).
- Variance treats good and bad surprises alike; a real planner may prefer a downside-only
  risk measure.
""")
