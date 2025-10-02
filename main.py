# app.py
import streamlit as st
import os
import json
import random
import re
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()
OPENAI_API_KEY = st.secrets["general"]["OPENAI_API_KEY"]

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Helper function to extract JSON from LLM output
def extract_json(raw_text):
    raw_text = raw_text.strip()
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if not match:
        return None, raw_text
    return json.loads(match.group(0)), None

# Function to get a WWE question from LLM
def get_question():
    system_prompt = """
    You are a WWE Quizmaster.
    Ask ONE multiple-choice question strictly based on kayfabe storylines.
    Format output ONLY as JSON with fields: question, options (A-D), and answer.
    Do NOT include any extra text or commentary.
    Example:
    {
      "question": "Who betrayed The Shield in 2014?",
      "options": ["A: Roman Reigns", "B: Dean Ambrose", "C: Seth Rollins", "D: Kane"],
      "answer": "C"
    }
    """
    user_prompt = "Generate 1 MCQ question in JSON format."

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
            st.error("Failed to parse LLM output.")
            return None

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
        return question_data

    except Exception as e:
        st.error(f"Error generating question: {str(e)}")
        return None

# ---------- Streamlit UI ----------
st.title("🤼 WWE Quiz")

# Initialize session state
if "question_data" not in st.session_state:
    st.session_state.update({
        "question_data": None,
        "score": 0,
        "answered": False
    })

# Load next question
def load_next_question():
    st.session_state.question_data = get_question()
    st.session_state.answered = False

# Buttons
col1, col2 = st.columns(2)
with col1:
    if st.button("Next Question"):
        load_next_question()

# Display question
qdata = st.session_state.question_data
if qdata:
    st.subheader(qdata["question"])
    user_choice = st.radio("Select your answer:", qdata["options"], key="options_radio")

    if st.button("Submit Answer") and not st.session_state.answered:
        selected_letter = user_choice.split(":")[0].strip()
        correct_letter = qdata["answer"]
        st.session_state.answered = True
        if selected_letter == correct_letter:
            st.session_state.score += 1
            st.success(f"✅ Correct! Answer: {qdata['correct_answer_full']}")
        else:
            st.error(f"❌ Wrong! Correct answer: {qdata['correct_answer_full']}")

# Display score
st.write(f"Your score: {st.session_state.score}")

# Automatically load first question if none
if st.session_state.question_data is None:
    load_next_question()
