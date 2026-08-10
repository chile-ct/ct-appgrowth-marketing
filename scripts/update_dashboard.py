"""
App Growth Dashboard — Auto Update Script
Queries BigQuery directly. No Claude/Anthropic API. $0 token cost.
Cost data is managed manually via the Budget tab in the dashboard (localStorage).
"""
import json, os, datetime, calendar
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

# Days per month — partial month uses actual days elapsed (today.day - 1)
def days_in(d):
    if d.year == today.year and d.month == today.month:
        return max(1, today.day - 1)
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
        if any(k in lc for k in ['pty','property','bds','nha dat','nha_dat','_5010','_5020','_5030','nha_vua','bat_dong_san']): return 'pty'
        if any(k in lc for k in ['job','viec lam','viec_lam','tuyen dung','tuyen_dung']): return 'job'
        if any(k in lc for k in ['veh','vehicle','autox','_2010','_2020','_2030','_2040']): return 'veh'
        if any(k in lc for k in ['gds','elt','electronics','world_cup','awo_rewards','app_install','digital_activate','digital_install']): return 'gds'
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

# ── Detail Camp Performance — Growth team, App phase ────────────────────────
# cost + install come from the Google Sheet "[CT] App Growth - performance
# tracking 2026", tab raw_total. Activation metrics come from BigQuery.
# The two are joined on campaign name.
#
# The sheet is read through the docs.google.com CSV export endpoint rather than
# the Sheets API on purpose: GOOGLE_CREDENTIALS is a user (authorized_user) ADC
# token whose account lacks serviceusage.serviceUsageConsumer on chotot-dwh, so
# any *.googleapis.com call needing a quota project returns 403. docs.google.com
# does not enforce a quota project, so a plain Bearer request works.
SHEET_ID = '1eLdUTKfR9yHcUnnEfyIouZlCiVDPvR6yn3igxdoy8eE'
SHEET_GID = '2065956136'         # raw_total
SHEET_TARGET_GID = '2028964073'  # target

# The target tab's Month column is a bare month number, and the workbook itself
# is per-year ("[CT] App Growth - performance tracking 2026"), so the year has
# to be supplied here. Bump this when a 2027 workbook replaces it.
TARGET_YEAR = 2026

# Growth team / App phase ad accounts -> ad channel
GROWTH_ACCOUNTS = {
    'chotot_growth_sgd': 'FB',
    'chotot_pty_app':    'FB',
    'chotot_job_app':    'FB',
    'chotot_veh_app':    'FB',
    'chotot_app_pty':    'GG',
    'chotot_app_veh':    'GG',
    'chotot_app_job':    'GG',
    'chotot_growth_new': 'GG',
}
SHEET_PHASES = {'install', 'activate'}


def _sheet_token():
    """Access token for the Drive/Docs export endpoint.

    Handles both a service-account key and a user ADC token so the script keeps
    working if GOOGLE_CREDENTIALS is ever swapped for a proper service account.
    """
    from google.auth.transport.requests import Request as GRequest
    path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '/tmp/gcp-creds.json')
    with open(path) as f:
        info = json.load(f)
    if info.get('type') == 'service_account':
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
    else:
        from google.oauth2.credentials import Credentials as UserCredentials
        creds = UserCredentials.from_authorized_user_info(info)
    creds.refresh(GRequest())
    return creds.token


def _sheet_num(v):
    """Sheet numbers carry display thousands separators, e.g. "483,546"."""
    s = str(v or '').replace(',', '').replace('₫', '').strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _sheet_csv(gid):
    """Read one tab of the workbook as a list of CSV rows."""
    import csv, io, urllib.request
    url = (f'https://docs.google.com/spreadsheets/d/{SHEET_ID}'
           f'/export?format=csv&gid={gid}')
    req = urllib.request.Request(
        url, headers={'Authorization': 'Bearer ' + _sheet_token()})
    with urllib.request.urlopen(req, timeout=90) as r:
        text = r.read().decode('utf-8', 'replace')
    return list(csv.reader(io.StringIO(text)))


def fetch_camp_cost():
    """Aggregate cost + install by (month, campaign) for the growth accounts.

    Also returns how far into each month the spend data actually goes. A running
    month is only a few days old, so judging its actual against a whole month's
    target reads as a catastrophic miss when it may well be on pace. The last
    dated row per month is the honest denominator for that, and it has to come
    from here because raw_total is the only day-level source we have.

    Returns (agg, last_day, daily) where last_day maps the month's first-of-month
    date to the latest day seen for it, and daily maps (month, campaign) to
    {day: cost}. The day-level breakdown exists so a cost can be re-summed over a
    shorter window — needed when BigQuery has not published as many days as the
    sheet has, which would otherwise divide a longer stretch of spend by a shorter
    stretch of leads.
    """
    agg, seen, bad_dates = {}, 0, 0
    last_day, daily = {}, {}
    for row in _sheet_csv(SHEET_GID)[1:]:  # [1:] drops the header row
        # Columns N onward hold an unrelated account_name/channel lookup block,
        # so hard-stop at column M.
        row = (row + [''] * 13)[:13]
        date_s, account, camp = row[0].strip(), row[1].strip(), row[2].strip()
        phase, vertical = row[10].strip().lower(), row[11].strip().lower()
        if not date_s or not camp:
            continue
        channel = GROWTH_ACCOUNTS.get(account.lower())
        if channel is None or phase not in SHEET_PHASES:
            continue
        try:
            mth, dy, yr = (int(x) for x in date_s.split('/'))  # M/D/YYYY
            m_date = datetime.date(yr, mth, 1)
            d_date = datetime.date(yr, mth, dy)
        except (ValueError, TypeError):
            bad_dates += 1
            continue
        seen += 1
        prev = last_day.get(m_date)
        if prev is None or d_date > prev:
            last_day[m_date] = d_date
        e = agg.setdefault((m_date, camp), {
            'cost': 0.0, 'install': 0.0, 'channel': channel,
            'vertical': vertical or 'other', 'phases': set(),
        })
        cost = _sheet_num(row[6])
        e['cost'] += cost
        e['install'] += _sheet_num(row[5])
        e['phases'].add(phase)
        d = daily.setdefault((m_date, camp), {})
        d[d_date] = d.get(d_date, 0.0) + cost
    if bad_dates:
        print(f"  Sheet: {bad_dates} rows with unparseable dates skipped")
    print(f"  Sheet: {seen} growth rows -> {len(agg)} campaign-months")
    return agg, last_day, daily


def fetch_targets():
    """Monthly budget / install targets per vertical from the `target` tab.

    Only columns A-H (the Input + Formula target columns) are read. Columns I/J,
    "Actual spend" and "Actual install", are deliberately NOT used as the actual
    values for the progress table, for two reasons:
      1. They are maintained by hand and lag reality — they were still empty for
         July on 2026-07-31 despite 880M ₫ having been spent.
      2. At least one is wrong: May 2026 `job` reads 318,439,532 ₫, which is the
         May job spend (143,582,736) plus the May gds spend (174,856,794) added
         together, i.e. gds is counted twice in that column.
    Actuals are therefore computed from camp_detail, off the same raw_total rows
    the rest of section 6 uses. I/J are still read here purely to warn in the log
    when the sheet disagrees with us, which is how the May bug surfaced.

    Returns (target_rows, sheet_actuals) where sheet_actuals maps
    (month_label, vertical) -> (cost, install) for the non-empty cells only.
    """
    out, sheet_actuals = [], {}
    for row in _sheet_csv(SHEET_TARGET_GID):
        row = (row + [''] * 12)[:12]
        mth_s, vertical = row[0].strip(), row[1].strip().lower()
        if not mth_s.isdigit() or not 1 <= int(mth_s) <= 12 or not vertical:
            continue  # header rows and the trailing blank block
        label = datetime.date(TARGET_YEAR, int(mth_s), 1).strftime('%b %Y')

        a_cost, a_install = row[8].strip(), row[9].strip()
        if a_cost or a_install:
            sheet_actuals[(label, vertical)] = (
                _sheet_num(a_cost), _sheet_num(a_install))

        budget, t_install = _sheet_num(row[2]), _sheet_num(row[3])
        # Future months sit in the tab as placeholder rows of zeros; keeping them
        # would render as "0% of 0 ₫" noise.
        if not budget and not t_install:
            continue
        out.append({
            'month': label,
            'vertical': vertical,
            'budget': round(budget),
            'target_install': round(t_install),
            'bau_budget': round(_sheet_num(row[4])),
            'bau_install': round(_sheet_num(row[5])),
            'test_budget': round(_sheet_num(row[6])),
            'test_install': round(_sheet_num(row[7])),
        })
    print(f"  Targets: {len(out)} month-vertical rows with a target "
          f"({sorted({r['month'] for r in out})})")
    return out, sheet_actuals


camp_detail = []
month_cover = {}
try:
    sheet_agg, sheet_last_day, sheet_daily_cost = fetch_camp_cost()
    if not sheet_agg:
        raise RuntimeError('no growth rows found in raw_total')

    names = sorted({c for _m, c in sheet_agg})
    in_list = ','.join(
        "'" + n.replace('\\', '\\\\').replace("'", "\\'") + "'" for n in names)
    # channel != 'all' because that value is a pre-aggregated total of the real
    # channels; d0 is summed across the remaining channels per campaign name.
    #
    # `lead` counts contact events, not people, which is what was asked for
    # ("tổng số lượt liên hệ"). It is attributed to visit_date, so summing it
    # over the month gives exactly the leads that happened inside the period —
    # and unlike save_ad it covers Facebook, so every campaign here has one.
    # Caveat worth knowing: every row is return_status='new', so this is leads
    # made on the install day. Someone who installs on the 3rd and contacts on
    # the 6th is not in it. The lead_7d/lead_30d columns look like the fix but
    # are per-row averages, not counts — they cannot be summed — and the 30d
    # window is still filling in for recent months, so it would undercount most
    # in exactly the newest month people read first.
    #
    # Upper-bounded by the last day the spend sheet has. raw_total is filled in by
    # hand and is the source that actually lags: on 2026-08-10 the 04:38 run had
    # this table through 08-09 but the sheet only through 08-08, so Aug leads ran a
    # day ahead of Aug cost and blended Cost/Lead read 37,679 ₫ against the matched
    # 41,964 ₫ — 11% too cheap, in the direction that flatters. Capping keeps every
    # figure in this section on the window the Cost column already claims through
    # month_cover.through. The opposite skew, BigQuery trailing the sheet, cannot be
    # fixed here (the cost is already banked) and is handled below by lead_cost.
    sheet_max = max(sheet_last_day.values())
    print(f"  Camp detail: BigQuery capped at {sheet_max}, "
          f"the last day raw_total has spend for")
    act_rows = run(f"""
    SELECT
      DATE_TRUNC(visit_date, MONTH) as month,
      campaign,
      SUM(dau) as dau,
      SUM(d0) as d0,
      SUM(d1) as d1,
      SUM(d7) as d7,
      SUM(lead) as lead,
      SUM(dau_lead) as dau_lead,
      SUM(save_ad) as save_ad,
      MAX(visit_date) as bq_through
    FROM ct_digital.dashboard__retention_mapping_activation_by_source_campaign
    WHERE return_status = 'new'
      AND vertical_user = 'all'
      AND channel != 'all'
      AND visit_date >= '2026-01-01'
      AND visit_date <= '{sheet_max}'
      AND campaign IN ({in_list})
    GROUP BY 1, 2
    """)
    act = {(to_date(r['month']), str(r['campaign'])): r for r in act_rows}

    # Same table, but split by vertical, to answer "how much of this campaign's
    # contacting happened in the vertical we bought it for".
    #
    # It has to be dau_lead (users who contacted), NOT lead (contact events), and
    # that is not a style choice. On a vertical row `lead` is the user's contacts
    # across every vertical, copied into each vertical that user belongs to: for
    # 2026-08-01..09 the `other` bucket carries 1,355 contact events against 0
    # contacting users, and the five buckets sum to 82,651 against 60,593 on the
    # 'all' row (+36%). dau_lead sums to 34,188 against 33,718 (+1.4%), i.e. it
    # really does partition, and where only one vertical is involved the vertical
    # row equals the 'all' row exactly (541 of 541 slices checked). So dau_lead is
    # the only per-vertical contact figure in here that means what it says.
    #
    # Contact *events* per vertical do exist in chotot_data.traffic_lead_detail
    # joined to traffic_visit_detail, but that pair has no Facebook campaigns at
    # all — five FB names checked over 40 days return zero rows while GG ones
    # return ~29k each — and it scans 15.7 GB against this table's 0.04 GB.
    vert_rows = run(f"""
    SELECT
      DATE_TRUNC(visit_date, MONTH) as month,
      campaign,
      vertical_user,
      SUM(dau_lead) as dau_lead,
      SUM(d0) as d0
    FROM ct_digital.dashboard__retention_mapping_activation_by_source_campaign
    WHERE return_status = 'new'
      AND vertical_user IN ('pty', 'job', 'gds', 'veh')
      AND channel != 'all'
      AND visit_date >= '2026-01-01'
      AND visit_date <= '{sheet_max}'
      AND campaign IN ({in_list})
    GROUP BY 1, 2, 3
    """)
    vert = {(to_date(r['month']), str(r['campaign']), str(r['vertical_user'])): r
            for r in vert_rows}

    # How far this table has published, per month. Cost/Lead is the first number on
    # the page that divides a sheet figure by a BigQuery one, and the two sources
    # land a day apart in both directions: the cap above covers BigQuery running
    # ahead, this covers it trailing, where the spend is already banked and cannot
    # be capped away. Untested against a real occurrence — as of 2026-08-10 only the
    # other direction has been seen — so if a CPL looks wrong, check here first.
    bq_max = {}
    for r in act_rows:
        m = to_date(r['month'])
        t = to_date(r['bq_through']) if r.get('bq_through') else None
        if t and (m not in bq_max or t > bq_max[m]):
            bq_max[m] = t

    # "Save ad in D0" + its DAU denominator come from the MKT-owned adopt table,
    # where adopt_users is documented as "New user d0 adopt (save_ad d0)".
    #
    # Two quirks of this table drive the SQL below:
    #  1. report_date = first_date + 7, so the cohort month is report_date - 7.
    #     Grouping on report_date directly would push late-month cohorts into the
    #     following month and misalign them against cost.
    #  2. Rows only appear once the 7-day window has fully matured, so the most
    #     recent ~7 days of cohorts are simply absent. The ratio stays valid
    #     (numerator and denominator cover the same days) but the absolute counts
    #     understate the newest month — flagged as save_partial below.
    adopt_rows = run(f"""
    SELECT
      DATE_TRUNC(DATE_SUB(report_date, INTERVAL 7 DAY), MONTH) as month,
      campaign,
      SUM(dau) as dau,
      SUM(adopt_users) as save_ad_d0,
      MAX(DATE_SUB(report_date, INTERVAL 7 DAY)) as max_cohort
    FROM ct_product_analytics.new_user_adopt_activate
    WHERE channel != 'all'
      AND DATE_SUB(report_date, INTERVAL 7 DAY) >= '2026-01-01'
      AND campaign IN ({in_list})
    GROUP BY 1, 2
    """)
    adopt = {(to_date(r['month']), str(r['campaign'])): r for r in adopt_rows}

    # Last cohort date the adopt table has matured, per month — used to mark the
    # month whose save-ad counts are still filling in.
    adopt_max = {}
    for r in adopt_rows:
        m = to_date(r['month'])
        c = to_date(r['max_cohort']) if r['max_cohort'] else None
        if c and (m not in adopt_max or c > adopt_max[m]):
            adopt_max[m] = c

    def _int(v):
        return int(v) if v is not None else None

    def _rate(num, den):
        """Unlike safe_div, a real zero numerator stays 0.0 instead of becoming
        None — a campaign with genuinely 0 D7 retention must not render as "—".
        """
        if num is None or not den:
            return None
        return round(num / den, 4)

    def _month_end(m_date):
        """Last day of the month m_date starts, capped at today so the current
        month isn't reported as partial merely because it hasn't finished."""
        nxt = datetime.date(m_date.year + (m_date.month == 12),
                            m_date.month % 12 + 1, 1)
        return min(nxt - datetime.timedelta(days=1), today)

    for (m_date, name), s in sorted(sheet_agg.items()):
        a = act.get((m_date, name), {})
        d0 = _int(a.get('d0'))
        d1, d7 = _int(a.get('d1')), _int(a.get('d7'))
        lead = _int(a.get('lead'))
        users_lead = _int(a.get('dau_lead'))
        # The campaign's own vertical, as bought — column L of the sheet. Anything
        # not one of the four real verticals ('other', blank) has nothing to match
        # against, so it gets None and renders as "—" rather than a silent zero.
        own = s['vertical'] if s['vertical'] in ('pty', 'job', 'gds', 'veh') else None
        ov = vert.get((m_date, name, own), {}) if own else {}
        # None when the campaign has no BigQuery match at all; a real 0 when it
        # matched but nobody contacted inside its own vertical, which is a finding
        # rather than missing data and must not be blanked out.
        own_users = _int(ov.get('dau_lead')) if own and (m_date, name) in act else None
        if own_users is None and own and (m_date, name) in act:
            own_users = 0
        # DAU and save-ad-in-D0 both come from the adopt table so the % is an
        # internally consistent ratio. Mixing in the retention table's DAU here
        # would divide an app-only numerator by an all-platform denominator.
        ad = adopt.get((m_date, name), {})
        dau = _int(ad.get('dau'))
        save_ad_d0 = _int(ad.get('save_ad_d0'))
        last_cohort = adopt_max.get(m_date)
        cost, install = round(s['cost']), int(s['install'])
        # Cost restricted to the days BigQuery has actually published, so CPL
        # divides like for like. `cost` itself stays whole: it is real money and
        # the progress-vs-target table reconciles it against the sheet, so
        # trimming it there would make the dashboard contradict its own source.
        cutoff = bq_max.get(m_date)
        if cutoff is not None and cutoff < sheet_last_day.get(m_date, cutoff):
            lead_cost = round(sum(
                c for d, c in sheet_daily_cost.get((m_date, name), {}).items()
                if d <= cutoff))
        else:
            lead_cost = cost
        camp_detail.append({
            'name': name,
            'month': m_date.strftime('%b %Y'),
            'channel': s['channel'],
            'vertical': s['vertical'],
            'phase': '+'.join(sorted(s['phases'])),
            'cost': cost,
            'install': install,
            'cpi': round(cost / install) if install else None,
            'd0': d0,
            'd1': d1,
            'd7': d7,
            'rr_d1': _rate(d1, d0),
            'rr_d7': _rate(d7, d0),
            'lead': lead,
            # A campaign with cost but zero leads has no CPL to quote — None
            # renders as "—" rather than as a division by zero.
            'cpl': round(lead_cost / lead) if lead else None,
            # Only emitted when it differs from cost, i.e. when BigQuery is
            # behind the sheet; the front end uses it to blend CPL over the
            # same window and to say so.
            **({'lead_cost': lead_cost} if lead_cost != cost else {}),
            # Users who contacted anywhere, and users who contacted inside the
            # campaign's own vertical. Both are people, not contact events, so
            # they are not comparable with `lead` above — the front end labels
            # the unit on every one of these columns for exactly that reason.
            'users_lead': users_lead,
            'lead_own': own_users,
            'cpl_own': round(lead_cost / own_users) if own_users else None,
            'dau': dau,
            'save_ad_d0': save_ad_d0,
            'save_ad_rate': _rate(save_ad_d0, dau),
            # True when the month's cohorts have not all matured yet, so the
            # absolute save-ad/DAU counts are still incomplete.
            'save_partial': bool(
                last_cohort and last_cohort < _month_end(m_date)),
            'save_through': last_cohort.strftime('%d/%m') if last_cohort else None,
        })
    matched = sum(1 for r in camp_detail if r['d0'] is not None)
    save_matched = sum(1 for r in camp_detail if r['save_ad_d0'] is not None)
    # cd_ prefix on purpose: this module already has a module-level `lead_total`
    # (the section-3 activation series, a per-month list) and reusing that name
    # here silently replaced the list with an int, which only blew up 200 lines
    # later where lead_rate indexes into it.
    cd_lead_matched = sum(1 for r in camp_detail if r['lead'] is not None)
    cd_lead_total = sum(r['lead'] or 0 for r in camp_detail)
    cd_own_rows = [r for r in camp_detail if r['lead_own'] is not None]
    cd_own_users = sum(r['lead_own'] for r in cd_own_rows)
    cd_all_users = sum(r['users_lead'] or 0 for r in cd_own_rows)
    by_ch = {}
    for r in camp_detail:
        k = r['channel']
        by_ch.setdefault(k, [0, 0])
        by_ch[k][0] += 1
        if r['save_ad_d0'] is not None:
            by_ch[k][1] += 1
    det_months = sorted({r['month'] for r in camp_detail})

    # How much of each month the spend actually covers. Used by the front end to
    # judge a running month against the pace it should be at, not against a whole
    # month it has not had the days to reach yet.
    for m_date, last in sorted(sheet_last_day.items()):
        # calendar.monthrange, not _month_end() — the latter caps at today, which
        # would make the running month look like a full one (10 of 10 days).
        dim = calendar.monthrange(m_date.year, m_date.month)[1]
        bq_t = bq_max.get(m_date)
        month_cover[m_date.strftime('%b %Y')] = {
            'through': last.strftime('%Y-%m-%d'),
            'days': last.day,
            'days_in_month': dim,
            'elapsed': round(last.day / dim, 4),
            # Only set when BigQuery trails the sheet, so the front end can say
            # which window the lead numbers really cover.
            **({'bq_through': bq_t.strftime('%Y-%m-%d')}
               if bq_t and bq_t < last else {}),
        }
    running = [f"{k} through {v['through']} ({v['days']}/{v['days_in_month']}d"
               f" = {v['elapsed']:.0%})"
               for k, v in month_cover.items() if v['days'] < v['days_in_month']]
    if running:
        print(f"  Month coverage (incomplete): {'; '.join(running)}")

    print(f"  Camp detail: {len(camp_detail)} rows OK "
          f"({matched} matched BQ activation, months: {det_months})")
    print(f"  Lead: {cd_lead_matched}/{len(camp_detail)} rows have a lead count, "
          f"{cd_lead_total:,} lead events total "
          f"(unlike save_ad this covers FB, so a low match rate here is a bug)")
    if cd_all_users:
        print(f"  Own-vertical contact: {len(cd_own_rows)}/{len(camp_detail)} rows "
              f"have a vertical to match; {cd_own_users:,} of {cd_all_users:,} "
              f"contacting users stayed in the vertical the campaign was bought "
              f"for ({cd_own_users / cd_all_users:.0%}). A low share is a real "
              f"finding, not a join bug — check a campaign by hand before 'fixing'")
    else:
        print("  Own-vertical contact: nothing matched — check sheet column L")
    for m_date, last in sorted(sheet_last_day.items()):
        bq_t = bq_max.get(m_date)
        if bq_t and bq_t < last:
            trimmed = sum(r.get('lead_cost', r['cost']) for r in camp_detail
                          if r['month'] == m_date.strftime('%b %Y'))
            full = sum(r['cost'] for r in camp_detail
                       if r['month'] == m_date.strftime('%b %Y'))
            print(f"  CPL window: {m_date:%b %Y} spend runs to {last} but "
                  f"BigQuery only to {bq_t}; CPL divides {trimmed:,} ₫ "
                  f"instead of {full:,} ₫ so it is not inflated by "
                  f"{full - trimmed:,} ₫ of spend with no leads loaded yet")
    print(f"  Save ad in D0: {save_matched}/{len(camp_detail)} rows matched "
          f"new_user_adopt_activate "
          + ' '.join(f'{k}={v[1]}/{v[0]}' for k, v in sorted(by_ch.items()))
          + " (FB coverage is expected to be low until DA backfills it)")
except Exception as e:
    print(f"  WARNING Camp detail skipped: {e}")
    camp_detail = D.get('camp_detail', [])
    month_cover = D.get('month_cover', {})

# Monthly targets per vertical, for the progress table in section 6.
camp_target = D.get('camp_target', [])
try:
    camp_target, sheet_actuals = fetch_targets()

    # Tripwire: our actuals and the sheet's hand-typed ones should agree, since
    # both ultimately describe the same spend. Warn instead of failing — a stale
    # or half-filled Actual column is normal mid-month and is not our problem.
    ours = {}
    for r in camp_detail:
        k = (r['month'], r['vertical'])
        e = ours.setdefault(k, [0.0, 0.0])
        e[0] += r['cost']
        e[1] += r['install']
    for k, (s_cost, s_inst) in sorted(sheet_actuals.items()):
        o_cost, o_inst = ours.get(k, (0.0, 0.0))
        if s_cost and o_cost and abs(s_cost - o_cost) / s_cost > 0.10:
            print(f"  NOTE target tab Actual spend disagrees for {k[0]} {k[1]}: "
                  f"sheet {s_cost:,.0f} vs raw_total {o_cost:,.0f} "
                  f"({(o_cost - s_cost) / s_cost:+.1%}) — the dashboard uses "
                  f"raw_total")
except Exception as e:
    print(f"  WARNING Targets skipped: {e}")

# Vertical monthly breakdown — full 2026 trend
def classify_vertical(lc):
    if any(k in lc for k in ['pty','property','bds','nha dat','nha_dat','_5010','_5020','_5030','nha_vua','bat_dong_san']): return 'pty'
    if any(k in lc for k in ['job','viec lam','viec_lam','tuyen dung','tuyen_dung']): return 'job'
    if any(k in lc for k in ['veh','vehicle','autox','_2010','_2020','_2030','_2040']): return 'veh'
    if any(k in lc for k in ['gds','elt','electronics']): return 'gds'
    return 'other'

vertical_monthly = D.get('vertical_monthly', {})
try:
    vm_rows = run("""
    SELECT
      DATE_TRUNC(visit_date, MONTH) as month,
      LOWER(campaign) as campaign_lc,
      SUM(d0) as new_users,
      SUM(user_20adview_7d) as activated_adview
    FROM ct_digital.dashboard__retention_mapping_activation_by_source_campaign
    WHERE return_status = 'new'
      AND campaign NOT IN ('all', '(none)')
      AND channel NOT IN ('all', 'Direct', 'Organic Search', 'web_to_app')
      AND LOWER(campaign) NOT LIKE '%web_to_app%'
      AND LOWER(campaign) NOT LIKE '%web2app%'
      AND vertical_user = 'all'
      AND visit_date >= '2026-01-01'
    GROUP BY 1, 2
    ORDER BY 1, 2
    """)
    # Aggregate by (month, classified_vertical) using campaign name keywords
    vm_lookup = {}
    for r in vm_rows:
        m = to_date(r['month'])
        vert = classify_vertical(str(r.get('campaign_lc', '')))
        if vert == 'other':
            continue
        key = (m, vert)
        if key not in vm_lookup:
            vm_lookup[key] = {'new_users': 0, 'activated_adview': 0}
        vm_lookup[key]['new_users'] += int(r['new_users'] or 0)
        vm_lookup[key]['activated_adview'] += int(r['activated_adview'] or 0)
    def vm_arr(vert, key):
        return [vm_lookup.get((m, vert), {}).get(key, 0) for m in all_months]
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
    "camp_detail": camp_detail,
    "camp_target": camp_target,
    "month_cover": month_cover,
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
