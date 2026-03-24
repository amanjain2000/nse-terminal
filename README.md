# NSE Terminal — Phase 1

A professional stock analysis terminal for NSE-listed stocks. Built with FastAPI + React.

## What's in Phase 1

- Live NIFTY 50, SENSEX, NIFTY BANK, IT, Pharma indices in the top bar
- Search all 250+ NSE stocks by symbol or company name
- Full stock detail: price, change, OHLC, volume, market cap, P/E, P/B, EPS, ROE, ROA, debt/equity
- Interactive price chart with 1D / 1W / 1M / 3M / 1Y / 5Y views
- 52-week high/low range bar
- Company description and info
- Persistent watchlist (saved in browser)
- Sector performance heatmap (IT, Bank, Pharma, Auto, FMCG, Metal, Realty, Energy)

---

## Deployment (Zero Cost)

### Step 1 — Push to GitHub

1. Create a free account at github.com if you don't have one
2. Create a new repository (call it `nse-terminal`)
3. Upload this entire folder to it

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/nse-terminal.git
git push -u origin main
```

---

### Step 2 — Deploy Backend on Render (Free)

1. Go to **render.com** and sign up with GitHub
2. Click **New → Web Service**
3. Connect your `nse-terminal` repo
4. Set these settings:
   - **Name**: `nse-terminal-api`
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free
5. Click **Create Web Service**
6. Wait ~3 minutes for build. Your backend URL will be something like:
   `https://nse-terminal-api.onrender.com`

> **Note**: Free Render services sleep after 15 minutes of inactivity. First request after sleep takes ~30 seconds.
> Fix: Sign up at **uptimerobot.com** (free) and add a monitor pinging your `/health` endpoint every 10 minutes.

---

### Step 3 — Deploy Frontend on Vercel (Free)

1. Go to **vercel.com** and sign up with GitHub
2. Click **Add New → Project**
3. Import your `nse-terminal` repo
4. Set these settings:
   - **Framework Preset**: Vite
   - **Root Directory**: `frontend`
5. Under **Environment Variables**, add:
   - Key: `VITE_API_URL`
   - Value: `https://nse-terminal-api.onrender.com` (your Render URL from Step 2)
6. Click **Deploy**
7. Done! Your terminal will be live at `https://your-project.vercel.app`

---

## Running Locally (Development)

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`. Backend on `http://localhost:8000`.

The frontend defaults to `http://localhost:8000` when no `VITE_API_URL` is set.

---

## What's Coming in Phase 2+

- **Phase 2**: Fundamentals engine — earnings history, revenue growth, promoter holdings, FII/DII flows
- **Phase 3**: News ingestion + PESTEL scoring — auto-categorize RBI policy, regulations, market news
- **Phase 4**: Social sentiment — Reddit analysis (r/IndiaInvestments, r/Dalal_Street_Investments)
- **Phase 5**: AI synthesis engine — combine all signals into one structured analysis with a tip
- **Phase 6**: Alerts, prediction tracking, accuracy scoring

---

## Getting an Anthropic API Key (for Phase 5)

1. Go to **console.anthropic.com**
2. Sign up (free)
3. Go to **API Keys** → Create key
4. Cost: approximately ₹0.05 per full stock analysis
