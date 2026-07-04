# HEMS Load Forecasting Dashboard — Indonesia

Prophet-based household electricity load forecasting with weather and EV-charging
awareness, plus a rule-based AC/EV optimization advisor. Built for a GCP hackathon
prototype of a Home Energy Management System (HEMS).

## What it does

- Trains a **Prophet time-series model per household** using:
  - Weather regressors: temperature, humidity, rainfall
  - EV regressors: has_ev, evening-charger flag, night-charger flag
- Forecasts daily load **7–30 days ahead** with 85% confidence intervals
- Flags **peak-load days** within the forecast horizon (relative to that household's
  own forecasted range)
- Recommends:
  - AC setpoint adjustment (+1–2°C) on peak days, with estimated Rupiah savings
  - EV charging shift (evening → night) for households with evening-pattern chargers
- Visualizes: forecast vs. actuals, temperature-load correlation, EV-owner vs.
  non-EV comparison, EV charging pattern distribution

## Files

```
app.py                                          # Streamlit dashboard (run this)
forecasting.py                                  # Prophet model + recommendation logic
indonesian_household_data_with_ev_12months.csv  # Synthetic data: 100 households × 365 days
requirements.txt
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`. Use the sidebar to filter by income segment / EV
ownership and select a household to forecast.

## Notes on the model

- Data is **daily-resolution** (one row per household per day), so the model
  forecasts daily total kWh — not intra-day hourly load. This keeps training fast
  (~1–2 sec/household) which matters for a live demo.
- Future weather regressors are approximated with a seasonal-naive method (recent
  30-day average) since real forecast weather isn't in the synthetic dataset — swap
  in a weather API (e.g., BMKG or OpenWeather) for production use.
- MAPE varies a lot by household: **non-EV and evening-charger households forecast
  well (4–10% MAPE)** because load is weather-driven and smooth. **Night/flexible EV
  chargers show higher error (60–80% MAPE)** because charging is sporadic — this is
  a genuine finding, not a bug, and worth mentioning in your pitch as a "controllable
  but hard-to-predict load" insight.
- Tariff assumption: Rp 1,444.7/kWh (illustrative flat rate; swap in actual PLN R1
  tariff tiers for a more accurate savings estimate).

## Deploying to GCP (Cloud Run)

1. Add a `Dockerfile`:
   ```dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY . .
   RUN pip install -r requirements.txt
   EXPOSE 8080
   CMD streamlit run app.py --server.port=8080 --server.address=0.0.0.0
   ```
2. Build and deploy:
   ```bash
   gcloud builds submit --tag gcr.io/YOUR_PROJECT/hems-dashboard
   gcloud run deploy hems-dashboard \
     --image gcr.io/YOUR_PROJECT/hems-dashboard \
     --platform managed --region asia-southeast2 --allow-unauthenticated
   ```
   (`asia-southeast2` = Jakarta region, lowest latency for an Indonesia-focused demo)

## Possible extensions (if you have extra hackathon time)

- Swap Prophet's future-regressor approximation for a real weather API
- Add a Vertex AI–hosted alternative model for comparison
- Aggregate all 100 households into a feeder-level peak forecast (grid-side view)
- Add a simple linear-programming EV charge scheduler (OR-Tools) instead of the
  current rule-based recommendation
