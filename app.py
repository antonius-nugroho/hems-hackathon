"""
app.py
Streamlit dashboard for Indonesian HEMS load forecasting + AC/EV optimization.
Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import forecasting as fc

st.set_page_config(
    page_title="HEMS Load Forecasting — Indonesia",
    page_icon="⚡",
    layout="wide",
)

TARIFF_PER_KWH = 1444.7  # Rp/kWh, illustrative PLN residential rate


# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------
@st.cache_data
def load_data():
    return fc.load_data()


@st.cache_data
def get_meta(df):
    return fc.get_household_list(df)


@st.cache_data(show_spinner=False)
def run_forecast(household_id, forecast_days, history_days):
    df = load_data()
    return fc.get_forecast_for_household(
        df, household_id, forecast_days=forecast_days, history_days=history_days
    )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("⚡ HEMS Load Forecasting — Indonesian Households")
st.caption(
    "Prophet-based demand forecasting with weather + EV charging awareness. "
    "Synthetic data: 100 households, 12 months, tropical climate."
)

df = load_data()
meta = get_meta(df)

# ---------------------------------------------------------------------------
# Sidebar: household selection & settings
# ---------------------------------------------------------------------------
st.sidebar.header("Settings")

income_filter = st.sidebar.multiselect(
    "Income segment", options=sorted(meta['income_segment'].unique()),
    default=sorted(meta['income_segment'].unique())
)
ev_filter = st.sidebar.selectbox(
    "EV ownership", options=["All", "EV owners only", "Non-EV only"], index=0
)

filtered_meta = meta[meta['income_segment'].isin(income_filter)]
if ev_filter == "EV owners only":
    filtered_meta = filtered_meta[filtered_meta['has_ev'] == True]
elif ev_filter == "Non-EV only":
    filtered_meta = filtered_meta[filtered_meta['has_ev'] == False]

household_options = filtered_meta['household_id'].tolist()
if not household_options:
    st.sidebar.warning("No households match the filter.")
    st.stop()

household_id = st.sidebar.selectbox("Household", options=household_options)

forecast_days = st.sidebar.slider("Forecast horizon (days)", min_value=7, max_value=30, value=14, step=7)
history_days = st.sidebar.slider("History window shown (days)", min_value=30, max_value=180, value=60, step=30)

st.sidebar.markdown("---")
hh_row = meta[meta['household_id'] == household_id].iloc[0]
st.sidebar.subheader(f"Profile: {household_id}")
st.sidebar.write(f"**Income segment:** {hh_row['income_segment']}")
st.sidebar.write(f"**AC capacity:** {hh_row['ac_capacity_kw']} kW")
st.sidebar.write(f"**Solar:** {'Yes ☀️' if hh_row['has_solar'] else 'No'}")
if hh_row['has_ev']:
    st.sidebar.write(f"**EV:** Yes 🚗 ({hh_row['ev_charging_pattern']} charger)")
else:
    st.sidebar.write("**EV:** No")

st.sidebar.markdown("---")
st.sidebar.caption(f"Tariff assumption: Rp {TARIFF_PER_KWH:,.0f}/kWh (illustrative)")

# ---------------------------------------------------------------------------
# Run forecast
# ---------------------------------------------------------------------------
with st.spinner(f"Training Prophet model for {household_id}..."):
    result = run_forecast(household_id, forecast_days, history_days)

forecast = result['forecast']
accuracy = fc.compute_forecast_accuracy(forecast)
recommendations = fc.generate_ac_ev_recommendations(forecast, hh_row, tariff_per_kwh=TARIFF_PER_KWH)

# ---------------------------------------------------------------------------
# Top metrics row
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

avg_historical = forecast.dropna(subset=['y'])['y'].mean()
avg_forecast = forecast[forecast['y'].isna()]['yhat'].mean()
pct_change = (avg_forecast - avg_historical) / avg_historical * 100 if avg_historical else 0

col1.metric("Avg historical load", f"{avg_historical:.2f} kWh/day")
col2.metric("Avg forecasted load", f"{avg_forecast:.2f} kWh/day", f"{pct_change:+.1f}%")
if accuracy:
    col3.metric("Forecast accuracy (MAPE)", f"{accuracy['mape']:.1f}%")
else:
    col3.metric("Forecast accuracy (MAPE)", "N/A")
col4.metric("Peak days flagged", f"{len(recommendations)} / {forecast_days}")

if accuracy and accuracy['mape'] > 25 and hh_row['has_ev']:
    st.caption(
        "⚠️ Higher forecast error is expected for this household: EV charging is "
        "day-to-day sporadic (not every day, variable timing), which is harder for "
        "a daily time-series model to predict than steady AC/baseload consumption."
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Main forecast chart
# ---------------------------------------------------------------------------
st.subheader(f"📈 Load Forecast — {household_id}")

fig = go.Figure()

# Historical actuals
hist = forecast.dropna(subset=['y'])
fig.add_trace(go.Scatter(
    x=hist['ds'], y=hist['y'],
    mode='lines', name='Actual load',
    line=dict(color='#2c3e50', width=1.5)
))

# Forecast line (full range for continuity)
fig.add_trace(go.Scatter(
    x=forecast['ds'], y=forecast['yhat'],
    mode='lines', name='Forecast (Prophet)',
    line=dict(color='#e67e22', width=2, dash='dot')
))

# Confidence interval
fig.add_trace(go.Scatter(
    x=pd.concat([forecast['ds'], forecast['ds'][::-1]]),
    y=pd.concat([forecast['yhat_upper'], forecast['yhat_lower'][::-1]]),
    fill='toself', fillcolor='rgba(230,126,34,0.15)',
    line=dict(color='rgba(255,255,255,0)'),
    name='85% confidence interval', hoverinfo='skip'
))

# Vertical line marking "today" (last actual date)
last_actual = result['last_actual_date']
fig.add_vline(x=last_actual, line_dash="dash", line_color="gray")
fig.add_annotation(x=last_actual, y=forecast['yhat_upper'].max(), text="Forecast starts",
                    showarrow=False, yshift=10, font=dict(size=11, color="gray"))

fig.update_layout(
    xaxis_title="Date", yaxis_title="Daily load (kWh)",
    hovermode='x unified', height=450,
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
    margin=dict(t=30)
)

st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Recommendations panel
# ---------------------------------------------------------------------------
st.subheader("💡 AC & EV Optimization Recommendations")

if recommendations:
    st.info(
        f"**{len(recommendations)} peak day(s)** detected in the forecast window "
        f"(load in top 30% of this household's range)."
    )
    for rec in recommendations:
        total_savings = rec['ac_savings_rp'] + rec['ev_savings_rp']
        with st.container(border=True):
            rc1, rc2 = st.columns([3, 1])
            with rc1:
                st.markdown(f"**{rec['date']}** — predicted load: **{rec['predicted_load']} kWh** ⚠️")
                st.markdown(f"🌡️ {rec['ac_action']} — saves ~Rp {rec['ac_savings_rp']:,.0f}")
                if rec['ev_action']:
                    st.markdown(f"🚗 {rec['ev_action']} — saves ~Rp {rec['ev_savings_rp']:,.0f}")
            with rc2:
                st.metric("Est. savings", f"Rp {total_savings:,.0f}")
else:
    st.success("No peak-load days detected in this forecast window. Consumption looks stable. ✅")

st.markdown("---")

# ---------------------------------------------------------------------------
# Weather correlation chart
# ---------------------------------------------------------------------------
st.subheader("🌡️ Temperature vs. Load Correlation")

hh_full = df[df['household_id'] == household_id].copy()
fig2 = go.Figure()
fig2.add_trace(go.Scatter(
    x=hh_full['temperature_c'], y=hh_full['total_daily_load_with_ev_kwh'],
    mode='markers', marker=dict(size=5, color=hh_full['temperature_c'], colorscale='OrRd', showscale=True),
    name='Daily observations'
))
fig2.update_layout(
    xaxis_title="Temperature (°C)", yaxis_title="Total daily load incl. EV (kWh)",
    height=350, margin=dict(t=20)
)
st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# Fleet-level comparison
# ---------------------------------------------------------------------------
st.subheader("🏘️ Household Comparison")

comp_col1, comp_col2 = st.columns(2)

with comp_col1:
    st.markdown("**Average daily load by EV ownership**")
    ev_compare = df.groupby('has_ev')['total_daily_load_with_ev_kwh'].mean().reset_index()
    ev_compare['has_ev'] = ev_compare['has_ev'].map({True: 'EV owners', False: 'Non-EV'})
    fig3 = go.Figure(go.Bar(
        x=ev_compare['has_ev'], y=ev_compare['total_daily_load_with_ev_kwh'],
        marker_color=['#e67e22', '#3498db'], text=ev_compare['total_daily_load_with_ev_kwh'].round(2),
        textposition='auto'
    ))
    fig3.update_layout(yaxis_title="Avg daily load (kWh)", height=320, margin=dict(t=20))
    st.plotly_chart(fig3, use_container_width=True)

with comp_col2:
    st.markdown("**EV charging pattern distribution**")
    ev_only = meta[meta['has_ev'] == True]
    pattern_counts = ev_only['ev_charging_pattern'].value_counts().reset_index()
    pattern_counts.columns = ['pattern', 'count']
    fig4 = go.Figure(go.Pie(
        labels=pattern_counts['pattern'], values=pattern_counts['count'],
        marker=dict(colors=['#2ecc71', '#e74c3c', '#f39c12']), hole=0.4
    ))
    fig4.update_layout(height=320, margin=dict(t=20))
    st.plotly_chart(fig4, use_container_width=True)

st.markdown("---")
st.caption(
    "Built for Anthony's GCP HEMS Hackathon Project · Synthetic data reflects Indonesian tropical "
    "residential patterns · Prophet model with weather + EV regressors"
)
