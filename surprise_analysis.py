"""Optional forecast-surprise comparisons over a supplied historical study database."""
import argparse
import hashlib
import json
import math
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from database import connect
from study import metadata, session_responses
from build_case_report import write_csv

ROOT=Path(__file__).resolve().parent
PATTERN=re.compile(r'([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)([%KMB]?)',re.I)


def parse_value(raw):
    """Strict unambiguous numeric grammar; percentages stay in percentage points."""
    value=str(raw or '').strip().replace('\u2212','-')
    if value.lower() in {'','n/a','na','nan','--','-'}:
        return None,'missing'
    match=PATTERN.fullmatch(value)
    if not match:
        return None,'unsupported'
    number=Decimal(match[1].replace(',',''))
    suffix=match[2].upper()
    return (number*{'':1,'%':1,'K':1000,'M':1000000,'B':1000000000}[suffix],
            'percentage_points' if suffix=='%' else 'numeric')


def normalize_pair(actual,forecast):
    a,unit_a=parse_value(actual)
    f,unit_f=parse_value(forecast)
    reason='comparable'
    if a is None or f is None:
        reason='missing_value' if 'missing' in (unit_a,unit_f) else 'unsupported_format'
    elif unit_a!=unit_f:
        reason='unit_mismatch'
    delta=float(a-f) if reason=='comparable' else None
    return (float(a) if a is not None else None,float(f) if f is not None else None,
            unit_a if reason=='comparable' else '',delta,reason)


def query(connection,filename,parameters=()):
    result=connection.execute((ROOT/'sql'/filename).read_text(),parameters)
    names=[c[0] for c in result.description] if hasattr(result,'description') else list(result.keys())
    return [dict(zip(names,row)) for row in result.fetchall()]


def create_tables(connection):
    connection.execute('CREATE TABLE IF NOT EXISTS event_surprises ('
            'event_key VARCHAR(64) PRIMARY KEY,family VARCHAR(255),event_timestamp_utc VARCHAR(32),'
            'actual_raw VARCHAR(128),forecast_raw VARCHAR(128),actual_numeric DOUBLE,forecast_numeric DOUBLE,'
            'unit VARCHAR(32),numeric_delta DOUBLE,parse_status VARCHAR(32))')
    connection.execute('CREATE TABLE IF NOT EXISTS surprise_responses ('
            'event_key VARCHAR(64),instrument VARCHAR(16),mode VARCHAR(40),status VARCHAR(40),return_pct DOUBLE,'
            'baseline_timestamp_utc VARCHAR(32),observation_timestamp_utc VARCHAR(32),'
            'elapsed_hours_since_event DOUBLE,co_release_count INTEGER,PRIMARY KEY(event_key,instrument))')

def materialize(db):
    with connect(db) as connection:
        events=connection.execute('SELECT e.event_key,d.family,e.timestamp_utc,d.actual,d.forecast '
                                  'FROM events e JOIN event_details d ON d.event_key=e.event_key').fetchall()
    records=[tuple(row)+normalize_pair(row[3],row[4]) for row in events]
    responses=session_responses(db,horizons=[1])
    # MySQL DDL may commit implicitly: create before the atomic snapshot replacement.
    with connect(db) as connection:
        create_tables(connection)
    with connect(db) as connection:
        connection.execute('DELETE FROM surprise_responses')
        connection.execute('DELETE FROM event_surprises')
        connection.executemany('INSERT INTO event_surprises VALUES (?,?,?,?,?,?,?,?,?,?)',records)
        connection.executemany('INSERT INTO surprise_responses VALUES (?,?,?,?,?,?,?,?,?)',[
            (r['event_key'],r['instrument'],r['mode'],r['status'],
             100*math.expm1(r['log_return']) if r['status']=='ok' else None,
             r['baseline_timestamp_utc'],r['observation_timestamp_utc'],
             r['elapsed_hours_since_event'],r['co_release_count']) for r in responses])
    return records


def generate(db='data/real_cash.db',output='results/surprises',plot=True):
    provenance=metadata(db)
    if not provenance:
        raise ValueError('Prepare a sourced study database first')
    records=materialize(db)
    with connect(db) as connection:
        observations=query(connection,'surprise_observations.sql')
        summary=query(connection,'surprise_summary.sql',(.1,)*6)
    if not observations or not summary:
        raise ValueError('No repeated families with valid market observations in this snapshot')
    out=Path(output)
    out.mkdir(parents=True,exist_ok=True)
    write_csv(out/'observations.csv',observations)
    write_csv(out/'summary.csv',summary)
    stats=dict(event_records=len(records),parse_status_counts=dict(Counter(r[-1] for r in records)),
               recurring_families=len({r['family'] for r in observations}),
               recurring_event_records=len({r['event_key'] for r in observations}),
               valid_observations=sum(r['status']=='ok' for r in observations),
               neutral_threshold_pct=.1)
    (out/'coverage.json').write_text(json.dumps(stats,indent=2)+'\n',encoding='utf-8')
    if plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        focus=['united states: CPI (MoM)','united states: Nonfarm Payrolls',
               'united states: Fed Interest Rate Decision']
        fig,axes=plt.subplots(1,3,figsize=(15,5))
        colors={'HSI':'#167d9a','STOXX50E':'#c17a23','NDX':'#7058a3'}
        for ax,family in zip(axes,focus):
            rows=[r for r in summary if r['family']==family and r['surprise_category']!='unknown']
            labels=[]
            for i,r in enumerate(rows):
                ax.bar(i,r['mean_return_pct'],color=colors[r['instrument']])
                ax.annotate(f"n={r['n']}",(i,r['mean_return_pct']),xytext=(0,5 if r['mean_return_pct']>=0 else -13),
                            textcoords='offset points',ha='center',fontsize=9)
                labels.append(f"{r['instrument']}\n{r['surprise_category']}")
            ax.set_xticks(range(len(rows)),labels,rotation=45,ha='right',fontsize=8)
            ax.axhline(0,color='gray',lw=.8)
            ax.set_title(family.split(': ',1)[1])
            ax.set_ylabel('Mean observed return (%)')
            ax.margins(y=.3)
        fig.suptitle('Repeated announcements grouped by reported value versus forecast')
        fig.text(.5,.015,'Q4 2024 supplied snapshot; nominal +1h after release or reopening; tiny groups and different windows, descriptive only.',ha='center',fontsize=10)
        fig.tight_layout(rect=[0,.07,1,.94])
        fig.savefig(out/'forecast_comparison.png',dpi=150)
        plt.close(fig)
    files=['observations.csv','summary.csv','coverage.json']+(['forecast_comparison.png'] if plot else [])
    manifest={'source_metadata':provenance,'artifacts':{}}
    for filename in files:
        data=(out/filename).read_bytes()
        manifest['artifacts'][filename]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(stats,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default='data/real_cash.db')
    parser.add_argument('--output',default='results/surprises')
    parser.add_argument('--no-plot',action='store_true',help='Export SQL results using the standard library only')
    args=parser.parse_args()
    generate(args.db,args.output,not args.no_plot)
