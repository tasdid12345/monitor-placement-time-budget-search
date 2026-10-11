# Greedy-seeded vs random-restart swap local search for monitor placement

Placing a few monitors so that they observe as many end-to-end shortest paths as possible is a core problem in communication-network measurement. "A Metaheuristic Approach for Solving Monitor Placement Problem" (2023) tackles it with a metaheuristic. Its exact algorithm is not available to us, so this experiment uses a generic stand-in baseline and tests a simple improvement under tight time budgets.

## Question
Under the same wall-clock budgets, can a greedy-coverage-seeded swap local search beat a standard random-restart swap local search at choosing k monitor nodes (k=10, 20) that cover the most node-pair shortest paths?

## Dataset
A public SNAP AS-level topology (as-caida20071105), downloaded over HTTP. It is restricted to its largest connected component and subsampled to about 1,000 nodes by BFS from the top hub. If the download fails, the script falls back to networkx's generated Internet-like AS graph. Node pairs are sampled, and one shortest path per pair is split 70/30 into search pairs and held-out evaluation pairs. This is not the paper's own dataset.

## Baseline vs improved
- **Baseline:** random-restart first-improvement swap local search. It is untuned and restarts after stagnation.
- **Improved:** greedy max-coverage seed, then a sampled best-swap local search with perturbation restarts. Its neighbourhood sample size and number of restarts are tuned on the search pairs only.

Both methods share the same coverage evaluator and the same time budgets (0.5, 2 and 8 s), and each is run with 5 seeds. The main metric is held-out path coverage. The secondary metrics are search-set coverage and the time to reach 95% of the best coverage.

## How to run
```
pip install -r requirements.txt
python analysis.py
```

## Results
Results are written to `results.json` (and a chart to `figures/`).

## Results (latest run)

On the SNAP as-caida20071105 AS-graph subsample, a standard random-restart swap local search reached 99.93% held-out path coverage (mean over k in {10,20}, budgets 0.5-8 s, 5 seeds), while my greedy-seeded swap search reached 99.94%, a negligible gain near the ceiling.

| Metric | Value |
|---|---|
| baseline_score | 0.9993 |
| baseline_score_std | 0.0001361 |
| baseline_search_coverage | 1 |
| baseline_time_to_95pct_s | 0.00483 |
| baseline_heldout_k10_b0.5 | 0.9994 |
| baseline_heldout_k10_b2.0 | 0.9994 |
| baseline_heldout_k10_b8.0 | 0.9994 |
| baseline_heldout_k20_b0.5 | 0.9991 |
| baseline_heldout_k20_b2.0 | 0.9991 |
| baseline_heldout_k20_b8.0 | 0.9991 |
| improved_score | 0.9994 |
| improved_score_std | 1.11e-16 |
| improved_search_coverage | 1 |
| improved_time_to_95pct_s | 0.004032 |
| improved_heldout_k10_b0.5 | 0.9994 |
| improved_heldout_k10_b2.0 | 0.9994 |
| improved_heldout_k10_b8.0 | 0.9994 |
| improved_heldout_k20_b0.5 | 0.9994 |
| improved_heldout_k20_b2.0 | 0.9994 |
| improved_heldout_k20_b8.0 | 0.9994 |
| improvement | 0.0001667 |

Run on 2026-10-11. Full output: [results.json](results.json) · [run.log](run.log)

Notes: n_rows/n_train/n_test count sampled node pairs, not nodes. Each pair uses a single shortest path (networkx tie-breaking). Seeds 42-46 (5 seeds). Time-to-95% is measured on 8 s runs relative to the best search coverage seen for that k, censored at 8 s, and includes greedy seeding time. Wall-clock budgets make results machine-dependent. Tuning uses search-pair coverage with separate seeds (no CV). The baseline's patience is fixed and untuned. The paper's exact algorithm is unknown.

## Reference

This project is motivated by the following paper:

> A Duarte, J Sánchez-Oro (2023). *A Metaheuristic Approach for Solving Monitor Placement Problem*. … , ICVNS 2022, Abu Dhabi, United Arab. https://books.google.com/books?hl=en&lr=&id=LlvBEAAAQBAJ&oi=fnd&pg=PA1&dq=abraham.duarte%40urjc.es&ots=qLcjFiYnnu&sig=t_3Q5VrL2rlW17rZs1mm5RGWYws

Paper author: Prof. Dr. Abraham Duarte Muñoz, Universidad Rey Juan Carlos (abraham.duarte@urjc.es)


---
_The code in this repository was drafted with AI assistance and runs automatically on GitHub Actions; results come from the latest run._
