# Aegis Swarm

Aegis Swarm is a real-time, multi-agent cybersecurity simulation. The Red
attacker and Blue defender coordinate through graph stigmergy by reading and
mutating a live enterprise network topology stored in FalkorDB.

## Features

- **Red Probe:** Finds attack paths through the graph and compromises nodes.
- **Blue Sentinel:** Evaluates the topology and severs attack vectors.
- **Graph memory:** Stores tactical defense reasoning as incident reports.
- **Live console:** Displays the topology, event feed, metrics, and simulation
  controls in a React interface.

## Project Structure

```text
aegis-swarm/
├── backend/     FastAPI server, agents, graph logic, and tests
└── frontend/    React/Vite tactical console
```

## Tech Stack

- **Backend:** Python, FastAPI, asyncio, OpenAI SDK
- **Database:** FalkorDB
- **Frontend:** React, Vite, Tailwind CSS, Lucide React

## Prerequisites

Install the following before starting:

- [Git](https://git-scm.com/)
- [Python 3.11+](https://www.python.org/downloads/)
- [Node.js 18+](https://nodejs.org/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- An OpenAI API key for Blue Sentinel decisions

## 1. Clone the Repository

Run these commands in PowerShell:

```powershell
git clone https://github.com/Khush7Chauhan/aegis-swarm.git
Set-Location .\aegis-swarm
```

## 2. Start FalkorDB

Start FalkorDB in Docker:

```powershell
docker run --name aegis-falkordb -p 6379:6379 -d falkordb/falkordb:latest
```

If the container already exists, start it with:

```powershell
docker start aegis-falkordb
```

## 3. Set Up the Backend

Open a PowerShell terminal from the repository root:

```powershell
Set-Location .\backend
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create `backend\.env` and add your API key:

```dotenv
OPENAI_API_KEY=your-api-key-here
```

Start the FastAPI server:

```powershell
python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

The API is available at <http://localhost:8000>. Interactive API
documentation is available at <http://localhost:8000/docs>.

Keep this terminal running.

## 4. Set Up the Frontend

Open a second PowerShell terminal from the repository root:

```powershell
Set-Location .\aegis-swarm\frontend
npm install
npm run dev
```

Open the console at <http://localhost:5173>.

The frontend connects to `http://localhost:8000` by default. To use a
different backend URL, create `frontend\.env.local`:

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

## Usage

1. Open <http://localhost:5173>.
2. Use **Red Attack** to execute an attacker step.
3. Use **Blue Defense** to trigger a defender response.
4. Use **Engage Autonomous Swarm** to run the background simulation.
5. Enable **Show Agent Memory** to display incident reports on the graph.

## Troubleshooting

### PowerShell blocks virtual-environment activation

Run this once as your user:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### FalkorDB connection errors

Confirm that the container is running and port `6379` is available:

```powershell
docker ps
Test-NetConnection localhost -Port 6379
```

### Port 8000 or 5173 is already in use

Stop the process using the port, or start the service on another port. If the
backend port changes, update `VITE_API_BASE` in `frontend\.env.local`.

## Stopping the Services

Stop the frontend and backend with `Ctrl+C` in their terminals. Stop FalkorDB
with:

```powershell
docker stop aegis-falkordb
```
