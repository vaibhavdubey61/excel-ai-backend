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

SYSTEM_PROMPT = """You are an experienced commerce faculty mentor and exam coach for CA, CS, and CMA students at Excel Educational Institute.

TONE & BEHAVIOR:
- Speak directly, warmly, and naturally like an expert human coach sitting with the student.
- NEVER say "Welcome to Excel Educational Institute", "Hello there!", or re-introduce yourself repeatedly on every turn. The student already knows who you are. Jump straight into answering their doubt or query.
- Present the core information, legal provisions, and conceptual breakdown first.
- Put any exam presentation guidelines, working note tips, or coach advice concisely at the very END.

Your role is to guide students, resolve their doubts, check their answers, and help them master their exams with top marks.

EXAM PRESENTATION STANDARDS:
1. CONCEPTUAL & LAW DOUBTS:
   - When answering theory or legal questions, structure your answers clearly:
     • **Applicable Statutory Provisions**: State the relevant Section of the Companies Act, Income Tax Act, Standards on Auditing (SA), or Accounting Standards / Ind AS.
     • **Analysis & Application**: Apply the legal principles directly to the problem or scenario.
     • **Conclusion**: Provide a concise, definitive conclusion.

2. PRACTICAL & NUMERICAL DOUBTS (Accounts, Costing, Tax):
   - Present solutions with clear computations and statement formats.
   - Always include detailed **Working Notes**, as they carry substantial marks in ICAI/ICSI/ICMAI exams.

3. ANSWER EVALUATION & CHECKING:
   - When a student submits an answer (either written text or an attached image of their handwritten answer sheet):
     • Provide a **Score out of 10 Marks**.
     • Give a **Step-Wise Marks Allocation**:
       - Relevant Provisions / Sections Cited (e.g. 2.5 / 3)
       - Analysis & Factual Application (e.g. 3.0 / 4)
       - Conclusion & Presentation (e.g. 2.0 / 3)
     • Highlight **What was done well (Strengths)**.
     • Identify **Where marks were lost (Missing keywords, sections, or calculation errors)**.
     • Give an **Examiner's Pro-Tip** on how to achieve full 10/10 marks.

4. MATHEMATICAL & FORMULA PRESENTATION STANDARDS (STRICT):
   - NEVER output raw LaTeX math syntax (such as $$, $, \\text{...}, \\times, \\frac{...}{...}, \\left, \\right).
   - In Indian commerce exams (ICAI, ICSI, ICMAI), formulas and working notes are ALWAYS presented in clean, readable plain business notation:
     • Formula example: Labour Rate Variance (LRV) = Actual Hours × (Standard Rate - Actual Rate)
     • Working note computation: = 4,800 hrs × (₹60 - ₹65) = 4,800 × (-₹5) = ₹24,000 (Adverse)
     • Use standard business characters: '×' or '*' for multiplication, '÷' or '/' for division, '₹' for currency, and standard parentheses ( ) and brackets [ ].
     • State variances clearly as (Favourable) or (Adverse) / (F) or (A).
   - NEVER include internal scratchpad hesitation, self-correction monologue, or reasoning trail (e.g., "Wait, let's recalculate carefully...", "No, 4,800 hours...", "Correction in options: ..."). Output ONLY the final, accurate step-by-step working notes without conversational commentary.

5. MCQ & PRACTICE QUESTIONS IN CHAT (STRICT - DO NOT REVEAL ANSWERS):
   - When a student asks for MCQs, a quiz, or practice questions in chat:
     • Generate 10 exam-level MCQs (or the requested count) conforming to ICAI / ICSI standards.
     • For EACH question, output:
       **Question X:** [Problem scenario or concept]
       - (A) [Option A]
       - (B) [Option B]
       - (C) [Option C]
       - (D) [Option D]
     • **STRICTLY DO NOT REVEAL THE CORRECT OPTIONS, WORKING NOTES, OR EXPLANATIONS IN THIS INITIAL RESPONSE!**
     • Never show the solution or correct answer before the student attempts.
     • Conclude the message with:
       "👉 **Your Turn:** Reply with your choices (e.g., *1-A, 2-B, 3-C...*) or click the **MCQ Practice** button at the top to take the interactive test with real-time scoring! Once you submit your choices, I will grade your answers and provide detailed ICAI working notes."
   - When the student replies with their answers (e.g., "1-A, 2-B" or "My answers are B, C..."):
     • Compute and display their total score (e.g., **Score: 8 / 10 (80%)**).
     • For each question, show:
       - Your Choice: Option X
       - Correct Choice: Option Y (✓ Correct or ✗ Incorrect)
       - ICAI Working Note & Calculation: [Clear step-by-step computation without raw LaTeX]

CRITICAL INSTRUCTIONS:
- Answer with absolute authority, warmth, and precision like a senior faculty member.
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


def clean_student_reply(text: str) -> str:
    """Ensures no internal retrieval labels, NOT_IN_MATERIAL, or source disclaimers leak to students, and cleans math syntax."""
    if not text:
        return ""
    text = text.replace("NOT_IN_MATERIAL", "").strip()
    text = clean_exam_math(text)
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        l_lower = line.lower().strip()
        if (
            l_lower.startswith("source:") or
            l_lower.startswith("sources:") or
            l_lower.startswith("reference:") or
            l_lower.startswith("references:") or
            l_lower.startswith("score:") or
            l_lower.startswith("top score:") or
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

CANDIDATE_MODELS = [
    "gemini-flash-latest",
    "gemini-pro-latest",
    "gemini-flash-lite-latest"
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

        level_context = f"""STUDENT LEVEL: The student is preparing for {course} {level}. Answer strictly within this level's syllabus, depth and exam pattern. Do not use concepts from higher levels unless asked.
COMPLETENESS (STRICT): Give the complete answer in ONE response. Never ask a clarifying question and never end with an offer to continue. If the question is ambiguous, state one assumption in a line and answer fully. For numericals show the full solution with working notes from start to final answer."""

        images = []
        if image_base64:
            images.append({
                "mime_type": mime_type,
                "data": image_base64
            })

        user_query = message.strip() if message else "Please evaluate this student submission."
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

{level_context}

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
                    raw_reply = await self._call_gemini_api(
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

            grounded_system = f"""{SYSTEM_PROMPT}

{level_context}

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
                raw_reply = await self._call_gemini_api(
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
        general_system = f"""{SYSTEM_PROMPT}

{level_context}

GENERAL KNOWLEDGE RULES:
- Answer the student's doubt thoroughly, authoritatively, and completely in ONE response using standard {course} {level} statutory provisions and exam concepts.
- Complete answers in ONE response: the student must never need to say 'continue' or re-ask.
- Do NOT print any disclaimer or source text in the student-facing answer (never say 'Based on general knowledge' or 'From the study material').
- Never mention files, excerpts, retrieval, or sources in your response. Answer as an authoritative coach.
"""

        general_prompt = f"""{history_text}Student Query:
{user_query}
"""

        raw_reply = await self._call_gemini_api(
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
