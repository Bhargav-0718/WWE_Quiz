# main.py
import streamlit as st
import os
import json
import random
import re
import sqlite3
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
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return resp.data[0].embedding

def cosine_similarity(vec1, vec2):
    v1, v2 = np.array(vec1), np.array(vec2)
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def is_semantic_duplicate(new_embedding, threshold=0.9):
    c.execute("SELECT embedding FROM questions")
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

    try:
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
            new_options = []
            new_answer_letter = None
            for i, text in enumerate(shuffled_texts):
                new_options.append(f"{letters[i]}: {text}")
                if text == correct_text:
                    new_answer_letter = letters[i]

            question_data["options"] = new_options
            question_data["answer"] = new_answer_letter
            question_data["correct_answer_full"] = f"{new_answer_letter}: {correct_text}"

            # Get embedding & check similarity
            new_embedding = get_embedding(question_data["question"])
            if is_semantic_duplicate(new_embedding):
                continue  # regenerate

            # Save to DB
            save_question_to_db(question_data, difficulty, new_embedding)
            return question_data

    except Exception as e:
        st.error(f"Error generating question: {str(e)}")
        return None

# ---------------- STREAMLIT UI ----------------
st.title("🤼 WWE Quiz")

# Session state
if "question_data" not in st.session_state:
    st.session_state.update({
        "question_data": None,
        "score": 0,
        "answered": False,
        "difficulty": "Medium"
    })

# Difficulty selector
difficulty = st.radio("Choose Difficulty:", ["Easy", "Medium", "Hard"], index=["Easy", "Medium", "Hard"].index(st.session_state.difficulty))
st.session_state.difficulty = difficulty

# Load next question
def load_next_question():
    st.session_state.question_data = get_question(st.session_state.difficulty)
    st.session_state.answered = False

col1, col2 = st.columns(2)
with col1:
    if st.button("Next Question"):
        load_next_question()

# Show question
qdata = st.session_state.question_data
if qdata:
    st.subheader(qdata["question"])
    user_choice = st.radio("Select your answer:", qdata["options"], key=f"options_{qdata['question']}")

    if st.button("Submit Answer") and not st.session_state.answered:
        selected_letter = user_choice.split(":")[0].strip()
        correct_letter = qdata["answer"]
        st.session_state.answered = True
        if selected_letter == correct_letter:
            st.session_state.score += 1
            st.success(f"✅ Correct! Answer: {qdata['correct_answer_full']}")
        else:
            st.error(f"❌ Wrong! Correct answer: {qdata['correct_answer_full']}")

# Score
st.write(f"Your score: {st.session_state.score}")

# Auto-load first question
if st.session_state.question_data is None:
    load_next_question()
