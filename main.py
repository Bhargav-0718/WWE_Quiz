# main.py
import streamlit as st
import os, json, random, re, time, numpy as np
import requests
from dotenv import load_dotenv
from openai import OpenAI

# ---------------- OPENAI SETUP ----------------
load_dotenv()
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=OPENAI_API_KEY)

# ---------------- EXA.AI REST SETUP ----------------
EXA_API_KEY = st.secrets["EXA_API_KEY"]
EXA_BASE_URL = "https://api.exa.ai/v1"
HEADERS = {"Authorization": f"Bearer {EXA_API_KEY}"}

# ---------------- HELPER FUNCTIONS ----------------
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

# ---------------- EXA.AI REST FUNCTIONS ----------------
def save_question_to_exa(qdata, difficulty, embedding):
    metadata = {
        "question": qdata["question"],
        "options": qdata["options"],
        "answer": qdata["answer"],
        "difficulty": difficulty
    }
    payload = {"vector": embedding, "metadata": metadata}
    requests.post(f"{EXA_BASE_URL}/vectors", headers=HEADERS, json=payload)

def is_semantic_duplicate_exa(new_embedding, threshold=0.9):
    payload = {"vector": new_embedding, "top_k": 1}
    resp = requests.post(f"{EXA_BASE_URL}/query", headers=HEADERS, json=payload)
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        if results and results[0]["similarity"] >= threshold:
            return True
    return False

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
        try:
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

            # Check for duplicates using Exa.ai REST
            new_emb = get_embedding(question_data["question"])
            if is_semantic_duplicate_exa(new_emb):
                continue

            save_question_to_exa(question_data, difficulty, new_emb)
            return question_data

        except Exception as e:
            st.error(f"Error generating question: {str(e)}")
            return None

# ---------------- STREAMLIT UI ----------------
st.title("🤼 WWE Quiz")

# ---------------- SESSION STATE ----------------
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

# ---------------- RESET FUNCTION ----------------
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

# ---------------- TIMER ----------------
def update_timer():
    if st.session_state.timer_start:
        elapsed = int(time.time() - st.session_state.timer_start)
        st.session_state.time_left = max(0, 20 - elapsed)

# ---------------- START QUIZ ----------------
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

# ---------------- QUIZ FLOW ----------------
else:
    # Progress bar
    st.progress(st.session_state.question_count / st.session_state.max_questions)

    # Show question
    qdata = st.session_state.question_data
    if qdata:
        update_timer()
        st.subheader(qdata["question"])
        st.write(f"⏱️ Time left: {st.session_state.time_left} sec")

        # Show options if time left and not answered
        if st.session_state.time_left > 0 and not st.session_state.answered:
            choice = st.radio("Select your answer:", qdata["options"], key=f"opt_{qdata['question']}")

            if st.button("Submit Answer"):
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

        # Show Next Question button only after answering
        if st.session_state.answered:
            if st.button("➡️ Next Question"):
                if st.session_state.question_count < st.session_state.max_questions:
                    st.session_state.question_count += 1
                    st.session_state.question_data = get_question(st.session_state.difficulty)
                    st.session_state.answered = False
                    st.session_state.timer_start = time.time()
                    st.session_state.time_left = 20
                else:
                    st.success(f"🎉 Quiz Over! Final Score: {st.session_state.score}/{st.session_state.max_questions}")

        # Display score
        st.write(f"Score: {st.session_state.score}")

    # Reset button
    if st.button("🔄 Reset Quiz"):
        reset_quiz()
