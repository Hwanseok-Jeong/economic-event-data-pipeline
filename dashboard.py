"""Run after python pipeline.py demo: streamlit run dashboard.py."""
from pathlib import Path
import pandas as pd
import streamlit as st
from pipeline import responses

st.title('Economic Event & Market Response')
st.caption('Exploratory event study. The default demo contains synthetic data.')
db = st.text_input('Database path', 'data/market_events.db')
horizon = st.slider('Hours after announcement', 1, 24, 24)
if not Path(db).is_file():
    st.info('Create a demo database with: python pipeline.py demo')
    st.stop()
frame = pd.DataFrame(responses(db, horizon))
if frame.empty:
    st.info('No high-importance events in this database.')
    st.stop()
st.dataframe(frame, hide_index=True)
valid = frame[frame['status'] == 'ok']
if not valid.empty:
    st.bar_chart(valid.groupby('instrument')['log_return'].mean())
st.caption('Missing or distant bars are excluded. Returns are descriptive, without causal or trading-performance claims.')
