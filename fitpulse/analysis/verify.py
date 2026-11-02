"""Independent checks of supplied raw data, SQL outputs and revised statistics."""
from pathlib import Path
import hashlib,json,math
import numpy as np
import pandas as pd
from scipy import stats

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'
checks=[]
def check(name,condition):
    if not bool(condition):raise AssertionError(name)
    checks.append(name)

def main():
    hashes=json.loads((ROOT/'analysis/input_hashes.json').read_text())
    for name,expected in hashes.items():
        check('unchanged source '+name,hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==expected)
    users=pd.read_csv(ROOT/'data/users.csv',parse_dates=['signup_ts'])
    events=pd.read_csv(ROOT/'data/events.csv',parse_dates=['event_ts'])
    payments=pd.read_csv(ROOT/'data/payments.csv',parse_dates=['payment_ts'])
    check('648 exact duplicates',events.duplicated().sum()==648)
    check('40 missing event user ids',events.user_id.isna().sum()==40)
    users=users[users.channel.ne('internal')].set_index('user_id')
    events=events.drop_duplicates().merge(users[['signup_ts','platform']],left_on='user_id',right_index=True)
    repair=(events.platform.eq('android')&events.event_name.eq('session_start')&
            (events.event_ts==events.signup_ts-pd.Timedelta(days=1)+pd.Timedelta(seconds=30)))
    check('30 exact repairs',repair.sum()==30)
    events.loc[repair,'event_ts']+=pd.Timedelta(days=1)
    end=pd.Timestamp('2026-10-01')
    events=events[(events.event_ts>=events.signup_ts)&(events.event_ts<end)].copy()
    payments=payments.merge(users[['signup_ts']],left_on='user_id',right_index=True)
    payments=payments[(payments.payment_ts>=payments.signup_ts)&(payments.payment_ts<end)].copy()
    check('clean counts',(len(users),len(events),len(payments))==(3000,42292,442))
    events['age']=(events.event_ts-events.signup_ts)/pd.Timedelta(days=1)
    payments['age']=(payments.payment_ts-payments.signup_ts)/pd.Timedelta(days=1)
    flags={
        'onboarded_24h':events.event_name.eq('onboarding_complete')&(events.age<1),
        'started_trial':events.event_name.eq('trial_start')&(events.age<7),
        'saw_paywall':events.event_name.eq('paywall_view'),
        'active_d1':events.event_name.eq('session_start')&events.age.between(1,2,inclusive='left'),
        'active_w1':events.event_name.eq('session_start')&events.age.between(7,14,inclusive='left')}
    for col,mask in flags.items():users[col]=users.index.isin(events.loc[mask,'user_id'])
    first=payments[payments.payment_type.eq('purchase')&payments.amount_usd.gt(0)].groupby('user_id').age.min()
    users['is_payer']=users.index.isin(first[first<14].index)
    users['refunded']=users.index.isin(payments.loc[payments.payment_type.eq('refund'),'user_id'])
    users['mature_38d']=users.signup_ts+pd.Timedelta(days=38)<=end
    users['refunded_38d']=users.index.isin(payments.loc[payments.payment_type.eq('refund')&(payments.age<38),'user_id']).astype(float)
    users.loc[~users.mature_38d,'refunded_38d']=np.nan
    for days in [30,38]:
        users[f'revenue_{days}d']=payments[payments.age<days].groupby('user_id').amount_usd.sum().reindex(users.index,fill_value=0)
    users.loc[~users.mature_38d,'revenue_38d']=np.nan
    users['revenue_total']=payments.groupby('user_id').amount_usd.sum().reindex(users.index,fill_value=0)
    sql=pd.read_csv(OUT/'05_paywall_ab_test__all_user_facts.csv').set_index('user_id').sort_index()
    check('UTC signup timestamps exported unchanged',np.array_equal(pd.to_datetime(sql.signup_ts).to_numpy(),users.signup_ts.sort_index().to_numpy()))
    for col in [*flags,'is_payer','refunded','refunded_38d','mature_38d','revenue_30d','revenue_38d','revenue_total']:
        a=users[col].sort_index().astype(float);b=sql[col].astype(float)
        check('independent facts '+col,np.allclose(a,b,equal_nan=True))
    cohort=(users.signup_ts.dt.normalize()-pd.to_timedelta(users.signup_ts.dt.day_of_week,unit='D')).dt.strftime('%Y-%m-%d')
    sessions=events[events.event_name.eq('session_start')].copy()
    sessions['cohort']=sessions.user_id.map(cohort);sessions['week']=(sessions.age//7).astype(int)
    active=sessions.groupby(['cohort','week']).user_id.nunique()
    long=pd.read_csv(OUT/'02_cohort_retention__retention_long.csv')
    for r in long.itertuples():
        check(f'retention {r.cohort_week} W{r.week_n}',active.get((r.cohort_week,r.week_n),0)==r.active_users)
        complete=pd.Timestamp(r.cohort_week)+pd.Timedelta(days=7+7*(r.week_n+1))<=end
        check(f'censoring {r.cohort_week} W{r.week_n}',pd.notna(r.retention_pct)==complete)
        if complete:check(f'retention pct {r.cohort_week} W{r.week_n}',abs(r.retention_pct-100*r.active_users/r.cohort_users)<=.0500001)
    ab=users[users.ab_group.notna()]
    check('A/B sizes',ab.groupby('ab_group').size().to_dict()=={'A':485,'B':488})
    check('D38 mature sizes',ab[ab.mature_38d].groupby('ab_group').size().to_dict()=={'A':371,'B':379})
    renew=payments[payments.payment_type.eq('renewal')&payments.user_id.isin(ab.index)]
    check('28 renewals; zero before D37',len(renew)==28 and not (renew.age<37).any())
    check('27 renewals in mature D38',((renew.age<38)&renew.user_id.isin(ab[ab.mature_38d].index)).sum()==27)
    s=pd.read_csv(OUT/'ab_stats.csv').set_index('metric')
    r=s.loc['trial start'];pa=53/485;pb=77/488;pool=130/973
    p=2*stats.norm.sf(abs((pb-pa)/math.sqrt(pool*(1-pool)*(1/485+1/488))))
    check('trial nominal test',abs(r.p_value-p)<1e-12)
    se=math.sqrt(1/77-1/488+1/53-1/485)
    ci=np.exp(np.log(pb/pa)+np.array([-1,1])*stats.norm.ppf(.975)*se)-1
    check('direct risk ratio CI',np.allclose(ci,[r.rel_ci_low,r.rel_ci_high]))
    # Independent Wilson/Newcombe construction for the rate difference.
    def wilson(x,n):
        z=stats.norm.ppf(.975);p=x/n;den=1+z*z/n
        centre=(p+z*z/(2*n))/den;half=z/den*math.sqrt(p*(1-p)/n+z*z/(4*n*n))
        return centre-half,centre+half
    la,ua=wilson(53,485);lb,ub=wilson(77,488)
    expected=[pb-pa-math.sqrt((pb-lb)**2+(ua-pa)**2),pb-pa+math.sqrt((ub-pb)**2+(pa-la)**2)]
    check('Newcombe difference CI',np.allclose(expected,[r.ci_low,r.ci_high]))
    check('Holm trial p',abs(r.p_holm_six_outcomes-p*6)<1e-12)
    check('no exploratory family outcome survives Holm',(s.p_holm_six_outcomes.dropna()>.05).all())
    a=ab[ab.ab_group.eq('A')].revenue_30d.to_numpy();b=ab[ab.ab_group.eq('B')].revenue_30d.to_numpy()
    rng=np.random.default_rng(20261030)
    ma=a[rng.integers(0,len(a),(20000,len(a)))].mean(axis=1)
    mb=b[rng.integers(0,len(b),(20000,len(b)))].mean(axis=1)
    r=s.loc['revenue per user, first 30 days']
    # Sort order is identical to SQL user_id ordering after sorting the source IDs.
    check('ARPU Welch test',abs(r.p_value-stats.ttest_ind(b,a,equal_var=False).pvalue)<1e-12)
    check('ARPU bootstrap difference',np.allclose(np.percentile(mb-ma,[2.5,97.5]),[r.ci_low,r.ci_high]))
    check('ARPU bootstrap ratio',np.allclose(np.percentile(mb/ma-1,[2.5,97.5]),[r.rel_ci_low,r.rel_ci_high]))
    r=s.loc['monthly-plan revenue per assigned user, first 30 days']
    check('monthly component denominator',(r.n_a,r.n_b)==(485,488))
    check('monthly component means',np.allclose([r.a,r.b],[298.77/485,259.80/488]))
    d38=pd.read_csv(OUT/'ab_d38_stats.csv').iloc[0]
    aa=ab[ab.ab_group.eq('A')&ab.mature_38d].revenue_38d.to_numpy()
    bb=ab[ab.ab_group.eq('B')&ab.mature_38d].revenue_38d.to_numpy()
    check('D38 independent means',np.allclose([d38.a,d38.b,d38['diff']],[aa.mean(),bb.mean(),bb.mean()-aa.mean()]))
    check('D38 independent Welch test',abs(d38.p_value-stats.ttest_ind(bb,aa,equal_var=False).pvalue)<1e-12)
    check('no posterior probability labels',not s.astype(str).apply(lambda c:c.str.contains('P\\(B>A\\)',regex=True)).any().any())
    checks_file=OUT/'verification.json'
    checks_file.write_text(json.dumps({'status':'PASS','checks_passed':len(checks),'checks':checks},indent=2),encoding='utf-8')
    print(f'PASS: {len(checks)} independent checks')

if __name__=='__main__':main()
