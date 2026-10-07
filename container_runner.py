"""Container commands share one authenticated MySQL connection configuration."""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote_plus
from database import connect
from pipeline import demo, load, response_curve
from study import metadata, prepare, session_responses


def configure_database():
    if not os.environ.get('DATABASE_URL'):
        user=quote_plus(os.environ['MYSQL_USER'])
        password=quote_plus(os.environ['MYSQL_PASSWORD'])
        database=quote_plus(os.environ['MYSQL_DATABASE'])
        host=os.environ.get('MYSQL_HOST','mysql')
        os.environ['DATABASE_URL']=f'mysql+pymysql://{user}:{password}@{host}:3306/{database}'
    os.environ.setdefault('PIPELINE_DB','mysql')


def export(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(mode):
    configure_database()
    if mode=='dashboard':
        os.execvp(sys.executable,[sys.executable,'-m','streamlit','run','dashboard.py',
                   '--server.address=0.0.0.0','--server.port=8501','--server.headless=true',
                   '--browser.gatherUsageStats=false'])
    if mode=='demo':
        # Do not add synthetic instruments to a prepared real study database.
        with connect('mysql',initialize=True):
            pass
        if metadata('mysql'):
            raise ValueError('Use a separate Compose project/database for synthetic demo data')
        load('mysql',*demo(),'docker_demo')
        rows=response_curve('mysql')
        export(Path('outputs/demo/response_curve.csv'),rows)
    else:
        inputs=Path('/inputs')
        files={market:inputs/name for market,name in
               {'HSI':'HSI_1h_UTC.csv','STOXX50E':'STOXX50E_1h_UTC.csv','NDX':'NDX_1h_yahoo.csv'}.items()}
        event_file=inputs/'economic_calendar_data_final.csv'
        for path in [*files.values(),event_file]:
            if not path.is_file():
                raise FileNotFoundError(f'Required supplied archive: {path}')
        prepare('mysql',files,event_file,os.environ.get('STUDY_START','2024-10-08'),
                os.environ.get('STUDY_END','2024-12-30'),os.environ['EVENT_TIMEZONE'])
        rows=session_responses('mysql')
        export(Path('outputs/real/session_responses.csv'),rows)
        for script in ['build_real_report.py','build_case_report.py','surprise_analysis.py']:
            subprocess.run([sys.executable,script,'--db','mysql'],check=True)
        for folder in ['real','cases','surprises']:
            shutil.copytree(Path('results')/folder,Path('outputs')/folder,dirs_exist_ok=True)
        shutil.copyfile('docs/presentation_public.pdf','outputs/presentation_public.pdf')
    print(json.dumps({'stage':'pipeline_complete','mode':mode,'response_rows':len(rows),
                      'valid_rows':sum(r['status']=='ok' for r in rows)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['demo','real','dashboard'])
    run(parser.parse_args().mode)
