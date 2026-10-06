"""Session-aware empirical study: Yahoo cash indices + archived Investing calendar."""
import argparse
from bisect import bisect_left, bisect_right
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re

from database import connect
from pipeline import utc, validate

MARKETS = {
    'HSI': {'ticker': '^HSI', 'calendar': 'XHKG', 'zone': 'Asia/Hong_Kong'},
    'STOXX50E': {'ticker': '^STOXX50E', 'calendar': 'XPAR', 'zone': 'Europe/Paris'},
    'NDX': {'ticker': '^NDX', 'calendar': 'XNYS', 'zone': 'America/New_York'},
}


def read_rows(path):
    for encoding in ['utf-8-sig', 'cp1252']:
        try:
            with Path(path).open(encoding=encoding, newline='') as handle:
                return list(csv.DictReader(handle))
        except UnicodeDecodeError:
            pass
    raise ValueError('Unsupported CSV encoding')


def calendars(start, end):
    import exchange_calendars as xcals
    import pandas as pd
    segments = {}
    for market, spec in MARKETS.items():
        cal = xcals.get_calendar(spec['calendar'],
                                 start=(datetime.fromisoformat(start)-timedelta(days=7)).date().isoformat(),
                                 end=(datetime.fromisoformat(end)+timedelta(days=7)).date().isoformat())
        schedule = cal.schedule.loc[start:end]
        result = []
        for label, row in schedule.iterrows():
            points = [(row['open'], row['close'])]
            if pd.notna(row['break_start']):
                points = [(row['open'], row['break_start']), (row['break_end'], row['close'])]
            for opening, closing in points:
                result.append((opening.to_pydatetime(), closing.to_pydatetime(), str(label.date())))
        segments[market] = result
    return segments


def locate(segments, timestamp):
    index = bisect_right([s[0] for s in segments], timestamp) - 1
    if index >= 0 and segments[index][0] <= timestamp < segments[index][1]:
        return index
    return None


def normalize_bars(market, rows, segments, start, end):
    accepted, rejected = {}, []
    for row in rows:
        stamp = row.get('Datetime') or row.get('Date') or row.get('timestamp_utc')
        if not stamp:
            stamp = f"{row['date']}T{row['time']}:00+00:00"
        timestamp = datetime.fromisoformat(utc(stamp))
        if not start <= timestamp.date().isoformat() <= end:
            continue
        finish = timestamp + timedelta(hours=1)
        index = locate(segments, timestamp)
        # Do not assign a future close to a fabricated partial-bar end time.
        if index is None or finish > segments[index][1]:
            rejected.append({'instrument': market, 'bar_start_utc': timestamp.isoformat(),
                             'reason': 'outside_or_straddles_regular_segment'})
            continue
        opening, closing = float(row.get('Open', row.get('open', 'nan'))), float(row.get('Close', row.get('close', 'nan')))
        if any(not math.isfinite(p) or p <= 0 for p in [opening, closing]):
            raise ValueError(f'Invalid {market} OHLC row at {timestamp}')
        bar = (market, timestamp.isoformat(), finish.isoformat(), opening, closing, segments[index][2])
        if timestamp in accepted and accepted[timestamp] != bar:
            raise ValueError('Conflicting source bar duplicate')
        accepted[timestamp] = bar
    if not accepted:
        raise ValueError(f'No usable cash-session bars for {market}')
    return sorted(accepted.values(), key=lambda b: b[1]), rejected


def normalize_events(rows, start, end, input_timezone):
    from zoneinfo import ZoneInfo
    events, details, rejected = [], [], []
    for row in rows:
        date = row.get('event_date', row.get('date', ''))
        if not start <= date <= end or row['importance'].lower() != 'high':
            continue
        clock = row.get('event_time', row.get('time', ''))
        try:
            naive = datetime.fromisoformat(f'{date}T{clock}')
        except ValueError:
            rejected.append({'event_date': date, 'event': row['event'], 'reason': 'missing_or_all_day_time'})
            continue
        local = naive.replace(tzinfo=ZoneInfo(input_timezone))
        # A timezone argument is a source declaration, not an inferred correction.
        stamp = local.astimezone(timezone.utc).isoformat()
        name, country = row['event'].strip(), row.get('country_zone', row.get('zone', '')).strip()
        family = re.sub(r'\s*\([^()]*\)\s*$', '', name) if re.search(r'\((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\)$', name) else name
        family = country + ': ' + re.sub(r'\s+', ' ', family).strip()
        event = dict(name=name, country=country, timestamp_utc=stamp, importance='High')
        key = hashlib.sha256(json.dumps([name, country, stamp]).encode()).hexdigest()
        events.append(event)
        details.append((key, family, row.get('actual', ''), row.get('forecast', ''), row.get('previous', ''), row.get('event_id', row.get('id', ''))))
    return events, details, rejected


def prepare(db, files, event_path, start, end, event_timezone):
    segments = calendars((datetime.fromisoformat(start) - timedelta(days=7)).date().isoformat(),
                         (datetime.fromisoformat(end) + timedelta(days=7)).date().isoformat())
    bars, rejections, sources = [], [], []
    for market, path in files.items():
        accepted, rejected = normalize_bars(market, read_rows(path), segments[market], start, end)
        bars.extend(accepted)
        rejections.extend(rejected)
        sources.append(dict(market=market, ticker=MARKETS[market]['ticker'], source='Yahoo Finance',
                            file=Path(path).name, sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                            accepted_bars=len(accepted), excluded_bars=len(rejected)))
    events, details, event_rejections = normalize_events(read_rows(event_path), start, end, event_timezone)
    checkpoints = [('2024-10-10', 'CPI (MoM)', '12:30'),
                   ('2024-11-01', 'Nonfarm Payrolls', '12:30'),
                   ('2024-11-07', 'Fed Interest Rate Decision', '19:00')]
    verified = []
    for date, name, clock in checkpoints:
        matches = [e for e in events if e['country'] == 'united states' and
                   e['name'].startswith(name) and e['timestamp_utc'].startswith(date)]
        if matches:
            expected = f'{date}T{clock}:00+00:00'
            if any(e['timestamp_utc'] != expected for e in matches):
                raise ValueError(f'Calendar timezone disagrees with official release checkpoint: {date} {name}')
            verified.append({'date': date, 'release': name, 'timestamp_utc': expected})
    prices = [dict(instrument=b[0], timestamp_utc=b[2], close=b[4]) for b in bars]
    clean_prices, clean_events = validate(prices, events)
    with connect(db, initialize=True) as connection:
        # Dedicated real-study databases must not contain the synthetic demo.
        names = {r[0] for r in connection.execute('SELECT DISTINCT instrument FROM prices').fetchall()}
        if names - set(MARKETS):
            raise ValueError('Use a dedicated database containing only HSI, STOXX50E, NDX')
        for table in ['market_bars', 'market_sessions', 'event_details', 'study_metadata']:
            connection.execute(f'DELETE FROM {table}')
        connection.execute('DELETE FROM prices')
        connection.execute('DELETE FROM events')
        connection.executemany('INSERT INTO prices VALUES (?,?,?)', clean_prices)
        connection.executemany('INSERT INTO events VALUES (?,?,?,?,?)', clean_events)
        connection.executemany('INSERT INTO market_bars VALUES (?,?,?,?,?,?)', bars)
        session_rows = [(market, opening.isoformat(), closing.isoformat(), date) for market, rows in segments.items() for opening, closing, date in rows]
        connection.executemany('INSERT INTO market_sessions VALUES (?,?,?,?)', session_rows)
        connection.executemany('INSERT INTO event_details VALUES (?,?,?,?,?,?)', list(dict((d[0], d) for d in details).values()))
        metadata = dict(dataset='real', start=start, end=end, event_source='Investing.com archived coursework CSV',
                        event_timezone=event_timezone, event_file=Path(event_path).name,
                        event_sha256=hashlib.sha256(Path(event_path).read_bytes()).hexdigest(),
                        timezone_checkpoints=verified,
                        price_sources=sources, events=len(events), excluded_event_times=len(event_rejections),
                        source_bar_convention='UTC start labels; only full 1h bars inside regular cash segments retained',
                        calendar_proxies={'STOXX50E': 'XPAR main cash-session proxy, not STOXX dissemination calendar',
                                          'NDX': 'XNYS regular-hours proxy, not a Nasdaq-specific holiday calendar'})
        connection.execute('INSERT INTO study_metadata VALUES (?,?)', ('provenance', json.dumps(metadata)))
        connection.execute('INSERT INTO pipeline_runs (started_utc,source,price_rows,event_rows) VALUES (?,?,?,?)',
                           (datetime.now(timezone.utc).isoformat(), 'yahoo_cash_investing_archive', len(clean_prices), len(clean_events)))
    Path('outputs').mkdir(exist_ok=True)
    (Path('outputs') / 'bar_exclusions.json').write_text(json.dumps(rejections, indent=2), encoding='utf-8')
    return metadata


def metadata(db):
    with connect(db) as connection:
        if db == 'mysql':
            exists = connection.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='study_metadata'").fetchone()[0]
        else:
            exists = connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='study_metadata'").fetchone()[0]
        if not exists:
            return None
        rows = connection.execute('SELECT value_json FROM study_metadata WHERE metadata_key=?', ('provenance',)).fetchall()
    return json.loads(rows[0][0]) if rows else None


def session_responses(db, horizons=range(1, 25), tolerance_minutes=60):
    """Open market: reference=release; closed market: reference=next segment open."""
    horizons = list(horizons)
    if not horizons or any(h < 1 for h in horizons) or tolerance_minutes < 0:
        raise ValueError('Positive horizons and nonnegative tolerance required')
    with connect(db) as connection:
        events = connection.execute('SELECT e.event_key,e.name,e.country,e.timestamp_utc,d.family FROM events e JOIN event_details d ON e.event_key=d.event_key ORDER BY e.timestamp_utc,e.event_key').fetchall()
        bar_rows = connection.execute('SELECT instrument,bar_start_utc,bar_end_utc,open_price,close_price,session_date FROM market_bars ORDER BY bar_start_utc').fetchall()
        session_rows = connection.execute('SELECT instrument,segment_open_utc,segment_close_utc,session_date FROM market_sessions ORDER BY segment_open_utc').fetchall()
    bars, segments = {}, {}
    for market, start, end, opening, closing, date in bar_rows:
        bars.setdefault(market, []).append((datetime.fromisoformat(start), datetime.fromisoformat(end), opening, closing, date))
    for market, start, end, date in session_rows:
        segments.setdefault(market, []).append((datetime.fromisoformat(start), datetime.fromisoformat(end), date))
    release_counts = {}
    for key, name, country, stamp, family in events:
        release_counts[country, stamp] = release_counts.get((country, stamp), 0) + 1
    result = []
    for key, name, country, stamp, family in events:
        event_time = datetime.fromisoformat(stamp)
        for market, series in bars.items():
            active = locate(segments[market], event_time)
            mode = 'open_at_release' if active is not None else 'closed_at_release'
            reference = event_time
            if active is None:
                following = [s for s in segments[market] if s[0] > event_time]
                reference = following[0][0] if following else None
            completed = [b for b in series if b[1] <= event_time]
            baseline = (completed[-1][1], completed[-1][3], 'previous_observed_close') if completed else None
            if active is not None:
                # Avoid an overnight baseline if a bar open is already observable.
                observed_opens = [b for b in series if segments[market][active][0] <= b[0] <= event_time]
                if observed_opens and (baseline is None or baseline[0] < segments[market][active][0]):
                    baseline = (observed_opens[0][0], observed_opens[0][2], 'observed_session_bar_open')
            ends = [b[1] for b in series]
            for horizon in horizons:
                target = reference + timedelta(hours=horizon) if reference else None
                # A closed-hour target stays missing; it is never shifted to next day.
                target_active = locate(segments[market], target) if target else None
                if target and target_active is None:
                    # Include an exact segment closing endpoint, but not a closed interval.
                    target_active = locate(segments[market], target - timedelta(microseconds=1))
                status, value, observation = 'no_reference_session', None, None
                if reference:
                    status = 'market_closed_at_target' if target_active is None else 'missing_price'
                    if baseline is None:
                        status = 'missing_baseline'
                    elif target_active is not None:
                        index = bisect_left(ends, target)
                        if index < len(series):
                            candidate = series[index]
                            gap = (candidate[1] - target).total_seconds() / 60
                            # Require the observation to end within the target's same segment.
                            if gap <= tolerance_minutes and candidate[1] <= segments[market][target_active][1]:
                                observation = candidate
                                status, value = 'ok', math.log(candidate[3] / baseline[1])
                            else:
                                status = 'outside_tolerance'
                result.append(dict(event_key=key, event=name, family=family, country=country, instrument=market,
                                   event_timestamp_utc=stamp, mode=mode,
                                   reference_timestamp_utc=reference.isoformat() if reference else '',
                                   wait_to_reference_hours=(reference-event_time).total_seconds()/3600 if reference else None,
                                   horizon_hours=horizon, target_timestamp_utc=target.isoformat() if target else '',
                                   baseline_timestamp_utc=baseline[0].isoformat() if baseline else '',
                                   baseline_kind=baseline[2] if baseline else '',
                                   baseline_age_hours=(event_time-baseline[0]).total_seconds()/3600 if baseline else None,
                                   observation_timestamp_utc=observation[1].isoformat() if observation else '',
                                   elapsed_hours_since_event=(observation[1]-event_time).total_seconds()/3600 if observation else None,
                                   co_release_count=release_counts[country,stamp], status=status, log_return=value))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'analyze'])
    parser.add_argument('--db', default='data/real_cash.db')
    parser.add_argument('--hsi', default='HSI_1h_UTC.csv')
    parser.add_argument('--stoxx', default='STOXX50E_1h_UTC.csv')
    parser.add_argument('--ndx', default='data/raw/NDX_1h_yahoo.csv')
    parser.add_argument('--events', default='economic_calendar_data_final.csv')
    parser.add_argument('--start', default='2024-10-08')
    parser.add_argument('--end', default='2024-12-30')
    parser.add_argument('--event-timezone', help='Required source timezone, e.g. UTC')
    parser.add_argument('--output', default='outputs/real_session_responses.csv')
    args = parser.parse_args()
    if args.command == 'prepare':
        if not args.event_timezone:
            parser.error('Declare --event-timezone; it cannot be inferred from calendar CSVs')
        print(json.dumps(prepare(args.db, {'HSI': args.hsi, 'STOXX50E': args.stoxx, 'NDX': args.ndx},
                                 args.events, args.start, args.end, args.event_timezone), indent=2))
    rows = session_responses(args.db)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'response_rows': len(rows), 'valid_rows': sum(r['status']=='ok' for r in rows)}))


if __name__ == '__main__':
    main()
