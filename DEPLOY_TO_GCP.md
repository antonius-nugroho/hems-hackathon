# Deploying the HEMS Dashboard to GCP Cloud Run

Run these on **your own machine** (this sandbox has no Docker/gcloud access).
Total time: ~15-20 min, most of it unattended build time.

---

## 0. Prerequisites (one-time, skip if already done)

```bash
# Install gcloud CLI if you don't have it
# macOS:
brew install --cask google-cloud-sdk
# Or download: https://cloud.google.com/sdk/docs/install

gcloud auth login
gcloud components install docker-credential-gcr  # if prompted
```

---

## 1. Create the project (~2 min)

```bash
# Pick a globally-unique project ID
export PROJECT_ID="hems-hackathon-$(date +%s | tail -c 6)"
gcloud projects create $PROJECT_ID --name="HEMS Hackathon"

gcloud config set project $PROJECT_ID
```

**If your hackathon gave you GCP credits/a existing project**, skip project creation
and just run:
```bash
gcloud config set project YOUR_GIVEN_PROJECT_ID
```

---

## 2. Link billing (required for Cloud Run/Build)

```bash
# List your billing accounts
gcloud billing accounts list

# Link one to the project
gcloud billing projects link $PROJECT_ID --billing-account=YOUR_BILLING_ACCOUNT_ID
```

If you have hackathon credits, they're usually auto-applied once billing is linked —
check your hackathon's instructions for a specific coupon/redemption step.

---

## 3. Enable required APIs (~2 min)

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com
```

If deployment fails with a storage/object access error, grant the project compute service account the needed roles:

```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
SERVICE_ACCOUNT="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/storage.objectViewer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/logging.logWriter"
```

---

## 4. Deploy (~8-12 min, mostly unattended)

From inside the `hems_dashboard/` folder (the one with `Dockerfile`, `app.py`, etc.):

```bash
cd hems_dashboard

gcloud run deploy hems-dashboard \
  --source . \
  --region asia-southeast2 \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300
```

Notes on the flags:
- `--source .` — lets Cloud Run build the container for you (no manual `docker build`/`docker push` needed)
- `region asia-southeast2` — Jakarta, lowest latency for an Indonesia demo
- `--memory 2Gi` — Prophet/Stan needs more than the 512Mi default, or the build or cold-start can OOM
- `--timeout 300` — gives Prophet model training room on first request (default 300s is usually fine, raise if you see timeout errors)
- `--allow-unauthenticated` — makes it a public URL, needed for a hackathon demo

When it finishes, it prints a **Service URL** — that's your live demo link.

---

## 5. Verify it works

```bash
# Just open the printed Service URL in a browser, or:
curl -I <SERVICE_URL>
```

Click through: select a few different households (EV/non-EV), confirm charts render
and recommendations appear.

---

## Known gotcha: first build is slow

The `Dockerfile` pre-installs `cmdstan` (Prophet's C++ backend) at **build time**
specifically so it doesn't try to compile it on every cold start (which would time
out). This makes the *build* take longer (~5-8 min) but keeps the *running app* fast.
Don't panic if `gcloud run deploy` looks stuck for several minutes on this step —
it's compiling Stan, not frozen.

---

## If you hit errors

| Symptom | Likely cause | Fix |
|---|---|---|
| `PERMISSION_DENIED` on deploy | Billing not linked | Redo step 2 |
| Build fails on cmdstan install | Build timeout | Add `--timeout=1200` to a `gcloud builds submit` if using that path instead |
| App loads but crashes on household select | Memory limit hit | Increase `--memory 4Gi` |
| "Service Unavailable" right after deploy | Cold start still initializing | Wait 30s, refresh |

---

## Cost note

Cloud Run only bills while handling requests (scales to zero when idle), so leaving
this deployed after the hackathon costs effectively nothing unless people actively
use it. Delete when done if you want to be tidy:

```bash
gcloud run services delete hems-dashboard --region asia-southeast2
```
