"""Run after python pipeline.py demo: streamlit run dashboard.py."""
from pathlib import Path
import math
import altair as alt
import pandas as pd
import streamlit as st
from pipeline import response_curve
from study import metadata, session_responses

st.title('Economic events across global cash equity sessions')
st.caption('How do open markets respond, and what is observed when closed markets reopen?')
default_db = 'data/real_cash.db' if Path('data/real_cash.db').is_file() else 'data/market_events.db'
db = st.text_input('Database path', default_db)
if db != 'mysql' and not Path(db).is_file():
    st.info('Create a demo database with: python pipeline.py demo')
    st.stop()
provenance = metadata(db)
real = provenance is not None and provenance.get('dataset') == 'real'
if real:
    st.caption(f"REAL DATA | Yahoo Finance cash indices + Investing.com archive | {provenance['start']} to {provenance['end']}")
    frame = pd.DataFrame(session_responses(db))
    frame['event'] = frame['family']
    reference_mode = st.selectbox('Market state at release', ['open_at_release', 'closed_at_release'])
    frame = frame[frame['mode'] == reference_mode].copy()
    st.caption('Closed markets: reference is next segment opening, using a pre-release observed baseline. Returns include overnight information. Open markets: reference is release time.')
else:
    st.caption('SYNTHETIC DEMO | Offline execution fixture, not market evidence.')
    frame = pd.DataFrame(response_curve(db))
if frame.empty:
    st.info('No high-importance events in this database.')
    st.stop()
frame['year'] = pd.to_datetime(frame['event_timestamp_utc'], utc=True).dt.year
event_options = sorted(frame['event'].unique())
preferred = 'united states: CPI (MoM)'
event = st.selectbox('Event', event_options, index=event_options.index(preferred) if preferred in event_options else 0)
year = st.selectbox('Year', sorted(frame['year'].unique()))
return_type = st.radio('Return type', ['Log return', 'Percent return'])
frame['value'] = frame['log_return'] if return_type == 'Log return' else 100 * frame['log_return'].apply(lambda x: math.expm1(x) if pd.notna(x) else float('nan'))
unit = 'Mean log return' if return_type == 'Log return' else 'Mean return (%)'
valid = frame[(frame['status'] == 'ok') & (frame['year'] == year)]
curve_tab, heatmap_tab, records_tab = st.tabs(['1–24 hour response', 'Event heatmap', 'Records'])
with curve_tab:
    st.subheader(f'{event}: 1–24 hour response ({year})')
    selected = valid[valid['event'] == event]
    if selected.empty:
        st.info('No aligned observations for this event and year.')
    else:
        grouped = selected.groupby(['instrument', 'horizon_hours'])['value'].agg(['mean', 'count']).reset_index()
        # Keep unavailable horizons as explicit gaps instead of connecting across closures.
        grid = pd.MultiIndex.from_product([sorted(selected['instrument'].unique()), range(1,25)],
                                         names=['instrument','horizon_hours'])
        grouped = grouped.set_index(['instrument','horizon_hours']).reindex(grid).reset_index()
        grouped['count'] = grouped['count'].fillna(0).astype(int)
        chart = alt.Chart(grouped).mark_line(point=True).encode(
            x=alt.X('horizon_hours:Q', title='Hours after reference (release or next opening)'),
            y=alt.Y('mean:Q', title=unit), color='instrument:N',
            tooltip=['instrument', 'horizon_hours', 'mean', 'count'])
        st.altair_chart(chart, width='stretch')
        st.caption('Counts can differ by horizon because missing observations are excluded.')
with heatmap_tab:
    horizon = st.slider('Heatmap horizon (hours)', 1, 24, 24)
    top_n = st.slider('Maximum events', 5, 50, 20)
    selected = valid[valid['horizon_hours'] == horizon]
    if selected.empty:
        st.info('No aligned observations at this horizon.')
    else:
        grouped = selected.groupby(['event', 'instrument'])['value'].agg(['mean', 'count']).reset_index()
        ranking = grouped.groupby('event')['mean'].apply(lambda s: s.abs().max()).nlargest(top_n).index.tolist()
        grouped = grouped[grouped['event'].isin(ranking)]
        scale = max(abs(grouped['mean']).max(), 1e-12)
        chart = alt.Chart(grouped).mark_rect().encode(
            x='instrument:N', y=alt.Y('event:N', sort=ranking),
            color=alt.Color('mean:Q', title=unit, scale=alt.Scale(scheme='redblue', domain=[-scale, scale])),
            tooltip=['event', 'instrument', 'mean', 'count'])
        st.altair_chart(chart, width='stretch')
        st.caption('Ranked by maximum absolute mean return within the selected market state. Missing cells have no valid observations. Closed-hour targets are excluded. See records for actual elapsed time and baseline age.')
with records_tab:
    st.dataframe(frame, hide_index=True)
    st.download_button('Download response records', frame.to_csv(index=False), 'response_curve.csv', 'text/csv')
st.caption('Descriptive associations only; overlapping announcements and market conditions are not controlled for.')
