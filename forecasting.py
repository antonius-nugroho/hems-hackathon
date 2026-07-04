"""
forecasting.py
Prophet-based load forecasting for Indonesian HEMS households.
Trains a model per household using weather + EV regressors, forecasts N days ahead.
"""

import pandas as pd
import numpy as np
from prophet import Prophet
import logging
import warnings

warnings.filterwarnings('ignore')
logging.getLogger('prophet').setLevel(logging.WARNING)
logging.getLogger('cmdstanpy').setLevel(logging.WARNING)

import os
DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'indonesian_household_data_with_ev_12months.csv')


def load_data(path=DATA_PATH):
    """Load and prepare the synthetic household dataset."""
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    df['has_ev_flag'] = df['has_ev'].astype(int)
    df['is_evening_charger'] = (df['ev_charging_pattern'] == 'evening').astype(int)
    df['is_night_charger'] = (df['ev_charging_pattern'] == 'night').astype(int)
    return df


def get_household_list(df):
    """Return household metadata for dashboard selection."""
    meta = df.groupby('household_id').agg(
        income_segment=('income_segment', 'first'),
        has_solar=('has_solar', 'first'),
        has_ev=('has_ev', 'first'),
        ev_charging_pattern=('ev_charging_pattern', 'first'),
        ac_capacity_kw=('ac_capacity_kw', 'first'),
        avg_load=('total_daily_load_with_ev_kwh', 'mean'),
    ).reset_index()
    return meta


def prepare_prophet_df(df, household_id, target_col='total_daily_load_with_ev_kwh'):
    """Slice one household's history into Prophet's required ds/y format + regressors."""
    hh = df[df['household_id'] == household_id].sort_values('date').copy()

    prophet_df = pd.DataFrame({
        'ds': hh['date'],
        'y': hh[target_col],
        'temperature_c': hh['temperature_c'],
        'humidity_pct': hh['humidity_pct'],
        'rainfall_mm': hh['rainfall_mm'],
        'has_ev_flag': hh['has_ev_flag'],
        'is_evening_charger': hh['is_evening_charger'],
        'is_night_charger': hh['is_night_charger'],
    })
    return prophet_df


def train_forecast_model(prophet_df, forecast_days=14):
    """Train a Prophet model with weather + EV regressors, return model + forecast."""
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        seasonality_mode='additive',
        interval_width=0.85,
    )

    model.add_regressor('temperature_c')
    model.add_regressor('humidity_pct')
    model.add_regressor('rainfall_mm')
    model.add_regressor('has_ev_flag')
    model.add_regressor('is_evening_charger')
    model.add_regressor('is_night_charger')

    model.fit(prophet_df)

    # Build future dataframe: extend by forecast_days, carry forward regressors
    # using recent seasonal averages (since we don't have future weather in this demo)
    future = model.make_future_dataframe(periods=forecast_days)

    # For future regressor values: use a seasonal-naive approach
    # (average of same day-of-year in history, or last 30-day average as fallback)
    hist = prophet_df.set_index('ds')
    future = future.set_index('ds')

    for col in ['temperature_c', 'humidity_pct', 'rainfall_mm']:
        future[col] = hist[col].reindex(future.index)
        # Fill missing future dates with rolling recent average
        recent_avg = hist[col].tail(30).mean()
        future[col] = future[col].fillna(recent_avg)

    # EV regressors: carry forward the household's fixed EV status/pattern
    for col in ['has_ev_flag', 'is_evening_charger', 'is_night_charger']:
        val = hist[col].iloc[-1]
        future[col] = hist[col].reindex(future.index)
        future[col] = future[col].fillna(val)

    future = future.reset_index()

    forecast = model.predict(future)
    return model, forecast


def get_forecast_for_household(df, household_id, forecast_days=14, history_days=90):
    """Full pipeline: prepare data, train, forecast, and trim history for display."""
    prophet_df = prepare_prophet_df(df, household_id)
    model, forecast = train_forecast_model(prophet_df, forecast_days=forecast_days)

    # Merge actuals back in for comparison
    forecast = forecast.merge(
        prophet_df[['ds', 'y']], on='ds', how='left'
    )

    # Trim to recent history + forecast horizon for cleaner charting
    cutoff = prophet_df['ds'].max() - pd.Timedelta(days=history_days)
    forecast_trimmed = forecast[forecast['ds'] >= cutoff].copy()

    last_actual_date = prophet_df['ds'].max()

    return {
        'model': model,
        'forecast': forecast_trimmed,
        'full_forecast': forecast,
        'last_actual_date': last_actual_date,
        'prophet_df': prophet_df,
    }


def compute_forecast_accuracy(forecast_df):
    """Compute MAPE/RMSE on the portion of forecast that has actuals (in-sample check)."""
    valid = forecast_df.dropna(subset=['y'])
    if len(valid) == 0:
        return None
    errors = valid['y'] - valid['yhat']
    mape = (errors.abs() / valid['y'].replace(0, np.nan)).mean() * 100
    rmse = np.sqrt((errors ** 2).mean())
    return {'mape': mape, 'rmse': rmse}


def generate_ac_ev_recommendations(forecast_df, household_row, tariff_per_kwh=1444.7):
    """
    Generate simple rule-based AC + EV optimization recommendations
    based on forecasted peak load days.
    PLN average residential tariff ~ Rp 1,444.70/kWh (R1 900VA+ subsidized tiers vary;
    this is an illustrative flat rate for demo purposes).

    Peak day = forecasted load is in the top 30% of the household's own
    recent history+forecast range (relative, since every household's
    baseline differs).
    """
    future_only = forecast_df[forecast_df['y'].isna()].copy()
    if len(future_only) == 0:
        return []

    # Threshold relative to the forecast horizon itself: flag days that stand
    # out *within the upcoming period*, rather than vs. a shifting seasonal
    # baseline (which can flag an entire trending window).
    threshold = future_only['yhat'].quantile(0.70)
    # Guard against a flat/no-variance forecast flagging everything
    if future_only['yhat'].max() - future_only['yhat'].min() < 0.05:
        return []
    recommendations = []

    for _, row in future_only.iterrows():
        date_str = row['ds'].strftime('%a, %b %d')
        predicted = row['yhat']

        if predicted >= threshold:
            ac_savings_kwh = predicted * 0.08  # ~8% reduction from 1-2°C setpoint change
            ac_savings_rp = ac_savings_kwh * tariff_per_kwh

            rec = {
                'date': date_str,
                'predicted_load': round(predicted, 2),
                'is_peak': True,
                'ac_action': "Raise AC setpoint by 1-2°C during peak hours (2-8 PM)",
                'ac_savings_rp': round(ac_savings_rp, 0),
            }

            if household_row['has_ev'] and household_row['ev_charging_pattern'] == 'evening':
                ev_savings_kwh = predicted * 0.15
                ev_savings_rp = ev_savings_kwh * tariff_per_kwh
                rec['ev_action'] = "Shift EV charging from evening (6-10 PM) to night (10 PM-6 AM)"
                rec['ev_savings_rp'] = round(ev_savings_rp, 0)
            else:
                rec['ev_action'] = None
                rec['ev_savings_rp'] = 0

            recommendations.append(rec)

    return recommendations
