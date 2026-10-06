import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from database import connect
from pipeline import load
from study import calendars, locate, normalize_bars, normalize_events, session_responses


def dt(value):
    return datetime.fromisoformat('2024-10-' + value + '+00:00')


class SessionTests(unittest.TestCase):
    def test_closed_market_uses_next_open_and_never_fills_closed_target(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory)/'study.db'
            prices = [dict(instrument='TEST',timestamp_utc=dt('09T16:00:00').isoformat(),close=100),
                      dict(instrument='TEST',timestamp_utc=dt('10T10:00:00').isoformat(),close=110)]
            events = [dict(name='Release',country='Test',timestamp_utc=dt('09T18:00:00').isoformat(),importance='High')]
            load(db,prices,events,'fixture')
            with connect(db) as connection:
                key=connection.execute('SELECT event_key FROM events').fetchone()[0]
                connection.execute('INSERT INTO event_details VALUES (?,?,?,?,?,?)',(key,'Release','','','','1'))
                connection.executemany('INSERT INTO market_sessions VALUES (?,?,?,?)',[
                    ('TEST',dt('09T09:00:00').isoformat(),dt('09T16:00:00').isoformat(),'2024-10-09'),
                    ('TEST',dt('10T09:00:00').isoformat(),dt('10T16:00:00').isoformat(),'2024-10-10')])
                connection.executemany('INSERT INTO market_bars VALUES (?,?,?,?,?,?)',[
                    ('TEST',dt('09T15:00:00').isoformat(),dt('09T16:00:00').isoformat(),99,100,'2024-10-09'),
                    ('TEST',dt('10T09:00:00').isoformat(),dt('10T10:00:00').isoformat(),105,110,'2024-10-10')])
            first, closed = session_responses(db,[1,8])
            self.assertEqual(first['mode'],'closed_at_release')
            self.assertEqual(first['wait_to_reference_hours'],15)
            self.assertEqual(first['elapsed_hours_since_event'],16)
            self.assertEqual(first['baseline_timestamp_utc'],dt('09T16:00:00').isoformat())
            self.assertEqual(first['status'],'ok')
            self.assertEqual(closed['status'],'market_closed_at_target')
            self.assertIsNone(closed['log_return'])

    def test_partial_and_lunch_crossing_bars_are_excluded(self):
        segments=[(dt('10T01:30:00'),dt('10T04:00:00'),'2024-10-10')]
        rows=[dict(date='2024-10-10',time='01:30',Open=100,Close=101),
              dict(date='2024-10-10',time='03:30',Open=101,Close=102)]
        valid,rejected=normalize_bars('HSI',rows,segments,'2024-10-10','2024-10-10')
        self.assertEqual(len(valid),1)
        self.assertEqual(len(rejected),1)
        self.assertIsNone(locate(segments,dt('10T04:00:00')))

    def test_event_family_and_unknown_time(self):
        rows=[dict(event_date='2024-10-10',event_time='12:30',importance='high',
                   event='CPI (MoM)  (Sep)',country_zone='united states'),
              dict(event_date='2024-10-10',event_time='All Day',importance='high',
                   event='Holiday',country_zone='united states')]
        events,details,rejected=normalize_events(rows,'2024-10-10','2024-10-10','UTC')
        self.assertEqual(len(events),1)
        self.assertEqual(details[0][1],'united states: CPI (MoM)')
        self.assertEqual(len(rejected),1)

    @unittest.skipUnless(importlib.util.find_spec('exchange_calendars'), 'Optional calendar dependency not installed')
    def test_calendars_cover_dst_lunch_and_holiday(self):
        summer=calendars('2024-07-10','2024-07-10')
        winter=calendars('2024-12-10','2024-12-10')
        mismatch=calendars('2024-10-30','2024-10-30')
        self.assertEqual(summer['NDX'][0][0].hour,13)
        self.assertEqual(winter['NDX'][0][0].hour,14)
        self.assertEqual(mismatch['NDX'][0][0].hour,13)
        self.assertEqual(len(summer['HSI']),2)
        holiday=calendars('2024-10-11','2024-10-11')
        self.assertEqual(holiday['HSI'],[])
        self.assertEqual(calendars('2024-11-29','2024-11-29')['NDX'][0][1].hour,18)
