# Human-Sim: Multi-Agent Society Simulation

A distributed multi-agent simulation where humans live in simulated countries, interact with each other, and experience life events. Each human has stats (health, happiness, education, wealth) and makes decisions based on their state and environment.

## Project Structure

```
human-sim/
├── src/
│   ├── countries/          # Country simulation logic
│   ├── humans/             # Human agent class and behavior
│   └── brains/             # Decision-making brains for agents
├── tools/                  # Utility functions (name generation, gender assignment, etc.)
├── sims/                   # Simulation scripts and entry points
└── Dockerfile              # Container setup
```

## Getting Started

### Prerequisites
- Python 3.11+
- Docker (optional, for containerized runs)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/human-sim.git
   cd human-sim
   ```

2. (Optional) Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

### Running the Simulation

Run a simple country and human simulation:
```bash
python -m sims.simple_sim
```

## Architecture

### Core Classes

- **Human**: Individual agent with stats (health, happiness, education, wealth), a brain, and lifecycle methods
- **Country**: Simulated nation with various ratings (healthcare, education, economy, culture) and citizen management
- **Brain**: Decision-making component that humans use to think, remember, and decide actions
- **SimpleBrain**: Basic implementation of Brain with memory and thought tracking

### Key Features

- Random human/country generation
- Gender and name assignment
- Citizens can be added to countries
- Brain-based decision making
- Async life cycle simulation (WIP)

## Development

### Adding New Features

- Add new brain types to `src/brains/`
- Extend human behaviors in `src/humans/human_base.py`
- Add country mechanics to `src/countries/countries_base.py`

### Running Tests

(Tests to be added)

## Future Goals

- Multi-container deployment (one human per Docker container)
- Inter-human communication and networking
- Persistent state logging and visualization
- Scalable to thousands of agents
- Environmental interactions (resources, trade, conflict)

## License

MIT

## Contributing

Contributions welcome! Feel free to open issues and PRs.
