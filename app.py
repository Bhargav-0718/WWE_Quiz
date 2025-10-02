# app.py
import os
import json
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import re

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize FastAPI and OpenAI client
app = FastAPI()
client = OpenAI(api_key=OPENAI_API_KEY)

# Request model for checking answer
class AnswerRequest(BaseModel):
    question: str
    user_answer: str
    correct_answer: str  # letter (A/B/C/D)

# Helper function to extract JSON from LLM output
def extract_json(raw_text):
    raw_text = raw_text.strip()
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if not match:
        return None, raw_text
    return json.loads(match.group(0)), None

# Endpoint: Generate AI WWE question
import random

@app.get("/question")
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

        choice_obj = response.choices[0]
        raw_content = choice_obj.message.content.strip()

        # Extract JSON
        import re, json
        match = re.search(r'\{.*\}', raw_content, re.DOTALL)
        if not match:
            return {"error": "No valid JSON found in LLM response.", "raw_content": raw_content}

        question_data = json.loads(match.group(0))

        # Shuffle options randomly
        options = question_data["options"]
        correct_letter = question_data["answer"].strip().upper()
        # Map letters to text
        options_dict = {opt.split(":")[0].strip(): opt.split(":")[1].strip() for opt in options}
        correct_text = options_dict[correct_letter]

        # Shuffle the options
        shuffled_texts = list(options_dict.values())
        random.shuffle(shuffled_texts)

        # Reassign letters A-D
        new_options = []
        new_answer_letter = None
        letters = ["A", "B", "C", "D"]
        for i, text in enumerate(shuffled_texts):
            new_options.append(f"{letters[i]}: {text}")
            if text == correct_text:
                new_answer_letter = letters[i]

        question_data["options"] = new_options
        question_data["answer"] = new_answer_letter
        question_data["correct_answer_full"] = f"{new_answer_letter}: {correct_text}"

        return question_data

    except Exception as e:
        return {"error": str(e)}


# Endpoint: Check user's answer
@app.post("/answer")
def check_answer(req: AnswerRequest):
    correct = req.user_answer.strip().upper() == req.correct_answer.strip().upper()
    return {"correct": correct}
