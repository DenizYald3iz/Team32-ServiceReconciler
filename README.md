<div align="center">

# 🚀 Team32 Service Reconciler

### *Perfect System* (Tron UI) + Secure Failover Monitor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)
[![Node.js](https://img.shields.io/badge/Node.js-Express-339933.svg)](https://nodejs.org/)

**A comprehensive teaching and demonstration project showcasing Kubernetes-style orchestration and intelligent failover mechanisms**

[Features](#-features) • [Quick Start](#-quick-start) • [Architecture](#-architecture) • [Documentation](#-documentation) • [License](#-license)

</div>

---

## 📋 Table of Contents

- [🎯 Overview](#-overview)
- [✨ Features](#-features)
- [🏗️ Architecture](#️-architecture)
- [🚀 Quick Start](#-quick-start)
  - [Perfect System (Docker)](#perfect-system-docker)
  - [Secure Failover Monitor (Python/FastAPI)](#secure-failover-monitor-pythonfastapi)
- [📖 Documentation](#-documentation)
  - [Using the Perfect System API](#using-the-perfect-system-api)
  - [Service YAML Format](#service-yaml-format)
- [🔒 Security](#-security)
- [🧪 Testing](#-testing)
- [📁 Project Structure](#-project-structure)
- [🔧 Troubleshooting](#-troubleshooting)
- [📄 License](#-license)

---

## 🎯 Overview

**Team32 Service Reconciler** is a teaching and demonstration project that illustrates two powerful concepts in modern cloud-native systems:

### 1️⃣ Desired-State Orchestration (Kubernetes-Style)
Declare your desired system state (replicas, rollout strategies, health probes, autoscaling) using YAML configuration, and watch as the Controller automatically reconciles the simulated cluster to match your specifications.

### 2️⃣ Intelligent Failover Monitoring
A secure FastAPI-based monitoring dashboard that:
- Performs continuous health checks
- Logs all audit actions
- Supports chaos engineering toggles
- Automatically fails over between v1 → v2 → v3 service versions

> 💡 **Note**: This is a **simulation** - no real Kubernetes cluster required! Perfect for learning, teaching, and demonstrations.

---

## ✨ Features

### 🎮 Perfect System (Node/Express + Docker Compose)

<table>
<tr>
<td width="50%">

**Core Features**
- 🎨 **Tron UI Dashboard** with live SSE updates
- 📝 **YAML-based Service Specs** (`POST /apply`)
- 🔄 **Pod Lifecycle Management** (create/terminate)
- ❤️ **Health Probes** (readiness & liveness)
- 📊 **Autoscaling** based on simulated CPU
- 🔀 **Load Balancer** (round-robin selection)

</td>
<td width="50%">

**Advanced Features**
- 🚀 **Rollout Strategies**
  - Blue/Green deployments
  - Canary releases (step-based)
- 💥 **Chaos Engineering** (kill pods)
- 📈 **Prometheus Metrics** endpoint
- 📧 **Email Alerts** (optional)
- 🔌 **Proxy Support** (`/proxy/*`)

</td>
</tr>
</table>

### 🛡️ Secure Failover Monitor (Python/FastAPI)

- 🔐 **Password-Protected Dashboard** (HTTP Basic Auth)
- 📋 **Comprehensive Audit Logging** (SQLite)
- 📊 **Health Monitoring** with latency tracking
- ⚡ **Chaos Toggles**
  - CPU load simulation (100% load)
  - Data corruption injection
  - System crash simulation
- 🔄 **Smart Failover Logic**
  - Automatic version switching (v1/v2/v3)
  - Configurable cooldown periods
  - Failure threshold detection
- 📧 **Email Notifications** (Gmail SMTP)

---

## 🏗️ Architecture

### Perfect System (Docker)

```
┌─────────────────┐     YAML Spec      ┌─────────────────┐
│   Tron UI       │  ─────────────────► │   API Server    │  (Express)
│   Dashboard     │   SSE: /events      │   Port: 8080    │
│   (Web Client)  │   GET: /state       │                 │
└─────────────────┘                     └────────┬────────┘
                                                 │
                                                 │ state.json
                                                 │ (shared volume)
                                                 ▼
                                        ┌─────────────────┐
                                        │   Controller    │  Reconcile Loop
                                        │   Port: 8090    │  + Metrics
                                        │                 │  + Email Alerts
                                        └────────┬────────┘
                                                 │
                                                 │ Pod Management
                                                 ▼
                                        ┌─────────────────┐
                                        │   Agent         │  Pod Simulation
                                        │   Port: 8070    │  Runtime Engine
                                        └─────────────────┘
```

### Secure Failover Monitor (FastAPI)

```
┌─────────────────────────────────────────────────────────┐
│                   Monitor Dashboard                      │
│                   (main.py - Port 8000)                  │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Health Check │  │ Audit Logger │  │ Chaos Engine │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└────────┬──────────────────┬──────────────────┬──────────┘
         │                  │                  │
         ▼                  ▼                  ▼
    ┌─────────┐        ┌──────────┐      ┌─────────┐
    │ Service │        │ SQLite   │      │ Docker  │
    │ v1/v2/v3│        │ Database │      │ Client  │
    │ :8001-3 │        │monitor.db│      │   API   │
    └─────────┘        └──────────┘      └─────────┘
```

---

## 🚀 Quick Start

### Perfect System (Docker)

#### Prerequisites
- ✅ Docker Desktop or Docker Engine
- ✅ Docker Compose

#### Installation & Run

```bash
# Clone the repository
git clone https://github.com/DenizYald3iz/Team32-ServiceReconciler.git
cd Team32-ServiceReconciler

# Start all services
docker compose up --build
```

#### Access Points

| Service | URL | Description |
|---------|-----|-------------|
| 🎨 **Tron UI** | http://localhost:8080 | Interactive dashboard |
| 📚 **API Docs** | http://localhost:8080/docs | Swagger documentation |
| 📊 **Cluster State** | http://localhost:8080/state | JSON state view |
| 📈 **Metrics** | http://localhost:8080/metrics | Prometheus metrics |

#### Stop Services

```bash
docker compose down
```

---

### Secure Failover Monitor (Python/FastAPI)

#### Prerequisites
- ✅ Python 3.10 or higher

#### Installation

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements-dev.txt
```

#### Run Demo Services

Open **three separate terminals** and run:

```bash
# Terminal 1 - Service v1
uvicorn services.v1.app:app --port 8001

# Terminal 2 - Service v2
uvicorn services.v2.app:app --port 8002

# Terminal 3 - Service v3
uvicorn services.v3.app:app --port 8003
```

#### Run Monitor Dashboard

```bash
# Terminal 4 - Main Dashboard
uvicorn main:app --port 8000
```

#### Access Dashboard

🌐 **URL**: http://localhost:8000

🔐 **Credentials**:
- **Username**: `admin`
- **Password**: `secure123`

#### Optional: Email Notifications

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and configure:
# MAIL_USER=your-email@gmail.com
# MAIL_PASS=your-app-password
# MAIL_RECEIVER=recipient@example.com
```

> 💡 **Gmail Users**: Enable 2FA and generate an [App Password](https://support.google.com/accounts/answer/185833)

---

## 📖 Documentation

### Using the Perfect System API

#### 1️⃣ Apply a Service YAML

Deploy a service configuration:

```bash
curl -X POST http://localhost:8080/apply \
  -H "Content-Type: application/yaml" \
  --data-binary @examples/api-v1.yaml
```

#### 2️⃣ Chaos Engineering: Kill Pods

```bash
curl -X POST "http://localhost:8080/chaos/kill?service=api&count=2"
```

#### 3️⃣ Simulate CPU Load (Autoscaling)

```bash
curl -X POST "http://localhost:8080/load?service=api&cpu=80"
```

#### 4️⃣ Manual Scaling

```bash
# Scale up (+1 replica)
curl -X POST "http://localhost:8080/scale?service=api&delta=1"

# Scale down (-1 replica)
curl -X POST "http://localhost:8080/scale?service=api&delta=-1"
```

#### 5️⃣ Load Balancer Selection

```bash
curl "http://localhost:8080/lb/select?service=api"
```

---

### Service YAML Format

#### Minimal Configuration

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  replicas: 3
  image: local://demo@v1
```

#### Complete Configuration Options

| Field | Type | Description |
|-------|------|-------------|
| `spec.replicas` | `integer` | Number of pod replicas |
| `spec.image` | `string` | Image reference (e.g., `local://demo@v1`) |
| `spec.env` | `array` | Environment variables `[{name, value}]` |
| `spec.readinessProbe.httpGet.path` | `string` | Readiness probe endpoint |
| `spec.livenessProbe.httpGet.path` | `string` | Liveness probe endpoint |
| `spec.autoscale.targetCPU` | `integer` | CPU threshold for autoscaling |
| `spec.autoscale.min` | `integer` | Minimum replicas |
| `spec.autoscale.max` | `integer` | Maximum replicas |
| `spec.rollout.strategy` | `string` | `BlueGreen` or `Canary` |
| `spec.rollout.steps` | `array` | Canary rollout steps |

#### Example Configurations

📁 **Available in `examples/` directory**:
- `api-v1.yaml` - Basic deployment
- `api-v2.yaml` - Version 2 deployment
- `api-canary.yaml` - Canary rollout example

---

## 🔒 Security

This project demonstrates **secure coding best practices**:

### 🛡️ Security Features

| Feature | Implementation | Purpose |
|---------|---------------|---------|
| **API Key Protection** | Optional `X-API-Key` header | Protect Perfect System endpoints |
| **HTTP Basic Auth** | `secrets.compare_digest()` | Constant-time password comparison |
| **Audit Logging** | SQLite database | Track security-relevant actions |
| **Environment Variables** | `.env` file | Secure credential management |

### ⚠️ Security Limitations (By Design)

> **⚠️ IMPORTANT**: This is a **teaching/demo project**

- ❌ Hard-coded credentials (for classroom simplicity)
- ❌ Not production-ready
- ❌ Simplified Kubernetes semantics
- ✅ Use for learning and demonstrations only

---

## 🧪 Testing

### Run Tests

```bash
# Quick test run
pytest -q

# With coverage report
pytest --cov --cov-report=term-missing

# Verbose output
pytest -v
```

### Test Coverage

#### `tests/test_main_py.py`
- ✅ HTTP Basic Auth enforcement
- ✅ Audit log database writes
- ✅ Health check functionality (mocked requests)

#### `tests/test_services.py`
- ✅ v1/v2 CPU simulation
- ✅ v1/v2 data corruption & recovery
- ✅ v3 stability testing
- ✅ Reset endpoint functionality

#### `tests/conftest.py`
- ✅ Docker module stub (no daemon required for tests)

---

## 📁 Project Structure

```
Team32-ServiceReconciler/
│
├── 🐳 docker-compose.yml          # Docker orchestration
├── 📝 README.md                   # This file
├── 📄 LICENSE.txt                 # MIT License
├── ⚙️  .env.example                # Environment template
├── 🚫 .gitignore                  # Git ignore rules
│
├── 📦 requirements.txt            # Python dependencies
├── 📦 requirements-dev.txt        # Dev dependencies
├── 🧪 pytest.ini                  # Pytest configuration
│
├── 🐍 main.py                     # FastAPI Monitor Dashboard
│
├── 📂 examples/                   # YAML configuration examples
│   ├── api-v1.yaml
│   ├── api-v2.yaml
│   └── api-canary.yaml
│
├── 📂 services/
│   ├── 🌐 api/                    # Express API + Tron UI
│   │   ├── server.js
│   │   ├── package.json
│   │   └── public/
│   │
│   ├── 🎛️  controller/            # Reconciliation Engine
│   │   ├── controller.js
│   │   ├── package.json
│   │   └── Dockerfile
│   │
│   ├── 🤖 agent/                  # Pod Simulation Runtime
│   │   ├── agent.js
│   │   ├── package.json
│   │   └── Dockerfile
│   │
│   ├── 📌 v1/                     # Demo Service v1
│   │   ├── app.py
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   ├── 📌 v2/                     # Demo Service v2
│   │   └── ...
│   │
│   └── 📌 v3/                     # Demo Service v3
│       └── ...
│
└── 📂 tests/                      # Test Suite
    ├── conftest.py
    ├── test_main_py.py
    └── test_services.py
```

---

## 🔧 Troubleshooting

### ❓ UI loads but nothing changes

**Solution:**
```bash
# Check if all services are running
docker compose ps

# View logs
docker compose logs -f --tail=200
```

---

### ❓ API returns 401 Unauthorized

**Cause**: API key protection is enabled

**Solution:**
```bash
# Include X-API-Key header
curl -H "X-API-Key: changeme" http://localhost:8080/state
```

---

### ❓ Email notifications not working

**Possible causes:**
- ❌ Missing SMTP credentials
- ❌ Incorrect Gmail App Password
- ❌ 2FA not enabled on Gmail

**Solution:**
1. Enable 2FA on your Gmail account
2. Generate an [App Password](https://support.google.com/accounts/answer/185833)
3. Update `.env` file with correct credentials

---

### ❓ Port already in use

**Perfect System Ports:**
- `8080` - API Server
- `8090` - Controller
- `8070` - Agent

**FastAPI Demo Ports:**
- `8000` - Monitor Dashboard
- `8001` - Service v1
- `8002` - Service v2
- `8003` - Service v3

**Solution:**
```bash
# Check what's using the port (macOS/Linux)
lsof -i :8080

# Kill the process
kill -9 <PID>
```

---

## 📄 License

This project is licensed under the **MIT License** - see the [`LICENSE.txt`](LICENSE.txt) file for details.

```
MIT License

Copyright (c) 2024 Team32

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files...
```

---

<div align="center">

### 🌟 Star this repository if you find it helpful!

**Made with ❤️ by Team32**

[Report Bug](https://github.com/DenizYald3iz/Team32-ServiceReconciler/issues) • [Request Feature](https://github.com/DenizYald3iz/Team32-ServiceReconciler/issues)

</div>
