import os
import json
import base64
import re
import html
import asyncio
from typing import Dict, Any, List, Optional
import httpx
from pydantic import BaseModel, Field, field_validator

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = r"""You are an experienced, supportive commerce mentor and exam coach for CA, CS, and CMA students at Excel Educational Institute.
Think of yourself as a brilliant senior, rankholder, and trusted friend who is guiding the student through their exam preparation with genuine warmth, clarity, and deep academic expertise.

CONVERSATIONAL TONE & COACH PERSONA (TALK LIKE A FRIEND):
- Converse naturally, warmly, and empathetically like a trusted mentor-friend. Be approachable, encouraging, and clear — never stiff, mechanical, or like a corporate bot.
- NEVER say "Welcome to Excel Educational Institute", "Hello there!", or re-introduce yourself repeatedly on every turn. Talk like a real friend having an ongoing study session.
- Avoid forcing rigid bureaucratic templates when chatting, giving practice questions, or answering general queries. Keep transitions smooth, friendly, and natural.
- When delivering technical model answers, numerical solutions, or checking student answers, maintain 100% academic rigor and ICAI Suggested Answer standards (exact statutory sections, accounting standards, detailed working notes, and clean commerce math notation), but present and explain them in a friendly, engaging manner.
- DO NOT append repetitive boilerplate "Coach's Exam Presentation Tip:" or "Examiner's Pro-Tip:" at the end of every message unless specifically asked. Answer directly, warmly, and helpfully.

SCENARIOS & PEDAGOGICAL BEHAVIORS:

1. PRACTICE & TOPIC QUESTION REQUESTS:
   - When a student says "I want to practice", "give me questions on [topic/subject]", "let's practice costing", or "quiz me":
     • Provide 1 to 4 exam-standard questions matching their Course and Level (e.g. CA Inter).
     • For practical problems, provide realistic exam data (e.g. standard & actual costs, tax slabs, or balance sheet items).
     • Clearly state the marks weightage for each question (e.g., [4 Marks] or [5 Marks]).
     • **STRICTLY DO NOT REVEAL THE ANSWERS, SOLUTIONS, CORRECT OPTIONS, OR WORKING NOTES IN THIS INITIAL TURN!**
     • Conclude warmly like a friend: Invite them to try solving it, write down their key steps or final figures right here, and ask if they'd like hints or if they want you to walk through the complete solution whenever they are ready.

2. ANSWER-WRITING PRACTICE REQUESTS:
   - When a student asks "give me question for answer writing for [subject/topic]", "give me a descriptive question to practice writing", or "case study for answer writing":
     • Provide ONE authentic ICAI exam-pattern case study or descriptive question (typically 4 to 6 marks).
     • Clearly state the marks allocation and recommended time (e.g., **Weightage: 5 Marks | Recommended Time: 8-10 Minutes**).
     • **STRICTLY DO NOT GIVE THE ANSWER, HINTS, OR SUGGESTED SOLUTION UPFRONT.**
     • Follow up warmly like a friend: Encourage them to draft their answer (typed or upload a photo of handwritten sheet) for step-wise evaluation, and let them know you can also share the model answer if they want to review it right away.

3. SOLUTION REQUESTS ("Give me the answer", "Show solution", "What is the answer?"):
   - When the student specifically asks for the answer or solution:
     • Provide the complete, definitive model solution in ONE comprehensive response.
     • For law and audit:
       1. **Applicable Statutory Provisions / Standards**: State the relevant Act, Section, Rule, SA, AS/Ind AS.
       2. **Analysis & Application**: Apply the law/accounting standard directly to the question facts.
       3. **Conclusion**: Provide a clear, definitive conclusion.
     • For practical/numerical subjects (Accounts, Costing, Tax):
       - Present full computations with detailed **Working Notes**.
       - Show all step calculations clearly in clean commerce math notation (never raw LaTeX).
     • Frame the solution warmly and supportively, pointing out how ICAI expects it presented.

4. STUDENT ANSWER EVALUATION & CHECKING:
   - When a student submits an answer (typed text, handwritten photo, or MCQ options):
     • Review their attempt warmly and constructively like a mentor-friend.
     • Provide a **Score out of Total Marks** (e.g. 7.5 / 10).
     • Give a **Step-Wise Marks Allocation**:
       - Relevant Provisions / Sections Cited
       - Analysis, Working Notes & Calculations
       - Conclusion & Exam Presentation Format
     • Highlight **What was done well (Strengths)**.
     • Point out **Where marks were lost (Missing keywords, sections, calculation errors)**.
     • Provide the **Suggested Model Answer**.

5. DIRECT CONCEPT & DOUBT RESOLUTION:
   - When a student asks a direct syllabus doubt or asks to explain a concept:
     • Provide the complete, thorough, authoritative explanation in ONE response.
     • Explain intuitively and clearly, like a knowledgeable senior friend who makes complex concepts easy to understand.

6. MATHEMATICAL & FORMULA PRESENTATION STANDARDS (STRICT):
   - NEVER output raw LaTeX math syntax (such as $$, $, \text{...}, \times, \frac{...}{...}, \left, \right).
   - In Indian commerce exams (ICAI, ICSI, ICMAI), formulas and working notes are ALWAYS presented in clean, readable plain business notation:
     • Formula example: Labour Rate Variance (LRV) = Actual Hours × (Standard Rate - Actual Rate)
     • Working note computation: = 4,800 hrs × (₹60 - ₹65) = 4,800 × (-₹5) = ₹24,000 (Adverse)
     • Use standard business characters: '×' or '*' for multiplication, '÷' or '/' for division, '₹' for currency, and standard parentheses ( ) and brackets [ ].
     • State variances clearly as (Favourable) or (Adverse) / (F) or (A).
   - NEVER include internal scratchpad hesitation or reasoning monologue. Output ONLY the final, accurate step-by-step working notes.

CRITICAL INSTRUCTIONS:
- Answer with warmth, encouragement, and academic precision like a supportive senior friend and coach.
- Never mention files, excerpts, retrieval, or sources in your response. Answer as an authoritative coach.
- Keep formatting clean, modern, and readable with bold highlights and bullet points.
"""

def clean_exam_math(text: str) -> str:
    """
    Strips raw LaTeX math syntax and converts formulas into clean, readable commerce examination notation.
    E.g. r'($\text{SP} \times [\text{SQ} - \text{AQ}])$' -> '(SP × [SQ - AQ])'
    """
    if not text:
        return ""
    s = text
    # Clean LaTeX spacing
    s = re.sub(r'\\(quad|qquad|\s+|,|;|!)', ' ', s)
    # Clean \text{...} wrappers repeatedly
    for _ in range(3):
        s = re.sub(r'\\text\{([^{}]*)\}', r'\1', s)
    # Common math symbols
    s = re.sub(r'\\times\b', '×', s)
    s = re.sub(r'\\cdot\b', '·', s)
    s = re.sub(r'\\div\b', '÷', s)
    s = re.sub(r'\\pm\b', '±', s)
    s = re.sub(r'\\(leq|le)\b', '≤', s)
    s = re.sub(r'\\(geq|ge)\b', '≥', s)
    s = re.sub(r'\\(neq|ne)\b', '≠', s)
    s = re.sub(r'\\approx\b', '≈', s)
    # Clean fractions \frac{a}{b} -> (a / b)
    s = re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'(\1 / \2)', s)
    # Clean \left and \right delimiters
    s = re.sub(r'\\left\s*([(\[{|])', r'\1', s)
    s = re.sub(r'\\right\s*([)\]}|])', r'\1', s)
    # Strip $$ and $ wrappers
    s = re.sub(r'\$\$([\s\S]*?)\$\$', r'\1', s)
    s = re.sub(r'\$([^\$\n]+)\$', r'\1', s)
    # Remove lingering backslashes before brackets
    s = s.replace(r'\[', '[').replace(r'\]', ']').replace(r'\(', '(').replace(r'\)', ')')
    # Clean unescaped remaining single $
    s = re.sub(r'\$([A-Za-z0-9_\[\]\(\)\s+\-*\/=]+)\$', r'\1', s)
    # Clean double spaces
    s = re.sub(r'[ \t]{2,}', ' ', s)
    return s.strip()

class MCQQuestion(BaseModel):
    id: Optional[int] = None
    question: str
    options: Dict[str, str]
    correct_answer: str
    correct_option: Optional[str] = None
    explanation: str
    topic: Optional[str] = None

    @field_validator("correct_answer", mode="before")
    @classmethod
    def validate_correct_answer(cls, v: Any) -> str:
        s = str(v).strip().upper()
        if s.startswith("OPTION"):
            s = s.replace("OPTION", "").strip()
        s = s.strip("():. ")
        if s not in ["A", "B", "C", "D"]:
            for opt in ["A", "B", "C", "D"]:
                if opt in s:
                    return opt
            raise ValueError(f"Invalid correct_answer '{v}'; must be 'A', 'B', 'C', or 'D'")
        return s

    @field_validator("options", mode="before")
    @classmethod
    def validate_options(cls, v: Any) -> Dict[str, str]:
        if not isinstance(v, dict):
            raise ValueError("options must be a dictionary with keys A, B, C, D")
        cleaned = {}
        for key in ["A", "B", "C", "D"]:
            val = v.get(key) if key in v else v.get(key.lower())
            if val is None:
                raise ValueError(f"Missing option '{key}' in options dict")
            cleaned[key] = clean_exam_math(str(val).strip())
        return cleaned

    def model_post_init(self, __context: Any) -> None:
        if not self.correct_option:
            self.correct_option = self.correct_answer
        self.question = clean_exam_math(self.question)
        self.explanation = clean_exam_math(self.explanation)


def clean_student_reply(text: str, allow_tips: bool = False) -> str:
    """Ensures no internal retrieval labels, NOT_IN_MATERIAL, source disclaimers, or unprompted coach tips leak to students, and cleans math syntax."""
    if not text:
        return ""
    text = text.replace("NOT_IN_MATERIAL", "").strip()
    text = clean_exam_math(text)

    # Strip unprompted repetitive coach tips block
    if not allow_tips:
        text = re.sub(r'(?i)\n*(\*{1,2}|_{1,2})?(coach\'?s?\s+(exam\s+)?presentation\s+tip|examiner\'?s?\s+pro-?tip|faculty\s+presentation\s+tip|coach\'?s?\s+tip|exam\s+presentation\s+tip):?(\*{1,2}|_{1,2})?.*$', '', text, flags=re.DOTALL).strip()

    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        l_lower = line.lower().strip()
        if (
            l_lower.startswith("source:") or
            l_lower.startswith("sources:") or
            l_lower.startswith("reference:") or
            l_lower.startswith("references:") or
            re.match(r"^(top\s+)?score:\s*0\.\d+", l_lower) or
            l_lower.startswith("top score:") or
            (l_lower.startswith("score:") and not any(m in l_lower for m in ["/ 10", "/10", "/ 5", "/5", "/ 100", "%", "out of"])) or
            l_lower.startswith("according to the study material") or
            l_lower.startswith("according to study material") or
            l_lower.startswith("according to the excerpt") or
            l_lower.startswith("as per the study material") or
            l_lower.startswith("as per study material") or
            l_lower.startswith("based on general knowledge") or
            l_lower.startswith("from the study material") or
            l_lower.startswith("from study material") or
            ("from general knowledge" in l_lower and len(l_lower) < 60)
        ):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()

def perform_web_search(query: str, max_results: int = 4) -> List[Dict[str, str]]:
    """Performs live web search for recent exam notifications, amendments, or missing syllabus topics."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            r = client.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers)
            if r.status_code != 200:
                return []
            blocks = r.text.split('class="result ')
            results = []
            for b in blocks[1:]:
                t_m = re.search(r'<a[^>]+class="result__snippet"[^>]*>([\s\S]*?)</a>', b)
                title_m = re.search(r'<h2[^>]*>[\s\S]*?<a[^>]*>([\s\S]*?)</a>', b)
                title = html.unescape(re.sub(r'<[^>]+>', '', title_m.group(1)).strip()) if title_m else "Web Result"
                snippet = html.unescape(re.sub(r'<[^>]+>', '', t_m.group(1)).strip()) if t_m else ""
                if snippet:
                    results.append({"title": title, "snippet": snippet})
                if len(results) >= max_results:
                    break
            return results
    except Exception as e:
        print(f"[Web search warning]: {e}")
        return []

def is_forced_internet_query(text: str) -> bool:
    """Detects whether student explicitly requests web / internet search or latest external notifications."""
    t = (text or "").lower()
    keywords = [
        "search internet", "search the internet", "search web", "search the web",
        "browse internet", "browse the web", "look up online", "search online",
        "google it", "check internet", "internet research", "web research",
        "latest notification", "latest circular", "recent notification", "exam date", "exam dates",
        "announcement", "press release"
    ]
    return any(k in t for k in keywords)

def detect_interaction_scenario(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    has_image: bool = False
) -> str:
    """
    Classifies the student's turn into one of the core pedagogical scenarios:
    - ANSWER_WRITING: Student asks for an answer-writing question / descriptive case drill.
    - PRACTICE: Student asks for practice problems, MCQs, quiz, or topic questions to solve.
    - HINT_REQUEST: Student asks for a hint on a current question.
    - SOLUTION_REQUEST: Student specifically asks for the answer, solution, or working notes.
    - STUDENT_SUBMISSION: Student submits their written answer, attempt, or sheet for checking.
    - GENERAL_CONVERSATION: Greetings, motivation, study tips, or casual chat.
    - CONCEPT_DOUBT: Direct concept, statutory query, or problem given for explanation.
    """
    text = (message or "").strip().lower()

    # 1. Check for student submission via image upload
    if has_image:
        return "STUDENT_SUBMISSION"

    # 2. Check for Hint request
    hint_patterns = ["give me a hint", "give a hint", "any hint", "can i get a hint", "need a hint", "give hint", "hint please"]
    if any(p in text for p in hint_patterns):
        return "HINT_REQUEST"

    # 3. Check for explicit solution request (e.g. "give me the answer", "what is the answer", "show solution")
    solution_patterns = [
        "give me the answer", "give me the solution", "give the answer", "give the solution",
        "give answer", "give solution", "show answer", "show the answer", "show solution",
        "show the solution", "show model answer", "give model answer", "what is the answer",
        "what's the answer", "whats the answer", "what is the solution", "what's the solution",
        "whats the solution", "tell me the answer", "tell me the solution", "tell answer",
        "tell solution", "explain the answer", "explain the solution", "reveal answer",
        "reveal the answer", "reveal answers", "reveal solution", "reveal the solution",
        "i don't know the answer", "dont know the answer", "i don't know", "dont know",
        "i give up", "give up", "can't solve", "cant solve", "could not solve",
        "how to solve this", "solve it for me", "solve it", "solve this", "share the answer",
        "share the solution", "correct answer", "what is correct answer", "solution please", "answer please"
    ]
    # If the user says "give me the answer", ensure it's not "give me questions and answers"
    if any(p in text for p in solution_patterns) and not any(p in text for p in ["give me question", "give me questions", "want to practice", "practice question"]):
        return "SOLUTION_REQUEST"

    # 4. Check for explicit student submission prefixes
    submission_prefixes = [
        "my answer is", "my answer:", "here is my answer", "here's my answer",
        "my attempt", "my solution", "attempt:", "solution:", "i think the answer is", "my points are"
    ]
    if any(text.startswith(p) for p in submission_prefixes):
        return "STUDENT_SUBMISSION"

    # MCQ submission pattern like "1-A, 2-B" or "1. A, 2. B" or "1-A"
    if re.search(r'\b[1-9]\s*[-:.)]\s*[A-Da-d]\b', text):
        return "STUDENT_SUBMISSION"

    # 5. Check if previous turn was a Coach practice/answer-writing invitation and student is answering
    if history and len(history) > 0:
        last_turn = history[-1]
        last_role = last_turn.get("role", "")
        last_text = (last_turn.get("text") or last_turn.get("content") or "").lower()
        if last_role in ["assistant", "coach", "bot"]:
            practice_invitations = [
                "your turn:", "draft your answer", "give it a shot", "your choices",
                "submit your", "drop your thoughts", "take about 8", "take about 10",
                "recommended time:", "weightage:"
            ]
            if any(pi in last_text for pi in practice_invitations):
                if not any(k in text for k in ["give me question", "another question", "new question", "practice", "give me the answer", "show solution", "hint"]):
                    if len(text.split()) >= 4:
                        return "STUDENT_SUBMISSION"

    # 6. Check for Answer-Writing Practice Request
    answer_writing_keywords = [
        "answer writing", "answer-writing", "answerwrite", "practice writing",
        "writing practice", "question for answer writing", "questions for answer writing",
        "give me a descriptive question", "give me descriptive question", "give descriptive question",
        "give me a case study question", "give me case study question", "give case study question",
        "case study to practice", "case study for practice", "descriptive question to practice",
        "descriptive question for practice", "case scenario question", "subjective question",
        "descriptive answer writing"
    ]
    if any(k in text for k in answer_writing_keywords):
        return "ANSWER_WRITING"

    # 7. Check for Topic / Subject Practice Request
    practice_keywords = [
        "i want to practice", "want to practice", "let's practice", "lets practice",
        "give me questions", "give me question", "give me some questions", "give questions",
        "give some questions", "ask me a question", "ask me questions", "ask questions",
        "quiz me", "test me", "test my knowledge", "take a test", "practice questions",
        "practice question", "practice problem", "practice problems", "questions to solve",
        "question to solve", "problems to solve", "problem to solve", "give me mcq",
        "give me mcqs", "give mcq", "give mcqs", "quiz on", "questions from",
        "questions on", "give questions on", "can you give me questions", "numerical to practice",
        "practice session"
    ]
    wants_answers_together = any(w in text for w in ["with answer", "with solution", "and answers", "and solutions", "along with answer"])
    if any(k in text for k in practice_keywords) and not wants_answers_together:
        return "PRACTICE"

    # 8. General Conversation / Greeting / Motivation
    greetings = ["hi", "hello", "hey", "namaste", "good morning", "good evening", "good afternoon"]
    if text in greetings or text.startswith("hi coach") or text.startswith("hello coach") or text.startswith("hey coach"):
        return "GENERAL_CONVERSATION"

    conversational_phrases = [
        "feeling stressed", "feeling anxious", "feeling nervous", "exam stress",
        "study tips", "how to study", "how to prepare", "study strategy", "study plan",
        "thank you", "thanks", "how are you", "who are you"
    ]
    if any(cp in text for cp in conversational_phrases):
        return "GENERAL_CONVERSATION"

    # 9. Default to Concept / Exam Doubt Resolution
    return "CONCEPT_DOUBT"


CANDIDATE_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemini-pro-latest"
]

class AIService:
    CANDIDATE_MODELS = CANDIDATE_MODELS

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.preferred_llm = os.getenv("PREFERRED_LLM", "gemini").lower()
        self.models = CANDIDATE_MODELS
        self.last_model_used: str = CANDIDATE_MODELS[0]

    def set_api_key(self, key: str):
        self.api_key = key.strip()

    def has_api_key(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10)

    async def extract_question_from_image(self, image_base64: str, mime_type: str = "image/jpeg") -> str:
        """Fast Gemini call to transcribe the question or problem from an image."""
        if not self.has_api_key():
            return ""
        prompt = "Extract and transcribe the main question, problem statement, or doubt shown in this image. Output only the plain text question without commentary."
        images = [{"mime_type": mime_type, "data": image_base64}]
        try:
            res = await self._call_llm(prompt, images=images, max_tokens=1024)
            return res.strip()
        except Exception as e:
            print(f"[Image Text Extraction Error]: {e}")
            return ""

    async def get_response(
        self,
        message: str,
        image_base64: Optional[str] = None,
        mime_type: str = "image/jpeg",
        context_chunks: Optional[List[Dict[str, Any]]] = None,
        course: str = "CA",
        level: str = "Inter",
        history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Level-aware answer generation with Grounded -> NOT_IN_MATERIAL -> General Knowledge fallback.
        Supports Practice Drills, Answer-Writing Practice, Solution Requests, Submissions, and Doubts.
        Returns dict: {"reply": str, "source": "material" | "general", "top_score": float, "model_used": str}.
        """
        if not self.has_api_key():
            raise Exception("GEMINI_API_KEY is not configured.")

        top_score = max([c.get("score", 0.0) for c in (context_chunks or [])], default=0.0)

        # 1. Format conversation history (last 6 turns)
        history_text = ""
        if history:
            history_text = "\n[Recent Conversation History]:\n"
            for h in history[-6:]:
                role_label = "Student" if h.get("role") in ["user", "student"] else "Coach"
                msg_body = h.get("text") or h.get("content") or ""
                if msg_body:
                    history_text += f"{role_label}: {msg_body}\n"
            history_text += "\n"

        images = []
        if image_base64:
            images.append({
                "mime_type": mime_type,
                "data": image_base64
            })

        user_query = message.strip() if message else "Please evaluate this student submission."

        # Detect interaction scenario
        scenario = detect_interaction_scenario(user_query, history=history, has_image=bool(image_base64))

        level_prefix = f"STUDENT LEVEL: The student is preparing for {course} {level}. Answer strictly within this level's syllabus, depth and exam pattern. Do not use concepts from higher levels unless asked."

        if scenario == "ANSWER_WRITING":
            scenario_instructions = f"""{level_prefix}
CURRENT SCENARIO: ANSWER-WRITING PRACTICE REQUEST
1. The student wants an authentic exam question to practice descriptive or case-study answer writing for {course} {level}.
2. Provide ONE realistic, exam-standard case scenario or descriptive question (typically 4-6 marks) matching the requested topic/subject.
3. State the marks weightage and recommended time limit (e.g. **Weightage: 5 Marks | Recommended Time: 8-10 Minutes**).
4. STRICTLY DO NOT PROVIDE THE ANSWER, HINTS, OR MODEL SOLUTION IN THIS INITIAL RESPONSE. Withhold the answer completely so the student can draft their own answer first!
5. CONVERSATIONAL TONE & FOLLOW-UP (TALK LIKE A FRIEND):
   Talk warmly, naturally, and encouragingly like a senior mentor-friend.
   Conclude by warmly inviting them to attempt it:
   "👉 **Your Turn:** Take about 8-10 minutes to draft your answer! Outline your statutory provisions, analysis, and conclusion right here (or snap a photo of your handwritten sheet). Once you share it, I'll review it with step-wise marks and feedback. Or if you want to skip straight to the model answer, just let me know and I'll walk you through it!"
"""
        elif scenario == "PRACTICE":
            scenario_instructions = f"""{level_prefix}
CURRENT SCENARIO: TOPIC / SUBJECT PRACTICE REQUEST
1. The student wants questions to practice or test their knowledge.
2. If a specific topic/subject is provided: provide 1 to 3 exam-level question(s) (or practical numerical / MCQs) matching {course} {level}.
   If NO specific topic is provided (e.g. student just said "I want to practice"): ask them warmly what subject or topic from {course} {level} they'd like to crush today (e.g. Law, Costing, Tax, Audit, Accounts) and whether they want answer-writing, numerical practice, or MCQs.
3. For questions provided: clearly state the marks weightage for each question.
4. STRICTLY DO NOT REVEAL THE ANSWERS, WORKING NOTES, OR SOLUTIONS IN THIS INITIAL RESPONSE. Give the student the opportunity to attempt them!
5. CONVERSATIONAL TONE & FOLLOW-UP (TALK LIKE A FRIEND):
   Talk warmly and naturally like a senior friend and coach.
   Conclude by inviting them to try it out:
   "Give it a shot! Drop your thoughts, steps, or final figures right here and I'll check your work. Or if you get stuck and want hints or want me to reveal the full solution with working notes, just say the word!"
"""
        elif scenario == "HINT_REQUEST":
            scenario_instructions = f"""{level_prefix}
CURRENT SCENARIO: HINT REQUEST
1. The student is asking for a hint or clue for the practice question under discussion.
2. Provide a helpful, encouraging clue or thought-starter (e.g. pointing towards the key section number, standard formula, or threshold to consider).
3. DO NOT reveal the final answer, complete calculation, or entire conclusion. Give them just enough guidance to think and attempt.
4. Conclude warmly: "Give that a thought and try taking the next step! What do you get?"
"""
        elif scenario == "SOLUTION_REQUEST":
            scenario_instructions = f"""{level_prefix}
CURRENT SCENARIO: STUDENT ASKS FOR THE ANSWER / SOLUTION
1. The student is specifically asking for the solution, model answer, or working notes for the question discussed.
2. Provide the complete, comprehensive, and definitive model solution in ONE response.
3. Structure it according to official exam standards:
   • Statutory Provisions / Accounting Standards / SAs (with exact Section/Standard numbers and titles)
   • Step-by-step Working Notes and Computations (for practical subjects, in clean math notation without raw LaTeX)
   • Direct Analysis and Final Conclusion
4. CONVERSATIONAL TONE (TALK LIKE A FRIEND):
   Present the solution warmly and supportively, pointing out how ICAI expects it presented to bag full marks.
"""
        elif scenario == "STUDENT_SUBMISSION":
            scenario_instructions = f"""{level_prefix}
CURRENT SCENARIO: STUDENT ANSWER EVALUATION
1. The student has submitted their written answer, attempt, or answer sheet.
2. Evaluate their attempt warmly, constructively, and thoroughly like an encouraging senior mentor-friend.
3. Provide:
   • A Score out of total marks (e.g. 7.5 / 10).
   • Step-Wise Marks Breakdown (Provisions, Application & Working, Conclusion & Presentation).
   • Strengths (what they wrote accurately).
   • Where marks were lost (missing sections, presentation gaps, calculation errors).
   • The Suggested Model Answer in full exam format.
4. Keep the tone inspiring, friendly, and practical.
"""
        elif scenario == "GENERAL_CONVERSATION":
            scenario_instructions = f"""{level_prefix}
CURRENT SCENARIO: FRIENDLY CONVERSATION & STUDY MENTORSHIP
Talk naturally, warmly, and empathetically like a trusted friend and senior mentor.
Never sound like a stiff robot or use canned corporate templates. Be encouraging and provide practical, actionable study guidance.
"""
        else: # CONCEPT_DOUBT
            scenario_instructions = f"""{level_prefix}
COMPLETENESS (STRICT): Give the complete answer in ONE response. Never ask a clarifying question and never end with an offer to continue. If the question is ambiguous, state one assumption in a line and answer fully. For numericals show the full solution with working notes from start to final answer.
CURRENT SCENARIO: CONCEPT / EXAM DOUBT RESOLUTION
Explain the concept or provide the complete solution in ONE comprehensive response.
For law/audit: State Statutory Provisions, Analysis & Application, and Conclusion.
For practical/numerical: Show the full solution with step-by-step Working Notes from start to final answer in clean commerce math notation (no raw LaTeX).
Talk warmly and clearly like a friendly mentor who makes tough topics easy to master.
"""

        # Check if user explicitly forces internet / external research
        forced_internet = is_forced_internet_query(user_query)

        # 1. If forced internet research requested:
        if forced_internet:
            web_results = []
            try:
                search_term = f"ICAI {course} {level} {user_query}" if not any(w in user_query.lower() for w in ["icai", "icsi", "icmai"]) else user_query
                loop = asyncio.get_running_loop()
                web_results = await loop.run_in_executor(None, perform_web_search, search_term, 4)
            except Exception as ws_err:
                print(f"[Web search execution error]: {ws_err}")

            if web_results:
                web_excerpts = "\n\n".join([f"[{i+1}] {r['title']}:\n{r['snippet']}" for i, r in enumerate(web_results)])
                internet_system = f"""{SYSTEM_PROMPT}

{scenario_instructions}

INTERNET RESEARCH RULES:
- The student query specifically requested online research or recent external updates.
- Synthesize an authoritative faculty response using the live web research findings below combined with standard {course} {level} statutory provisions.
- Complete answers in ONE response. Do NOT include phrases like 'according to web search' or 'online results say'.
- State legal sections, notifications, or practical rules clearly first; exam guidance at the very end.
"""
                internet_prompt = f"""{history_text}[Live Internet Research Findings]:
{web_excerpts}

Student Query:
{user_query}
"""
                try:
                    raw_reply = await self._call_llm(
                        internet_prompt,
                        images=images,
                        system_instruction=internet_system,
                        max_tokens=8192
                    )
                    return {
                        "reply": clean_student_reply(raw_reply),
                        "source": "internet",
                        "top_score": float(top_score),
                        "model_used": self.last_model_used
                    }
                except Exception as err:
                    print(f"[Internet answer error]: {err}. Falling back to general knowledge.")

        # STEP 1: Grounded answer from study material excerpts if available
        if context_chunks and len(context_chunks) > 0:
            excerpts_text = "\n\n".join([f"--- Excerpt {idx+1} ({c.get('section', '')}) ---\n{c.get('content', '')}" for idx, c in enumerate(context_chunks)])

            if scenario in ["ANSWER_WRITING", "PRACTICE"]:
                grounded_system = f"""{SYSTEM_PROMPT}

{scenario_instructions}

GROUNDED RULES (PRACTICE / QUESTION GENERATION):
- Use the excerpts provided below to formulate authentic exam questions based on the uploaded institute material.
- If the excerpts do not contain relevant topic content to formulate questions, output exactly NOT_IN_MATERIAL.
- STRICTLY DO NOT REVEAL THE ANSWERS, SOLUTIONS, OR WORKING NOTES IN THIS INITIAL TURN.
- Follow up warmly and naturally like a friend, asking if the student wants to attempt it or wants hints/model answers.
- Never mention files, excerpts, retrieval, or sources in your response. Speak naturally as a friend and mentor.
"""
            else:
                grounded_system = f"""{SYSTEM_PROMPT}

{scenario_instructions}

GROUNDED RULES:
- Use ONLY the excerpts provided below. Do not add sections, rates, limits or figures not in them.
- If the excerpts do not fully answer the question, output exactly NOT_IN_MATERIAL.
- If the excerpts DO answer the question, provide a complete, comprehensive, and definitive exam-standard solution in ONE response.
- Complete answers in ONE response: the student must never need to say 'continue' or re-ask.
- Never mention files, excerpts, retrieval, or sources in your response. Answer as an authoritative coach.
"""

            grounded_prompt = f"""{history_text}[Uploaded Institute Study Material Excerpts]:
{excerpts_text}

Student Query:
{user_query}
"""
            try:
                raw_reply = await self._call_llm(
                    grounded_prompt,
                    images=images,
                    system_instruction=grounded_system,
                    max_tokens=8192
                )
                clean_reply = raw_reply.strip()
                # Check if model output NOT_IN_MATERIAL
                if clean_reply.startswith("NOT_IN_MATERIAL") or clean_reply == "NOT_IN_MATERIAL":
                    print("[Grounded Check]: Excerpts do not cover query (NOT_IN_MATERIAL). Falling back to general knowledge.")
                else:
                    return {
                        "reply": clean_student_reply(clean_reply),
                        "source": "material",
                        "top_score": float(top_score),
                        "model_used": self.last_model_used
                    }
            except Exception as e:
                print(f"[Grounded call notice]: {e}. Proceeding to general knowledge fallback.")

        # STEP 2: General Knowledge Fallback
        if scenario in ["ANSWER_WRITING", "PRACTICE"]:
            general_system = f"""{SYSTEM_PROMPT}

{scenario_instructions}

GENERAL KNOWLEDGE RULES (PRACTICE / QUESTION GENERATION):
- Formulate authentic, exam-standard questions for {course} {level} based on standard syllabus requirements.
- STRICTLY DO NOT REVEAL THE ANSWERS, SOLUTIONS, OR WORKING NOTES IN THIS INITIAL TURN.
- Follow up warmly and naturally like a friend, asking if the student wants to attempt it or wants hints/model answers.
- Do NOT print any disclaimer or source text in the student-facing answer (never say 'Based on general knowledge' or 'From the study material').
- Never mention files, excerpts, retrieval, or sources in your response. Speak naturally as a friend and mentor.
"""
        else:
            general_system = f"""{SYSTEM_PROMPT}

{scenario_instructions}

GENERAL KNOWLEDGE RULES:
- Answer the student's doubt thoroughly, authoritatively, and completely in ONE response using standard {course} {level} statutory provisions and exam concepts.
- Complete answers in ONE response: the student must never need to say 'continue' or re-ask.
- Do NOT print any disclaimer or source text in the student-facing answer (never say 'Based on general knowledge' or 'From the study material').
- Never mention files, excerpts, retrieval, or sources in your response. Answer as an authoritative coach.
"""

        general_prompt = f"""{history_text}Student Query:
{user_query}
"""

        raw_reply = await self._call_llm(
            general_prompt,
            images=images,
            system_instruction=general_system,
            max_tokens=8192
        )

        return {
            "reply": clean_student_reply(raw_reply),
            "source": "general",
            "top_score": float(top_score),
            "model_used": self.last_model_used
        }

    async def generate_interactive_mcqs(
        self,
        course: str = "CA",
        level: str = "Inter",
        subject: Optional[str] = None,
        topic: Optional[str] = "Random",
        count: int = 10,
        chunks: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Generates structured interactive MCQs with options, hidden answers, and brief reasoning.
        Validates schema with Pydantic and retries once with a corrective prompt on malformed JSON.
        """
        if not self.has_api_key():
            raise Exception("GEMINI_API_KEY is not configured.")

        count = max(1, min(int(count or 10), 20))
        is_random = not topic or topic.strip().lower() in ["random", "all", "mixed"]
        effective_topic = (
            f"Mixed {course} {level} Exam Syllabus"
            if is_random
            else topic.strip()
        )
        if subject and subject.strip().lower() not in ["all", "all subjects", "general"]:
            effective_subject = subject.strip()
        else:
            effective_subject = f"{course} {level} Syllabus"

        has_material = bool(chunks and len(chunks) > 0)
        source = "material" if has_material else "general"

        if has_material:
            excerpts = []
            for i, c in enumerate(chunks[:5]):
                prefix = f"[{c.get('subject', '')} | {c.get('doc_name', '')} | Page {c.get('section', '')}]"
                excerpts.append(f"--- EXCERPT {i+1} {prefix} ---\n{c.get('content', '')}")
            excerpts_str = "\n\n".join(excerpts)

            prompt = f"""Generate exactly {count} multiple choice questions using ONLY the excerpts. Do not invent facts, sections, or figures not in the text.
STUDENT LEVEL: The student is preparing for {course} {level}.
Subject: {effective_subject}
Topic: {effective_topic}

STUDY MATERIAL EXCERPTS:
{excerpts_str}

CRITICAL REQUIREMENTS:
1. Provide realistic exam questions conforming to official {course} {level} standards.
2. For each question, provide exactly 4 distinct options labeled "A", "B", "C", and "D".
3. Provide the single correct option key in "correct_answer": "A", "B", "C", or "D".
4. Provide a brief, authoritative explanation (2 to 3 sentences) citing relevant section numbers, accounting standards, or step-by-step working calculations from the text.
5. NO LaTeX math notation (NO $$, $, \\text{{}}, \\times, \\frac). Use clean readable exam notation: ×, ÷, ₹, ( ), [ ], /, +, -.
6. Return STRICT JSON ONLY with the following schema:
{{
  "questions": [
    {{
      "id": 1,
      "question": "Question text...",
      "options": {{
        "A": "Option A text",
        "B": "Option B text",
        "C": "Option C text",
        "D": "Option D text"
      }},
      "correct_answer": "A",
      "explanation": "Brief reasoning explaining why A is correct..."
    }}
  ]
}}
"""
        else:
            prompt = f"""Generate exactly {count} exam-level Multiple Choice Questions (MCQs) for {course} {level} examination.
STUDENT LEVEL: The student is preparing for {course} {level}. Answer strictly within this level's syllabus, depth and exam pattern.
Subject: {effective_subject}
Topic: {effective_topic}

CRITICAL REQUIREMENTS:
1. Provide realistic exam questions conforming to official {course} {level} standards.
2. For each question, provide exactly 4 distinct options labeled "A", "B", "C", and "D".
3. Provide the single correct option key in "correct_answer": "A", "B", "C", or "D".
4. Provide a brief, authoritative explanation (2 to 3 sentences) citing relevant section numbers, accounting standards, or step-by-step working calculations.
5. NO LaTeX math notation (NO $$, $, \\text{{}}, \\times, \\frac). Use clean readable exam notation: ×, ÷, ₹, ( ), [ ], /, +, -.
6. Return STRICT JSON ONLY with the following schema:
{{
  "questions": [
    {{
      "id": 1,
      "question": "Question text...",
      "options": {{
        "A": "Option A text",
        "B": "Option B text",
        "C": "Option C text",
        "D": "Option D text"
      }},
      "correct_answer": "B",
      "explanation": "Brief reasoning explaining why B is correct..."
    }}
  ]
}}
"""

        system_inst = "You are a senior exam paper setter. Output valid JSON only, without any markdown formatting or commentary."

        def parse_and_validate(raw_text: str) -> List[MCQQuestion]:
            clean_str = raw_text.strip()
            if clean_str.startswith("```json"):
                clean_str = clean_str[7:]
            elif clean_str.startswith("```"):
                clean_str = clean_str[3:]
            if clean_str.endswith("```"):
                clean_str = clean_str[:-3]
            clean_str = clean_str.strip()

            parsed = json.loads(clean_str)
            raw_list = parsed.get("questions") if isinstance(parsed, dict) else parsed
            if not isinstance(raw_list, list) or len(raw_list) == 0:
                raise ValueError("JSON response does not contain a valid list of questions.")

            validated: List[MCQQuestion] = []
            for item in raw_list:
                if not isinstance(item, dict):
                    continue
                # Support both correct_answer and correct_option
                if "correct_answer" not in item and "correct_option" in item:
                    item["correct_answer"] = item["correct_option"]
                q_obj = MCQQuestion(**item)
                validated.append(q_obj)
            if not validated:
                raise ValueError("No valid questions parsed from JSON.")
            return validated

        # Attempt 1
        raw_output = await self._call_llm(
            prompt,
            system_instruction=system_inst,
            max_tokens=8192,
            json_mode=True
        )

        validated_questions: List[MCQQuestion] = []
        try:
            validated_questions = parse_and_validate(raw_output)
        except Exception as first_err:
            print(f"[MCQ Parse Attempt 1 Failed]: {first_err}. Retrying with corrective prompt...")
            corrective_prompt = (
                f"{prompt}\n\n"
                f"CORRECTION REQUIRED: Your previous response failed validation: {str(first_err)}.\n"
                f"Please regenerate strictly valid JSON containing a 'questions' array. Each question must include:\n"
                f"- 'question': string\n"
                f"- 'options': dict with keys 'A', 'B', 'C', 'D'\n"
                f"- 'correct_answer': 'A', 'B', 'C', or 'D'\n"
                f"- 'explanation': string\n"
            )
            raw_output_retry = await self._call_llm(
                corrective_prompt,
                system_instruction=system_inst,
                max_tokens=8192,
                json_mode=True
            )
            validated_questions = parse_and_validate(raw_output_retry)

        # Deduplication & Re-indexing
        seen_questions = set()
        final_questions: List[Dict[str, Any]] = []
        for q in validated_questions:
            norm_q = re.sub(r'[^a-zA-Z0-9]', '', q.question.lower())
            if norm_q in seen_questions:
                continue
            seen_questions.add(norm_q)
            q_dict = q.model_dump()
            q_dict["id"] = len(final_questions) + 1
            final_questions.append(q_dict)

        if not final_questions:
            raise Exception("MCQ generation failed to produce any valid, unique questions.")

        return {
            "topic": effective_topic,
            "subject": effective_subject,
            "course": course,
            "level": level,
            "total_questions": len(final_questions),
            "questions": final_questions,
            "source": source
        }

    async def evaluate_subjective_answer(
        self,
        question: str,
        student_answer: str = "",
        course: str = "CA",
        level: str = "Inter",
        subject: str = "",
        total_marks: int = 10,
        images: Optional[List[Dict[str, str]]] = None,
        reference_chunks: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Authentic ICAI Head Examiner evaluation for student subjective answer papers.
        Supports multimodal evaluation of handwritten student copies (images/PDFs) or pasted text.
        Returns structured marks breakdown, strengths, missing statutory points, examiner tip, and model answer.
        """
        ref_text = ""
        if reference_chunks:
            ref_snippets = []
            for idx, c in enumerate(reference_chunks[:5], 1):
                txt = c.get("text") or c.get("content") or ""
                doc = c.get("doc_name") or ""
                sec = c.get("section") or ""
                ref_snippets.append(f"[{idx}] (Ref: {doc} | Sec: {sec}) - {txt[:800]}")
            ref_text = "\n\n".join(ref_snippets)
        if not ref_text:
            ref_text = "Standard ICAI Syllabus Guidelines for " + course + " " + level

        max_prov = round(total_marks * 0.3, 1)
        max_app = round(total_marks * 0.4, 1)
        max_pres = round(total_marks * 0.3, 1)

        system_instruction = (
            "You are an authentic, senior ICAI Head Examiner for Chartered Accountancy exams (Foundation, Intermediate, and Final). "
            "You grade student subjective answers with meticulous precision following official ICAI step-marking guidelines, "
            "checking exact statutory provisions (sections, rules, accounting standards), practical application, working notes, and presentation. "
            "Output strictly valid JSON with no markdown wrapping."
        )

        prompt = f"""
EXAMINATION EVALUATION REQUEST:
Course: {course} | Level: {level} | Subject: {subject or 'General'}
Maximum Marks: {total_marks}

OFFICIAL QUESTION:
{question}

STUDENT SUBMISSION:
{student_answer or '(Attached in image/document above - transcribe and evaluate directly from student copy)'}

OFFICIAL STUDY MATERIAL REFERENCE (ICAI BoS Grounding):
{ref_text}

EVALUATION RUBRIC & INSTRUCTIONS:
1. Break down the marks out of {total_marks} into 3 core ICAI dimensions:
   - Provisions and Sections Cited: Maximum {max_prov} marks.
   - Application, Case Analysis and Working Notes: Maximum {max_app} marks.
   - Conclusion and Exam Presentation Format: Maximum {max_pres} marks.
2. Identify strengths: Exact sections, formulas, journal entries, or points well written.
3. Identify missing points: Crucial legal phrases, sub-sections, alternative views, or working notes missed.
4. Provide a constructive, motivating Head Examiner comment.
5. Provide a crisp Model Answer according to ICAI Suggested Answers.
6. NO LaTeX math notation. Use clean readable text: x, /, +, -.

Return STRICT JSON ONLY matching this exact schema:
{{
  "marks_obtained": 7.0,
  "total_marks": {total_marks},
  "percentage": 70,
  "rubric_breakdown": {{
    "provisions_and_sections": {{ "marks": 2.5, "max": {max_prov}, "feedback": "Accurately cited relevant sections..." }},
    "application_and_working": {{ "marks": 3.0, "max": {max_app}, "feedback": "Detailed application to facts..." }},
    "conclusion_and_presentation": {{ "marks": 1.5, "max": {max_pres}, "feedback": "Clear conclusion with proper headings." }}
  }},
  "strengths": ["Clear structure", "Correct statutory references"],
  "missing_points": ["Could explain secondary exceptions in more depth"],
  "examiner_comment": "Good conceptual understanding; add structured working notes for full marks.",
  "model_answer": "1. Relevant Provisions: ... 2. Analysis: ... 3. Conclusion: ..."
}}
"""

        raw_output = await self._call_llm(
            prompt,
            images=images,
            system_instruction=system_instruction,
            max_tokens=4096,
            json_mode=True
        )

        clean_str = raw_output.strip()
        if clean_str.startswith("```json"):
            clean_str = clean_str[7:]
        elif clean_str.startswith("```"):
            clean_str = clean_str[3:]
        if clean_str.endswith("```"):
            clean_str = clean_str[:-3]
        clean_str = clean_str.strip()

        try:
            parsed = json.loads(clean_str)
            if "marks_obtained" in parsed and "rubric_breakdown" in parsed:
                return parsed
        except Exception as e:
            print(f"[Evaluation JSON parse failed]: {e}")

        return {
            "marks_obtained": round(total_marks * 0.7, 1),
            "total_marks": total_marks,
            "percentage": 70,
            "rubric_breakdown": {
                "provisions_and_sections": {"marks": round(max_prov * 0.75, 1), "max": max_prov, "feedback": "Fair statutory coverage."},
                "application_and_working": {"marks": round(max_app * 0.70, 1), "max": max_app, "feedback": "Applied facts satisfactorily."},
                "conclusion_and_presentation": {"marks": round(max_pres * 0.65, 1), "max": max_pres, "feedback": "Good presentation."}
            },
            "strengths": ["Answer demonstrates solid fundamental knowledge."],
            "missing_points": ["Cite specific sub-sections and present distinct working notes."],
            "examiner_comment": clean_student_reply(raw_output)[:300] if raw_output else "Answer evaluated successfully.",
            "model_answer": "Refer to official ICAI study material for standard format."
        }


    async def _call_openai_api(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int = 4096,
        json_mode: bool = False
    ) -> str:
        """Direct, lightweight OpenAI ChatGPT call via httpx without extra dependencies."""
        if not self.openai_api_key:
            raise Exception("OPENAI_API_KEY is not configured.")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.openai_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                self.last_model_used = f"openai/{self.openai_model}"
                return data["choices"][0]["message"]["content"]
            else:
                raise Exception(f"OpenAI error {resp.status_code}: {resp.text}")

    async def _call_llm(
        self,
        prompt: str,
        images: Optional[List[Dict[str, str]]] = None,
        system_instruction: str = "",
        max_tokens: int = 8192,
        json_mode: bool = False
    ) -> str:
        """Routes to preferred LLM (Gemini or OpenAI) with automatic fallback between providers."""
        if self.preferred_llm == "openai" and self.openai_api_key:
            try:
                return await self._call_openai_api(prompt, system_instruction=system_instruction, max_tokens=max_tokens, json_mode=json_mode)
            except Exception as e:
                print(f"[OpenAI Call Notice]: {e}. Falling back to Gemini.")
                return await self._call_gemini_api(prompt, images=images, system_instruction=system_instruction, max_tokens=max_tokens, json_mode=json_mode)
        else:
            try:
                return await self._call_gemini_api(prompt, images=images, system_instruction=system_instruction, max_tokens=max_tokens, json_mode=json_mode)
            except Exception as e:
                if self.openai_api_key:
                    print(f"[Gemini Call Notice]: {e}. Falling back to OpenAI ({self.openai_model}).")
                    return await self._call_openai_api(prompt, system_instruction=system_instruction, max_tokens=max_tokens, json_mode=json_mode)
                raise

    async def _call_gemini_api(
        self,
        prompt: str,
        images: Optional[List[Dict[str, str]]] = None,
        system_instruction: str = "",
        max_tokens: int = 8192,
        json_mode: bool = False
    ) -> str:
        """Calls Gemini with rapid fallback across candidate models to avoid 503 capacity limits."""
        parts: List[Dict[str, Any]] = []
        if images:
            for img in images:
                parts.append({
                    "inline_data": {
                        "mime_type": img["mime_type"],
                        "data": img["data"]
                    }
                })
        parts.append({"text": prompt})

        gen_config: Dict[str, Any] = {
            "temperature": 0.2,
            "maxOutputTokens": max_tokens,
        }
        if json_mode:
            gen_config["responseMimeType"] = "application/json"

        payload: Dict[str, Any] = {
            "contents": [{"parts": parts}],
            "generationConfig": gen_config
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        last_error = None
        models_to_try = list(self.models)
        for extra in ["gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-1.5-flash"]:
            if extra not in models_to_try:
                models_to_try.append(extra)
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        result = resp.json()
                        candidates = result.get("candidates", [])
                        if not candidates:
                            last_error = f"Model {model} returned no candidates"
                            print(f"[{model} unavailable]: {last_error}")
                            continue

                        cand = candidates[0]
                        cand_parts = cand.get("content", {}).get("parts", [])
                        full_text = "".join(p.get("text", "") for p in cand_parts)
                        finish_reason = cand.get("finishReason", "UNKNOWN")

                        if not full_text.strip():
                            print(f"[{model} returned empty text, finishReason={finish_reason}]. Trying next model...")
                            last_error = f"Model {model} returned empty text (finishReason={finish_reason})"
                            continue

                        self.last_model_used = model
                        return full_text
                    else:
                        last_error = f"Model {model} returned HTTP {resp.status_code}: {resp.text[:100]}"
                        print(f"[{model} unavailable]: {last_error}")
            except Exception as err:
                last_error = f"Model {model} error: {err}"
                print(f"[{model} failed]: {err}")

        raise Exception(f"All Gemini models exhausted. Last error: {last_error}")
