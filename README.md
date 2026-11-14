# Checkpoint – Cardiac Surgery Recovery Companion
Prototype for the Medtronic challenge. Python + Streamlit + SQLite.
**Not a medical device. Use synthetic/demo data only – never real patient info.**

## Run
    python -m venv .venv
    source .venv/bin/activate        # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=your_key   # optional; app works without it (FAQ fallback)
    streamlit run app.py

## Features
AI Recovery Assistant, Medication Management (pill counter, refills), Daily Check-in,
Early Risk Detection, Emergency Guidance, Wearable Monitoring (demo/CSV),
Care Team (calls, video visit, interpreter/ASL requests), Caregiver Support, Recovery Dashboard,
accessibility (large text, read aloud).
