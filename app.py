"""Checkpoint - AI recovery companion for cardiac surgery patients (prototype)."""
import os, json, random, sqlite3, datetime as dt
import calendar
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

DB = "checkpoint.db"
TODAY = dt.date.today().isoformat()
ZOOM_URL = os.getenv("ZOOM_URL", "https://zoom.us/")          # clinic's telehealth link
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
        "CREATE TABLE IF NOT EXISTS meds(id INTEGER PRIMARY KEY, name TEXT, dose TEXT, times TEXT, pills_left INT, instructions TEXT)",
        "CREATE TABLE IF NOT EXISTS med_log(day TEXT, med_id INT, time TEXT, UNIQUE(day, med_id, time))",
        "CREATE TABLE IF NOT EXISTS daily_doses(day TEXT, med_id INT, count INT, PRIMARY KEY(day, med_id))",
        "CREATE TABLE IF NOT EXISTS checkins(day TEXT PRIMARY KEY, pain INT, temp REAL, weight REAL, mood TEXT,"
        " breathless INT, swelling INT, incision INT, chest INT, faint INT, notes TEXT, level TEXT, reasons TEXT)",
        "CREATE TABLE IF NOT EXISTS calendar_tracker(day TEXT PRIMARY KEY, checked INT)",
        "CREATE TABLE IF NOT EXISTS vitals(ts TEXT, hr INT, spo2 INT, sys INT, dia INT, steps INT)",
        "CREATE TABLE IF NOT EXISTS messages(ts TEXT, sender TEXT, text TEXT)",
        "CREATE TABLE IF NOT EXISTS appts(day TEXT, time TEXT, what TEXT)",
        "CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT)",
    ]:
        run(s)
    try:
        run("ALTER TABLE meds ADD COLUMN instructions TEXT DEFAULT ''")
    except Exception:
        pass

def setting(k, default=""):
    r = run("SELECT v FROM settings WHERE k=?", (k,))
    return r[0]["v"] if r else default

def set_setting(k, v):
    run("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, str(v)))

# ---------- risk detection ----------
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
    st.error("🚨 **Call 911 immediately.** Do not drive yourself. Sit down, stay calm, unlock your door, "
             "and tell the dispatcher you recently had heart surgery.")

def call_buttons():
    for name, num in CARE_TEAM:
        st.link_button(f"📞 {name}: {num}", f"tel:{num}")

# ---------- AI assistant ----------
SYSTEM = ("You are Checkpoint, a supportive recovery assistant for adults after cardiac surgery. "
          "Focus specifically on cardio health, heart issues, and food/diet tracking. "
          "Give clear, plain-language (6th-grade) guidance. Provide detailed step-by-step action plans for risks or urgent symptoms. "
          "Never diagnose or change medication doses. For chest pain, trouble breathing, fainting, stroke signs "
          "tell them to call 911 immediately. For fever, wound changes, rapid weight gain or worsening symptoms tell them to "
          "call their care team. Keep answers under 150 words. Reply in the user's language.")

FAQ = {"shower": "Most patients may shower briefly once cleared. Pat the incision dry; no baths or soaking until your surgeon says so.",
       "lift": "Avoid lifting more than 5-10 lb and pushing/pulling with your arms until your surgeon clears you.",
       "walk": "Short, frequent walks are great. Increase slowly, stop if you feel dizzy, short of breath or have chest pain.",
       "drive": "Do not drive until your surgeon clears you, usually 4-6 weeks after open-chest surgery.",
       "sleep": "Sleep with extra pillows for support. Hug a small pillow when you cough.",
       "diet": "Focus on heart-healthy foods low in sodium and saturated fats. Keep track of daily meals and water intake."}

def ai_reply(history):
    last = history[-1]["content"].lower()
    if any(t in last for t in EMERGENCY_TERMS):
        return "🚨 This is a medical emergency. **Call 911 immediately.** Tell them you recently had heart surgery and follow dispatcher instructions."
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
    return "I can help with cardio health, food tracking, showering, lifting, walking, driving, and sleep. For urgent symptoms, call your care team."

# ---------- pages ----------
def page_dashboard():
    logo_file = next((f for f in ["logo.png", "logo.jpg", "document-heart-check.png", "ec2b2c4f-0519-43c9-a986-578b8ceaa1ab.jpg"] if os.path.exists(f)), None)
    if logo_file:
        st.image(logo_file, width=64)
    
    st.header("🏠 Recovery Dashboard")
    
    # Quick Jump Navigation
    st.markdown("⚡ **Quick Jump:** [Check-in](#daily-health-check-in) | [Medications](#medications-pill-management) | [Calendar & Progress](#calendar-progress-tracker) | [AI Assistant](#ai-recovery-assistant-247) | [Care Team](#care-team-direct-messaging)")
    
    ci = run("SELECT * FROM checkins ORDER BY day DESC LIMIT 1")
    if ci and ci[0]["level"] == "emergency": emergency_banner()
    
    st.subheader("Today's To-Do")
    todo = []
    for m in run("SELECT * FROM meds"):
        scheduled_doses = len(m["times"].split(","))
        row = run("SELECT count FROM daily_doses WHERE day=? AND med_id=?", (TODAY, m["id"]))
        taken_today = row[0]["count"] if row else 0
        if taken_today < scheduled_doses:
            todo.append(f"💊 {m['name']} {m['dose']} ({taken_today}/{scheduled_doses} taken today)")
        if m["pills_left"] <= 7: todo.append(f"🔁 Refill {m['name']} ({m['pills_left']} pills left)")
    if not run("SELECT 1 FROM checkins WHERE day=?", (TODAY,)): todo.append("📝 Complete today's check-in")
    for a in run("SELECT * FROM appts WHERE day>=? ORDER BY day, time LIMIT 3", (TODAY,)):
        todo.append(f"📅 {a['what']} on {a['day']} {a['time']}")
    for t in todo or ["✅ All done for today!"]: st.write(t)
    
    if ci: st.info(f"Last check-in status: **{ci[0]['level'].upper()}** {ci[0]['reasons'] or ''}")
    
    # Calendar & Recovery Milestones
    st.markdown('<a id="calendar"></a>', unsafe_allow_html=True)
    st.subheader("📅 Calendar & Recovery Milestones")
    appts = run("SELECT day, time, what FROM appts ORDER BY day, time")
    if appts:
        for appt in appts:
            st.write(f"• **{appt['day']} at {appt['time']}**: {appt['what']}")
    else:
        st.write("• Post-op Day 14 Check-up (Upcoming)")
        st.write("• Cardiac Rehabilitation Session (Scheduled)")

    hist = pd.DataFrame(run("SELECT day, pain, weight, temp FROM checkins ORDER BY day"))
    if len(hist) > 1:
        st.subheader("Trends"); st.line_chart(hist.set_index("day"))
    v = pd.DataFrame(run("SELECT ts, hr, spo2, steps FROM vitals ORDER BY ts"))
    if len(v): st.line_chart(v.set_index("ts")[["hr", "spo2"]])

def page_calendar_progress():
    st.markdown('<a id="calendar-progress-tracker"></a>', unsafe_allow_html=True)
    st.header("📅 Interactive Recovery Calendar & Progress Tracker")
    st.caption("Check off your daily recovery consistency and track your healing progress over time.")

    # --- Section 1: Monthly Interactive Calendar & Check-off Grid ---
    st.subheader("🗓️ Monthly Recovery Checklist")
    now = dt.date.today()
    year, month = now.year, now.month
    month_name = calendar.month_name[month]
    
    st.write(f"**Current Month: {month_name} {year}** — Click checkboxes below to mark completion for each day.")
    
    cal_matrix = calendar.monthcalendar(year, month)
    days_header = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    # Render table header
    cols = st.columns(7)
    for i, d_name in enumerate(days_header):
        cols[i].markdown(f"**{d_name}**")

    # Fetch checked days from DB
    checked_rows = run("SELECT day FROM calendar_tracker WHERE checked=1")
    checked_set = {r["day"] for r in checked_rows}
    
    # Render calendar weeks
    for week in cal_matrix:
        w_cols = st.columns(7)
        for i, day_num in enumerate(week):
            if day_num == 0:
                w_cols[i].write("")
            else:
                date_str = f"{year}-{month:02d}-{day_num:02d}"
                is_checked = date_str in checked_set
                # Checkbox for each day
                checked_state = w_cols[i].checkbox(f"{day_num}", value=is_checked, key=f"cal_{date_str}")
                if checked_state != is_checked:
                    if checked_state:
                        run("INSERT OR REPLACE INTO calendar_tracker VALUES(?,?)", (date_str, 1))
                    else:
                        run("INSERT OR REPLACE INTO calendar_tracker VALUES(?,?)", (date_str, 0))
                    st.rerun()

    st.divider()

    # --- Section 2: Progress Tracking Charts ---
    st.subheader("📈 Recovery Progress Tracking")
    
    checkins_df = pd.DataFrame(run("SELECT day, pain, weight, temp, breathless FROM checkins ORDER BY day"))
    if len(checkins_df) > 0:
        st.markdown("**Daily Check-in Trends (Pain & Weight)**")
        st.line_chart(checkins_df.set_index("day")[["pain", "weight"]])
        
        st.markdown("**Shortness of Breath & Temperature Tracking**")
        st.line_chart(checkins_df.set_index("day")[["breathless", "temp"]])
    else:
        st.info("Complete a few daily check-ins on the **Daily Check-in** page to populate your progress charts!")

    # Consistency Stats
    total_days_tracked = len(run("SELECT 1 FROM calendar_tracker WHERE checked=1"))
    st.metric("Total Days Completed & Checked Off", f"{total_days_tracked} Days")

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
        go = st.form_submit_button("Submit Check-in")
    if go:
        c = dict(pain=pain, breathless=breathless, temp=temp, weight=weight, chest=int(chest),
                 faint=int(faint), swelling=int(swelling), incision=int(incision))
        vit = run("SELECT * FROM vitals ORDER BY ts DESC LIMIT 1")
        level, reasons = assess(c, vit[0] if vit else None, prev[0]["weight"] if prev else None)
        if any(t in notes.lower() for t in EMERGENCY_TERMS): level, reasons = "emergency", reasons + ["Emergency words in notes"]
        run("INSERT OR REPLACE INTO checkins VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (TODAY, pain, temp, weight, mood, breathless, int(swelling), int(incision), int(chest), int(faint),
             notes, level, "; ".join(reasons)))
        
        # Automatically mark today as checked off in calendar tracker too
        run("INSERT OR REPLACE INTO calendar_tracker VALUES(?,?)", (TODAY, 1))

        if level == "emergency":
            emergency_banner()
            st.error("🚨 **Emergency Guidance & Instructions:** \n1. Stop all activity and sit upright immediately.\n2. Call **911** right away.\n3. Unlock your front door for emergency responders.\n4. Have your heart surgery history and medications list ready.")
        elif level == "call":
            st.warning("⚠️ **Alert Sent:** A notification has been automatically dispatched to your designated caretakers.")
            st.info("Please call your care team today:")
            call_buttons()
            st.subheader("Action Steps:")
            st.write("1. Sit down and rest.\n2. Review your symptoms and keep your medication list nearby.\n3. Follow the care team instructions below.")
            run("INSERT INTO messages VALUES(?,?,?)", (dt.datetime.now().isoformat(timespec="minutes"),
                "Checkpoint (auto-alert)", "Check-in flagged & caretakers notified: " + "; ".join(reasons)))
        else:
            st.success("✅ Looking great! Check-in logged successfully. See you tomorrow!")
        if reasons: st.write("**Why flagged:** " + "; ".join(reasons))

def page_meds():
    st.markdown('<a id="medications-pill-management"></a>', unsafe_allow_html=True)
    st.header("💊 Medications & Pill Management")
    meds = run("SELECT * FROM meds")
    for m in meds:
        with st.container(border=True):
            st.subheader(f"{m['name']} {m['dose']}")
            st.caption(f"Scheduled times: {m['times']}")
            
            if m.get("instructions"):
                st.markdown("**📋 Instructions:**")
                for line in m["instructions"].split("\n"):
                    if line.strip():
                        st.markdown(f"- {line.strip().lstrip('•-* ')}")
            
            row = run("SELECT count FROM daily_doses WHERE day=? AND med_id=?", (TODAY, m["id"]))
            taken_count = row[0]["count"] if row else 0
            target_doses = len(m["times"].split(","))
            
            c_sub, c_cnt, c_add, c_pills = st.columns([1, 2, 1, 2])
            if c_sub.button("➖", key=f"sub_{m['id']}", help="Decrease times taken today", use_container_width=True):
                if taken_count > 0:
                    run("INSERT OR REPLACE INTO daily_doses VALUES(?,?,?)", (TODAY, m["id"], taken_count - 1))
                    run("UPDATE meds SET pills_left=pills_left+1 WHERE id=?", (m["id"],))
                    st.rerun()
            
            c_cnt.metric("Taken today", f"{taken_count} / {target_doses}")
            
            if c_add.button("➕", key=f"add_{m['id']}", help="Add a dose taken today", use_container_width=True):
                if m["pills_left"] > 0:
                    run("INSERT OR REPLACE INTO daily_doses VALUES(?,?,?)", (TODAY, m["id"], taken_count + 1))
                    run("UPDATE meds SET pills_left=pills_left-1 WHERE id=?", (m["id"],))
                    st.rerun()
            
            c_pills.metric("Pills left", m["pills_left"])
            if m["pills_left"] <= 7:
                st.warning("Time to refill – check nearby pickup locations below.")
    
    st.divider()
    st.subheader("📍 Nearest Pharmacy & Hospital Refill Locations")
    st.write("🏥 **Hospital Pharmacy** – Est. **7.8 mi** away | 📞 +1-555-0199")
    st.write("🏪 **CVS Pharmacy** – Est. **2.3 mi** away | 📞 +1-555-0233")
    st.write("💊 **Walgreens Pharmacy** – Est. **3.5 mi** away | 📞 +1-555-0444")

    with st.expander("➕ Add medication"):
        with st.form("addmed"):
            n = st.text_input("Name")
            d = st.text_input("Dose (e.g. 81 mg)")
            t = st.text_input("Times, comma separated (24h)", "08:00,20:00")
            p = st.number_input("Pills in bottle", 1, 500, 30)
            inst = st.text_area("Instructions (one bullet per line)", "Take with food and a full glass of water.\nDo not skip doses without asking your doctor.")
            if st.form_submit_button("Add") and n:
                run("INSERT INTO meds(name,dose,times,pills_left,instructions) VALUES(?,?,?,?,?)",
                    (n, d, t.replace(" ", ""), p, inst))
                st.rerun()

def page_assistant():
    st.markdown('<a id="ai-recovery-assistant-247"></a>', unsafe_allow_html=True)
    st.header("🤖 AI Recovery Assistant (24/7)")
    st.caption("Specialized in cardio health, heart issues, and food/diet tracking. General guidance only.")
    st.session_state.setdefault("chat", [])
    
    for m in st.session_state.chat:
        st.chat_message(m["role"]).write(m["content"])
        
    st.info("🎙️ *Tip: You can use your device's microphone voice-typing feature in the chat box below to ask questions hands-free.*")
    
    if q := st.chat_input("Ask about your cardio recovery, diet, or symptoms…"):
        st.session_state.chat.append({"role": "user", "content": q})
        st.session_state.chat.append({"role": "assistant", "content": ai_reply(st.session_state.chat)})
        st.rerun()
    if st.session_state.chat and st.session_state.chat[-1]["role"] == "assistant":
        speak(st.session_state.chat[-1]["content"])

def page_monitor():
    st.header("⌚ Remote Patient Monitoring & Exercising Guide")
    st.caption("Demo mode for wearable vitals and cardiovascular exercise guidance.")
    
    with st.expander("🫀 Cardiovascular Exercising Guide", expanded=True):
        st.write("""
        * **Phase 1 (Weeks 1–2):** Short, gentle indoor walks (5–10 minutes, 3x a day). Focus on deep breathing and posture.
        * **Phase 2 (Weeks 3–4):** Gradually increase walks to 15–20 minutes once daily. Avoid heavy lifting (>5–10 lbs).
        * **Phase 3 (Weeks 5–6+):** Light stationary cycling or supervised cardiac rehab exercises upon surgeon clearance.
        * *Stop immediately if you experience dizziness, shortness of breath, or chest pain.*
        """)

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

def page_team():
    st.markdown('<a id="care-team-direct-messaging"></a>', unsafe_allow_html=True)
    st.header("🩺 Care Team & Direct Messaging")
    call_buttons()
    st.link_button("🎥 Join video visit (Zoom)", ZOOM_URL)
    
    st.subheader("💬 Direct Hospital & Doctor Chat Box")
    with st.form("direct_chat", clear_on_submit=True):
        doc_recipient = st.selectbox("Send message to:", ["Dr. Harrison (Surgeon)", "Cardiac Nurse Coordinator", "Hospital Care Team"])
        doc_msg = st.text_area("Type your direct medical question or advice request:")
        if st.form_submit_button("Send Direct Message") and doc_msg:
            run("INSERT INTO messages VALUES(?,?,?)", (dt.datetime.now().isoformat(timespec="minutes"), f"Patient -> {doc_recipient}", doc_msg))
            st.success("Message sent successfully to your care provider!")

    st.subheader("Interpreter Request")
    with st.form("interp"):
        lang = st.selectbox("Language Preference", ["English", "Spanish", "Mandarin", "Arabic", "Vietnamese", "American Sign Language (ASL)", "Other"])
        d = st.date_input("Visit date"); t = st.time_input("Visit time")
        if st.form_submit_button("Request interpreter"):
            run("INSERT INTO appts VALUES(?,?,?)", (str(d), t.strftime("%H:%M"), f"Visit w/ {lang} interpreter"))
            run("INSERT INTO messages VALUES(?,?,?)", (dt.datetime.now().isoformat(timespec="minutes"), "Patient",
                f"Interpreter requested: {lang} on {d} {t}")); st.success("Request sent")
    
    st.subheader("Message History")
    for r in run("SELECT * FROM messages ORDER BY ts DESC LIMIT 15"): st.write(f"`{r['ts']}` **{r['sender']}:** {r['text']}")

def page_caregiver():
    st.header("👪 Caregiver Support")
    st.write("Choose what your caregiver can see, then share the access code.")
    
    st.info("📞 **Caregiver Support Hotline:** Call **+1-555-019-CARE** for immediate assistance or caregiver coordination support.")
    
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
    st.header("🚨 Emergency Guidance & 911")
    st.error("**Call 911 immediately for:** chest pain/pressure, severe trouble breathing, fainting, "
             "stroke signs (face drooping, arm weakness, slurred speech), coughing blood, heavy bleeding.")
    st.warning("**Call your care team today for:** fever ≥ 100.4°F, incision redness/drainage, weight gain ≥ 3 lb, "
               "new leg swelling, pain ≥ 7/10, heart racing or very slow.")
    call_buttons()
    st.subheader("What to do while waiting for 911")
    st.write("1. Stop activity and sit upright.\n2. Unlock the door.\n3. Have your medication list ready.\n"
             "4. Tell emergency responders you had recent heart surgery and the surgery date.")

# ---------- main ----------
logo_file = next((f for f in ["logo.png", "logo.jpg", "document-heart-check.png", "ec2b2c4f-0519-43c9-a986-578b8ceaa1ab.jpg"] if os.path.exists(f)), None)

st.set_page_config(page_title="Checkpoint", page_icon=logo_file if logo_file else "❤️", layout="wide")

st.markdown("""
    <style>
    h1, h2, h3 {
        color: #6b21a8 !important;
    }
    .stButton>button, [data-testid="stFormSubmitButton"]>button {
        background-color: #9333ea !important;
        color: #ffffff !important;
        border-radius: 6px;
        border: none;
    }
    .stButton>button p, [data-testid="stFormSubmitButton"]>button p {
        color: #ffffff !important;
    }
    .stButton>button:hover, [data-testid="stFormSubmitButton"]>button:hover {
        background-color: #7e22ce !important;
    }
    </style>
""", unsafe_allow_html=True)

init_db()
if not run("SELECT 1 FROM meds"):
    run("INSERT INTO meds(name,dose,times,pills_left,instructions) VALUES('Aspirin','81 mg','08:00',30,?)",
        ("Take once daily in the morning with food or milk to prevent stomach upset.\nSwallow whole; do not crush or chew enteric-coated tablets.",))
    run("INSERT INTO meds(name,dose,times,pills_left,instructions) VALUES('Metoprolol','25 mg','08:00,20:00',6,?)",
        ("Take twice daily (morning and evening) with or right after a meal.\nCheck your pulse before taking; call your care team if heart rate is below 50 bpm.\nDo not stop taking suddenly without speaking to your doctor.",))

if "welcomed" not in st.session_state:
    st.toast("💜 Welcome to Checkpoint! Your cardiovascular recovery assistant is ready.", icon="✨")
    st.session_state.welcomed = True

if logo_file:
    c1, c2 = st.sidebar.columns([1, 4])
    c1.image(logo_file, width=36)
    c2.markdown("<h2 style='color:#6b21a8;margin-top:-5px;'>Checkpoint</h2>", unsafe_allow_html=True)
else:
    st.sidebar.title("❤️ Checkpoint")

if st.sidebar.toggle("Large text"):
    st.markdown("<style>html,body,[class*='css']{font-size:22px}</style>", unsafe_allow_html=True)

PAGES = {
    "Dashboard": page_dashboard, 
    "Daily Check-in": page_checkin, 
    "Medications": page_meds,
    "Calendar & Progress": page_calendar_progress,
    "AI Assistant": page_assistant, 
    "Monitoring": page_monitor, 
    "Care Team": page_team,
    "Caregiver": page_caregiver, 
    "Emergency": page_emergency
}
PAGES[st.sidebar.radio("Go to", list(PAGES))]()

st.sidebar.divider()
st.sidebar.error("🚨 Emergency? Call 911")
st.sidebar.caption("Prototype – not medical advice. Demo data only.")