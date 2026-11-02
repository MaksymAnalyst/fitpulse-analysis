"""Four charts retained in the submitted report. Reads output/*.csv (run_sql.py, stats.py) and writes charts/*.png."""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).resolve().parents[1]
OUT, CHARTS = ROOT / "output", ROOT / "charts"

# Reference palette (dataviz skill): grey for context, one blue accent for the point of the chart.
SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, GREY, GREY_LIGHT = "#2a78d6", "#eb6834", "#b4b2a9", "#d9d7cf"
GOOD, CRITICAL = "#0ca30c", "#d03b3b"
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False,
    "axes.titlesize": 13, "axes.titleweight": "semibold", "axes.titlecolor": INK,
    "axes.titlelocation": "left", "axes.titlepad": 14,
    "text.parse_math": False,  # labels contain "$"
})


def read(name):
    return pd.read_csv(OUT / f"{name}.csv")


def finish(fig, name, source):
    # Source line goes just below everything already drawn (tick labels included).
    fig.canvas.draw()
    inv = fig.transFigure.inverted()
    bottom = min(inv.transform(ax.get_tightbbox().p0)[1] for ax in fig.axes)
    fig.text(0.01, bottom - 0.02, source, fontsize=8, color=MUTED, ha="left", va="top")
    fig.savefig(CHARTS / f"{name}.png", dpi=200, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print("wrote", name)


def retention_heatmap():
    t = read("02_cohort_retention__retention_table")
    weeks = [f"w{i}" for i in range(1, 13)]
    m = t[weeks].to_numpy(float)
    fig, ax = plt.subplots(figsize=(10, 5.6))
    cmap = LinearSegmentedColormap.from_list("blues", BLUES)
    ax.imshow(np.ma.masked_invalid(m), cmap=cmap, vmin=20, vmax=65, aspect="auto")
    for (i, j), v in np.ndenumerate(m):
        if not np.isnan(v):
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8.5,
                    color="#ffffff" if v >= 45 else INK)
    ax.set_xticks(range(12), [f"W{i}" for i in range(1, 13)])
    labels = [f"{pd.Timestamp(d):%b %d}  ({n})" for d, n in zip(t.cohort_week, t.cohort_users)]
    ax.set_yticks(range(len(t)), labels)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlabel("Weeks since signup  (W0 observed = 100% after cleaning; not shown)")
    ax.set_ylabel("Signup week  (users)")
    ax.set_title("Week-1 retention slipped from ~61% (June cohorts) to ~55% (August cohorts)")
    finish(fig, "1_cohort_retention",
           "Share of each weekly signup cohort with ≥1 session in week N. Blank = week not yet fully observed. "
           "Source: 02_cohort_retention.sql")


def onboarding_by_week():
    d = read("03_ceo_august_cohort__onboarding_by_week_platform")
    d["signup_week"] = pd.to_datetime(d.signup_week)
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for platform, color, z in [("ios", GREY, 2), ("android", BLUE, 3)]:
        s = d[d.platform == platform]
        ax.plot(s.signup_week, s.onboarding_pct, color=color, lw=2, marker="o", ms=5, zorder=z)
        last = s.iloc[-1]
        ax.text(last.signup_week + pd.Timedelta(days=2), last.onboarding_pct,
                f"{'iOS' if platform == 'ios' else 'Android'} {last.onboarding_pct:.0f}%",
                color=color if platform == "android" else INK2, va="center", fontsize=10, fontweight="semibold")
    brk = pd.Timestamp("2026-08-15")
    ax.axvline(brk, color=CRITICAL, lw=1, ls="--")
    ax.text(brk - pd.Timedelta(days=1), 88, "Aug 15: candidate break\nfrom daily data",
            ha="right", va="top", color=CRITICAL, fontsize=9)
    ax.set_ylim(0, 90)
    ax.set_yticks(range(0, 91, 20), [f"{v}%" for v in range(0, 91, 20)])
    ax.set_xlim(d.signup_week.min() - pd.Timedelta(days=3), d.signup_week.max() + pd.Timedelta(days=14))
    ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%b %d"))
    ax.set_ylabel("Onboarding completed within 24 h")
    ax.set_title("Android onboarding: 62% → 33% across mid-August; iOS: 62% → 66%")
    finish(fig, "2_onboarding_by_platform",
           "Weekly signup cohorts (Monday start). Source: 03_ceo_august_cohort.sql :: onboarding_by_week_platform")


def ab_forest():
    s = read("ab_stats").set_index("metric")
    rows = [
        ("trial start rate", "trial start"),
        ("trial → paid (trial starters)", "trial -> paid (among trial starters)"),
        ("paid conversion", "paid conversion (any plan)"),
        ("annual plan purchase", "annual plan purchase"),
        ("revenue per user, 30 days", "revenue per user, first 30 days"),
        ("monthly revenue / assigned user", "monthly-plan revenue per assigned user, first 30 days"),
        ("D1 retention (guardrail)", "D1 retention (guardrail)"),
        ("week-1 retention (guardrail)", "week-1 retention (guardrail)"),
    ]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    lim_lo, lim_hi = -100, 350
    for i, (label, key) in enumerate(rows):
        r = s.loc[key]
        lift, lo, hi = 100 * r.rel_lift, 100 * r.rel_ci_low, 100 * r.rel_ci_high
        sig = r.p_value < 0.05
        color = BLUE if sig else GREY
        y = len(rows) - 1 - i
        ax.plot([max(lo, lim_lo), min(hi, lim_hi)], [y, y], color=color, lw=2, solid_capstyle="round")
        if hi > lim_hi:
            ax.annotate("", xy=(lim_hi, y), xytext=(lim_hi - 12, y),
                        arrowprops=dict(arrowstyle="-|>", color=color, lw=1.5))
        ax.plot(lift, y, "o", ms=8, color=color, mec=SURFACE, mew=1.5, zorder=3)
        unit = "$" if r.unit == "usd" else ""
        a_txt = f"{unit}{r.a:.2f}" if r.unit == "usd" else f"{100 * r.a:.1f}%"
        b_txt = f"{unit}{r.b:.2f}" if r.unit == "usd" else f"{100 * r.b:.1f}%"
        ax.text(lim_hi + 8, y, f"{a_txt} → {b_txt}   p = {r.p_value:.2f}", va="center", fontsize=9,
                color=INK if sig else INK2, fontweight="semibold" if sig else "normal")
    ax.axvline(0, color=INK2, lw=1)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows][::-1])
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(lim_lo, lim_hi)
    ax.set_xticks(range(-100, 351, 50), [f"{v:+d}%" if v else "0" for v in range(-100, 351, 50)])
    ax.set_xlabel("Relative change B vs A; pointwise 95% CI for the ratio")
    ax.set_title("Paywall B: trial lift is nominally significant; revenue remains uncertain")
    finish(fig, "3_ab_test_effects",
           "Blue = nominal p < .05; no outcome passes Holm across six outcomes (trial adjusted p = .157).\n"
           "Ratio CIs: log/log-adjusted for rates; direct bootstrap for revenue. A=485, B=488. Source: stats.py")


def ab_revenue_by_plan():
    d = read("05_paywall_ab_test__ab_revenue_by_plan")
    d = d[d.plan != "none"].pivot(index="ab_group", columns="plan", values="revenue_30d").loc[["A", "B"]]
    users = read("05_paywall_ab_test__ab_revenue_by_plan").groupby("ab_group").users.sum()
    fig, ax = plt.subplots(figsize=(10, 2.8))
    for y, g in enumerate(["B", "A"]):
        m, a = d.loc[g, "monthly"], d.loc[g, "annual"]
        ax.barh(y, m, color=GREY, height=0.5)
        ax.barh(y, a, left=m, color=BLUE, height=0.5)
        ax.text(m / 2, y, f"monthly ${m:,.0f}", ha="center", va="center", color=INK, fontsize=9)
        ax.text(m + a / 2, y, f"annual ${a:,.0f}", ha="center", va="center", color="#ffffff", fontsize=9)
        ax.text(m + a + 14, y, f"${m + a:,.0f}  (${(m + a) / users[g]:.2f} per user)", va="center",
                color=INK, fontweight="semibold", fontsize=9.5)
    plans = read("ab_stats").set_index("metric").loc["annual plan purchase"]
    ax.set_yticks([0, 1], [f"B ({int(plans.x_b)} annual buyers)", f"A ({int(plans.x_a)} annual buyers)"])
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, 1300)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.set_title("B has six more annual buyers; monthly revenue is lower (descriptive)")
    finish(fig, "4_ab_revenue_by_plan",
           "Revenue in each user's first 30 days, by plan bought. Source: 05_paywall_ab_test.sql :: ab_revenue_by_plan")


def main():
    CHARTS.mkdir(exist_ok=True)
    retention_heatmap()
    onboarding_by_week()
    ab_forest()
    ab_revenue_by_plan()


if __name__ == "__main__":
    main()
