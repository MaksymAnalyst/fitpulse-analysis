"""Statistics for the retained paywall A/B and channel analyses.

Reads the CSVs written by run_sql.py and writes:
  output/ab_stats.csv          per-metric rates, lift, 95% CI, p-value
  output/ab_checks.csv         SRM, covariate balance, regression-adjusted effects
  output/ab_d38_stats.csv      exploratory revenue in the mature D38 subset
  output/channel_quality_check.csv  iOS paid-social July/August comparison
"""
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.proportion import confint_proportions_2indep
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
RNG = np.random.default_rng(20261030)
N_BOOT = 20_000


def two_proportions(x_a, n_a, x_b, n_b):
    """Rates, Newcombe difference CI and directly estimated risk-ratio CI.
    Fisher's exact test replaces the z-test when any cell count is below 10."""
    p_a, p_b = x_a / n_a, x_b / n_b
    diff = p_b - p_a
    lo, hi = confint_proportions_2indep(x_b, n_b, x_a, n_a, method="newcomb", compare="diff")
    ratio_method = "log-adjusted" if min(x_a, x_b) < 10 else "log"
    rr_lo, rr_hi = confint_proportions_2indep(x_b, n_b, x_a, n_a,
                                             method=ratio_method, compare="ratio")
    if min(x_a, x_b, n_a - x_a, n_b - x_b) < 10:
        p_value = stats.fisher_exact([[x_b, n_b - x_b], [x_a, n_a - x_a]])[1]
        test = "Fisher exact"
    else:
        pooled = (x_a + x_b) / (n_a + n_b)
        z = diff / np.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
        p_value = 2 * stats.norm.sf(abs(z))
        test = "two-proportion z"
    return dict(a=p_a, b=p_b, diff=diff, ci_low=lo, ci_high=hi,
                rel_lift=diff / p_a if p_a else np.nan, rel_ci_low=rr_lo-1, rel_ci_high=rr_hi-1,
                p_value=p_value, test=test, ci_method="Newcombe difference; " + ratio_method + " risk ratio")


def bootstrap_mean_diff(a, b):
    """Pointwise percentile CIs for difference and ratio, each resampled directly.

    Positive bootstrap fractions are deliberately not presented as posterior probabilities.
    Sparse, zero-inflated revenue still makes these intervals exploratory.
    """
    ia = RNG.integers(0, len(a), (N_BOOT, len(a)))
    ib = RNG.integers(0, len(b), (N_BOOT, len(b)))
    ma, mb = a[ia].mean(axis=1), b[ib].mean(axis=1)
    diffs = mb - ma
    ratio_ci = np.percentile(mb/ma-1, [2.5, 97.5]) if np.all(ma > 0) else (np.nan, np.nan)
    return np.percentile(diffs, [2.5, 97.5]), ratio_ci


def ab_metrics(users):
    a, b = users[users.ab_group == "A"], users[users.ab_group == "B"]
    rows = []

    binary = [
        ("onboarding (sanity: happens before the paywall)", "onboarded_24h", None),
        ("paywall view", "saw_paywall", None),
        ("trial start", "started_trial", None),
        ("trial -> paid (among trial starters)", "is_payer", "started_trial"),
        ("paid conversion (any plan)", "is_payer", None),
        ("annual plan purchase", "is_annual", None),
        ("monthly plan purchase", "is_monthly", None),
        ("D1 retention (guardrail)", "active_d1", None),
        ("week-1 retention (guardrail)", "active_w1", None),
    ]
    for label, col, among in binary:
        sa, sb = (a, b) if among is None else (a[a[among]], b[b[among]])
        r = two_proportions(sa[col].sum(), len(sa), sb[col].sum(), len(sb))
        rows.append(dict(metric=label, unit="rate", n_a=len(sa), n_b=len(sb),
                         x_a=int(sa[col].sum()), x_b=int(sb[col].sum()), **r))

    for label, col in [("revenue per user, first 30 days", "revenue_30d"),
                       ("revenue per user, to date", "revenue_total")]:
        va, vb = a[col].to_numpy(float), b[col].to_numpy(float)
        (lo, hi), (rlo, rhi) = bootstrap_mean_diff(va, vb)
        welch = stats.ttest_ind(vb, va, equal_var=False)
        rows.append(dict(metric=label, unit="usd", n_a=len(va), n_b=len(vb),
                         x_a=round(va.sum(), 2), x_b=round(vb.sum(), 2),
                         a=va.mean(), b=vb.mean(), diff=vb.mean() - va.mean(),
                         ci_low=lo, ci_high=hi, rel_lift=vb.mean() / va.mean() - 1,
                         rel_ci_low=rlo, rel_ci_high=rhi, p_value=welch.pvalue,
                         test="Welch t", ci_method="percentile bootstrap difference and ratio; 20000 resamples"))

    # Decompose revenue WITHOUT dropping post-treatment annual buyers from the denominator.
    va = a.revenue_30d.where(a.is_monthly, 0).to_numpy(float)
    vb = b.revenue_30d.where(b.is_monthly, 0).to_numpy(float)
    (lo, hi), (rlo, rhi) = bootstrap_mean_diff(va, vb)
    rows.append(dict(metric="monthly-plan revenue per assigned user, first 30 days", unit="usd",
                     n_a=len(va), n_b=len(vb), x_a=round(va.sum(), 2), x_b=round(vb.sum(), 2),
                     a=va.mean(), b=vb.mean(), diff=vb.mean() - va.mean(), ci_low=lo, ci_high=hi,
                     rel_lift=vb.mean() / va.mean() - 1,
                     p_value=stats.ttest_ind(vb, va, equal_var=False).pvalue,
                     rel_ci_low=rlo, rel_ci_high=rhi, test="Welch t",
                     ci_method="percentile bootstrap; descriptive component, all assigned users"))
    result = pd.DataFrame(rows)
    # Explicit exploratory outcome family. Sanity checks and conditional diagnostics are separate.
    family=["trial start", "paid conversion (any plan)", "annual plan purchase",
            "D1 retention (guardrail)", "week-1 retention (guardrail)", "revenue per user, first 30 days"]
    mask=result.metric.isin(family)
    result["p_holm_six_outcomes"]=np.nan
    result.loc[mask,"p_holm_six_outcomes"]=multipletests(result.loc[mask,"p_value"],method="holm")[1]
    result["in_exploratory_family"]=mask
    return result


def ab_checks(users, balance, srm):
    rows = []
    n = srm.set_index("ab_group")["users"]
    chi = stats.chisquare([n["A"], n["B"]])
    rows.append(dict(check="SRM: 50/50 split", stat=chi.statistic, p_value=chi.pvalue,
                     note=f"A={n['A']}, B={n['B']}"))
    for dim, g in balance.groupby("dimension"):
        c = stats.chi2_contingency(g[["users_a", "users_b"]].to_numpy())
        rows.append(dict(check=f"balance: {dim}", stat=c.statistic, p_value=c.pvalue,
                         note="; ".join(f"{v} {x}/{y}" for v, x, y in g[["value", "users_a", "users_b"]].to_numpy())))

    # Effects adjusted for platform, channel and country (B has more Android, fewer search users).
    # Annual purchases (12 events) are too rare for this model; they are tested with Fisher above.
    d = users.assign(is_b=(users.ab_group == "B").astype(int))
    for outcome in ["started_trial", "is_payer", "active_d1"]:
        m = smf.logit(f"{outcome} ~ is_b + C(platform) + C(channel) + C(country)",
                      data=d.assign(**{outcome: d[outcome].astype(int)})).fit(disp=0)
        lo, hi = np.exp(m.conf_int().loc["is_b"])
        rows.append(dict(check=f"adjusted odds ratio B vs A: {outcome}", stat=np.exp(m.params["is_b"]),
                         p_value=m.pvalues["is_b"], note=f"95% CI {lo:.2f}-{hi:.2f}; logit with platform, channel, country"))
    ols = smf.ols("revenue_30d ~ is_b + C(platform) + C(channel) + C(country)", data=d).fit(cov_type="HC1")
    lo, hi = ols.conf_int().loc["is_b"]
    rows.append(dict(check="adjusted revenue_30d difference B - A (USD)", stat=ols.params["is_b"],
                     p_value=ols.pvalues["is_b"], note=f"95% CI {lo:.2f} to {hi:.2f}; OLS, robust SE"))

    return pd.DataFrame(rows)


def d38_analysis(users):
    mature=users[users.mature_38d].copy()
    a=mature[mature.ab_group=="A"].revenue_38d.to_numpy(float)
    b=mature[mature.ab_group=="B"].revenue_38d.to_numpy(float)
    (lo,hi),(rlo,rhi)=bootstrap_mean_diff(a,b)
    summary=pd.DataFrame([dict(metric="cash revenue D38 per assigned user, mature subset",
        n_a=len(a),n_b=len(b),a=a.mean(),b=b.mean(),diff=b.mean()-a.mean(),ci_low=lo,ci_high=hi,
        rel_ci_low=rlo,rel_ci_high=rhi,p_value=stats.ttest_ind(b,a,equal_var=False).pvalue,
        interpretation="exploratory post-hoc metric; cash net of refunds, before store fees")])
    return summary


def main():
    ab = pd.read_csv(OUT / "05_paywall_ab_test__ab_users.csv")
    for c in ["onboarded_24h", "saw_paywall", "started_trial", "is_payer", "refunded", "active_d1", "active_w1", "mature_38d", "refunded_38d"]:
        ab[c] = ab[c].astype(str).str.lower().eq("true")
    ab["is_annual"] = ab.plan.eq("annual")
    ab["is_monthly"] = ab.plan.eq("monthly")

    metrics = ab_metrics(ab)
    metrics.to_csv(OUT / "ab_stats.csv", index=False)
    checks = ab_checks(ab, pd.read_csv(OUT / "05_paywall_ab_test__balance.csv"),
                       pd.read_csv(OUT / "05_paywall_ab_test__srm.csv"))
    checks.to_csv(OUT / "ab_checks.csv", index=False)

    d38=d38_analysis(ab)
    d38.to_csv(OUT / "ab_d38_stats.csv", index=False)
    ios=pd.read_csv(OUT / "04_marketing_channels__channel_month_ios.csv")
    ios["month"]=pd.to_datetime(ios.month).dt.strftime("%Y-%m-%d")
    ios=ios[ios.channel.eq("paid_social")].set_index("month")
    jul,aug=ios.loc["2026-07-01"],ios.loc["2026-08-01"]
    quality=two_proportions(jul.payers,jul.installs,aug.payers,aug.installs)
    pd.DataFrame([dict(comparison="iOS paid social July vs August",**quality)]).to_csv(OUT/"channel_quality_check.csv",index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 120)
    print(metrics.round(4).to_string(index=False))
    print()
    print(checks.round(4).to_string(index=False))
    print()
    print(d38.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
