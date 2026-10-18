Aegis Swarm: Autonomous Cyber-Warfare on FalkorDB
Built for the WeMakeDevs Graph Hacks (Track 2: Agent Memory & Coordination).

Aegis Swarm is a real-time, multi-agent cybersecurity simulation where AI agents do not communicate via text. Instead, they coordinate entirely through Graph Stigmergy—reading and mutating a live enterprise network topology on FalkorDB.

🧠 Core Architecture
The Red Probe (Attacker): Uses mathematical openCypher shortest-path algorithms to hunt down vulnerabilities and mutate network nodes to COMPROMISED.

The Blue Sentinel (Defender): A GPT-4o-mini agent wrapped in a ReAct framework. It evaluates egress edges and downstream centrality to sever attack vectors, isolating the blast radius (QUARANTINED).

Episodic Graph Memory: The Blue agent writes its tactical defense reasoning directly back into FalkorDB as permanent IncidentReport nodes, allowing it to query its own past memory for future defense maneuvers.

🛠 Tech Stack
Database: FalkorDB (Local Docker Container)

Backend: FastAPI, Python, asyncio, OpenAI SDK (GPT-4o-mini)

Frontend: React, Vite, Tailwind CSS (Norrvik Brutalist UI)

🚀 Setup & Installation
Prerequisites
Docker (to run FalkorDB locally)

Python 3.10+ (for the FastAPI backend)

Node.js 18+ & npm (for the React frontend)

OpenAI API Key (for the Blue Sentinel agent)

1. Start FalkorDB
The easiest way to run FalkorDB is via Docker. Open a new terminal and run:

Bash
docker run -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest
The database will now be accessible locally on port 6379.

2. Configure the Backend
Open a new terminal and navigate to the backend directory.

Bash
cd backend

# Create and activate a virtual environment (Windows)
python -m venv venv
venv\Scripts\activate

# Create and activate a virtual environment (Mac/Linux)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
Create a .env file in the root of the backend folder and add your OpenAI key:

Code snippet
OPENAI_API_KEY="your-api-key-here"
Start the FastAPI server:

Bash
uvicorn server:app --reload
The backend will run on http://localhost:8000.

3. Configure the Frontend
Open a new terminal and navigate to the frontend directory.

Bash
cd frontend

# Install dependencies
npm install

# Start the Vite development server
npm run dev
The frontend will run on http://localhost:5173.

🕹 Usage Instructions
Open http://localhost:5173 in your browser.

The initial graph state will load from FalkorDB automatically.

Step Red Attack: Click to execute a single openCypher traversal. Watch the graph mutate as a node is compromised.

Engage Blue Defense: Click to trigger the ReAct loop. Blue will evaluate the topology, sever the egress edge, and write a purple IncidentReport memory node to the database.

Engage Autonomous Swarm: Starts an asyncio background loop on the server. Agents will autonomously attack and defend the network in real-time until all routes to the database are severed.

Show Agent Memory: Toggle this to visualize the AI's forensic reasoning nodes directly on the graph canvas. Clicking an IncidentReport node will display the exact timestamp and ReAct logic in the sidebar.
