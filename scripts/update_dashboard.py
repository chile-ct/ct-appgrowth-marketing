"""
App Growth Dashboard — Auto Update Script
Queries BigQuery directly. No Claude/Anthropic API. $0 token cost.
Cost data is managed manually via the Budget tab in the dashboard (localStorage).
"""
import json, os, datetime
from google.cloud import bigquery

PROJECT = "chotot-dwh"
DATA_JSON = os.path.join(os.path.dirname(__file__), '..', 'data.json')

client = bigquery.Client(project=PROJECT)

def run(sql):
    return [dict(r) for r in client.query(sql).result()]

def to_date(val):
    if isinstance(val, datetime.date): return val
    return datetime.datetime.strptime(str(val)[:10], '%Y-%m-%d').date()

def month_label(d, today):
    label = d.strftime("%b %Y")
    return label + "*" if d >= datetime.date(today.year, today.month, 1) else label

def get_arr(rows, key, months, channel=None):
    lookup = {}
    for r in rows:
        m = to_date(r['month'])
        ch = str(r.get('channel', r.get('channelGrouping', '')))
        if channel is None or ch == channel:
            lookup[m] = r.get(key)
    return [lookup.get(m) for m in months]

def safe_div(a, b):
    return round(a/b, 4) if a and b else None

def daily(arr, days):
    return [round(arr[i]/days[i]) if arr[i] else None for i in range(len(arr))]

print("Loading current data.json...")
with open(DATA_JSON) as f:
    D = json.load(f)

print("Querying BigQuery...")
today = datetime.date.today()

# MAU
mau_rows = run("""
SELECT month,
  SUM(mau) as mau_app,
  SUM(CASE WHEN login_status='login' THEN mau END) as mau_login
FROM ct_product.dashboard__user_management_login_monthly
WHERE platform IN ('Android','iOS') AND month >= '2026-01-01'
GROUP BY 1 ORDER BY 1
""")

# DAU
dau_rows = run("""
SELECT DATE_TRUNC(date,MONTH) as month, AVG(daily_dau) as avg_dau
FROM (SELECT date, SUM(dau) as daily_dau
FROM ct_product.dashboard__user_management_DAU
WHERE platform IN ('Android','iOS') AND date >= '2026-01-01' GROUP BY date)
GROUP BY 1 ORDER BY 1
""")

# Total CT MAU
ct_rows = run("""
SELECT month, SUM(mau) as total_ct_mau
FROM ct_product.dashboard__user_management_login_monthly
WHERE month >= '2026-01-01' GROUP BY 1 ORDER BY 1
""")

# New users
new_rows = run("""
SELECT DATE_TRUNC(date,MONTH) as month, channelGrouping,
  COUNT(DISTINCT clientId) as new_mau,
  COUNT(DISTINCT CASE WHEN account_id IS NOT NULL THEN clientId END) as new_login_mau
FROM chotot_data.traffic_visit_detail
WHERE newVisits=1 AND platform IN ('iOS','Android') AND date >= '2026-01-01'
GROUP BY 1,2 ORDER BY 1,2
""")
print(f"  MAU: {len(mau_rows)} months | New users: {len(new_rows)} rows")

# Activation (may fail with 403)
act_rows = []
try:
    act_rows = run("""
    SELECT DATE_TRUNC(visit_date,MONTH) as month,
      CASE WHEN channel='all' THEN 'Total' ELSE channel END as channel,
      AVG(dau) as avg_new_dau,
      SUM(user_20adview_7d) as adview_total, SUM(user_1lead_7d) as lead_total,
      SUM(save_ad) as save_total,
      SAFE_DIVIDE(SUM(d1),SUM(d0)) as nurr_d1,
      SAFE_DIVIDE(SUM(d7),SUM(d0)) as nurr_d7,
      SAFE_DIVIDE(SUM(m1),SUM(d0)) as nurr_m1
    FROM ct_digital.dashboard__retention_mapping_activation_by_source_campaign
    WHERE return_status='new' AND campaign='all'
    AND vertical_user = 'all'
    AND channel IN ('all','Direct','Organic Search','Paid Search','Display','Growth','Social')
    AND visit_date >= '2026-01-01'
    GROUP BY 1,2 ORDER BY 1,2
    """)
    print(f"  Activation: {len(act_rows)} rows OK")
except Exception as e:
    print(f"  WARNING Activation skipped: {e}")

# Daily activation — last 90 days by day and channel (for date-range chart)
daily_act_rows = []
try:
    daily_act_rows = run("""
    SELECT visit_date,
      CASE WHEN channel='all' THEN 'Total'
           WHEN channel IN ('Paid Search','Display','Growth') THEN 'Growth'
           ELSE channel END as channel,
      SUM(d0) as new_users,
      SUM(user_20adview_7d) as adview_activated,
      SUM(user_1lead_7d) as lead_activated,
      SUM(save_ad) as save_activated
    FROM ct_digital.dashboard__retention_mapping_activation_by_source_campaign
    WHERE return_status='new' AND campaign='all'
      AND vertical_user='all'
      AND channel IN ('all','Direct','Organic Search','Paid Search','Display','Growth')
      AND visit_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    GROUP BY 1,2 ORDER BY 1,2
    """)
    print(f"  Daily activation: {len(daily_act_rows)} rows OK")
except Exception as e:
    print(f"  WARNING Daily activation skipped: {e}")

# Retention (may fail with 403)
ret_total_rows = []
ret_app_rows = []
ret_web_rows = []
try:
    ret_total_rows = run("""
    SELECT DATE_TRUNC(min_date,MONTH) as month,
      SAFE_DIVIDE(SUM(d1),SUM(d0)) as ret_d1,
      SAFE_DIVIDE(SUM(d7),SUM(d0)) as ret_d7,
      SAFE_DIVIDE(SUM(m1),SUM(d0)) as ret_m1
    FROM ct_digital.dashboard__retention_90d
    WHERE new_status='return' AND min_date >= '2026-01-01'
    GROUP BY 1 ORDER BY 1
    """)
    ret_app_rows = run("""
    SELECT DATE_TRUNC(min_date,MONTH) as month,
      SAFE_DIVIDE(SUM(d1),SUM(d0)) as ret_d1,
      SAFE_DIVIDE(SUM(d7),SUM(d0)) as ret_d7,
      SAFE_DIVIDE(SUM(m1),SUM(d0)) as ret_m1
    FROM ct_digital.dashboard__retention_90d
    WHERE new_status='return' AND min_date >= '2026-01-01'
      AND platform IN ('Android','iOS')
    GROUP BY 1 ORDER BY 1
    """)
    ret_web_rows = run("""
    SELECT DATE_TRUNC(min_date,MONTH) as month,
      SAFE_DIVIDE(SUM(d1),SUM(d0)) as ret_d1,
      SAFE_DIVIDE(SUM(d7),SUM(d0)) as ret_d7,
      SAFE_DIVIDE(SUM(m1),SUM(d0)) as ret_m1
    FROM ct_digital.dashboard__retention_90d
    WHERE new_status='return' AND min_date >= '2026-01-01'
      AND platform NOT IN ('Android','iOS')
    GROUP BY 1 ORDER BY 1
    """)
    print(f"  Retention: total={len(ret_total_rows)}, app={len(ret_app_rows)}, web={len(ret_web_rows)} rows OK")
except Exception as e:
    print(f"  WARNING Retention skipped: {e}")
    ret_web_rows = []

# Build month list
all_months = sorted(set(to_date(r['month']) for r in mau_rows))
months_labels = [month_label(m, today) for m in all_months]
partial = [m for m in months_labels if m.endswith("*")]
n = len(all_months)

# Days per month
def days_in(d):
    if d.month == 12: return 31
    return (datetime.date(d.year, d.month+1, 1) - datetime.timedelta(days=1)).day
days = [days_in(m) for m in all_months]

# Overview
mau_app   = get_arr(mau_rows, 'mau_app', all_months)
mau_login = get_arr(mau_rows, 'mau_login', all_months)
ct_mau    = get_arr(ct_rows, 'total_ct_mau', all_months)
avg_dau   = [round(v) if v else None for v in get_arr(dau_rows, 'avg_dau', all_months)]

# New users aggregated
ch_map = {}
for r in new_rows:
    m = to_date(r['month'])
    ch = r.get('channelGrouping','')
    ch_map[(m,ch)] = r

def by_ch(ch, key='new_mau'):
    return [ch_map.get((m,ch),{}).get(key, 0) or 0 for m in all_months]

direct_n  = by_ch('Direct'); organic_n = by_ch('Organic Search')
paid_n    = by_ch('Paid Search'); display_n= by_ch('Display')
growth_crm= by_ch('Growth'); other_n   = by_ch('(Other)')
growth_n  = [paid_n[i]+display_n[i]+growth_crm[i] for i in range(n)]
total_n   = [direct_n[i]+organic_n[i]+growth_n[i]+other_n[i] for i in range(n)]
new_login_total = [
    by_ch('Direct','new_login_mau')[i] + by_ch('Organic Search','new_login_mau')[i] +
    by_ch('Paid Search','new_login_mau')[i] + by_ch('Display','new_login_mau')[i] +
    by_ch('Growth','new_login_mau')[i] + by_ch('(Other)','new_login_mau')[i]
    for i in range(n)]

# Activation / NURR
if act_rows:
    def a(ch, key): return get_arr(act_rows, key, all_months, channel=ch)
    adview_total = a('Total','adview_total'); lead_total = a('Total','lead_total')
    save_total = a('Total','save_total')
    nurr_d1=a('Total','nurr_d1'); nurr_d7=a('Total','nurr_d7'); nurr_m1=a('Total','nurr_m1')
    dir_adv=a('Direct','adview_total'); org_adv=a('Organic Search','adview_total')
    paid_adv=a('Paid Search','adview_total'); disp_adv=a('Display','adview_total')
    crm_adv=a('Growth','adview_total')
    growth_adv=[( paid_adv[i] or 0)+(disp_adv[i] or 0)+(crm_adv[i] or 0) for i in range(n)]
    dir_lead=a('Direct','lead_total'); org_lead=a('Organic Search','lead_total')
    paid_lead=a('Paid Search','lead_total'); disp_lead=a('Display','lead_total')
    crm_lead=a('Growth','lead_total')
    growth_lead=[(paid_lead[i] or 0)+(disp_lead[i] or 0)+(crm_lead[i] or 0) for i in range(n)]
    dir_save=a('Direct','save_total'); org_save=a('Organic Search','save_total')
    paid_save=a('Paid Search','save_total'); disp_save=a('Display','save_total')
    crm_save=a('Growth','save_total')
    growth_save=[(paid_save[i] or 0)+(disp_save[i] or 0)+(crm_save[i] or 0) for i in range(n)]
    dir_d1=a('Direct','nurr_d1'); dir_d7=a('Direct','nurr_d7'); dir_m1=a('Direct','nurr_m1')
    org_d1=a('Organic Search','nurr_d1'); org_d7=a('Organic Search','nurr_d7'); org_m1=a('Organic Search','nurr_m1')
    paid_d1=a('Paid Search','nurr_d1'); paid_d7=a('Paid Search','nurr_d7'); paid_m1=a('Total','nurr_m1')
else:
    print("  Using existing activation data")
    ex=D['activation']; er=D['retention']; eg=D['growth_channel']
    adview_total=ex['adview_total']; lead_total=ex['lead_total']
    save_total=ex.get('save_total',[None]*n)
    nurr_d1=er['nurr_d1']; nurr_d7=er['nurr_d7']; nurr_m1=er['nurr_m1']
    dir_adv=ex['direct_adview']; org_adv=ex['organic_adview']; growth_adv=ex['growth_adview']
    dir_lead=ex['direct_lead']; org_lead=ex['organic_lead']; growth_lead=ex['growth_lead']
    dir_save=ex.get('direct_save',[None]*n); org_save=ex.get('organic_save',[None]*n)
    growth_save=ex.get('growth_save',[None]*n)
    dir_d1=er['direct_d1']; dir_d7=er['direct_d7']; dir_m1=er['direct_m1']
    org_d1=er['organic_d1']; org_d7=er['organic_d7']; org_m1=er['organic_m1']
    paid_d1=eg['nurr_d1']; paid_d7=eg['nurr_d7']; paid_m1=eg['nurr_m1']

if ret_total_rows:
    tot_d1_bq=get_arr(ret_total_rows,'ret_d1',all_months); tot_d7_bq=get_arr(ret_total_rows,'ret_d7',all_months)
    tot_m1_bq=get_arr(ret_total_rows,'ret_m1',all_months)
    app_d1=get_arr(ret_app_rows,'ret_d1',all_months) if ret_app_rows else tot_d1_bq
    app_d7=get_arr(ret_app_rows,'ret_d7',all_months) if ret_app_rows else tot_d7_bq
    app_m1=get_arr(ret_app_rows,'ret_m1',all_months) if ret_app_rows else tot_m1_bq
    web_d1=get_arr(ret_web_rows,'ret_d1',all_months) if ret_web_rows else [None]*n
    web_d7=get_arr(ret_web_rows,'ret_d7',all_months) if ret_web_rows else [None]*n
    web_m1=get_arr(ret_web_rows,'ret_m1',all_months) if ret_web_rows else [None]*n
else:
    er=D['retention']
    tot_d1_bq=er.get('total_d1',[None]*n); tot_d7_bq=er.get('total_d7',[None]*n); tot_m1_bq=er.get('total_m1',[None]*n)
    app_d1=er.get('app_d1',tot_d1_bq); app_d7=er.get('app_d7',tot_d7_bq); app_m1=er.get('app_m1',tot_m1_bq)
    web_d1=er.get('web_d1',[None]*n); web_d7=er.get('web_d7',[None]*n); web_m1=er.get('web_m1',[None]*n)

def pad(arr, length, val=None):
    return list(arr) + [val]*(length-len(arr))

tot_d1 = pad(tot_d1_bq, n)
tot_d7 = pad(tot_d7_bq, n)
tot_m1 = pad(tot_m1_bq, n)

# Null out D7/M1 for partial months — these metrics need full month data to be meaningful
# D7 = need users from last 7 days of month to have completed their D7 window (null current month)
# M1 = need users from ~30 days ago (null current month + previous month)
def null_partial(arr, partial_indices, extra_indices=None):
    """Set values to None for partial/incomplete month indices."""
    result = list(arr)
    for i in (partial_indices + (extra_indices or [])):
        if i < len(result):
            result[i] = None
    return result

current_month_i = n - 1  # last index = current (partial) month
prev_month_i = n - 2     # second-to-last = previous month

# D7: show partial month data (current month D7 is valid for users installed ≥7 days ago)
# M1: null current + previous month (need full month cohort to complete 30-day window).
app_m1  = null_partial(app_m1,  [current_month_i, prev_month_i])
web_m1  = null_partial(web_m1,  [current_month_i, prev_month_i])
tot_m1  = null_partial(tot_m1,  [current_month_i, prev_month_i])
nurr_d7 = nurr_d7 if act_rows else D['retention']['nurr_d7']
nurr_m1_raw = nurr_m1 if act_rows else D['retention']['nurr_m1']
nurr_m1 = null_partial(nurr_m1_raw, [current_month_i, prev_month_i])
dir_m1  = null_partial(dir_m1,  [current_month_i, prev_month_i])
org_m1  = null_partial(org_m1,  [current_month_i, prev_month_i])
paid_m1 = null_partial(paid_m1, [current_month_i, prev_month_i])

# Campaign-level data — latest full month only
campaigns = []
try:
    # Fetch top 30 campaigns per month for ALL full months (Jan → last full month)
    last_full = all_months[prev_month_i]
    last_full_end = (last_full.replace(day=28) + datetime.timedelta(days=4)).replace(day=1).strftime('%Y-%m-%d')
    camp_rows = run(f"""
    SELECT * EXCEPT(rn) FROM (
      SELECT *,
        ROW_NUMBER() OVER (PARTITION BY month ORDER BY new_users DESC) as rn
      FROM (
        SELECT
          DATE_TRUNC(visit_date, MONTH) as month,
          campaign,
          LOWER(campaign) as campaign_lc,
          SUM(d0) as new_users,
          SUM(user_20adview_7d) as activated_adview,
          SUM(user_1lead_7d) as activated_lead,
          SAFE_DIVIDE(SUM(user_20adview_7d), SUM(d0)) as activation_rate,
          SAFE_DIVIDE(SUM(d1), SUM(d0)) as nurr_d1,
          SAFE_DIVIDE(SUM(d7), SUM(d0)) as nurr_d7
        FROM ct_digital.dashboard__retention_mapping_activation_by_source_campaign
        WHERE return_status = 'new'
          AND campaign NOT IN ('all', '(none)')
          AND channel NOT IN ('all', 'Direct', 'Organic Search', 'web_to_app')
          AND vertical_user = 'all'
          AND LOWER(campaign) NOT LIKE '%web_to_app%'
          AND LOWER(campaign) NOT LIKE '%web2app%'
          AND visit_date >= '2026-01-01' AND visit_date < '{last_full_end}'
        GROUP BY 1, 2, 3
        HAVING SUM(d0) >= 100
      )
    )
    WHERE rn <= 30
    ORDER BY month, new_users DESC
    """)
    def classify_camp(lc):
        if any(k in lc for k in ['pty','property','bds','nha dat']): return 'pty'
        if any(k in lc for k in ['job','viec lam','tuyen dung']): return 'job'
        if any(k in lc for k in ['veh','vehicle']): return 'veh'
        if any(k in lc for k in ['gds','elt','electronics']): return 'gds'
        return 'other'
    for r in camp_rows:
        lc = str(r.get('campaign_lc',''))
        m_date = to_date(r['month'])
        campaigns.append({
            'name': str(r['campaign']),
            'vertical': classify_camp(lc),
            'new_users': int(r['new_users']) if r['new_users'] else 0,
            'activated_adview': int(r['activated_adview']) if r['activated_adview'] else 0,
            'activated_lead': int(r['activated_lead']) if r['activated_lead'] else 0,
            'activation_rate': round(float(r['activation_rate']),4) if r['activation_rate'] else None,
            'nurr_d1': round(float(r['nurr_d1']),4) if r['nurr_d1'] else None,
            'nurr_d7': round(float(r['nurr_d7']),4) if r['nurr_d7'] else None,
            'month': m_date.strftime('%b %Y'),
        })
    months_fetched = sorted(set(c['month'] for c in campaigns))
    print(f"  Campaigns: {len(campaigns)} rows OK (months: {months_fetched})")
except Exception as e:
    print(f"  WARNING Campaigns skipped: {e}")
    campaigns = D.get('campaigns', [])

# Vertical monthly breakdown — full 2026 trend
def classify_vertical(lc):
    if any(k in lc for k in ['pty','property','bds','nha dat']): return 'pty'
    if any(k in lc for k in ['job','viec lam','tuyen dung']): return 'job'
    if any(k in lc for k in ['veh','vehicle']): return 'veh'
    if any(k in lc for k in ['gds','elt','electronics']): return 'gds'
    return 'other'

vertical_monthly = D.get('vertical_monthly', {})
try:
    vm_rows = run("""
    SELECT
      DATE_TRUNC(visit_date, MONTH) as month,
      CASE
        WHEN LOWER(campaign) LIKE '%pty%' THEN 'pty'
        WHEN LOWER(campaign) LIKE '%job%' OR LOWER(campaign) LIKE '%viec lam%' THEN 'job'
        WHEN LOWER(campaign) LIKE '%veh%' THEN 'veh'
        WHEN LOWER(campaign) LIKE '%gds%' OR LOWER(campaign) LIKE '%elt%' THEN 'gds'
        ELSE 'other'
      END as vertical,
      SUM(d0) as new_users,
      SUM(user_20adview_7d) as activated_adview
    FROM ct_digital.dashboard__retention_mapping_activation_by_source_campaign
    WHERE return_status = 'new'
      AND campaign NOT IN ('all', '(none)')
      AND channel NOT IN ('all', 'Direct', 'Organic Search')
      AND vertical_user = 'all'
      AND LOWER(campaign) NOT LIKE '%web_to_app%'
      AND LOWER(campaign) NOT LIKE '%web2app%'
      AND visit_date >= '2026-01-01'
    GROUP BY 1, 2
    ORDER BY 1, 2
    """)
    vm_lookup = {}
    for r in vm_rows:
        vm_lookup[(to_date(r['month']), r['vertical'])] = r
    def vm_arr(vert, key):
        return [int(vm_lookup.get((m, vert), {}).get(key) or 0) for m in all_months]
    vertical_monthly = {
        'pty_new_users': vm_arr('pty', 'new_users'),
        'job_new_users': vm_arr('job', 'new_users'),
        'veh_new_users': vm_arr('veh', 'new_users'),
        'gds_new_users': vm_arr('gds', 'new_users'),
        'pty_activated': vm_arr('pty', 'activated_adview'),
        'job_activated': vm_arr('job', 'activated_adview'),
        'veh_activated': vm_arr('veh', 'activated_adview'),
        'gds_activated': vm_arr('gds', 'activated_adview'),
    }
    print(f"  Vertical monthly: OK ({len(vm_rows)} rows)")
except Exception as e:
    print(f"  WARNING Vertical monthly skipped: {e}")

# Attribution assist — % of Direct/Organic users that are Growth-campaign last-touch attributed
attribution_assist = D.get('attribution_assist', {'direct_pct': [None]*n, 'organic_pct': [None]*n})
try:
    aa_rows = run("""
    SELECT
      DATE_TRUNC(visit_date, MONTH) as month,
      channel,
      SUM(CASE WHEN campaign = 'all' THEN d0 ELSE 0 END) as total_channel,
      SUM(CASE WHEN campaign NOT IN ('all','(none)')
           AND NOT REGEXP_CONTAINS(LOWER(campaign), r'web.to.app|web2app')
           THEN d0 ELSE 0 END) as growth_campaign_attributed
    FROM ct_digital.dashboard__retention_mapping_activation_by_source_campaign
    WHERE return_status = 'new'
      AND vertical_user = 'all'
      AND channel IN ('Direct', 'Organic Search')
      AND visit_date >= '2026-01-01'
    GROUP BY 1, 2
    ORDER BY 1, 2
    """)
    aa_lookup = {}
    for r in aa_rows:
        aa_lookup[(to_date(r['month']), r['channel'])] = r
    def aa_pct(ch):
        out_arr = []
        for m in all_months:
            row = aa_lookup.get((m, ch), {})
            total = int(row.get('total_channel') or 0)
            tagged = int(row.get('growth_campaign_attributed') or 0)
            out_arr.append(round(tagged/total, 4) if total else None)
        return out_arr
    attribution_assist = {
        'direct_pct': aa_pct('Direct'),
        'organic_pct': aa_pct('Organic Search'),
    }
    print(f"  Attribution assist: {len(aa_rows)} rows OK")
except Exception as e:
    print(f"  WARNING Attribution assist skipped: {e}")

# Cost — managed manually via Budget tab in dashboard (localStorage)
# Keep existing cost data from data.json; do not overwrite with BQ or Sheet data.
cost = pad(D['growth_channel']['cost'], n)
new_forecast = D['growth_channel'].get('cost_forecast', [])
gc_new = growth_n
ret_d1_gc=[round(gc_new[i]*(paid_d1[i] or 0)) if gc_new[i] else None for i in range(n)]
ret_d7_gc=[round(gc_new[i]*(paid_d7[i] or 0)) if gc_new[i] else None for i in range(n)]
ret_m1_gc=[round(gc_new[i]*(paid_m1[i] or 0)) if gc_new[i] and paid_m1[i] else None for i in range(n)]

# Build output
out = {
    "updated_at": today.strftime("%Y-%m-%d"),
    "months": months_labels,
    "partial_months": partial,
    "overview": {
        "mau_app": mau_app, "mau_login": mau_login,
        "mau_nonlogin": [a-b if a and b else None for a,b in zip(mau_app,mau_login)],
        "avg_dau": avg_dau, "total_ct_mau": ct_mau,
        "web_other_mau": [a-b if a and b else None for a,b in zip(ct_mau,mau_app)],
        "new_mau": total_n, "new_login_mau": new_login_total,
        "avg_new_dau": daily(total_n, days),
        "returning_mau": [a-b if a and b else None for a,b in zip(mau_app,total_n)],
        "pct_new": [safe_div(total_n[i],mau_app[i]) for i in range(n)],
        "login_rate": [safe_div(mau_login[i],mau_app[i]) for i in range(n)],
        "new_login_rate": [safe_div(new_login_total[i],total_n[i]) for i in range(n)],
        "pct_app_ct": [safe_div(mau_app[i],ct_mau[i]) for i in range(n)],
    },
    "acquisition": {
        "direct": direct_n, "organic": organic_n, "growth": gc_new, "other": other_n,
        "direct_daily": daily(direct_n,days), "organic_daily": daily(organic_n,days),
        "growth_daily": daily(gc_new,days), "other_daily": daily(other_n,days),
        "growth_pct_total": [safe_div(gc_new[i],total_n[i]) for i in range(n)],
    },
    "activation": {
        "adview_total": adview_total, "lead_total": lead_total, "save_total": save_total,
        "adview_rate": [safe_div(adview_total[i],total_n[i]) for i in range(n)],
        "lead_rate": [safe_div(lead_total[i],total_n[i]) for i in range(n)],
        "save_rate": [safe_div(save_total[i],total_n[i]) if save_total[i] else None for i in range(n)],
        "adview_daily": daily(adview_total,days), "lead_daily": daily(lead_total,days),
        "save_daily": daily(save_total,days),
        "direct_adview": dir_adv, "organic_adview": org_adv, "growth_adview": growth_adv,
        "direct_lead": dir_lead, "organic_lead": org_lead, "growth_lead": growth_lead,
        "direct_save": dir_save, "organic_save": org_save, "growth_save": growth_save,
        "direct_adview_daily": daily(dir_adv,days), "organic_adview_daily": daily(org_adv,days),
        "growth_adview_daily": daily(growth_adv,days),
        "direct_lead_daily": daily(dir_lead,days), "organic_lead_daily": daily(org_lead,days),
        "growth_lead_daily": daily(growth_lead,days),
        "direct_save_daily": daily(dir_save,days), "organic_save_daily": daily(org_save,days),
        "growth_save_daily": daily(growth_save,days),
    },
    "retention": {
        "total_d1": tot_d1, "total_d7": tot_d7, "total_m1": tot_m1,
        "app_d1": app_d1, "app_d7": app_d7, "app_m1": app_m1,
        "web_d1": web_d1, "web_d7": web_d7, "web_m1": web_m1,
        "nurr_d1": nurr_d1, "nurr_d7": nurr_d7, "nurr_m1": nurr_m1,
        "direct_d1": dir_d1, "direct_d7": dir_d7, "direct_m1": dir_m1,
        "organic_d1": org_d1, "organic_d7": org_d7, "organic_m1": org_m1,
        "growth_d1": paid_d1, "growth_d7": paid_d7, "growth_m1": paid_m1,
    },
    "growth_channel": {
        "new_users": gc_new, "avg_new_dau": daily(gc_new,days),
        "adview_activated": growth_adv, "lead_activated": growth_lead,
        "adview_rate": [safe_div(growth_adv[i],gc_new[i]) for i in range(n)],
        "lead_rate": [safe_div(growth_lead[i],gc_new[i]) for i in range(n)],
        "adview_daily": daily(growth_adv,days), "lead_daily": daily(growth_lead,days),
        "nurr_d1": paid_d1, "nurr_d7": paid_d7, "nurr_m1": paid_m1,
        "cost": cost, "cost_forecast": new_forecast,
        "pct_of_total_new": [safe_div(gc_new[i],total_n[i]) for i in range(n)],
        "retained_d1": ret_d1_gc, "retained_d7": ret_d7_gc, "retained_m1": ret_m1_gc,
        "cpa": [round(cost[i]/gc_new[i]) if cost[i] and gc_new[i] else None for i in range(n)],
        "caa": [round(cost[i]/growth_adv[i]) if cost[i] and growth_adv[i] else None for i in range(n)],
        "crr_d1": [round(cost[i]/ret_d1_gc[i]) if cost[i] and ret_d1_gc[i] else None for i in range(n)],
        "crr_d7": [round(cost[i]/ret_d7_gc[i]) if cost[i] and ret_d7_gc[i] else None for i in range(n)],
        "crr_m1": [round(cost[i]/ret_m1_gc[i]) if cost[i] and ret_m1_gc[i] else None for i in range(n)],
    },
    "vertical_monthly": vertical_monthly,
    "attribution_assist": attribution_assist,
    "campaigns": campaigns,
    "daily_activation": [
        {
            "date": str(r["visit_date"]),
            "channel": str(r["channel"]),
            "new_users": int(r["new_users"]) if r["new_users"] else 0,
            "adview_activated": int(r["adview_activated"]) if r["adview_activated"] else 0,
            "lead_activated": int(r["lead_activated"]) if r["lead_activated"] else 0,
            "save_activated": int(r["save_activated"]) if r["save_activated"] else 0,
        }
        for r in daily_act_rows
    ] if daily_act_rows else D.get("daily_activation", []),
}

with open(DATA_JSON, 'w') as f:
    json.dump(out, f, indent=2, default=str)

print(f"✅ data.json updated — {months_labels}")
print(f"   Latest: {months_labels[-1]} | App MAU: {mau_app[-1]:,} | New: {total_n[-1]:,}")
