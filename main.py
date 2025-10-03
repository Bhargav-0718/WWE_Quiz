# app.py
import streamlit as st
import json
import random
import re
import time
from openai import OpenAI

# Fetch OpenAI key from Streamlit secrets
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
client = OpenAI(api_key=OPENAI_API_KEY)

# Helper function
def extract_json(raw_text):
    raw_text = raw_text.strip()
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if not match:
        return None, raw_text
    return json.loads(match.group(0)), None

# Function to generate WWE question
def get_question(difficulty="Medium", used_questions=None):
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
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=1.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        raw_content = response.choices[0].message.content.strip()
        question_data, _ = extract_json(raw_content)
        if not question_data:
            return None

        # Prevent repetition: skip if in used questions
        if used_questions and question_data["question"] in used_questions:
            return get_question(difficulty, used_questions)

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
        return question_data

    except Exception as e:
        st.error(f"Error generating question: {str(e)}")
        return None

# ----------------- Streamlit UI -----------------
st.title("🤼 WWE Quiz")

# Session state
if "started" not in st.session_state:
    st.session_state.update({
        "started": False,
        "difficulty": "Medium",
        "question_data": None,
        "score": 0,
        "answered": False,
        "current_q": 0,
        "used_questions": [],
        "start_time": None
    })

# Reset quiz
def reset_quiz():
    st.session_state.started = False
    st.session_state.score = 0
    st.session_state.answered = False
    st.session_state.current_q = 0
    st.session_state.used_questions = []
    st.session_state.question_data = None
    st.session_state.start_time = None
    st.experimental_rerun()

# Start Quiz UI
if not st.session_state.started:
    st.subheader("🎯 Select Difficulty")
    st.session_state.difficulty = st.radio(
        "Choose difficulty level:",
        ["Easy", "Medium", "Hard"],
        index=1
    )
    if st.button("▶️ Start Quiz"):
        st.session_state.started = True
        st.session_state.current_q = 0
        st.session_state.score = 0
        st.session_state.used_questions = []
        st.session_state.question_data = get_question(st.session_state.difficulty)
        st.session_state.start_time = time.time()
        st.experimental_rerun()

# Main Quiz
if st.session_state.started and st.session_state.question_data:
    qdata = st.session_state.question_data
    st.subheader(f"Q{st.session_state.current_q + 1}: {qdata['question']}")

    # Timer logic (20s)
    elapsed = int(time.time() - st.session_state.start_time)
    remaining = 20 - elapsed
    if remaining > 0:
        st.progress(remaining / 20)
        st.write(f"⏳ Time left: {remaining}s")
    else:
        if not st.session_state.answered:
            st.session_state.answered = True
            st.error(f"⏰ Time’s up! Correct answer: {qdata['correct_answer_full']}")

    user_choice = st.radio("Select your answer:", qdata["options"], key=f"q{st.session_state.current_q}")

    # Submit Answer
    if st.button("Submit Answer") and not st.session_state.answered:
        selected_letter = user_choice.split(":")[0].strip()
        correct_letter = qdata["answer"]
        st.session_state.answered = True

        if selected_letter == correct_letter:
            st.session_state.score += 1
            st.success(f"✅ Correct! Answer: {qdata['correct_answer_full']}")
        else:
            st.error(f"❌ Wrong! Correct answer: {qdata['correct_answer_full']}")

    # Next Question / End Quiz
    if st.session_state.answered:
        if st.session_state.current_q + 1 < 10:
            if st.button("➡️ Next Question"):
                st.session_state.current_q += 1
                st.session_state.used_questions.append(qdata["question"])
                if len(st.session_state.used_questions) > 25:
                    st.session_state.used_questions.pop(0)  # keep only last 25
                st.session_state.question_data = get_question(
                    st.session_state.difficulty,
                    st.session_state.used_questions
                )
                st.session_state.answered = False
                st.session_state.start_time = time.time()
                st.experimental_rerun()
        else:
            st.success(f"🏁 Quiz Finished! Final Score: {st.session_state.score}/10")
            if st.button("🔄 Restart Quiz"):
                reset_quiz()

    # Score + Progress
    st.write(f"📊 Score: {st.session_state.score}")
    st.progress((st.session_state.current_q + 1) / 10)

# Reset button always visible
if st.button("Reset Quiz"):
    reset_quiz()
