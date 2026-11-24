"""Ecological regression models for vote transfer estimation.

Model A2: Constrained OLS (scipy L-BFGS-B with bounds 0-1)
Model A3: Bootstrap EI approximation (1000 bootstrap resamples of A2)

Input: mun_turnos.csv
Output: transferencia.json (also copied to the turnos repo's data/ folder when found:
        $TURNOS_DATA_DIR, or ../../data when this script lives in turnos/scripts/bu/)
"""
import csv, json, os, sys, time, shutil
import numpy as np
from scipy.optimize import minimize

# Force UTF-8 stdout on Windows to avoid cp1252 encoding errors
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "mun_turnos.csv")
OUT_PATH = os.path.join(SCRIPT_DIR, "transferencia.json")
COPY_PATH = os.path.join(
    os.environ.get("TURNOS_DATA_DIR") or os.path.join(SCRIPT_DIR, "..", "..", "data"),
    "transferencia.json")

N_BOOTSTRAP = 1000

ELIMINATED = ["55", "70", "14", "28", "30", "80", "27", "16", "21", "35", "29"]

CANDIDATE_NAMES = {
    "55": "Ronaldo Caiado", "70": "Augusto Cury", "14": "Renan Santos",
    "28": "Pablo Marçal", "30": "Zema", "80": "Samara",
    "27": "Clariana Barão", "16": "Hertz Dias", "21": "Edmilson Costa",
    "35": "Wilson Grassi", "29": "Rui Costa Pimenta"
}
PARTY_NAMES = {
    "55": "PSD", "70": "Avante", "14": "Missão", "28": "PRTB",
    "30": "Novo", "80": "UP", "27": "DC", "16": "PSTU",
    "21": "PCB", "35": "PMB", "29": "PCO"
}

REGIONS = {
    'Norte': ['AC','AM','AP','PA','RO','RR','TO'],
    'Nordeste': ['AL','BA','CE','MA','PB','PE','PI','RN','SE'],
    'Centro-Oeste': ['DF','GO','MS','MT'],
    'Sudeste': ['ES','MG','RJ','SP'],
    'Sul': ['PR','RS','SC']
}

# Reverse lookup: UF -> region name
UF_TO_REGION = {}
for region, ufs in REGIONS.items():
    for uf in ufs:
        UF_TO_REGION[uf] = region

# Feature labels for display
FEATURE_LABELS = {
    "v55_1t": "Caiado (55/PSD)", "v70_1t": "Cury (70/Avante)",
    "v14_1t": "Renan Santos (14/Missão)", "v28_1t": "Marçal (28/PRTB)",
    "v30_1t": "Zema (30/Novo)", "v80_1t": "Samara (80/UP)",
    "v27_1t": "Clariana (27/DC)", "v16_1t": "Hertz (16/PSTU)",
    "v21_1t": "Edmilson (21/PCB)", "v35_1t": "Grassi (35/PMB)",
    "v29_1t": "Rui Costa Pimenta (29/PCO)",
    "d_brancos": "Brancos (redução)", "d_nulos": "Nulos (redução)",
    "d_comp": "Novos eleitores (delta comp.)"
}


def load_data():
    """Load mun_turnos.csv and build feature matrix X, target vector y, and UF array."""
    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    n = len(rows)

    # Target: delta Lula = v13_2t - v13_1t
    y = np.array([int(r["v13_2t"]) - int(r["v13_1t"]) for r in rows], dtype=np.float64)

    # UF for each municipality
    ufs = np.array([r["uf"] for r in rows])

    # Feature columns: eliminated candidates + 3 other sources + 4 regional dummies
    feature_names = [f"v{c}_1t" for c in ELIMINATED] + ["d_brancos", "d_nulos", "d_comp"]
    n_transfer = len(feature_names)  # number of transfer features (constrained [0,1])
    region_dummies = ["reg_norte", "reg_nordeste", "reg_centro_oeste", "reg_sul"]
    feature_names += region_dummies
    n_features = len(feature_names)
    X = np.zeros((n, n_features), dtype=np.float64)

    for i, r in enumerate(rows):
        for j, c in enumerate(ELIMINATED):
            X[i, j] = float(r.get(f"v{c}_1t", 0))
        # Reduction in brancos (positive = votes freed up)
        X[i, len(ELIMINATED)]     = float(r["brancos_1t"]) - float(r["brancos_2t"])
        # Reduction in nulos
        X[i, len(ELIMINATED) + 1] = float(r["nulos_1t"]) - float(r["nulos_2t"])
        # New voters (increased turnout)
        X[i, len(ELIMINATED) + 2] = float(r["comp_2t"]) - float(r["comp_1t"])
        # Regional dummies (Sudeste = base)
        reg = UF_TO_REGION.get(r["uf"], "")
        if reg == "Norte":         X[i, n_transfer] = 1
        elif reg == "Nordeste":    X[i, n_transfer + 1] = 1
        elif reg == "Centro-Oeste":X[i, n_transfer + 2] = 1
        elif reg == "Sul":         X[i, n_transfer + 3] = 1

    return rows, X, y, feature_names, ufs, n_transfer


def model_a2(X, y, n_constrained=None):
    """Constrained OLS: minimize ||y - X*beta||^2.

    First n_constrained features bounded [0, 1] (transfer coefficients).
    Remaining features unconstrained (regional dummies).
    Uses scipy L-BFGS-B with analytical gradient.
    Returns (beta, r_squared, convergence_success).
    """
    n_features = X.shape[1]
    if n_constrained is None:
        n_constrained = n_features

    def objective(beta):
        residuals = y - X @ beta
        return np.sum(residuals ** 2)

    def gradient(beta):
        residuals = y - X @ beta
        return -2.0 * (X.T @ residuals)

    x0 = np.full(n_features, 0.5)
    x0[n_constrained:] = 0.0  # dummies start at 0
    bounds = [(0.0, 1.0)] * n_constrained + [(None, None)] * (n_features - n_constrained)

    result = minimize(
        objective, x0, jac=gradient, method='L-BFGS-B',
        bounds=bounds, options={'maxiter': 10000, 'ftol': 1e-15, 'gtol': 1e-10}
    )

    beta = result.x

    # R-squared
    y_pred = X @ beta
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1.0 - ss_res / ss_tot

    return beta, r_squared, result.success


def model_ei_bootstrap(X, y, n_constrained=None, n_bootstrap=N_BOOTSTRAP, seed=42):
    """Bootstrap EI approximation.

    Runs model_a2 on n_bootstrap resamples (80% of municipalities, with replacement).
    Returns (mean, std, ci_low, ci_high) arrays for each coefficient.
    """
    rng = np.random.RandomState(seed)
    n_mun = X.shape[0]
    n_features = X.shape[1]
    sample_size = int(n_mun * 0.8)
    betas = np.zeros((n_bootstrap, n_features))

    t0 = time.time()
    for b in range(n_bootstrap):
        idx = rng.choice(n_mun, sample_size, replace=True)
        X_s, y_s = X[idx], y[idx]
        beta_b, _, success = model_a2(X_s, y_s, n_constrained=n_constrained)
        betas[b] = beta_b

        if (b + 1) % 50 == 0 or b == 0:
            elapsed = time.time() - t0
            eta = elapsed / (b + 1) * (n_bootstrap - b - 1)
            print(f"    bootstrap {b+1}/{n_bootstrap} "
                  f"({elapsed:.0f}s elapsed, ~{eta:.0f}s remaining)")

    mean = np.mean(betas, axis=0)
    std = np.std(betas, axis=0)
    ci_low = np.percentile(betas, 2.5, axis=0)
    ci_high = np.percentile(betas, 97.5, axis=0)

    return mean, std, ci_low, ci_high


def main():
    t_start = time.time()

    print("=" * 70)
    print("Ecological Regression: Vote Transfer Estimation (1T -> 2T)")
    print("=" * 70)

    # --- Load data ---
    print("\nLoading data...")
    rows, X, y, feature_names, ufs, n_transfer = load_data()
    n_mun = len(rows)
    print(f"  Municipalities: {n_mun}")
    print(f"  Features: {X.shape[1]} ({len(ELIMINATED)} candidates + 3 other sources + 4 regional dummies)")

    # Sanity checks
    total_delta_lula = np.sum(y)
    total_delta_bolso = sum(int(r["v22_2t"]) - int(r["v22_1t"]) for r in rows)
    print(f"\n  Total delta Lula (2T - 1T):     {total_delta_lula:>+14,.0f}")
    print(f"  Total delta Bolsonaro (2T - 1T): {total_delta_bolso:>+14,.0f}")
    print(f"  Sum of all source features:      {np.sum(X):>14,.0f}")

    # Per-feature totals
    print(f"\n  Feature totals (national):")
    for j, name in enumerate(feature_names):
        label = FEATURE_LABELS.get(name, name)
        print(f"    {label:40s} {np.sum(X[:, j]):>12,.0f}")

    # --- Model A2: Constrained OLS ---
    print("\n" + "-" * 70)
    print("Model A2: Constrained OLS (L-BFGS-B, bounds [0, 1])")
    print("-" * 70)

    beta_a2, r2_a2, converged = model_a2(X, y, n_constrained=n_transfer)

    print(f"\n  Converged: {converged}")
    print(f"  R-squared: {r2_a2:.6f}")
    print()
    print(f"  {'Source':<40s} {'beta':>6s}  {'-> Lula':>8s}  {'-> Bolso':>9s}  {'Votes':>12s}  {'-> Lula':>12s}  {'-> Bolso':>12s}")
    print(f"  {'-'*40} {'-'*6}  {'-'*8}  {'-'*9}  {'-'*12}  {'-'*12}  {'-'*12}")

    for j in range(n_transfer):
        name = feature_names[j]
        label = FEATURE_LABELS.get(name, name)
        b = beta_a2[j]
        total_votes = np.sum(X[:, j])
        to_lula = b * total_votes
        to_bolso = (1.0 - b) * total_votes
        print(f"  {label:<40s} {b:>6.3f}  {b*100:>7.1f}%  {(1-b)*100:>8.1f}%  {total_votes:>12,.0f}  {to_lula:>12,.0f}  {to_bolso:>12,.0f}")
    # Show regional dummy coefficients
    print(f"\n  Regional controls (dummies, Sudeste=base):")
    for j in range(n_transfer, len(feature_names)):
        print(f"    {feature_names[j]}: {beta_a2[j]:>+.0f}")

    # Residual diagnostics
    y_pred = X @ beta_a2
    residuals = y - y_pred
    print(f"\n  Residuals: mean={np.mean(residuals):,.0f}, "
          f"std={np.std(residuals):,.0f}, "
          f"max={np.max(np.abs(residuals)):,.0f}")

    # --- Model A3: Bootstrap EI ---
    print("\n" + "-" * 70)
    print(f"Model A3: Bootstrap EI Approximation ({N_BOOTSTRAP} resamples, 80% each)")
    print("-" * 70)

    ei_mean, ei_std, ei_ci_low, ei_ci_high = model_ei_bootstrap(X, y, n_constrained=n_transfer, n_bootstrap=N_BOOTSTRAP)

    print(f"\n  {'Source':<40s} {'mean':>6s}  {'std':>6s}  {'CI low':>7s}  {'CI high':>8s}")
    print(f"  {'-'*40} {'-'*6}  {'-'*6}  {'-'*7}  {'-'*8}")
    for j, name in enumerate(feature_names):
        label = FEATURE_LABELS.get(name, name)
        print(f"  {label:<40s} {ei_mean[j]:>6.3f}  {ei_std[j]:>6.3f}  "
              f"{ei_ci_low[j]:>7.3f}  {ei_ci_high[j]:>8.3f}")

    # --- Regional A2 models ---
    print("\n" + "-" * 70)
    print("Regional Model A2: Constrained OLS per region")
    print("-" * 70)

    regional_results = {}
    output_keys = list(ELIMINATED) + ["brancos", "nulos", "novos_eleitores"]

    for region_name, region_ufs in REGIONS.items():
        mask = np.isin(ufs, region_ufs)
        X_reg = X[mask][:, :n_transfer]  # only transfer features, no dummies
        y_reg = y[mask]
        n_reg = int(np.sum(mask))

        if n_reg < 10:
            print(f"\n  {region_name}: only {n_reg} municipalities, skipping")
            continue

        beta_reg, r2_reg, conv_reg = model_a2(X_reg, y_reg, n_constrained=n_transfer)
        print(f"\n  {region_name}: {n_reg} municipalities, R²={r2_reg:.6f}, converged={conv_reg}")

        reg_coefficients = {}
        for j, key in enumerate(output_keys):
            votes_total = int(np.sum(X_reg[:, j]))
            b = float(beta_reg[j])
            votes_to_lula = int(round(b * votes_total))
            votes_to_bolso = votes_total - votes_to_lula
            reg_coefficients[key] = {
                "to_lula": round(b, 4),
                "to_bolso": round(1.0 - b, 4),
                "votes_total": votes_total,
                "votes_to_lula": votes_to_lula,
                "votes_to_bolso": votes_to_bolso,
            }
            if key in CANDIDATE_NAMES:
                reg_coefficients[key]["name"] = CANDIDATE_NAMES[key]
                reg_coefficients[key]["party"] = PARTY_NAMES[key]

        regional_results[region_name] = {
            "r_squared": round(float(r2_reg), 6),
            "n_municipalities": n_reg,
            "coefficients": reg_coefficients,
        }

    # --- Print regional comparison table ---
    print("\n" + "=" * 70)
    print("REGIONAL COMPARISON: % of votes -> Lula (A2 model)")
    print("=" * 70)

    # Header
    region_names = list(REGIONS.keys())
    hdr = f"  {'Source':<30s} {'Nacional':>8s}"
    for rn in region_names:
        hdr += f" {rn:>12s}"
    print(hdr)
    print(f"  {'-'*30} {'-'*8}" + (" " + "-" * 12) * len(region_names))

    for j, key in enumerate(output_keys):
        if key in CANDIDATE_NAMES:
            label = f"{CANDIDATE_NAMES[key]} ({key})"
        elif key == "brancos":
            label = "Brancos (redução)"
        elif key == "nulos":
            label = "Nulos (redução)"
        elif key == "novos_eleitores":
            label = "Novos eleitores"
        else:
            label = key

        b_nat = float(beta_a2[j])
        row = f"  {label:<30s} {b_nat*100:>7.1f}%"
        for rn in region_names:
            if rn in regional_results:
                b_reg = regional_results[rn]["coefficients"][key]["to_lula"]
                # Mark boundary values with * for emphasis
                marker = "*" if b_nat <= 0.001 or b_nat >= 0.999 else " "
                row += f" {b_reg*100:>10.1f}%{marker}"
            else:
                row += f" {'n/a':>12s}"
        print(row)

    # Summary row: n_municipalities
    row = f"  {'N municipalities':<30s} {n_mun:>8d}"
    for rn in region_names:
        if rn in regional_results:
            row += f" {regional_results[rn]['n_municipalities']:>12d}"
        else:
            row += f" {'n/a':>12s}"
    print(row)

    # Summary row: R²
    row = f"  {'R-squared':<30s} {r2_a2:>8.4f}"
    for rn in region_names:
        if rn in regional_results:
            row += f" {regional_results[rn]['r_squared']:>12.4f}"
        else:
            row += f" {'n/a':>12s}"
    print(row)

    # --- Build output JSON ---
    print("\n" + "-" * 70)
    print("Building output JSON...")
    print("-" * 70)

    result = {
        "model_a2": {},
        "model_ei": {},
        "by_region": regional_results,
        "meta": {
            "r_squared": round(float(r2_a2), 6),
            "n_municipalities": n_mun,
            "n_bootstrap": N_BOOTSTRAP,
            "description": "Ecological regression: fraction of each source's votes that went to Lula in 2T"
        }
    }

    # Build national model entries (output_keys defined above for regional analysis)
    for j, key in enumerate(output_keys):
        votes_total = int(np.sum(X[:, j]))
        b_a2 = float(beta_a2[j])
        votes_to_lula = int(round(b_a2 * votes_total))
        votes_to_bolso = votes_total - votes_to_lula

        entry_a2 = {
            "to_lula": round(b_a2, 4),
            "to_bolso": round(1.0 - b_a2, 4),
            "votes_total": votes_total,
            "votes_to_lula": votes_to_lula,
            "votes_to_bolso": votes_to_bolso,
        }
        if key in CANDIDATE_NAMES:
            entry_a2["name"] = CANDIDATE_NAMES[key]
            entry_a2["party"] = PARTY_NAMES[key]

        entry_ei = {
            "to_lula": round(float(ei_mean[j]), 4),
            "ci_low": round(float(ei_ci_low[j]), 4),
            "ci_high": round(float(ei_ci_high[j]), 4),
            "std": round(float(ei_std[j]), 4),
            "votes_total": votes_total,
        }
        if key in CANDIDATE_NAMES:
            entry_ei["name"] = CANDIDATE_NAMES[key]
            entry_ei["party"] = PARTY_NAMES[key]

        result["model_a2"][key] = entry_a2
        result["model_ei"][key] = entry_ei

    # Save
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {OUT_PATH} ({os.path.getsize(OUT_PATH):,} bytes)")

    # Copy to turnos/data/
    if os.path.isdir(os.path.dirname(COPY_PATH)):
        shutil.copy2(OUT_PATH, COPY_PATH)
        print(f"  Copied to: {COPY_PATH}")
    else:
        print(f"  WARNING: destination dir not found, skipped copy to {COPY_PATH}")

    elapsed = time.time() - t_start
    print(f"\nDone in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
