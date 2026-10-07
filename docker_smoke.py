"""End-to-end container checks: SQL, repeat loads, report export and dashboard rendering."""
import argparse
import csv
import json
from pathlib import Path
from container_runner import configure_database, run
from database import connect
from study import metadata, session_responses


def snapshot():
    with connect('mysql') as connection:
        return tuple(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                     for table in ['prices','events'])


def verify(real=False,save_state=None,check_state=None):
    configure_database()
    before=snapshot()
    if check_state:
        previous=json.loads(Path(check_state).read_text())
        with connect('mysql') as connection:
            audit_runs=connection.execute('SELECT COUNT(*) FROM pipeline_runs').fetchone()[0]
        assert list(before)==previous['source_counts'],'Stored source counts changed on restart'
        assert audit_runs>=previous['audit_runs'],'Ingestion audit history was lost on restart'
    if real:
        assert metadata('mysql')['dataset']=='real'
        rows=session_responses('mysql',[1])
        assert sum(r['status']=='ok' for r in rows)>0
        with connect('mysql') as connection:
            assert connection.execute('SELECT COUNT(*) FROM event_surprises').fetchone()[0]==before[1]
        for folder in ['real','cases','surprises']:
            assert (Path('outputs')/folder/'manifest.json').is_file()
    else:
        assert before==(288,3),before
        run('demo')
        assert snapshot()==before,'Repeat load duplicated source rows'
        with Path('outputs/demo/response_curve.csv').open(newline='') as handle:
            rows=list(csv.DictReader(handle))
        assert len(rows)==216
        assert all(r['status']=='ok' for r in rows)
        with connect('mysql') as connection:
            query=Path('sql/analysis.sql').read_text()
            assert len(connection.execute(query).fetchall())==285
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file('dashboard.py',default_timeout=60).run()
    assert not app.exception,[str(e) for e in app.exception]
    assert app.text_input[0].value=='mysql'
    app.radio[0].set_value('Percent return').run()
    assert not app.exception
    if real:
        app.selectbox[0].set_value('closed_at_release').run()
        assert not app.exception
    if save_state:
        with connect('mysql') as connection:
            audit_runs=connection.execute('SELECT COUNT(*) FROM pipeline_runs').fetchone()[0]
        Path(save_state).write_text(json.dumps({'source_counts':before,'audit_runs':audit_runs}))
    print(json.dumps({'check':'docker_smoke','mode':'real' if real else 'demo',
                      'price_rows':before[0],'event_rows':before[1],'dashboard':'passed'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real',action='store_true')
    parser.add_argument('--save-state')
    parser.add_argument('--check-state')
    args=parser.parse_args()
    verify(args.real,args.save_state,args.check_state)
