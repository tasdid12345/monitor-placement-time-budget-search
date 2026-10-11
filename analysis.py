"""Monitor placement: greedy-seeded sampled swap local search vs random-restart swap local search."""
import gzip, itertools, json, os, sys, time
from time import perf_counter
import numpy as np, pandas as pd, networkx as nx, requests

URL = "https://snap.stanford.edu/data/as-caida20071105.txt.gz"
SEEDS = [42, 43, 44, 45, 46]          # 42-44 required, two extra for the 5-seed design
KS, BUDGETS = (10, 20), (0.5, 2.0, 8.0)
GRID = list(itertools.product((10, 50, 200), (1, 4)))   # (neighbourhood sample, restarts)
PATIENCE = 1000                        # baseline: restart after this many non-improving swaps
N_NODES, N_PAIRS = 1000, 6000


def load_graph():
    """Download a SNAP AS graph (retry on 429/5xx); fall back to a generated Internet-like graph."""
    try:
        for a in range(4):
            r = requests.get(URL, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** a); continue
            r.raise_for_status(); break
        else:
            raise RuntimeError("retries exhausted")
        G = nx.Graph()
        for ln in gzip.decompress(r.content).decode().splitlines():
            if ln and ln[0] != "#":
                p = ln.split(); G.add_edge(int(p[0]), int(p[1]))
        src = URL
    except Exception as e:
        print("download failed, using fallback:", e)
        G = nx.random_internet_as_graph(N_NODES, seed=42); src = "networkx.random_internet_as_graph"
    G.remove_edges_from(nx.selfloop_edges(G))
    G = G.subgraph(max(nx.connected_components(G), key=len))
    root = max(G.degree, key=lambda x: x[1])[0]          # BFS ball around the top hub (connected)
    nodes = [root] + [v for _, v in nx.bfs_edges(G, root)]
    G = nx.convert_node_labels_to_integers(G.subgraph(nodes[:N_NODES]).copy())
    return G, src


def incidence(G, pairs):
    """Boolean matrix (node x pair): node lies on the (one) shortest path of the pair."""
    inc = np.zeros((G.number_of_nodes(), len(pairs)), bool)
    for j, (s, t) in enumerate(pairs):
        inc[nx.shortest_path(G, s, t), j] = True
    return inc


def swap_cov(inc, cnt, cov, u, v):
    """Coverage count after replacing monitor u by v (cnt = monitors covering each path)."""
    uniq = (cnt == 1) & inc[u]
    return cov - np.count_nonzero(uniq) + np.count_nonzero(inc[v] & ((cnt == 0) | uniq))


def search(inc, k, budget, seed, method, nsample=50, restarts=1):
    """Shared evaluator/time budget; method='base' (random restarts) or 'imp' (greedy seed)."""
    rng = np.random.default_rng(seed); N, P = inc.shape
    t0 = perf_counter(); trace = []; best = [-1, None]

    def init(nodes):
        nodes = list(nodes); cnt = inc[nodes].sum(0, dtype=np.int16); cov = int(np.count_nonzero(cnt))
        if cov > best[0]:
            best[0], best[1] = cov, list(nodes); trace.append((perf_counter() - t0, cov / P))
        return nodes, cnt, cov

    def move(nodes, cnt, i, v, new):
        cnt[inc[nodes[i]]] -= 1; cnt[inc[v]] += 1; nodes[i] = v
        if new > best[0]:
            best[0], best[1] = new, list(nodes); trace.append((perf_counter() - t0, new / P))
        return new

    if method == "base":
        while perf_counter() - t0 < budget:
            nodes, cnt, cov = init(rng.choice(N, k, replace=False)); stale = 0
            while stale < PATIENCE and perf_counter() - t0 < budget:
                i, v = int(rng.integers(k)), int(rng.integers(N))
                if v in nodes: continue
                new = swap_cov(inc, cnt, cov, nodes[i], v)
                if new > cov: cov = move(nodes, cnt, i, v, new); stale = 0   # first improvement
                else: stale += 1
    else:
        g_nodes, g_cnt = [], np.zeros(P, np.int16)         # greedy max-coverage seed (time counted)
        for _ in range(k):
            gain = inc[:, g_cnt == 0].sum(1); gain[g_nodes] = -1
            g_nodes.append(int(np.argmax(gain))); g_cnt[inc[g_nodes[-1]]] += 1
        for r in range(restarts):
            end = budget * (r + 1) / restarts
            if r == 0: nodes, cnt, cov = init(g_nodes)
            else:                                           # perturb incumbent ~30% of monitors
                b = list(best[1])
                for i in rng.choice(k, max(1, round(0.3 * k)), replace=False):
                    b[i] = int(rng.choice([x for x in range(N) if x not in b]))
                nodes, cnt, cov = init(b)
            while perf_counter() - t0 < end:                # best swap among a random sample
                bi, bv, bn = None, None, cov
                for _ in range(nsample):
                    i, v = int(rng.integers(k)), int(rng.integers(N))
                    if v in nodes: continue
                    new = swap_cov(inc, cnt, cov, nodes[i], v)
                    if new > bn: bn, bi, bv = new, i, v
                if bi is not None: cov = move(nodes, cnt, bi, bv, bn)
    return best[1], best[0] / P, trace


def t_reach(trace, target, budget):
    return next((t for t, c in trace if c >= target), budget)   # censored at the budget


def main():
    G, src = load_graph(); n = G.number_of_nodes()
    print(f"graph: {n} nodes, {G.number_of_edges()} edges ({src})")
    rng = np.random.default_rng(42); pairs = set()
    while len(pairs) < N_PAIRS:
        s, t = rng.integers(n, size=2)
        if s != t: pairs.add((int(min(s, t)), int(max(s, t))))
    pairs = sorted(pairs); rng.shuffle(pairs)
    cut = int(0.7 * len(pairs))                              # single split: search / held-out pairs
    inc_s, inc_e = incidence(G, pairs[:cut]), incidence(G, pairs[cut:])
    print(f"search pairs {inc_s.shape[1]}, held-out pairs {inc_e.shape[1]}")

    rows = []
    for k in KS:
        for b in BUDGETS:
            # tune (nsample, restarts) on search pairs only, with seeds disjoint from evaluation seeds
            sc = {g: np.mean([search(inc_s, k, b, 1000 + s, "imp", *g)[1] for s in range(2)]) for g in GRID}
            cfg = max(sc, key=sc.get); print(f"k={k} budget={b}: tuned (nsample, restarts)={cfg}")
            for seed in SEEDS:
                for m, kw in (("base", {}), ("imp", dict(nsample=cfg[0], restarts=cfg[1]))):
                    nodes, scov, tr = search(inc_s, k, b, seed, m, **kw)
                    rows.append(dict(k=k, budget=b, seed=seed, method=m, search=scov,
                                     heldout=float(inc_e[nodes].any(0).mean()), trace=tr))
            print(pd.DataFrame(rows).query("k==@k and budget==@b").groupby("method")[["search", "heldout"]].mean().round(4))
    df = pd.DataFrame(rows)

    # secondary: time to reach 95% of the best search coverage seen for that k (8 s runs)
    ref = df[df.budget == max(BUDGETS)].groupby("k").search.max()
    df["t95"] = [t_reach(r.trace, 0.95 * ref[r.k], r.budget) if r.budget == max(BUDGETS) else np.nan
                 for r in df.itertuples()]
    met = {}
    for m, name in (("base", "baseline"), ("imp", "improved")):
        d = df[df.method == m]
        per_seed = d.groupby("seed").heldout.mean()
        met[f"{name}_score"] = float(per_seed.mean()); met[f"{name}_score_std"] = float(per_seed.std(ddof=0))
        met[f"{name}_search_coverage"] = float(d.search.mean())
        met[f"{name}_time_to_95pct_s"] = float(d.t95.mean())
        for (k, b), v in d.groupby(["k", "budget"]).heldout.mean().items():
            met[f"{name}_heldout_k{k}_b{b}"] = float(v)
    met["improvement"] = met["improved_score"] - met["baseline_score"]
    if not all(np.isfinite(v) for v in met.values()) or met["baseline_score"] <= 0:
        sys.exit("no meaningful metrics")

    os.makedirs("figures", exist_ok=True)
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, len(KS), figsize=(9, 3.5), sharey=True)
    for a, k in zip(ax, KS):
        for j, (m, c) in enumerate((("base", "gray"), ("imp", "tab:blue"))):
            d = df[(df.k == k) & (df.method == m)].groupby("budget").heldout.agg(["mean", "std"])
            a.bar(np.arange(len(BUDGETS)) + 0.4 * j, d["mean"], 0.4, yerr=d["std"], color=c, label=m)
        a.set_xticks(np.arange(len(BUDGETS)) + 0.2); a.set_xticklabels(BUDGETS)
        a.set_title(f"k={k}"); a.set_xlabel("time budget (s)")
        lo = df[df.k == k].heldout.min(); a.set_ylim(lo - 0.02, None)
    ax[0].set_ylabel("held-out path coverage"); ax[0].legend()
    fig.tight_layout(); fig.savefig("figures/coverage_by_budget.png", dpi=120)

    res = {
        "question": "Under the same tight time budgets, can a greedy-seeded swap local search beat a random-restart local search at choosing k monitors covering the most shortest paths?",
        "method": "Largest-component ~1000-node subsample of a SNAP AS graph; one shortest path per sampled node pair, split 70/30 into search/held-out pairs; both methods use the same incidence-based coverage evaluator and wall-clock budgets; improved parameters tuned on search pairs only.",
        "dataset": {"name": "SNAP as-caida20071105 (BFS subsample ~1000 nodes)" if src == URL else "networkx random_internet_as_graph (fallback)",
                    "source_url": src, "n_rows": len(pairs), "n_train": cut, "n_test": len(pairs) - cut,
                    "same_as_paper": False, "baseline_is_papers_method": False},
        "metric_name": "held-out path coverage (fraction of held-out pairs whose shortest path contains a monitor), mean over k in {10,20}, budgets {0.5,2,8}s, 5 seeds",
        "higher_is_better": True,
        "baseline": "Random-restart first-improvement swap local search (random starts, restart after stagnation), untuned stand-in for a generic metaheuristic.",
        "improved": "Greedy max-coverage seed + sampled best-swap local search with perturbation restarts; neighbourhood sample size and restarts tuned on search pairs per (k, budget).",
        "metrics": met,
        "notes": "n_rows/n_train/n_test count sampled node pairs, not nodes. Each pair uses a single shortest path (networkx tie-breaking). Seeds 42-46 (5 seeds). Time-to-95% is measured on 8 s runs relative to the best search coverage seen for that k, censored at 8 s, and includes greedy seeding time. Wall-clock budgets make results machine-dependent. Tuning uses search-pair coverage with separate seeds (no CV). The baseline's patience is fixed and untuned. The paper's exact algorithm is unknown.",
    }
    with open("results.json", "w", encoding="utf-8") as f: json.dump(res, f, indent=2)
    print(json.dumps(met, indent=1))


if __name__ == "__main__":
    main()
