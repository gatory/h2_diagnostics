Unitree H2 EDU Diagnostic Dashboard – Project Brief
1. Project Overview

I'm building a comprehensive diagnostic dashboard for the Unitree H2 EDU humanoid robot.

The goal is to develop a research/lab-oriented monitoring platform that provides:

Real-time robot telemetry.
Joint and motor diagnostics.
IMU and sensor monitoring.
Battery and power analytics.
System health monitoring.
Historical telemetry and experiment tracking.
Error logs and diagnostic alerts.

Project constraints:

Timeline: 1 month.
Purpose: Research and lab diagnostics.
Deployment: Network-based.
Backend host: Dedicated Ubuntu lab workstation.
Dashboard users: Single user initially.
Robot: One Unitree H2 EDU.

The initial application should be read-only. It should monitor the robot without issuing motor commands or interfering with its motion-control systems.

2. Proposed Architecture

Use a separate telemetry collector and lab workstation backend.

Data flow:

Unitree H2 EDU → Robot telemetry agent → Lab network → FastAPI backend → TimescaleDB → React dashboard.

Robot telemetry agent
Runs wherever the supported Unitree SDK/DDS interfaces are accessible.
Uses Unitree SDK2 and/or ROS 2.
Collects robot state.
Normalizes telemetry into a consistent internal schema.
Validates timestamps and data quality.
Sends telemetry to the lab workstation.
Lab workstation

Hosts:

FastAPI backend.
WebSocket server.
TimescaleDB database.
Diagnostics and alert processing.
Next.js frontend.
Dashboard

Accessible through a browser on the lab network.

Example: http://LAB_SERVER_IP:3000

The robot's DDS interfaces should not be exposed directly to dashboard clients. The telemetry agent should act as a bridge between robot communication and the application network.

3. Technology Stack
Layer	Technology
Robot communication	Unitree SDK2 / ROS 2
Robot telemetry agent	Python or C++
Backend	FastAPI
Live communication	WebSockets
Database	PostgreSQL + TimescaleDB
Frontend	Next.js + React + TypeScript
Charts	Apache ECharts
Styling	Tailwind CSS
Icons	Lucide
Deployment	Docker Compose
Reverse proxy	Nginx or Caddy (optional)
Testing	Pytest

Avoid unnecessary infrastructure initially. No Kubernetes, Kafka, or microservices for version one.

4. Official Resources

Start with these repositories and documentation:

Unitree SDK2: https://github.com/unitreerobotics/unitree_sdk2
Unitree SDK2 Python: https://github.com/unitreerobotics/unitree_sdk2_python
Unitree ROS 2: https://github.com/unitreerobotics/unitree_ros2
ROS 2 documentation: https://docs.ros.org/en/humble/
FastAPI: https://fastapi.tiangolo.com/
TimescaleDB: https://docs.timescale.com/
Docker: https://docs.docker.com/engine/install/ubuntu/
Apache ECharts: https://echarts.apache.org/

Important: Verify H2-specific SDK and ROS 2 compatibility against the actual robot firmware and official developer instructions. Do not assume all generic Unitree examples work on H2.

Potential telemetry sources to investigate:

rt/lowstate
rt/secondary_imu
H2 motor-state structures
Joint positions and velocities
Motor torque estimates
IMU orientation and angular velocity
Battery management information
Temperature and robot operating state

The H2 has 31 degrees of freedom, but verify which telemetry fields are actually exposed through the installed SDK.

If the Python SDK doesn't expose the necessary information, use a small C++ SDK subscriber and forward normalized telemetry to Python.

5. Telemetry Requirements
Joint diagnostics
Joint positions.
Joint velocities.
Estimated torque.
Motor temperatures, if exposed.
Target versus actual position, if both are available.
Tracking error.
IMU and sensors
Orientation.
Angular velocity.
Linear acceleration.
Sensor availability.
Update frequency.
Stale-data detection.
Power
Battery percentage.
Voltage.
Current.
Temperature.
Power consumption.
System health
Robot connection status.
SDK/DDS connection status.
Network latency.
Packet loss, if measurable.
CPU and memory usage.
Error and warning logs.

Suggested initial collection targets, subject to actual SDK publication rates:

Joint telemetry: 50–100 Hz where available.
IMU: 50–100 Hz where available.
Battery: 1–2 Hz.
Temperature: 1–2 Hz.
Dashboard rendering: approximately 5–20 Hz for high-frequency telemetry.

Do not unnecessarily stream every high-frequency sample to the browser.

6. Database Design

Use TimescaleDB for time-series telemetry and PostgreSQL for application data.

Suggested tables:

robots
experiment_sessions
joint_telemetry
imu_telemetry
power_telemetry
system_events
sensor_health

Introduce experiment sessions so research runs can be recorded, reviewed, compared, and exported.

Preserve both source timestamps and collector receive timestamps where available.

Support:

Experiment names.
Descriptions.
Start/end times.
Historical telemetry.
Experiment comparison.
CSV exports.
7. Backend API

Suggested REST endpoints:

GET /health
GET /api/robot/status
GET /api/robot/telemetry/latest
GET /api/robot/joints
GET /api/telemetry/joints
GET /api/telemetry/imu
GET /api/telemetry/power
GET /api/events
POST /api/sessions
PATCH /api/sessions/{id}
GET /api/sessions
GET /api/sessions/{id}

WebSocket:

WS /ws/telemetry

The backend should handle telemetry ingestion, normalization, persistence, health monitoring, and live broadcasting.

8. Frontend Pages

Build six primary sections:

System Overview
Connection status.
Battery status.
Active alerts.
Overall subsystem health.
Robot operating state.
Joint Diagnostics
Individual joint selection.
Position and velocity graphs.
Torque and temperature.
Target versus actual position.
Sensor Diagnostics
IMU readings.
Sensor availability.
Update rates.
Data freshness.
Power Diagnostics
Battery percentage.
Voltage and current.
Power consumption history.
Events and Logs
Warnings.
Errors.
Timestamped events.
Connection interruptions.
Experiment Management
Start and stop recording sessions.
Add experiment descriptions.
Review historical data.
Compare experiment sessions.
Export CSV files.
9. Repository Structure
text
h2-diagnostics/
├── robot-agent/
│   ├── src/
│   │   ├── main.py
│   │   ├── robot_interface.py
│   │   ├── telemetry.py
│   │   ├── normalizer.py
│   │   └── publisher.py
│   ├── config/
│   └── tests/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── websocket/
│   │   ├── services/
│   │   ├── diagnostics/
│   │   ├── models/
│   │   └── database/
│   └── tests/
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── features/
│   │   ├── overview/
│   │   ├── joints/
│   │   ├── sensors/
│   │   ├── power/
│   │   ├── events/
│   │   └── experiments/
│   └── lib/
│
├── database/
├── deployment/
│   └── docker-compose.yml
├── docs/
└── README.md

10. One-Month Development Timeline
Week 1: Robot integration
Install development environment.
Verify SDK and ROS 2 compatibility.
Connect to H2 telemetry.
Identify available state fields.
Build the Python/C++ collector.
Normalize telemetry.

Deliverable: Working robot telemetry collector.

Week 2: Backend and database
Build FastAPI.
Implement telemetry ingestion.
Set up TimescaleDB.
Implement WebSocket streaming.
Build experiment session functionality.

Deliverable: Live and historical telemetry accessible through the API.

Week 3: Frontend
Build Next.js dashboard.
Create overview page.
Implement joint diagnostics.
Implement power and sensor pages.
Add historical graphs.
Connect WebSocket updates.

Deliverable: Functional network-accessible dashboard.

Week 4: Diagnostics and testing
Implement health thresholds.
Add alerts and event logs.
Implement experiment comparison.
Test network interruptions.
Test stale telemetry.
Add CSV export.
Deploy and document.

Deliverable: Demonstrable research-oriented diagnostic MVP.

11. First Three Days: Immediate Tasks
Day 1: Environment and telemetry discovery
Install Ubuntu development dependencies.
Install Docker and Docker Compose.
Set up Python virtual environment.
Create Git repository.
Clone official Unitree SDK repositories.
Verify H2 compatibility.
Inspect H2-specific SDK examples.
Document available telemetry fields.

Deliverable: Documented telemetry availability.

Day 2: Build telemetry collector
Create robot-agent project structure.
Implement robot interface.
Subscribe to available motor and IMU state.
Normalize telemetry.
Add timestamps and validity checks.
Verify update frequency.
Test missing/stale data.

Deliverable: Collector producing structured telemetry from the actual robot.

Day 3: Backend integration
Start TimescaleDB.
Build FastAPI backend.
Implement telemetry ingestion endpoint.
Implement WebSocket broadcasting.
Connect collector to backend.
Verify messages from another computer if possible.

Deliverable: First end-to-end telemetry demonstration.

12. Deployment and Engineering Principles
Use a dedicated Ubuntu lab workstation.
Prefer wired Ethernet.
Keep the robot-side collector separate from the dashboard.
Keep the diagnostic integration read-only.
Avoid exposing DDS interfaces to browser clients.
Store high-frequency telemetry efficiently.
Track data freshness and validity.
Keep source and receive timestamps.
Use Docker Compose for the server.
Keep secrets out of Git.
Back up the database.
Add authentication and HTTPS before broader lab access.
13. Outstanding Architecture Question

One important decision still needs to be made:

Where will the robot telemetry collector run?

Options:

H2 onboard development computer.
Ubuntu lab workstation.
Separate computer connected to the robot.

Also establish whether physical access to the H2 EDU is currently available.

These two details determine the exact SDK installation, DDS configuration, networking, and collector implementation.

14. Overall Project Objective

The immediate goal is to deliver a working, polished diagnostic dashboard within one month.

Prioritize reliable telemetry collection, historical storage, real-time visualization, and experiment tracking.

Defer predictive maintenance, machine learning, multi-robot support, and elaborate 3D visualization to future development phases.

First milestone: Retrieve one actual H2 joint-state reading, send it over the lab network, and display it in a browser.