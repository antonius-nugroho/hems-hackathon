# Putting the HEMS Dashboard on GitHub

## 0. One thing to decide first: the CSV file (9.3 MB)

The synthetic data file is 9.3 MB. GitHub handles this fine (limit is 100 MB per
file on a normal repo), so **you can just commit it as-is** — no special setup
needed for a hackathon. Skip to step 1.

*(Only worry about Git LFS if your data grows past ~50 MB or you're on GitHub's
free tier with tight repo-size limits — not the case here.)*

---

## 1. Create the repo on GitHub

1. Go to https://github.com/new
2. Repository name: `hems-hackathon` (or whatever you like)
3. **Do NOT** check "Add a README" or "Add .gitignore" — you already have both
4. Set visibility (Public is fine for a hackathon demo; makes the Cloud Run
   source-deploy step simpler too)
5. Click **Create repository** — it'll show you a page with setup commands, but
   use the ones below instead (they match your existing folder).

---

## 2. Initialize git locally and push

Run these from inside your `hems_dashboard/` folder:

```bash
cd hems_dashboard

git init
git add .
git commit -m "Initial commit: HEMS Prophet forecasting dashboard"

# Replace with your actual GitHub username/repo
git remote add origin https://github.com/YOUR_USERNAME/hems-hackathon.git
git branch -M main
git push -u origin main
```

If prompted for credentials, GitHub no longer accepts passwords for git operations —
use a **Personal Access Token** instead:
- https://github.com/settings/tokens → "Generate new token (classic)" → check `repo` scope
- Paste the token as your password when git asks

Or simpler: use `gh auth login` if you have the [GitHub CLI](https://cli.github.com/)
installed, then `git push` will just work.

---

## 3. Verify

Go to `https://github.com/YOUR_USERNAME/hems-hackathon` — you should see all files:
`app.py`, `forecasting.py`, `Dockerfile`, `requirements.txt`, the CSV, and your docs.

---

## 4. Bonus: deploy straight from GitHub to Cloud Run

Once it's on GitHub, you can skip `--source .` and deploy directly from the repo,
which is nice for judges who want to see "this exact commit is what's running":

```bash
gcloud run deploy hems-dashboard \
  --source https://github.com/YOUR_USERNAME/hems-hackathon \
  --region asia-southeast2 \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi
```

Or set up **continuous deployment** (auto-redeploy on every push) via Cloud Run's
console: Cloud Run → your service → "Set up Continuous Deployment" → connect the
GitHub repo → pick branch `main`. This is genuinely nice for a hackathon since you
can push a fix mid-demo-prep and it redeploys automatically in ~5 min.

---

## 5. Making changes later

Normal git workflow from here:

```bash
# after editing app.py or forecasting.py
git add .
git commit -m "Add EV charge scheduler"
git push
```

If you set up continuous deployment in step 4, that's it — Cloud Run picks it up
automatically. Otherwise, redeploy manually with the same `gcloud run deploy`
command from `DEPLOY_TO_GCP.md`.

---

## Quick reference: what goes where

| File | Committed to GitHub? |
|---|---|
| `app.py`, `forecasting.py` | Yes |
| `requirements.txt`, `Dockerfile`, `.dockerignore` | Yes |
| `indonesian_household_data_with_ev_12months.csv` | Yes (fine at 9.3 MB) |
| `README.md`, `DEPLOY_TO_GCP.md` | Yes |
| Any GCP service account `.json` key | **No** — `.gitignore` blocks this |
| `.venv/` / `__pycache__/` | No — `.gitignore` blocks this |
