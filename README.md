# Intelligent-DC-Fault-Discrimination-for-800VDC-AI-Data-Center-Power-Distribution
Physics-based digital twin and machine learning pipeline for intelligent DC fault discrimination in 800VDC AI data center. Built for Delta Cup 2026
**Delta Cup 2026 (Automation and Energy Track)**

This repository contains the physics-based digital twin and machine-learning methodology for solving the "nuisance trip" dilemma in 800 VDC AI data center power distribution. 

As rack power densities approach 1 MW, synchronized GPU workloads produce massive current transients (di/dt) that mimic catastrophic short circuits. Traditional threshold-based circuit breakers cannot easily distinguish between a legitimate AI workload and a true fault, risking multi-million-baht training interruptions.

### Repository Contents
*   `MODEL.md`: Versioned model specification and mathematical grounding (v0.1.1).
*   `model.py`: Numba-JIT accelerated RK4 physics simulator for the 800 VDC bus.
*   `/figures`: Publication-ready visualizations of the "gray zone" between benign load steps and high-impedance faults.
*   *(Coming Soon - Stage 2)*: Synthetic transient event dataset and lightweight ML classifier (CNN/Boosted Trees).
