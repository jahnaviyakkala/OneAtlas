# Setup & Installation Guide

This guide covers detailed setup instructions for running OneAtlas locally.

## Prerequisites

- **Python 3.12+** (check with `python --version`)
- **Node.js 18+** (for frontend)
- **Git**
- **uv** (Python package manager) - Install with `pip install uv`

## Backend Setup (FastAPI / CrewAI)

### 1. Clone the Repository

```bash
git clone https://github.com/jahnaviyakkala/OneAtlas.git
cd oneatlas
```

### 2. Install Python Dependencies

```bash
uv sync
```

This will:
- Create a virtual environment at `.venv/`
- Install all 150+ dependencies
- Build the local package

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
GROQ_API_KEY=your_groq_key_here
GOOGLE_API_KEY=your_google_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
```

**How to get API keys:**
- **Groq**: https://console.groq.com/keys
- **Google Gemini**: https://makersuite.google.com/app/apikey
- **OpenRouter**: https://openrouter.ai/keys

### 4. Run the Backend

```bash
uv run uvicorn compiler.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend will be available at: http://localhost:8000

**API Documentation**: http://localhost:8000/docs

## Frontend Setup (React / Vite)

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Configure Frontend Environment (Optional)

```bash
cp .env.local.example .env.local
```

Edit if you need custom API endpoint or other frontend config.

### 3. Run Development Server

```bash
npm run dev
```

Frontend will be available at: http://localhost:5173

## Docker Setup (Optional)

### Build Docker Image

```bash
docker build -t oneatlas:latest .
```

### Run Container

```bash
docker run -p 8000:8000 \
  -e GROQ_API_KEY=$GROQ_API_KEY \
  -e GOOGLE_API_KEY=$GOOGLE_API_KEY \
  oneatlas:latest
```

## Verifying Installation

### Backend Check

```bash
curl http://localhost:8000/health
# Should respond with: {"status": "healthy"}
```

### Frontend Check

Open http://localhost:5173 in your browser. You should see the OneAtlas UI.

### Full Integration Test

1. Go to http://localhost:5173
2. Enter a natural language app description
3. Click "Generate AppSpec"
4. Wait for the pipeline to complete (~3-5 minutes)

## Troubleshooting

### Issue: `uv command not found`

**Solution**: Install uv globally
```bash
pip install --user uv
# Add ~/.local/bin to your PATH if needed
```

### Issue: `GROQ_API_KEY not found`

**Solution**: Ensure `.env` file exists and contains your API key
```bash
cat .env | grep GROQ_API_KEY
```

### Issue: Port 8000 already in use

**Solution**: Run on a different port
```bash
uv run uvicorn compiler.main:app --port 8001
```

### Issue: Frontend can't connect to backend

**Solution**: Check CORS configuration in `compiler/main.py` and update `.env.local`

## Development Workflow

### Running Tests

```bash
uv run pytest
```

### Code Formatting

```bash
uv run black src/
```

### Type Checking

```bash
uv run mypy src/
```

### Linting

```bash
uv run pylint src/
```

## Performance Tips

- Use **Groq** for fastest responses (recommended)
- Groq falls back to Gemini on rate-limiting
- Keep `.venv/` and `node_modules/` in `.gitignore`
- Monitor API usage to avoid unexpected costs

## Next Steps

- Read [README.md](./README.md) for feature overview
- Check [ARCHITECTURE.md](./ARCHITECTURE.md) for system design
- See [CONTRIBUTING.md](./CONTRIBUTING.md) to contribute

---

**Need help?** Open an issue on GitHub or check the documentation above.
