"""Reproducible economic-event pipeline. All persisted timestamps are UTC."""
import argparse
import csv
import hashlib
import json
import math
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta, timezone
from pathlib import Path
from database import connect

ROOT = Path(__file__).resolve().parent


def utc(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError(f'Timestamp must include a timezone: {value}')
    return parsed.astimezone(timezone.utc).isoformat()


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def validate(prices, events):
    clean_prices, clean_events = {}, {}
    for row in prices:
        instrument = row['instrument'].strip()
        timestamp = utc(row['timestamp_utc'])
        close = float(row['close'])
        if not instrument or not math.isfinite(close) or close <= 0:
            raise ValueError('Prices require an instrument and a finite positive close')
        key = (instrument, timestamp)
        value = (instrument, timestamp, close)
        if key in clean_prices and clean_prices[key] != value:
            raise ValueError(f'Conflicting price duplicate: {key}')
        clean_prices[key] = value
    for row in events:
        name, country = row['name'].strip(), row['country'].strip()
        timestamp = utc(row['timestamp_utc'])
        importance = row['importance'].strip()
        if not name or not country or importance not in {'Low', 'Medium', 'High'}:
            raise ValueError('Events require name, country, and Low/Medium/High importance')
        key = hashlib.sha256(json.dumps([name, country, timestamp]).encode()).hexdigest()
        value = (key, name, country, timestamp, importance)
        if key in clean_events and clean_events[key] != value:
            raise ValueError(f'Conflicting event duplicate: {name}')
        clean_events[key] = value
    if not clean_prices or not clean_events:
        raise ValueError('Both price and event inputs must contain records')
    return list(clean_prices.values()), list(clean_events.values())


def load(db, prices, events, source):
    prices, events = validate(prices, events)
    with connect(db, initialize=True) as connection:
        price_conflict = ('ON DUPLICATE KEY UPDATE close=VALUES(close)' if db == 'mysql'
                          else 'ON CONFLICT(instrument,timestamp_utc) DO UPDATE SET close=excluded.close')
        event_conflict = ('ON DUPLICATE KEY UPDATE importance=VALUES(importance)' if db == 'mysql'
                          else 'ON CONFLICT(event_key) DO UPDATE SET importance=excluded.importance')
        connection.executemany(
            'INSERT INTO prices VALUES (?, ?, ?) ' + price_conflict, prices)
        connection.executemany(
            'INSERT INTO events VALUES (?, ?, ?, ?, ?) ' + event_conflict, events)
        connection.execute('INSERT INTO pipeline_runs '
                           '(started_utc,source,price_rows,event_rows) VALUES (?,?,?,?)',
                           (datetime.now(timezone.utc).isoformat(), source, len(prices), len(events)))
    return {'validated_prices': len(prices), 'validated_events': len(events)}


def demo():
    """Synthetic fixtures, deliberately unrelated to historical market performance."""
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    prices = []
    for position, (instrument, base) in enumerate([('DEMO_US', 100), ('DEMO_EU', 200), ('DEMO_ASIA', 300)]):
        for hour in range(96):
            prices.append(dict(instrument=instrument,
                               timestamp_utc=(start + timedelta(hours=hour)).isoformat(),
                               close=round(base * (1 + hour * .0002 * (position + 1) +
                                                    (.002 + .001 * position) * math.sin(hour + position)), 6)))
    events = [dict(name=name, country='Demo country',
                   timestamp_utc=(start + timedelta(hours=hour)).isoformat(), importance='High')
              for name, hour in zip(['Synthetic policy announcement', 'Synthetic inflation release',
                                     'Synthetic employment release'], [12, 36, 60])]
    return prices, events


def responses(db, horizon=24, tolerance=1):
    return response_curve(db, [horizon], tolerance)


def response_curve(db, horizons=range(1, 25), tolerance=1):
    """Hourly timestamps represent bar END times; tolerate at most one-hour gaps."""
    horizons = list(horizons)
    if not horizons or any(h <= 0 for h in horizons) or tolerance < 0:
        raise ValueError('Horizon must be positive and tolerance nonnegative')
    result = []
    with connect(db) as connection:
        events = connection.execute("SELECT name,timestamp_utc FROM events WHERE importance='High' ORDER BY timestamp_utc").fetchall()
        series = {}
        for instrument, timestamp, close in connection.execute('SELECT instrument,timestamp_utc,close FROM prices ORDER BY instrument,timestamp_utc').fetchall():
            times, values = series.setdefault(instrument, ([], []))
            times.append(datetime.fromisoformat(timestamp))
            values.append(close)
        # Sort parsed datetimes so fractional-second formatting cannot affect alignment.
        for instrument, (times, values) in series.items():
            pairs = sorted(zip(times, values))
            series[instrument] = ([p[0] for p in pairs], [p[1] for p in pairs])
        for horizon in horizons:
            for name, timestamp in events:
                event_time = datetime.fromisoformat(timestamp)
                target = event_time + timedelta(hours=horizon)
                for instrument, (times, values) in series.items():
                    base = bisect_right(times, event_time) - 1
                    end = bisect_left(times, target)
                    before = (times[base].isoformat(), values[base]) if base >= 0 else None
                    after = (times[end].isoformat(), values[end]) if end < len(times) else None
                    status, value = 'missing_price', None
                    if before and after:
                        base_gap = (event_time - datetime.fromisoformat(before[0])).total_seconds() / 3600
                        target_gap = (datetime.fromisoformat(after[0]) - target).total_seconds() / 3600
                        if max(base_gap, target_gap) <= tolerance:
                            status, value = 'ok', math.log(after[1] / before[1])
                        else:
                            status = 'outside_tolerance'
                    result.append(dict(event=name, event_timestamp_utc=timestamp, instrument=instrument,
                                       horizon_hours=horizon, base_timestamp_utc=before[0] if before else '',
                                       target_timestamp_utc=after[0] if after else '', status=status, log_return=value))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['demo', 'ingest', 'analyze', 'fetch-prices'])
    parser.add_argument('--db', default='data/market_events.db')
    parser.add_argument('--prices')
    parser.add_argument('--events')
    parser.add_argument('--output', default='outputs/event_responses.csv')
    parser.add_argument('--horizon', type=int, default=24)
    parser.add_argument('--ticker', default='^NDX')
    parser.add_argument('--start')
    parser.add_argument('--end')
    args = parser.parse_args()
    if args.command == 'fetch-prices':
        if not args.start or not args.end:
            parser.error('fetch-prices requires --start and --end')
        import yfinance as yf
        frame = yf.download(args.ticker, start=args.start, end=args.end,
                            interval='1h', auto_adjust=True, progress=False)
        if frame.empty:
            raise ValueError('Provider returned no data; check dates and hourly retention limits')
        if frame.columns.nlevels > 1:
            frame.columns = frame.columns.get_level_values(0)
        if frame.index.tz is None:
            raise ValueError('Provider returned timezone-naive timestamps')
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=['instrument', 'timestamp_utc', 'close'])
            writer.writeheader()
            for timestamp, row in frame.iterrows():
                # Yahoo labels hourly bars by start time; store their end time.
                end = timestamp.to_pydatetime() + timedelta(hours=1)
                writer.writerow(dict(instrument=args.ticker, timestamp_utc=utc(end.isoformat()), close=row['Close']))
        print(json.dumps({'output': str(path), 'rows': len(frame)}))
        return
    if args.command in {'demo', 'ingest'}:
        if args.command == 'demo':
            prices, events = demo()
        else:
            if not args.prices or not args.events:
                parser.error('ingest requires --prices and --events')
            prices, events = read_csv(args.prices), read_csv(args.events)
        print(json.dumps(load(args.db, prices, events, args.command)))
    rows = responses(args.db, args.horizon)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['event','event_timestamp_utc','instrument','horizon_hours','base_timestamp_utc','target_timestamp_utc','status','log_return'])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'output': str(path), 'responses': len(rows)}))


if __name__ == '__main__':
    main()
