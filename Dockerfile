FROM python:3.11-slim

WORKDIR /app

# System deps needed by prophet/cmdstanpy (C++ toolchain for Stan)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-install cmdstan (prophet's backend) at build time so it's not
# downloaded on every cold start
RUN python -c "import cmdstanpy; cmdstanpy.install_cmdstan()"

COPY . .

EXPOSE 8080

CMD streamlit run app.py --server.port=8080 --server.address=0.0.0.0 --server.headless=true
