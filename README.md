# DLMP ABM Stochastic Scenario Lab

> **Distribution-Level Marginal Pricing (DLMP) via Agent-Based Modeling (ABM)**  
> A multi-agent stochastic simulation platform for distribution network economics using AC Optimal Power Flow (OPF).

---

## Overview

This project implements a **multi-agent stochastic scenario simulation** platform to analyze **Distribution-Level Marginal Prices (DLMPs)** on the IEEE 33-bus test network (`case33bw`). Each bus in the distribution network is represented by an autonomous agent that submits bids to a central Market Operator, which clears the market via AC OPF using [PandaPower](https://pandapower.org/) and the IPOPT solver.

The web interface mimics the layout of the original MATLAB App Designer prototype but runs entirely on a **Python / FastAPI / Vanilla JS** stack.

---

## Architecture

```
abm-dlmp/
│
├── agents/                    # Autonomous agent classes
│   ├── __init__.py
│   ├── base_agent.py          # Abstract base class for all agents
│   ├── load_agent.py          # Passive consumer bus
│   ├── der_agent.py           # Distributed Energy Resource (generator)
│   ├── prosumer_agent.py      # Prosumer (generates and consumes)
│   └── market_operator.py     # Market Operator / AC OPF coordinator
│
├── services/                  # Business logic layer
│   ├── __init__.py
│   ├── backend.py             # FastAPI HTTP routes (controller)
│   ├── simulation.py          # Core stochastic simulation loop
│   ├── state.py               # Global in-memory state
│   ├── excel_exporter.py      # Excel results export
│   ├── matlab_runner.py       # MATLAB scenario generator bridge
│   ├── plot_builder.py        # Chart data builders
│   ├── regressions.py         # OLS econometric regressions
│   └── validation.py          # RUNPF scenario validation
│
├── utils/
│   └── data_io.py             # Config load / template generation
│
├── static/                    # Front-end (HTML, CSS, JS)
│   ├── index.html
│   ├── style.css
│   └── script.js
│
├── app.py                     # Legacy Streamlit interface (optional)
├── requirements.txt
├── Dockerfile
└── run.bat                    # Windows launcher (FastAPI + uvicorn)
```

---

## Agent Roles

| Role | Description |
|------|-------------|
| **Slack / Grid** | Bus 1 — External grid reference; provides slack power at a quadratic cost |
| **PQ Load** | Passive consumer; submits demand bids based on base case load |
| **DER** | Distributed energy resource; submits generation offers with cost curve |
| **Prosumer** | Hybrid agent; both generates and consumes; net billing policy |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Front-end | HTML5, Vanilla CSS, Vanilla JS |
| Back-end | Python 3.10+, FastAPI, Uvicorn |
| Power System | PandaPower ≥ 2.14, IPOPT solver |
| Scenario Generation | Python RNG *or* MATLAB (optional bridge) |
| Data Export | OpenPyXL (Excel), Pandas |
| Regression Analysis | Statsmodels (OLS) |

---

## Quick Start

### Prerequisites

- Python 3.10+
- (Optional) MATLAB with Optimization Toolbox — for MATLAB-based scenario generation

### 1. Clone the repository

```bash
git clone https://github.com/Erdemhan/Agent-Based-Distributed-Local-Marginal-Pricing.git
cd Agent-Based-Distributed-Local-Marginal-Pricing
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
```

### 3. Install dependencies

> **Windows kullanıcıları bu adımı atlayabilir.**  
> `run.bat` ilk çalıştırmada otomatik olarak bir sanal ortam oluşturur ve `requirements.txt` bağımlılıklarını yükler.

```bash
pip install -r requirements.txt
```

### 4. Run the application

**Windows (recommended):**
```bat
run.bat
```

**Manual (any OS):**
```bash
uvicorn services.backend:app --host localhost --port 8501 --reload
```

Then open your browser at [http://localhost:8501](http://localhost:8501).

---

## Docker

```bash
docker build -t abm-dlmp .
docker run -p 8501:8501 abm-dlmp
```

> **Note:** The Dockerfile uses the Streamlit entry point (`app.py`). To run the FastAPI version inside Docker, update the `ENTRYPOINT` in `Dockerfile` to:
> ```dockerfile
> ENTRYPOINT ["uvicorn", "services.backend:app", "--host", "0.0.0.0", "--port", "8501"]
> ```

---

## Simulation Workflow

```
1. Configure bus roles        (Topology tab in UI)
2. Set simulation parameters  (season, time-of-day, scenario count, PDFs, ...)
3. Generate stochastic scenarios  (Python RNG or MATLAB)
4. Per scenario:
   a. Each agent submits an offer to the Market Operator
   b. Market Operator runs AC OPF (PandaPower + IPOPT)
   c. DLMPs and dispatch results are settled back to agents
5. Aggregate results → Excel export, OLS regressions, interactive charts
```

---

## Key Parameters

| Parameter | Description |
|-----------|-------------|
| `season` | Winter / Summer — affects demand multiplier |
| `case_time` | Night / Morning / Noon / Evening — affects DER generation capacity |
| `scenario_count` | Number of Monte Carlo scenarios |
| `global_load_scale_pdf` | Distribution for global load scaling (Uniform, Normal, ...) |
| `offer_pdf` | Distribution for agent cost coefficient sampling |
| `prosumer_policy` | Net billing strategy for prosumer agents |
| `run_validation` | Run RUNPF validation after each scenario |

---

## Results

Simulation results are exported as a multi-sheet Excel file containing:

| Sheet | Contents |
|-------|----------|
| `scenario_summary` | Per-scenario aggregate metrics (cost, load, losses) |
| `bus_results_long` | Bus voltage, DLMP, and dispatch per bus per scenario |
| `branch_results_long` | Line loading and power flow per branch |
| `gen_results_long` | Generator dispatch results |
| `runpf_validation` | Convergence and constraint validation |
| `bus_role_config` | Bus role configuration used in the simulation |

---

## Contributing

This project is part of the **TÜBİTAK 1001 DLMP Research Project** at Erciyes University.  
For contributions or questions, please open an issue.

---

## License

This project is for academic research purposes. All rights reserved.
