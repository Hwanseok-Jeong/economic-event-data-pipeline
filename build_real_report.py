"""Publish derived empirical summaries and a question-led PDF; sources remain local."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo

from pipeline import ROOT
from study import calendars, metadata, session_responses

FOCUS = ['united states: CPI (MoM)', 'united states: Nonfarm Payrolls',
         'united states: Fed Interest Rate Decision']


def summary(rows):
    groups = defaultdict(list)
    for row in rows:
        if row['status'] == 'ok':
            groups[(row['family'], row['instrument'], row['mode'], row['horizon_hours'])].append(row)
    result = []
    for (family, instrument, mode, horizon), observations in sorted(groups.items()):
        returns = [100 * math.expm1(r['log_return']) for r in observations]
        result.append(dict(family=family, instrument=instrument, mode=mode, horizon_hours=horizon,
                           n=len(returns), mean_return_pct=mean(returns), median_return_pct=median(returns),
                           mean_wait_to_reference_hours=mean(r['wait_to_reference_hours'] for r in observations),
                           mean_elapsed_hours_since_event=mean(r['elapsed_hours_since_event'] for r in observations),
                           mean_baseline_age_hours=mean(r['baseline_age_hours'] for r in observations)))
    return result


def generate(db='data/real_cash.db'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor

    output = ROOT / 'results/real'
    output.mkdir(parents=True, exist_ok=True)
    meta = metadata(db)
    if not meta or meta['dataset'] != 'real':
        raise ValueError('Prepare a real study database before generating the report')
    rows = session_responses(db)
    summaries = summary(rows)
    for path, records in [(output / 'aggregated_responses.csv', summaries),
                          (output / 'focus_1h_summary.csv', [s for s in summaries if s['family'] in FOCUS and s['horizon_hours']==1])]:
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    meta['response_rows'] = len(rows)
    meta['valid_response_rows'] = sum(r['status']=='ok' for r in rows)
    meta['response_status_counts'] = dict(Counter(r['status'] for r in rows))
    meta['focus_families'] = FOCUS
    meta['methodology'] = 'Full regular-session 1h bars only. Open-at-release reference=event time; closed-at-release reference=next segment opening. Target observations at most 60min late within same segment. Baseline is last observed pre-release completed close, or already observed current-session bar open. No closed-hour fill.'
    meta['scope'] = 'Observational study, no causal identification. Release groups can overlap. Reopening returns include overnight news and unobserved price movements.'
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':10, 'svg.hashsalt':'real-cash-study',
                         'axes.spines.top':False, 'axes.spines.right':False})
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, instrument in zip(axes, ['HSI', 'STOXX50E', 'NDX']):
        for family, color in zip(FOCUS, ['#0f766e','#2563eb','#b45309']):
            modes = sorted({s['mode'] for s in summaries if s['family']==family and s['instrument']==instrument})
            for mode in modes:
                selected = {s['horizon_hours']:s for s in summaries if s['family']==family and s['instrument']==instrument and s['mode']==mode}
                label = family.replace('united states: ','') + (' / reopen' if mode=='closed_at_release' else ' / release')
                ax.plot(range(1,25), [selected[h]['mean_return_pct'] if h in selected else np.nan for h in range(1,25)],
                        label=label, color=color, linestyle='--' if mode=='closed_at_release' else '-', marker='.', linewidth=1.8)
        ax.set_title(instrument)
        ax.set_xlabel('Hours after reference (release or next open)')
        ax.set_xticks([1,6,12,18,24])
        ax.grid(alpha=.15)
        ax.axhline(0,color='#94a3b8',linewidth=.7)
        ax.legend(fontsize=7)
    axes[0].set_ylabel('Mean observed return (%)')
    fig.suptitle('REAL DATA | U.S. releases across three cash indices | Oct–Dec 2024', fontweight='bold')
    fig.tight_layout()
    fig.savefig(output / 'response_curve.png', dpi=150)
    fig.savefig(output / 'response_curve.svg', metadata={'Date':None})
    plt.close(fig)

    cells = [s for s in summaries if s['family'] in FOCUS and s['horizon_hours']==1]
    matrix = [[next((s['mean_return_pct'] for s in cells if s['family']==family and s['instrument']==market),np.nan)
               for market in ['HSI','STOXX50E','NDX']] for family in FOCUS]
    fig, ax = plt.subplots(figsize=(9,4))
    bound = max(abs(v) for r in matrix for v in r if not math.isnan(v))
    image = ax.imshow(matrix, cmap='RdBu_r',vmin=-bound,vmax=bound,aspect='auto')
    ax.set_xticks(range(3), ['HSI','STOXX50E','NDX'])
    ax.set_yticks(range(3),[f.replace('united states: ','') for f in FOCUS])
    for y,family in enumerate(FOCUS):
        for x,market in enumerate(['HSI','STOXX50E','NDX']):
            cell = next((s for s in cells if s['family']==family and s['instrument']==market),None)
            if cell:
                label = f"{cell['mean_return_pct']:+.3f}%\nn={cell['n']} | " + ('next open' if cell['mode']=='closed_at_release' else 'release')
                ax.text(x,y,label,ha='center',va='center',fontsize=9,
                        color='white' if abs(cell['mean_return_pct'])>.6*bound else '#111827')
    ax.set_title('REAL DATA | Nominal +1h: release vs next-opening references',fontweight='bold',pad=14)
    fig.colorbar(image,ax=ax,label='Mean observed return (%)')
    fig.tight_layout()
    fig.savefig(output/'event_heatmap.png',dpi=150)
    fig.savefig(output/'event_heatmap.svg',metadata={'Date':None})
    plt.close(fig)

    fig, axes = plt.subplots(3,1,figsize=(11,6),sharex=True)
    dates = ['2024-07-10','2024-10-30','2024-12-10']
    time_rows = []
    for ax,date in zip(axes,dates):
        segments = calendars(date,date)
        for y,market in enumerate(['HSI','STOXX50E','NDX']):
            for start,end,label in segments[market]:
                left,right = start.astimezone(ZoneInfo('Europe/Brussels')),end.astimezone(ZoneInfo('Europe/Brussels'))
                x = left.hour + left.minute/60
                width = (end-start).total_seconds()/3600
                ax.barh(y,width,left=x,color=['#0f766e','#2563eb','#b45309'][y],height=.55)
                ax.text(x-.1,y,left.strftime('%H:%M'),ha='right',va='center',fontsize=8)
                ax.text(x+width+.1,y,right.strftime('%H:%M'),ha='left',va='center',fontsize=8)
                time_rows.append(dict(date=date,market=market,opening_utc=start.isoformat(),closing_utc=end.isoformat(),
                                      opening_brussels=left.isoformat(),closing_brussels=right.isoformat()))
        ax.set_yticks(range(3),['Hong Kong','Europe cash proxy','Nasdaq regular'])
        ax.set_title(date+' | '+left.tzname(),loc='left',fontsize=10)
        ax.grid(axis='x',alpha=.15)
        ax.set_xlim(0,24)
    axes[-1].set_xticks(range(0,25,2))
    axes[-1].set_xlabel('Europe/Brussels local clock (date-aware CET / CEST)')
    fig.suptitle('Regular cash sessions: summer, DST mismatch week, winter',fontweight='bold')
    fig.tight_layout()
    fig.savefig(output/'market_sessions.png',dpi=150)
    fig.savefig(output/'market_sessions.svg',metadata={'Date':None})
    plt.close(fig)
    with (output/'session_time_examples.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(time_rows[0]));writer.writeheader();writer.writerows(time_rows)

    first = [s for s in cells if s['family']=='united states: CPI (MoM)']
    interpretation = '\n'.join(f"- {s['instrument']}: mean {s['mean_return_pct']:+.3f}%, median {s['median_return_pct']:+.3f}%, n={s['n']}; {s['mode']}; mean elapsed since release {s['mean_elapsed_hours_since_event']:.1f}h." for s in first)
    (output/'findings.md').write_text('# Observed results\n\n'+
        'Question: how do cash indices respond around economic announcements, accounting for which markets are open?\n\n'+
        '## Illustrative U.S. CPI (MoM) releases\n\n'+interpretation+'\n\n'+
        'These are nominal +1h targets after the release for open markets or after the next segment opening for closed markets. '+
        'They are not simultaneous responses. Reopening returns use a pre-release observed close and include overnight information. '+
        'Only three CPI releases are available; there is no significance or causal claim. CPI, core CPI and jobless claims can be released together. '+
        'The mean/median and observation counts are in the CSVs. Closed targets remain absent rather than flat-filled.\n',encoding='utf-8')

    pdf = ROOT/'docs/presentation_public.pdf'
    c=canvas.Canvas(str(pdf),pagesize=(960,540),invariant=1)
    c.setTitle('Economic Events Across Global Cash Equity Sessions')
    c.setAuthor('Hwanseok Jeong')
    def text(x,y,value,size=13,bold=False):
        c.setFillColor(HexColor('#0f172a'));c.setFont('Helvetica-Bold' if bold else 'Helvetica',size);c.drawString(x,y,value)
    def page(number,title,subtitle):
        c.setFillColor(HexColor('#f8fafc'));c.rect(0,0,960,540,fill=1,stroke=0)
        text(38,497,title,25,True);text(38,471,subtitle,11)
        text(38,22,'Hwanseok Jeong | Biological Databases -> empirical SQL / Streamlit project',10)
        text(898,22,f'{number}/3',10)
    page(1,'Economic events across global cash equity sessions',
         'Question: how do open markets respond, and what is observed when closed markets subsequently reopen?')
    c.drawImage(str(output/'market_sessions.png'),38,112,width=510,height=342,preserveAspectRatio=True,anchor='c')
    for i,line in enumerate(['Hong Kong: Hang Seng (^HSI)', 'Europe: EURO STOXX 50 (^STOXX50E)',
                             'U.S.: Nasdaq-100 cash index (^NDX)', '',
                             'Three cash indices; no NQ=F futures.',
                             'Sessions overlap; they do not cover 24h.',
                             'DST, lunch breaks and holidays matter.',
                             'Europe: main cash-session proxy;',
                             'index dissemination is a different window.']):
        text(575,405-i*25,line,12)
    text(38,76,'Verified against HKEX / Nasdaq hours; XPAR and XNYS are documented calendar proxies.',11)
    c.showPage()
    page(2,'From the question to a SQL-backed event study',
         'Actual observations | 2024-10-08 to 2024-12-30 | Original Yahoo Finance / Investing.com source flow retained')
    text(38,417,'Yahoo cash-index OHLC + Investing.com economic calendar archive',19,True)
    text(38,376,'-> explicit timezone / trading-calendar checks -> SQLite or MySQL -> session-aware reports',16)
    count=sum(s['accepted_bars'] for s in meta['price_sources'])
    text(38,321,f"{count:,} accepted hourly bars | {meta['events']} timed high-importance events | {len(rows):,} response attempts",17,True)
    for i,line in enumerate(['SQL tables: prices, events, market_bars, market_sessions, event_details, pipeline_runs.',
                             'Open at release: reference = announcement time; baseline = an already observed price.',
                             'Closed at release: reference = next opening; baseline = last observed pre-release close.',
                             'Targets in closed sessions are missing. Full hourly bars crossing boundaries are excluded.',
                             'Actual reference, baseline age, observed time, elapsed time and co-releases are recorded.',
                             'Inputs are local archives / downloads; published results are derived summaries.']):
        text(38,270-i*31,line,13)
    text(38,61,'UTC calendar timestamps spot-checked against BLS CPI/payrolls and Federal Reserve release times.',11)
    c.showPage()
    page(3,'Observed results: responses depend on the session',
         'REAL DATA | Descriptive observations, not isolated causal effects | Counts differ across releases and horizons')
    c.drawImage(str(output/'response_curve.png'),38,250,width=884,height=181,preserveAspectRatio=True,anchor='c')
    c.drawImage(str(output/'event_heatmap.png'),38,63,width=470,height=180,preserveAspectRatio=True,anchor='c')
    text(538,211,'CPI (MoM): nominal +1h summary',15,True)
    for i,s in enumerate(sorted(first,key=lambda s:s['instrument'])):
        text(538,182-i*24,f"{s['instrument']}: {s['mean_return_pct']:+.3f}% mean (n={s['n']}); "+('reopen' if s['mode']=='closed_at_release' else 'release'),12)
    text(538,98,'Reopening returns include other overnight news.',11)
    text(538,77,'Small samples, co-releases, and hourly resolution limit inference.',11)
    c.showPage();c.save()

    meta['artifacts']={str(p.relative_to(ROOT)).replace('\\','/'):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                       for p in sorted(output.iterdir()) if p.name not in {'manifest.json','README.md'}}
    meta['artifacts']['docs/presentation_public.pdf']=dict(bytes=pdf.stat().st_size,sha256=hashlib.sha256(pdf.read_bytes()).hexdigest())
    (output/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'dataset':'real','accepted_bars':count,'events':meta['events'],'response_rows':len(rows),
                      'valid_rows':meta['valid_response_rows'],'artifact_bytes':sum(a['bytes'] for a in meta['artifacts'].values())}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--db',default='data/real_cash.db')
    generate(parser.parse_args().db)
