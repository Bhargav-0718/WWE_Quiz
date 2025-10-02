# frontend.py
import streamlit as st
import requests

BASE_URL = "http://Localhost:8000"

st.title("🤼 WWE Quiz")

# Initialize session state
if "question" not in st.session_state:
    st.session_state.update({
        "question": None,
        "options": [],
        "correct_answer": None,
        "correct_answer_full": None,
        "score": 0,
        "answered": False,
        "last_feedback": "",
        "next_clicked": True  # allows first question to load
    })

def get_new_question():
    st.session_state.next_clicked = False
    try:
        response = requests.get(f"{BASE_URL}/question").json()
        if "error" in response:
            st.error(f"Error fetching question: {response['error']}")
            if "raw_content" in response:
                st.write("LLM raw output:", response["raw_content"])
            return
        st.session_state.question = response["question"]
        st.session_state.options = response["options"]
        st.session_state.correct_answer = response["answer"]
        st.session_state.correct_answer_full = response.get("correct_answer_full", response["answer"])
        st.session_state.answered = False
        st.session_state.last_feedback = ""
    except Exception as e:
        st.error(f"Error fetching question: {str(e)}")

# Button to load next question
if st.button("Next Question"):
    get_new_question()

# Show current question
if st.session_state.question:
    st.subheader(st.session_state.question)
    choice = st.radio("Select your answer", st.session_state.options, key="options_radio")
    
    if st.button("Submit Answer") and not st.session_state.answered:
        user_choice = choice.split(":")[0]  # Extract A/B/C/D
        try:
            resp = requests.post(f"{BASE_URL}/answer",
                                 json={
                                     "question": st.session_state.question,
                                     "user_answer": user_choice,
                                     "correct_answer": st.session_state.correct_answer
                                 }).json()
            st.session_state.answered = True
            if resp.get("correct"):
                st.session_state.score += 1
                st.success(f"✅ Correct! The answer is {st.session_state.correct_answer_full}")
            else:
                st.error(f"❌ Wrong! The correct answer is {st.session_state.correct_answer_full}")
        except Exception as e:
            st.error(f"Error checking answer: {str(e)}")

    # Show score
    st.write(f"Your score: {st.session_state.score}")
