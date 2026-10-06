"""Download real Yahoo cash index bars into ignored source storage."""
import argparse
from pathlib import Path

TICKERS = {'HSI': '^HSI', 'STOXX50E': '^STOXX50E', 'NDX': '^NDX'}


def main():
    import yfinance as yf
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True, help='Exclusive end date')
    parser.add_argument('--market', choices=TICKERS, action='append')
    parser.add_argument('--output', default='data/raw')
    args = parser.parse_args()
    Path(args.output).mkdir(parents=True, exist_ok=True)
    for market in args.market or TICKERS:
        frame = yf.download(TICKERS[market], start=args.start, end=args.end, interval='1h',
                            auto_adjust=False, progress=False)
        if frame is None or frame.empty:
            raise RuntimeError(f'No hourly data for {market}; historical retention varies by provider')
        if frame.columns.nlevels > 1:
            frame.columns = frame.columns.get_level_values(0)
        if frame.index.tz is None:
            raise ValueError('Timezone-naive Yahoo timestamps cannot be safely imported')
        frame.index = frame.index.tz_convert('UTC')
        path = Path(args.output) / f'{market}_1h_yahoo.csv'
        frame.to_csv(path)
        print(f'{market}: {len(frame)} UTC bar-start observations saved to {path}')


if __name__ == '__main__':
    main()
