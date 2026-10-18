# Aegis Swarm

Aegis Swarm is a tactical network-defense console with:

- A React/Vite frontend for the live topology, event feed, and controls.
- A FastAPI backend for the Red and Blue agents.
- FalkorDB for the graph database.

## Prerequisites

Install the following before starting:

- [Git](https://git-scm.com/)
- [Python 3.11+](https://www.python.org/downloads/)
- [Node.js 18+](https://nodejs.org/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) for FalkorDB

## 1. Clone the Repository

Run these commands in PowerShell:

```powershell
git clone https://github.com/Khush7Chauhan/aegis-swarm.git
Set-Location .\aegis-swarm
```

## 2. Start FalkorDB

Start the graph database in Docker:

```powershell
docker run --name aegis-falkordb -p 6379:6379 -d falkordb/falkordb:latest
```

If the container already exists, start it with:

```powershell
docker start aegis-falkordb
```

## 3. Set Up the Backend

Create and activate a Python virtual environment:

```powershell
Set-Location .\backend
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks script execution, run this once in PowerShell as your
user:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Start the FastAPI server:

```powershell
python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

The API is available at <http://localhost:8000>. Open
<http://localhost:8000/docs> to view the interactive API documentation.

Keep this terminal running.

## 4. Set Up the Frontend

Open a second PowerShell terminal from the repository root:

```powershell
Set-Location .\aegis-swarm\frontend
npm install
npm run dev
```

Open the frontend at <http://localhost:5173>.

The frontend uses `http://localhost:8000` as the default backend URL. To use a
different backend URL, create `frontend\.env.local` with:

```dotenv
VITE_API_BASE=http://localhost:8000
```

## Common Commands

Run these commands from `frontend\`:

```powershell
# Start the development server
npm run dev

# Run the linter
npm run lint

# Create a production build
npm run build

# Preview the production build
npm run preview
```

Run these commands from `backend\`:

```powershell
# Start the API with hot reload
python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000

# Re-seed the baseline graph
python seeder.py

# Run backend tests, when pytest is installed
python -m pytest tests
```

## Stopping the Services

Stop the frontend and backend with `Ctrl+C` in their terminals. Stop
FalkorDB with:

```powershell
docker stop aegis-falkordb
```

## Troubleshooting

### Port 6379 is already in use

Check whether another FalkorDB or Redis container is running:

```powershell
docker ps
```

### Port 8000 or 5173 is already in use

Stop the process using the port, or start the service on a different port.
If the backend port changes, update `VITE_API_BASE` in
`frontend\.env.local`.

### FalkorDB connection errors

Confirm that the database container is running and that port `6379` is
published:

```powershell
docker ps
Test-NetConnection localhost -Port 6379
```
