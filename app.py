"""Checkpoint - AI recovery companion for cardiac surgery patients (prototype)."""
import os, json, random, sqlite3, datetime as dt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

DB = "checkpoint.db"
TODAY = dt.date.today().isoformat()
ZOOM_URL = os.getenv("ZOOM_URL", "https://zoom.us/")          # replace with clinic's link
CARE_TEAM = [("Cardiac Nurse Line", "+1-555-010-0101"),
             ("Surgeon's Office", "+1-555-010-0102"),
             ("After-hours Line", "+1-555-010-0103")]
EMERGENCY_TERMS = ["chest pain", "can't breathe", "cannot breathe", "fainted", "passed out",
                   "stroke", "face drooping", "slurred", "coughing blood", "severe bleeding"]

# ---------- database ----------
def run(sql, p=()):
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        cur = c.execute(sql, p)
        return [dict(r) for r in cur.fetchall()] if cur.description else []

def init_db():
    for s in [
        "CREATE TABLE IF NOT EXISTS meds(id INTEGER PRIMARY KEY, name TEXT, dose TEXT, times TEXT, pills_left INT)",
        "CREATE TABLE IF NOT EXISTS med_log(day TEXT, med_id INT, time TEXT, UNIQUE(day, med_id, time))",
        "CREATE TABLE IF NOT EXISTS checkins(day TEXT PRIMARY KEY, pain INT, temp REAL, weight REAL, mood TEXT,"
        " breathless INT, swelling INT, incision INT, chest INT, faint INT, notes TEXT, level TEXT, reasons TEXT)",
        "CREATE TABLE IF NOT EXISTS vitals(ts TEXT, hr INT, spo2 INT, sys INT, dia INT, steps INT)",
        "CREATE TABLE IF NOT EXISTS messages(ts TEXT, sender TEXT, text TEXT)",
        "CREATE TABLE IF NOT EXISTS appts(day TEXT, time TEXT, what TEXT)",
        "CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT)",
    ]:
        run(s)

def setting(k, default=""):
    r = run("SELECT v FROM settings WHERE k=?", (k,))
    return r[0]["v"] if r else default

def set_setting(k, v):
    run("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, str(v)))

# ---------- risk detection (rule-based on purpose: predictable + explainable) ----------
def assess(c, latest_vitals=None, prev_weight=None):
    emergency, call = [], []
    if c["chest"]: emergency.append("Chest pain/pressure")
    if c["faint"]: emergency.append("Fainting or near-fainting")
    if c["breathless"] >= 8: emergency.append("Severe shortness of breath")
    if c["temp"] >= 100.4: call.append(f"Fever {c['temp']}°F")
    if c["pain"] >= 7: call.append(f"High pain ({c['pain']}/10)")
    if 5 <= c["breathless"] < 8: call.append("Increasing shortness of breath")
    if c["swelling"]: call.append("New leg/ankle swelling")
    if c["incision"]: call.append("Incision redness, drainage or opening")
    if prev_weight and c["weight"] - prev_weight >= 3: call.append("Weight up 3+ lb since last check-in")
    if latest_vitals:
        if latest_vitals["spo2"] < 92: call.append(f"Low oxygen ({latest_vitals['spo2']}%)")
        if latest_vitals["hr"] > 120 or latest_vitals["hr"] < 45: call.append(f"Heart rate {latest_vitals['hr']} bpm")
    level = "emergency" if emergency else "call" if call else "ok"
    return level, emergency + call

# ---------- helpers ----------
def speak(text):
    components.html(f"<button style='font-size:16px' onclick='speechSynthesis.speak("
                    f"new SpeechSynthesisUtterance({json.dumps(text)}))'>🔊 Read aloud</button>", height=45)

def emergency_banner():
    st.error("🚨 **Call 911 now.** Do not drive yourself. Sit down, stay calm, unlock your door, "
             "and tell the dispatcher you recently had heart surgery.")

def call_buttons():
    for name, num in CARE_TEAM:
        st.link_button(f"📞 {name}: {num}", f"tel:{num}")

# ---------- AI assistant ----------
SYSTEM = ("You are Checkpoint, a supportive recovery assistant for adults after cardiac surgery. "
          "Give clear, plain-language (6th-grade) guidance on recovery, activity, wound care, diet and meds. "
          "Never diagnose or change medication doses. For chest pain, trouble breathing, fainting, stroke signs "
          "tell them to call 911. For fever, wound changes, rapid weight gain or worsening symptoms tell them to "
          "call their care team. Keep answers under 150 words. Reply in the user's language.")
FAQ = {"shower": "Most patients may shower briefly once cleared. Pat the incision dry; no baths or soaking until your surgeon says so.",
       "lift": "Avoid lifting more than 5-10 lb and pushing/pulling with your arms until your surgeon clears you.",
       "walk": "Short, frequent walks are great. Increase slowly, stop if you feel dizzy, short of breath or have chest pain.",
       "drive": "Do not drive until your surgeon clears you, usually 4-6 weeks after open-chest surgery.",
       "sleep": "Sleep with extra pillows for support. Hug a small pillow when you cough."}

def ai_reply(history):
    last = history[-1]["content"].lower()
    if any(t in last for t in EMERGENCY_TERMS):
        return "🚨 This could be an emergency. **Call 911 now.** Tell them you recently had heart surgery."
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            r = anthropic.Anthropic().messages.create(
                model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"), max_tokens=500,
                system=SYSTEM, messages=history[-12:])
            return r.content[0].text
        except Exception as e:
            st.warning(f"AI unavailable, using basic answers ({type(e).__name__}).")
    for k, v in FAQ.items():
        if k in last: return v
    return "I can help with showering, lifting, walking, driving, sleep and more. For anything urgent, call your care team."

# ---------- pages ----------
def page_dashboard():
    st.header("🏠 Recovery Dashboard")
    ci = run("SELECT * FROM checkins ORDER BY day DESC LIMIT 1")
    if ci and ci[0]["level"] == "emergency": emergency_banner()
    st.subheader("Today's to-do")
    todo = []
    for m in run("SELECT * FROM meds"):
        for t in m["times"].split(","):
            if not run("SELECT 1 FROM med_log WHERE day=? AND med_id=? AND time=?", (TODAY, m["id"], t)):
                todo.append(f"💊 {m['name']} {m['dose']} at {t}")
        if m["pills_left"] <= 7: todo.append(f"🔁 Refill {m['name']} ({m['pills_left']} pills left)")
    if not run("SELECT 1 FROM checkins WHERE day=?", (TODAY,)): todo.append("📝 Complete today's check-in")
    for a in run("SELECT * FROM appts WHERE day>=? ORDER BY day, time LIMIT 3", (TODAY,)):
        todo.append(f"📅 {a['what']} on {a['day']} {a['time']}")
    for t in todo or ["✅ All done for today!"]: st.write(t)
    if ci: st.info(f"Last check-in status: **{ci[0]['level'].upper()}** {ci[0]['reasons'] or ''}")
    hist = pd.DataFrame(run("SELECT day, pain, weight, temp FROM checkins ORDER BY day"))
    if len(hist) > 1:
        st.subheader("Trends"); st.line_chart(hist.set_index("day"))
    v = pd.DataFrame(run("SELECT ts, hr, spo2, steps FROM vitals ORDER BY ts"))
    if len(v): st.line_chart(v.set_index("ts")[["hr", "spo2"]])

def page_checkin():
    st.header("📝 Daily Health Check-in")
    prev = run("SELECT weight FROM checkins WHERE day<? ORDER BY day DESC LIMIT 1", (TODAY,))
    with st.form("ci"):
        pain = st.slider("Pain level", 0, 10, 2)
        breathless = st.slider("Shortness of breath", 0, 10, 0)
        temp = st.number_input("Temperature (°F)", 95.0, 106.0, 98.6, 0.1)
        weight = st.number_input("Weight (lb)", 60.0, 500.0, prev and 180.0 or 180.0, 0.1)
        mood = st.select_slider("Mood", ["😞", "😕", "😐", "🙂", "😀"], "🙂")
        chest = st.checkbox("Chest pain or pressure")
        faint = st.checkbox("Fainted or felt like I might faint")
        swelling = st.checkbox("New swelling in legs/ankles")
        incision = st.checkbox("Incision red, leaking or opening")
        notes = st.text_area("Anything else?")
        go = st.form_submit_button("Submit")
    if go:
        c = dict(pain=pain, breathless=breathless, temp=temp, weight=weight, chest=int(chest),
                 faint=int(faint), swelling=int(swelling), incision=int(incision))
        vit = run("SELECT * FROM vitals ORDER BY ts DESC LIMIT 1")
        level, reasons = assess(c, vit[0] if vit else None, prev[0]["weight"] if prev else None)
        if any(t in notes.lower() for t in EMERGENCY_TERMS): level, reasons = "emergency", reasons + ["Emergency words in notes"]
        run("INSERT OR REPLACE INTO checkins VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (TODAY, pain, temp, weight, mood, breathless, int(swelling), int(incision), int(chest), int(faint),
             notes, level, "; ".join(reasons)))
        if level == "emergency": emergency_banner()
        elif level == "call":
            st.warning("⚠️ Please call your care team today:"); call_buttons()
            run("INSERT INTO messages VALUES(?,?,?)", (dt.datetime.now().isoformat(timespec="minutes"),
                "Checkpoint (auto-alert)", "Check-in flagged: " + "; ".join(reasons)))
        else: st.success("✅ Looking good. See you tomorrow!")
        if reasons: st.write("**Why:** " + "; ".join(reasons))

def page_meds():
    st.header("💊 Medications")
    meds = run("SELECT * FROM meds")
    for m in meds:
        st.subheader(f"{m['name']} {m['dose']}")
        cols = st.columns(len(m["times"].split(",")) + 1)
        for col, t in zip(cols, m["times"].split(",")):
            done = run("SELECT 1 FROM med_log WHERE day=? AND med_id=? AND time=?", (TODAY, m["id"], t))
            if done: col.success(f"✔ {t}")
            elif col.button(f"Take {t}", key=f"{m['id']}{t}"):
                run("INSERT OR IGNORE INTO med_log VALUES(?,?,?)", (TODAY, m["id"], t))
                run("UPDATE meds SET pills_left=pills_left-1 WHERE id=?", (m["id"],)); st.rerun()
        cols[-1].metric("Pills left", m["pills_left"])
        if m["pills_left"] <= 7: st.warning("Time to refill – call your pharmacy.")
    with st.expander("➕ Add medication"):
        with st.form("addmed"):
            n = st.text_input("Name"); d = st.text_input("Dose (e.g. 81 mg)")
            t = st.text_input("Times, comma separated (24h)", "08:00,20:00"); p = st.number_input("Pills in bottle", 1, 500, 30)
            if st.form_submit_button("Add") and n:
                run("INSERT INTO meds(name,dose,times,pills_left) VALUES(?,?,?,?)", (n, d, t.replace(" ", ""), p)); st.rerun()

def page_assistant():
    st.header("🤖 AI Recovery Assistant (24/7)")
    st.caption("General guidance only. Not a substitute for your care team.")
    st.session_state.setdefault("chat", [])
    for m in st.session_state.chat:
        st.chat_message(m["role"]).write(m["content"])
    if q := st.chat_input("Ask about your recovery…"):
        st.session_state.chat.append({"role": "user", "content": q})
        st.session_state.chat.append({"role": "assistant", "content": ai_reply(st.session_state.chat)})
        st.rerun()
    if st.session_state.chat and st.session_state.chat[-1]["role"] == "assistant":
        speak(st.session_state.chat[-1]["content"])

def page_monitor():
    st.header("⌚ Remote Patient Monitoring")
    st.caption("Demo mode. Real devices: Fitbit/Garmin/Withings via their cloud APIs; Apple Watch needs a "
               "native iOS HealthKit companion app that uploads to your backend.")
    c1, c2 = st.columns(2)
    if c1.button("Simulate wearable sync"):
        now = dt.datetime.now()
        for i in range(24):
            ts = (now - dt.timedelta(hours=23 - i)).isoformat(timespec="minutes")
            run("INSERT INTO vitals VALUES(?,?,?,?,?,?)", (ts, random.randint(62, 95), random.randint(94, 99),
                random.randint(108, 135), random.randint(65, 85), random.randint(0, 600)))
    f = c2.file_uploader("Or upload CSV (ts,hr,spo2,sys,dia,steps)", type="csv")
    if f:
        for r in pd.read_csv(f).itertuples(index=False):
            run("INSERT INTO vitals VALUES(?,?,?,?,?,?)", tuple(r)[:6]); 
        st.success("Imported")
    v = pd.DataFrame(run("SELECT * FROM vitals ORDER BY ts"))
    if len(v):
        last = v.iloc[-1]
        a, b, c = st.columns(3)
        a.metric("Heart rate", f"{last.hr} bpm"); b.metric("SpO₂", f"{last.spo2}%"); c.metric("BP", f"{last.sys}/{last.dia}")
        if last.spo2 < 92 or last.hr > 120 or last.hr < 45: st.warning("Reading outside safe range – call your care team."); call_buttons()
        st.line_chart(v.set_index("ts")[["hr", "spo2", "sys", "dia"]])
        st.subheader("Compare health trends")
        st.line_chart(v.set_index("ts")[["steps"]])

def page_team():
    st.header("🩺 Care Team")
    call_buttons()
    st.link_button("🎥 Join video visit (Zoom)", ZOOM_URL)
    st.subheader("Accessibility / interpreter request")
    with st.form("interp"):
        lang = st.selectbox("Language", ["Spanish", "Mandarin", "Arabic", "Vietnamese", "American Sign Language (ASL)", "Other"])
        d = st.date_input("Visit date"); t = st.time_input("Visit time")
        if st.form_submit_button("Request interpreter"):
            run("INSERT INTO appts VALUES(?,?,?)", (str(d), t.strftime("%H:%M"), f"Visit w/ {lang} interpreter"))
            run("INSERT INTO messages VALUES(?,?,?)", (dt.datetime.now().isoformat(timespec="minutes"), "Patient",
                f"Interpreter requested: {lang} on {d} {t}")); st.success("Request sent")
    st.subheader("Messages")
    with st.form("msg", clear_on_submit=True):
        m = st.text_area("Message your care team")
        if st.form_submit_button("Send") and m:
            run("INSERT INTO messages VALUES(?,?,?)", (dt.datetime.now().isoformat(timespec="minutes"), "Patient", m))
    for r in run("SELECT * FROM messages ORDER BY ts DESC LIMIT 15"): st.write(f"`{r['ts']}` **{r['sender']}:** {r['text']}")

def page_caregiver():
    st.header("👪 Caregiver Support")
    st.write("Choose what your caregiver can see, then share the access code.")
    code = setting("code") or str(random.randint(100000, 999999)); set_setting("code", code)
    for k, label in [("share_meds", "Medications"), ("share_checkins", "Check-ins & status"), ("share_vitals", "Wearable vitals")]:
        set_setting(k, int(st.toggle(label, setting(k, "1") == "1")))
    st.info(f"Caregiver access code: **{code}**")
    st.divider(); st.subheader("Caregiver view")
    if st.text_input("Enter code", type="password") == code:
        st.success("Access granted (read-only)")
        if setting("share_checkins", "1") == "1":
            for r in run("SELECT day, level, reasons FROM checkins ORDER BY day DESC LIMIT 7"): st.write(r)
        if setting("share_meds", "1") == "1":
            for m in run("SELECT name, dose, pills_left FROM meds"): st.write(m)
        if setting("share_vitals", "1") == "1":
            st.write(run("SELECT * FROM vitals ORDER BY ts DESC LIMIT 1"))
        st.markdown("**How to help:** encourage short walks, help with meds and appointments, watch for confusion, "
                    "fever, wound changes, or breathlessness – and call the care team if you see them.")

def page_emergency():
    st.header("🚨 Emergency Guidance")
    st.error("**Call 911 immediately for:** chest pain/pressure, severe trouble breathing, fainting, "
             "stroke signs (face drooping, arm weakness, slurred speech), coughing blood, heavy bleeding.")
    st.warning("**Call your care team today for:** fever ≥ 100.4°F, incision redness/drainage, weight gain ≥ 3 lb, "
               "new leg swelling, pain ≥ 7/10, heart racing or very slow.")
    call_buttons()
    st.subheader("What to do while waiting")
    st.write("1. Stop activity and sit upright.\n2. Unlock the door.\n3. Have your medication list ready.\n"
             "4. Tell responders you had heart surgery and the date.")

# ---------- main ----------
st.set_page_config(page_title="Checkpoint", page_icon="❤️", layout="wide")
init_db()
if not run("SELECT 1 FROM meds"):
    run("INSERT INTO meds(name,dose,times,pills_left) VALUES('Aspirin','81 mg','08:00',30)")
    run("INSERT INTO meds(name,dose,times,pills_left) VALUES('Metoprolol','25 mg','08:00,20:00',6)")
st.sidebar.title("❤️ Checkpoint")
if st.sidebar.toggle("Large text"):
    st.markdown("<style>html,body,[class*='css']{font-size:22px}</style>", unsafe_allow_html=True)
PAGES = {"Dashboard": page_dashboard, "Daily Check-in": page_checkin, "Medications": page_meds,
         "AI Assistant": page_assistant, "Monitoring": page_monitor, "Care Team": page_team,
         "Caregiver": page_caregiver, "Emergency": page_emergency}
PAGES[st.sidebar.radio("Go to", list(PAGES))]()
st.sidebar.divider()
st.sidebar.error("🚨 Emergency? Call 911")
st.sidebar.caption("Prototype – not medical advice. Demo data only.")
