"""Regenerate curated synthetic results and a three-page public presentation."""
import csv
import hashlib
import json
import math
import tempfile
from pathlib import Path

from pipeline import ROOT, demo, load, response_curve


def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def generate(output=ROOT / 'results'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    prices, events = demo()
    with tempfile.TemporaryDirectory() as temporary:
        db = Path(temporary) / 'demo.db'
        load(db, prices, events, 'synthetic_portfolio')
        rows = response_curve(db)
    write_csv(output / 'synthetic_prices.csv', prices)
    write_csv(output / 'synthetic_events.csv', events)
    write_csv(output / 'response_curve.csv', rows)
    daily = [r for r in rows if r['horizon_hours'] == 24]
    write_csv(output / 'responses_24h.csv', daily)

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'svg.hashsalt': 'market-event-demo',
                         'axes.spines.top': False, 'axes.spines.right': False})
    instruments = sorted({r['instrument'] for r in rows})
    colors = ['#b45309', '#0f766e', '#2563eb']
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6), sharey=True)
    for ax, event in zip(axes, events):
        for instrument, color in zip(instruments, colors):
            selected = [r for r in rows if r['event'] == event['name'] and r['instrument'] == instrument and r['status'] == 'ok']
            ax.plot([r['horizon_hours'] for r in selected],
                    [100 * math.expm1(r['log_return']) for r in selected],
                    color=color, label=instrument, linewidth=2)
        ax.set_title(event['name'].replace('Synthetic ', ''), fontsize=11)
        ax.set_xlabel('Hours after announcement (UTC)')
        ax.set_xticks([1, 6, 12, 18, 24])
        ax.axhline(0, color='#94a3b8', linewidth=.7)
        ax.grid(alpha=.15)
    axes[0].set_ylabel('Return (%)')
    axes[-1].legend(fontsize=8)
    fig.suptitle('SYNTHETIC DEMO | 1–24 hour event responses', fontweight='bold')
    fig.tight_layout()
    fig.savefig(output / 'response_curve.png', dpi=150)
    fig.savefig(output / 'response_curve.svg', metadata={'Date': None})
    plt.close(fig)

    names = [e['name'] for e in events]
    matrix = [[next(100 * math.expm1(r['log_return']) for r in daily
                   if r['event'] == name and r['instrument'] == instrument) for instrument in instruments]
              for name in names]
    limit = max(abs(value) for row in matrix for value in row)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    image = ax.imshow(matrix, cmap='RdBu_r', vmin=-limit, vmax=limit, aspect='auto')
    ax.set_xticks(range(3), instruments)
    ax.set_yticks(range(3), [name.replace('Synthetic ', '') for name in names])
    for y, row in enumerate(matrix):
        for x, value in enumerate(row):
            ax.text(x, y, f'{value:.3f}%\nn=1', ha='center', va='center',
                    color='white' if abs(value) > .65 * limit else '#111827', fontsize=10)
    ax.set_title('SYNTHETIC DEMO | 2024 event heatmap at +24h', fontweight='bold', pad=14)
    fig.colorbar(image, ax=ax, label='Return (%)')
    fig.tight_layout()
    fig.savefig(output / 'event_heatmap.png', dpi=150)
    fig.savefig(output / 'event_heatmap.svg', metadata={'Date': None})
    plt.close(fig)

    pdf = ROOT / 'docs/presentation_synthetic.pdf'
    pdf.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(pdf), pagesize=(960, 540), invariant=1)
    c.setTitle('Economic Event & Market Data Pipeline - Public Portfolio')
    c.setAuthor('Hwanseok Jeong')
    navy, teal, muted = '#0f172a', '#0f766e', '#475569'

    def text(x, y, value, size=15, color=navy, bold=False):
        c.setFillColor(HexColor(color))
        c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        c.drawString(x, y, value)

    def page(number, title, subtitle):
        c.setFillColor(HexColor('#f8fafc'))
        c.rect(0, 0, 960, 540, fill=1, stroke=0)
        text(42, 494, title, 27, bold=True)
        text(42, 465, subtitle, 12, muted)
        text(42, 23, 'Hwanseok Jeong | Biological Databases coursework -> maintained side project', 10, muted)
        text(890, 23, f'{number}/3', 10, muted)

    def box(x, y, width, height, title, lines):
        c.setFillColor(HexColor('#ffffff'))
        c.setStrokeColor(HexColor('#cbd5e1'))
        c.roundRect(x, y, width, height, 10, fill=1, stroke=1)
        text(x + 16, y + height - 30, title, 16, teal, True)
        for index, line in enumerate(lines):
            text(x + 16, y + height - 58 - index * 24, line, 12)

    page(1, 'Economic Event & Market Data Pipeline',
         'Public revision | Original coursework context and reproducible engineering implementation')
    box(42, 240, 425, 190, 'Original question', [
        'How do global markets behave around economic releases?',
        'Integrate announcements and market observations.',
        'Query structured data and explore event responses.',
        'HSI / EURO STOXX 50: indices; NQ: futures.'])
    box(493, 240, 425, 190, 'Data engineering focus', [
        'Explicit CSV contracts and timezone-aware validation.',
        'SQL constraints, transactional upserts, and run records.',
        'SQLite demo + executable MySQL / SQLAlchemy backend.',
        'Streamlit curves, heatmaps, and alignment records.'])
    text(42, 192, 'Original flow', 16, teal, True)
    text(42, 161, 'yfinance / investpy -> pandas / CSV -> MySQL -> SQLAlchemy -> Streamlit', 16)
    text(42, 113, 'Current flow: price connector / event CSV or synthetic generator -> validation -> DB -> reports', 13)
    text(42, 83, 'investpy collection is historical context; current events enter through a CSV contract.', 12, muted)
    c.showPage()

    page(2, 'Relational storage and repeatable ingestion',
         'Historical MySQL design preserved as context; maintained schema is tested on SQLite and MySQL 8.4')
    box(42, 235, 425, 195, 'Original coursework tables', [
        'economic_events: release time, country, importance,',
        'actual / forecast / previous values.',
        'futures_1d_all and futures_1h_all: OHLCV + instrument.',
        'Daily and hourly records were queried from MySQL.'])
    box(493, 235, 425, 195, 'Maintained tables', [
        'prices: key = instrument + UTC bar-end timestamp.',
        'events: key = hash(name, country, UTC timestamp).',
        'pipeline_runs: source, timestamp, validated row counts.',
        'Upserts retain unique records on repeated ingestion.'])
    text(42, 193, 'SQL return calculation', 16, teal, True)
    c.setFont('Courier', 14)
    c.setFillColor(HexColor(navy))
    c.drawString(42, 158, 'LAG(close) OVER (PARTITION BY instrument ORDER BY timestamp_utc)')
    text(42, 116, 'Completed hourly bars | UTC offsets required | Missing/distant observations explicitly excluded', 13)
    text(42, 82, 'GitHub Actions: duplicate loads, corrections, invalid batches, SQL returns, and event curves.', 12, muted)
    c.showPage()

    page(3, 'Event responses and heatmap',
         'SYNTHETIC DEMO ONLY | Generated inputs, not historical market evidence or investment results')
    c.drawImage(str(output / 'response_curve.png'), 42, 252, width=876, height=180, preserveAspectRatio=True, anchor='c', mask='auto')
    c.drawImage(str(output / 'event_heatmap.png'), 42, 66, width=460, height=190, preserveAspectRatio=True, anchor='c', mask='auto')
    text(540, 212, '288 prices / 3 events / 216 responses', 15, teal, True)
    for index, line in enumerate([
        'Illustrates the same alignment used by Streamlit.',
        'One synthetic observation per event / instrument.',
        'Heatmap: +24h, not next-day daily close returns.',
        'Tests confirm implementation, not causal impact.',
        'No costs, strategy results, or profitability claims.']):
        text(540, 180 - index * 24, line, 12, muted)
    c.showPage()
    c.save()

    artifacts = list(output.glob('*.csv')) + list(output.glob('*.png')) + list(output.glob('*.svg')) + [pdf]
    manifest = dict(dataset='synthetic', generator='pipeline.demo', price_rows=len(prices),
                    event_rows=len(events), response_rows=len(rows), valid_response_rows=sum(r['status'] == 'ok' for r in rows),
                    command='python build_portfolio.py', methodology='UTC completed hourly bars; 1h alignment tolerance',
                    artifacts={str(p.relative_to(ROOT)).replace('\\', '/'): dict(bytes=p.stat().st_size,
                               sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(artifacts)})
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'response_rows': len(rows),
                      'artifact_bytes': sum(p.stat().st_size for p in artifacts)}))


if __name__ == '__main__':
    generate()
