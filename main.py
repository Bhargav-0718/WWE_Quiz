# main.py
import streamlit as st
import os, json, random, re, sqlite3, time
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

# ---------------- DB SETUP ----------------
conn = sqlite3.connect("questions.db", check_same_thread=False)
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT UNIQUE,
    options TEXT,
    answer TEXT,
    difficulty TEXT,
    embedding TEXT
)
''')
conn.commit()

# ---------------- OPENAI SETUP ----------------
load_dotenv()
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=OPENAI_API_KEY)

# ---------------- HELPERS ----------------
def extract_json(raw_text):
    raw_text = raw_text.strip()
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if not match:
        return None, raw_text
    return json.loads(match.group(0)), None

def get_embedding(text):
    resp = client.embeddings.create(model="text-embedding-3-small", input=text)
    return resp.data[0].embedding

def cosine_similarity(vec1, vec2):
    v1, v2 = np.array(vec1), np.array(vec2)
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def is_semantic_duplicate(new_embedding, threshold=0.9):
    c.execute("SELECT embedding FROM questions ORDER BY id DESC LIMIT 25")  # only check last 25 for freshness
    rows = c.fetchall()
    for (emb,) in rows:
        if emb:
            old_emb = json.loads(emb)
            sim = cosine_similarity(new_embedding, old_emb)
            if sim >= threshold:
                return True
    return False

def save_question_to_db(qdata, difficulty, embedding):
    try:
        c.execute(
            "INSERT INTO questions (question, options, answer, difficulty, embedding) VALUES (?, ?, ?, ?, ?)",
            (qdata["question"], json.dumps(qdata["options"]), qdata["answer"], difficulty, json.dumps(embedding))
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass

# ---------------- QUESTION GENERATION ----------------
def get_question(difficulty="Medium"):
    system_prompt = f"""
    You are a WWE Quizmaster.
    Ask ONE multiple-choice question strictly based on kayfabe storylines.
    Difficulty level: {difficulty}.
    Format output ONLY as JSON with fields: question, options (A-D), and answer.
    Example:
    {{
      "question": "Who betrayed The Shield in 2014?",
      "options": ["A: Roman Reigns", "B: Dean Ambrose", "C: Seth Rollins", "D: Kane"],
      "answer": "C"
    }}
    """
    user_prompt = "Generate 1 MCQ question in JSON format."

    while True:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )

        raw_content = response.choices[0].message.content.strip()
        question_data, _ = extract_json(raw_content)
        if not question_data:
            continue

        # Shuffle options
        options = question_data["options"]
        correct_letter = question_data["answer"].strip().upper()
        options_dict = {opt.split(":")[0].strip(): opt.split(":")[1].strip() for opt in options}
        correct_text = options_dict[correct_letter]

        shuffled_texts = list(options_dict.values())
        random.shuffle(shuffled_texts)

        letters = ["A", "B", "C", "D"]
        new_options, new_answer_letter = [], None
        for i, text in enumerate(shuffled_texts):
            new_options.append(f"{letters[i]}: {text}")
            if text == correct_text:
                new_answer_letter = letters[i]

        question_data["options"] = new_options
        question_data["answer"] = new_answer_letter
        question_data["correct_answer_full"] = f"{new_answer_letter}: {correct_text}"

        # Embedding check
        new_emb = get_embedding(question_data["question"])
        if is_semantic_duplicate(new_emb):
            continue

        save_question_to_db(question_data, difficulty, new_emb)
        return question_data

# ---------------- STREAMLIT UI ----------------
st.title("🤼 WWE Quiz")

# Session state
if "started" not in st.session_state:
    st.session_state.update({
        "started": False,
        "question_data": None,
        "score": 0,
        "answered": False,
        "difficulty": "Medium",
        "timer_start": None,
        "time_left": 20,
        "question_count": 0,
        "max_questions": 10
    })

# Reset function
def reset_quiz():
    st.session_state.update({
        "started": False,
        "question_data": None,
        "score": 0,
        "answered": False,
        "timer_start": None,
        "time_left": 20,
        "question_count": 0
    })

# Timer updater
def update_timer():
    if st.session_state.timer_start:
        elapsed = int(time.time() - st.session_state.timer_start)
        st.session_state.time_left = max(0, 20 - elapsed)

# Difficulty selector + Start button
if not st.session_state.started:
    st.write("### ⚙️ Select Difficulty")
    difficulty = st.radio(
        "Choose Difficulty:", 
        ["Easy", "Medium", "Hard"],
        index=["Easy", "Medium", "Hard"].index(st.session_state.difficulty),
        horizontal=True
    )
    st.session_state.difficulty = difficulty

    if st.button("▶️ Start Quiz"):
        st.session_state.started = True
        st.session_state.question_data = get_question(st.session_state.difficulty)
        st.session_state.timer_start = time.time()
        st.session_state.time_left = 20
        st.session_state.question_count = 1

    # Progress bar
    st.progress(st.session_state.question_count / st.session_state.max_questions)

    # Show question
# Show question
qdata = st.session_state.question_data
if qdata:
    update_timer()
    st.subheader(qdata["question"])
    st.write(f"⏱️ Time left: {st.session_state.time_left} sec")

    choice = None
    if st.session_state.time_left > 0:
        choice = st.radio("Select your answer:", qdata["options"], key=f"opt_{qdata['question']}")

    # ---------------- Dynamic Submit / Next Question Button ----------------
    button_label = "Submit Answer" if not st.session_state.answered else "➡️ Next Question"
    if st.button(button_label):
        if not st.session_state.answered:
            # Submit logic
            if choice:
                selected_letter = choice.split(":")[0].strip()
                st.session_state.answered = True
                if selected_letter == qdata["answer"]:
                    st.session_state.score += 1
                    st.success(f"✅ Correct! {qdata['correct_answer_full']}")
                else:
                    st.error(f"❌ Wrong! Correct: {qdata['correct_answer_full']}")
            else:
                st.warning("Please select an answer before submitting!")
        else:
            # Next question logic
            if st.session_state.question_count < st.session_state.max_questions:
                st.session_state.question_count += 1
                st.session_state.question_data = get_question(st.session_state.difficulty)
                st.session_state.answered = False
                st.session_state.timer_start = time.time()
                st.session_state.time_left = 20
            else:
                st.success(f"🎉 Quiz Over! Final Score: {st.session_state.score}/{st.session_state.max_questions}")

    st.write(f"Score: {st.session_state.score}")

    # Reset button
    if st.button("🔄 Reset Quiz"):
        reset_quiz()
