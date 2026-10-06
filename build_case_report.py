"""Materialize session-aware returns, then answer cross-market questions in SQL."""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from database import connect
from study import metadata, session_responses

ROOT = Path(__file__).resolve().parent
COLUMNS = ['event_key', 'country', 'event_timestamp_utc', 'instrument', 'status',
           'observation_timestamp_utc', 'return_pct']


def classify(connection, threshold=0.1):
    result = connection.execute((ROOT/'sql/release_cases.sql').read_text(), (threshold, threshold))
    names = [column[0] for column in result.description] if hasattr(result, 'description') else list(result.keys())
    return [dict(zip(names, row)) for row in result.fetchall()]


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def generate(db='data/real_cash.db'):
    provenance = metadata(db)
    if not provenance:
        raise ValueError('Prepare a real study database first')
    responses = session_responses(db, horizons=[1])
    for row in responses:
        row['return_pct'] = 100*math.expm1(row['log_return']) if row['status']=='ok' else None
    # Dedicated derived table: replace the snapshot, leaving sourced tables untouched.
    with connect(db) as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS session_responses_report ('
                           'event_key VARCHAR(64), country VARCHAR(128), event_timestamp_utc VARCHAR(32), '
                           'instrument VARCHAR(16), status VARCHAR(40), observation_timestamp_utc VARCHAR(32), '
                           'return_pct DOUBLE)')
        connection.execute('DELETE FROM session_responses_report')
        connection.executemany('INSERT INTO session_responses_report VALUES (?,?,?,?,?,?,?)',
                               [tuple(row[c] for c in COLUMNS) for row in responses])
        cases = classify(connection)
        sensitivity = []
        for threshold in [0, 0.05, 0.1, 0.2]:
            classified = classify(connection, threshold)
            counts = Counter(c['direction'] for c in classified)
            sensitivity.extend(dict(threshold_pct=threshold, category=category, count=counts[category],
                                    eligible_releases=len(classified), share_pct=100*counts[category]/len(classified))
                               for category in ['all_positive','all_negative','mixed_direction','includes_neutral'])
    out = ROOT/'results/cases'
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out/'release_classifications.csv', cases)
    write_csv(out/'threshold_sensitivity.csv', sensitivity)
    counts = Counter(c['direction'] for c in cases)
    total = len({(r['country'],r['event_timestamp_utc']) for r in responses})
    stats = dict(event_records=len(responses)//3, release_clusters=total, eligible_releases=len(cases),
                 excluded_releases=total-len(cases), threshold_pct=0.1, categories=dict(counts),
                 same_direction_increasing_magnitude=sum(c['increasing_magnitude'] for c in cases),
                 percentages={k:100*v/len(cases) for k,v in counts.items()})
    # Deterministic examples: earliest eligible release in each specified class.
    selections = []
    for title, predicate in [('Same direction',lambda c:c['direction'] in ['all_positive','all_negative']),
                             ('Different directions',lambda c:c['direction']=='mixed_direction'),
                             ('Increasing magnitude',lambda c:c['increasing_magnitude']==1)]:
        matches = [c for c in cases if predicate(c)]
        if matches:
            selections.append((title,matches[0]))
    example_rows = []
    for title, case in selections:
        names = sorted({r['event'] for r in responses if r['country']==case['country'] and
                        r['event_timestamp_utc']==case['event_timestamp_utc']})
        for row in responses:
            if row['event_key']==case['event_key']:
                example_rows.append(dict(example=title, release_indicators='; '.join(names), **row))
    write_csv(out/'example_observations.csv',example_rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1,len(selections),figsize=(15,5), squeeze=False)
    colors={'HSI':'#167d9a','STOXX50E':'#c17a23','NDX':'#7058a3'}
    for ax,(title,case) in zip(axes[0],selections):
        rows=sorted([r for r in example_rows if r['example']==title],key=lambda r:r['observation_timestamp_utc'])
        ax.bar(range(3),[r['return_pct'] for r in rows],color=[colors[r['instrument']] for r in rows])
        ax.set_xticks(range(3),[f"{r['instrument']}\n+{r['elapsed_hours_since_event']:g}h after release" for r in rows])
        for i,r in enumerate(rows):
            ax.annotate(f"{r['return_pct']:+.3f}%",(i,r['return_pct']),xytext=(0,5 if r['return_pct']>=0 else -14),textcoords='offset points',ha='center')
        ax.axhline(0,color='gray',lw=.8)
        ax.set_title(f"{title}\n{case['country']} | {case['event_timestamp_utc'][:10]}")
        ax.set_ylabel('Observed return from market-specific baseline (%)')
        ax.margins(y=.3)
    fig.suptitle('Same release, different cash-session observation windows',fontsize=15)
    fig.text(.5,.01,'Earliest eligible example per class; +1h after release or reopening. Timing and baselines differ; no causal transmission claim.',ha='center',fontsize=10)
    fig.tight_layout(rect=[0,.06,1,.94])
    fig.savefig(out/'release_examples.png',dpi=160)
    plt.close(fig)
    (out/'summary.json').write_text(json.dumps(stats,indent=2)+'\n',encoding='utf-8')
    manifest={'source_metadata':provenance,'artifacts':{}}
    for path in sorted(out.iterdir()):
        if path.name in ['manifest.json','README.md']:
            continue
        data=path.read_bytes()
        manifest['artifacts'][path.relative_to(ROOT).as_posix()]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(stats,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default='data/real_cash.db')
    generate(parser.parse_args().db)
