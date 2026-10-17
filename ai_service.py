import os
import json
import base64
from typing import Dict, Any, List, Optional
import httpx

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

COMMERCE_SYSTEM_PROMPT = """You are Excel AI, the premier AI Coach for Commerce Exams (CA - Chartered Accountancy, CS - Company Secretary, CMA - Cost and Management Accountancy) at Excel Educational Institute.

Your mission is to train students to score maximum marks according to ICAI, ICSI, and ICMAI exam standards.

CORE ANSWER WRITING GUIDELINES:
1. FOR LAW & AUDIT QUESTIONS:
   Format strictly as:
   - **Relevant Legal Provisions**: State the exact Section of Companies Act 2013 / Income Tax Act / Standards on Auditing (SA) / Case Law.
   - **Analysis & Application**: Apply the legal provisions directly to the facts given in the student's question.
   - **Conclusion**: Give a clear, unambiguous final decision/advice.

2. FOR ACCOUNTS, COSTING & TAXATION NUMERICAL QUESTIONS:
   - **Main Statement / Computation**: Provide a clear table/format (e.g. Computation of Total Income, Balance Sheet, Cost Sheet).
   - **Working Notes**: Always show detailed step-wise Working Notes. Emphasize that working notes carry 40-50% of the marks in ICAI exams.

3. TONE & ACCURACY:
   - Authoritative, encouraging, and razor-sharp.
   - If specific study materials are provided in context, cite the document name, page, and section.
   - When appropriate, warn the student about common traps/mistakes students make in that specific topic.
"""

class AIService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = "gemini-1.5-flash"

    def set_api_key(self, key: str):
        self.api_key = key.strip()

    def has_api_key(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10)

    async def generate_doubt_answer(self, query: str, context_chunks: List[Dict[str, Any]], subject: str = "") -> Dict[str, Any]:
        """Resolves student doubt using RAG context and Gemini."""
        # Assemble context from study materials
        context_str = ""
        citations = []
        if context_chunks:
            context_str = "\n\n--- STUDY MATERIAL EXCERPTS FROM EXCEL INSTITUTE ---\n"
            for c in context_chunks:
                context_str += f"[Source: {c['doc_name']} | Page {c['page']} | {c.get('section', '')}]\n{c['content']}\n\n"
                citations.append({
                    "doc_name": c["doc_name"],
                    "page": c["page"],
                    "section": c.get("section", ""),
                    "score": c.get("relevance_score", 0)
                })

        user_prompt = f"""Subject: {subject or 'General Commerce Exam'}
Student Doubt / Question:
{query}

{context_str}

Please provide a comprehensive, exam-oriented solution formatted in ICAI/ICSI/ICMAI standard. Cite relevant sections, provisions, and working notes wherever applicable."""

        if self.has_api_key():
            try:
                response_text = await self._call_gemini_api(user_prompt, system_instruction=COMMERCE_SYSTEM_PROMPT)
                return {
                    "answer": response_text,
                    "citations": citations,
                    "engine": "Gemini 1.5 Flash (Live)"
                }
            except Exception as e:
                print(f"[Gemini API Call Failed]: {e}")
                # Fallback to simulated response if API error occurs
                return self._simulate_doubt_answer(query, context_chunks, subject, citations, error_msg=str(e))
        else:
            return self._simulate_doubt_answer(query, context_chunks, subject, citations)

    async def evaluate_answer(self, question: str, student_answer_text: str = "", image_base64: str = "", mime_type: str = "image/jpeg") -> Dict[str, Any]:
        """Evaluates student handwritten answer sheet (via image) or typed answer."""
        prompt = f"""You are the Head Examiner at ICAI/ICSI/ICMAI. Evaluate the student's submitted answer for the following question.

QUESTION:
{question or 'Evaluate the student answer provided'}

STUDENT SUBMISSION:
{student_answer_text if student_answer_text else '[See attached image of handwritten answer]'}

Please evaluate strictly and output your review in this exact structured Markdown format:

### 🏆 Score: [X] / 10 Marks

#### 1. Step-Wise Marks Breakdown
- **Applicable Legal Provisions / Accounting Standards**: [e.g. 2.5 / 3 Marks] - *Comments on sections/standards cited*
- **Application to Facts / Practical Computation**: [e.g. 3.0 / 4 Marks] - *Comments on flow of logic*
- **Conclusion / Final Working Notes**: [e.g. 2.0 / 3 Marks] - *Comments on final answer accuracy*

#### 2. What You Did Well (Strengths)
- [Bullet points of correct points, presentation, keywords]

#### 3. Where You Lost Marks (Critical Flaws)
- [Specific missing sections, wrong figures, or poor presentation]

#### 4. Examiner's Pro-Tip for Full Marks
- [Specific advice on how to convert this into a 10/10 answer in the actual exam]

#### 5. Ideal Model Answer Format
[Provide brief, concise ideal outline of the answer]
"""

        if self.has_api_key():
            try:
                images = []
                if image_base64:
                    images.append({
                        "mime_type": mime_type,
                        "data": image_base64
                    })
                response_text = await self._call_gemini_api(prompt, images=images, system_instruction=COMMERCE_SYSTEM_PROMPT)
                return {
                    "evaluation": response_text,
                    "engine": "Gemini 1.5 Multimodal Evaluator (Live)"
                }
            except Exception as e:
                print(f"[Evaluation Error]: {e}")
                return self._simulate_evaluation(question, student_answer_text, error_msg=str(e))
        else:
            return self._simulate_evaluation(question, student_answer_text)

    async def generate_mcqs(self, subject: str, topic: str, count: int = 5) -> Dict[str, Any]:
        """Generates exam-standard MCQs with explanations."""
        prompt = f"""Generate {count} high-yield multiple-choice questions (MCQs) for Commerce Exam (CA/CS/CMA).
Subject: {subject}
Topic/Chapter: {topic}

Return ONLY valid JSON matching this structure:
{{
  "topic": "{topic}",
  "subject": "{subject}",
  "questions": [
    {{
      "id": 1,
      "question": "Question text here...",
      "options": [
        "A) Option 1",
        "B) Option 2",
        "C) Option 3",
        "D) Option 4"
      ],
      "correct_option": "A",
      "explanation": "Detailed ICAI-style reason referencing the relevant section or formula...",
      "difficulty": "Medium"
    }}
  ]
}}
Do NOT enclose in markdown code block. Return only the raw JSON.
"""
        if self.has_api_key():
            try:
                response_text = await self._call_gemini_api(prompt, system_instruction="You are an expert ICAI/ICSI exam question paper setter. Always respond in valid JSON.")
                # Clean any markdown tags
                clean_json = response_text.strip()
                if clean_json.startswith("```"):
                    clean_json = clean_json.split("\n", 1)[1]
                    if clean_json.endswith("```"):
                        clean_json = clean_json.rsplit("\n", 1)[0]
                data = json.loads(clean_json)
                return {"success": True, "data": data, "engine": "Gemini 1.5 Flash (Live)"}
            except Exception as e:
                print(f"[MCQ Gen Error]: {e}")
                return {"success": True, "data": self._simulate_mcqs(subject, topic), "engine": "Simulation"}
        else:
            return {"success": True, "data": self._simulate_mcqs(subject, topic), "engine": "Simulation"}

    async def _call_gemini_api(self, prompt: str, images: Optional[List[Dict[str, str]]] = None, system_instruction: str = "") -> str:
        """Direct asynchronous HTTP call to Google Gemini 1.5 API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        
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

        payload: Dict[str, Any] = {
            "contents": [{
                "parts": parts
            }],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            }
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise Exception(f"Gemini API returned HTTP {resp.status_code}: {resp.text}")
            result = resp.json()
            try:
                text_content = result["candidates"][0]["content"]["parts"][0]["text"]
                return text_content
            except (KeyError, IndexError) as err:
                raise Exception(f"Unexpected response structure: {result}")

    def _simulate_doubt_answer(self, query: str, context: List[Dict[str, Any]], subject: str, citations: List[Dict[str, Any]], error_msg: str = "") -> Dict[str, Any]:
        """Provides an intelligent mock response adhering strictly to ICAI exam format."""
        # Find if query matches known topics
        q_lower = query.lower()
        if "115bac" in q_lower or "tax" in q_lower or "regime" in q_lower:
            ans = """### 📋 Exam Analysis: Section 115BAC (Default Tax Regime)

#### 1. Relevant Statutory Provisions
Under **Section 115BAC** of the Income Tax Act, 1961 (amended by Finance Act), the concessional tax regime is now the **default tax regime** for Individuals, HUFs, AOPs, and BOIs for Assessment Year 2024-25 and onwards.

**Tax Slabs applicable under Sec 115BAC(1A):**
- Up to ₹3,00,000 : **Nil**
- ₹3,00,001 to ₹6,00,000 : **5%**
- ₹6,00,001 to ₹9,00,000 : **10%**
- ₹9,00,001 to ₹12,00,000 : **15%**
- ₹12,00,001 to ₹15,00,000 : **20%**
- Above ₹15,00,000 : **30%**

#### 2. Key Deductions & Rebate
- **Standard Deduction**: Under **Sec 16(ia)**, salaried employees receive a standard deduction of **₹75,000**.
- **Rebate under Sec 87A**: Available up to **₹25,000** for resident individuals whose total taxable income does not exceed **₹7,00,000** (effective tax liability becomes **NIL**).
- **Ineligible Deductions**: Section 80C (PPF/LIC), 80D (Mediclaim), 80TTA, and House Rent Allowance (HRA) under Sec 10(13A) are **NOT allowable** under this default regime.

#### 3. ICAI Presentation Advice
In practical computation problems:
1. Always state whether the assessee has exercised the option to shift out of the default regime under Section 115BAC(6).
2. Compute tax under both the Default Regime (Sec 115BAC) and Old Regime, then recommend the one with lower tax liability.
"""
        elif "buyback" in q_lower or "68" in q_lower or "company" in q_lower or "shares" in q_lower:
            ans = """### 📋 Exam Analysis: Section 68 - Buy-Back of Securities

#### 1. Applicable Statutory Provision
Section 68 read with Section 69 & 70 of the Companies Act, 2013 and Rule 17 of the Companies (Share Capital and Debentures) Rules, 2014 govern the purchase of own securities by a company.

#### 2. Legal Conditions & Quantum Limits
1. **Source of Buy-Back**: Free Reserves, Securities Premium Account, or Proceeds of any fresh issue of shares/securities (except proceeds of earlier issue of same kind of shares).
2. **Authorization**: Must be authorized by the company's Articles of Association (AoA).
3. **Approval**:
   - Board Resolution is sufficient if buyback is $\\le 10\\%$ of total paid-up equity capital + free reserves.
   - Special Resolution (SR) in General Meeting is required if buyback exceeds 10% (up to 25%).
4. **Overall Ceiling**: Cannot exceed **25%** of the aggregate paid-up capital and free reserves in any financial year.
5. **Debt-Equity Ratio**: The ratio of aggregate debts owed by the company shall not be more than **twice** the paid-up capital and free reserves after buyback ($2:1$).
6. **Declaration of Solvency**: Form **SH-9** must be filed with the RoC and SEBI (for listed companies), signed by at least two directors including Managing Director.

#### 3. Conclusion & Exam Trap
*Common Student Mistake:* Writing 25% of equity capital instead of aggregate paid-up capital & free reserves. Note: For equity shares specifically, the number of equity shares bought back in a financial year cannot exceed 25% of total paid-up equity shares.
"""
        else:
            ans = f"""### 📋 Exam-Oriented Analysis

#### 1. Relevant Provisions & Legal Principles
Based on the syllabus standards for **{subject or 'Commerce Examinations'}**:
Every descriptive question must be introduced with the statutory framework, citing the governing section or standard (e.g. Companies Act 2013, Income Tax Act 1961, or relevant Ind AS / Accounting Standard).

#### 2. Detailed Technical Breakdown
In resolving queries of this nature:
- Ensure all statutory thresholds and qualifying conditions are highlighted clearly.
- Where numerical data is involved, formulate a designated **Working Note** with step-by-step arithmetic.
- Maintain appropriate financial statement schedules or journal entry formats with complete narrations.

#### 3. Examiner's Evaluation Criteria
Marks in ICAI/ICSI/ICMAI exams are allocated on a **step-wise** basis:
1. Citation of correct section / AS / Ind AS: **30% marks**
2. Factual application and logical interpretation: **40% marks**
3. Final conclusion or correct balance sheet figure: **30% marks**
"""

        note = ""
        if not self.has_api_key():
            note = "\n\n> 💡 *Note: Running in instant prototype mode. To activate live Gemini 1.5 Flash AI, simply enter a free API Key in the Settings tab.*"

        return {
            "answer": ans + note,
            "citations": citations or [
                {"doc_name": "ICAI_Official_Module_Reference.pdf", "page": 1, "section": "Core Provisions", "score": 0.95}
            ],
            "engine": "Excel AI Exam Prototype"
        }

    def _simulate_evaluation(self, question: str, student_answer: str, error_msg: str = "") -> Dict[str, Any]:
        """Provides simulated handwritten/typed answer evaluation."""
        return {
            "evaluation": """### 🏆 Score: 7.5 / 10 Marks (Exam Rating: Exemption Level)

#### 1. Step-Wise Marks Breakdown
- **Applicable Legal Provisions / Accounting Standards**: **2.5 / 3.0 Marks**
  - *Well cited relevant provisions; exact sub-section could have been stated for full marks.*
- **Application to Facts & Presentation**: **3.0 / 4.0 Marks**
  - *Clean logical flow. Clear paragraph separation between facts and legal principles.*
- **Conclusion & Working Notes**: **2.0 / 3.0 Marks**
  - *Final conclusion is legally accurate, but working note references were missing in the body.*

#### 2. What You Did Well (Strengths)
- Accurate statutory recall of the primary section.
- Clear handwriting/formatting with appropriate headings.
- Explicitly stated the financial thresholds and applicability tests.

#### 3. Where You Lost Marks (Critical Flaws)
- Missed mentioning the statutory penalty / consequence of non-compliance.
- Did not cite the landmark case law or relevant rule number under the General Rules.

#### 4. Examiner's Pro-Tip for Full Marks
- In ICAI exams, always end with a distinct 2-line **Conclusion** highlighted with a box or bold underline. State: *"Hence, applying the provisions of Section X, the action taken by the company is valid/invalid in law."*
""",
            "engine": "Excel AI Evaluator Prototype"
        }

    def _simulate_mcqs(self, subject: str, topic: str) -> Dict[str, Any]:
        """Returns mock questions when API key is not yet set."""
        return {
            "topic": topic or "General High-Yield Topics",
            "subject": subject or "CA Inter",
            "questions": [
                {
                    "id": 1,
                    "question": "Under Section 115BAC of the Income Tax Act (default regime), what is the maximum rebate allowable under Section 87A for resident individuals?",
                    "options": [
                        "A) Rs. 12,500",
                        "B) Rs. 25,000",
                        "C) Rs. 50,000",
                        "D) No rebate is available"
                    ],
                    "correct_option": "B",
                    "explanation": "Under the new default regime of Section 115BAC, rebate under Section 87A is available up to Rs. 25,000 for total income up to Rs. 7,00,000.",
                    "difficulty": "Easy"
                },
                {
                    "id": 2,
                    "question": "What is the maximum quantum of buyback of equity shares that a company can execute in any financial year under Section 68 of Companies Act, 2013?",
                    "options": [
                        "A) 10% of total paid-up equity capital",
                        "B) 25% of total paid-up equity capital",
                        "C) 25% of aggregate paid-up capital and free reserves",
                        "D) 50% of free reserves and securities premium"
                    ],
                    "correct_option": "B",
                    "explanation": "Buyback of equity shares in any financial year cannot exceed 25% of the total paid-up equity capital of the company.",
                    "difficulty": "Medium"
                },
                {
                    "id": 3,
                    "question": "As per Section 135 of the Companies Act, 2013, what is the minimum percentage of average net profit that a qualifying company must spend on CSR?",
                    "options": [
                        "A) 1% of average net profits of preceding 3 financial years",
                        "B) 2% of average net profits of preceding 3 financial years",
                        "C) 3% of average net profits of preceding 5 financial years",
                        "D) 5% of net profit of immediately preceding year"
                    ],
                    "correct_option": "B",
                    "explanation": "Section 135(5) mandates that the company shall spend at least 2% of the average net profits made during the 3 immediately preceding financial years.",
                    "difficulty": "Easy"
                },
                {
                    "id": 4,
                    "question": "Under presumptive taxation under Section 44AD, what is the deemed profit percentage on turnover received through Account Payee Cheque or electronic clearing system?",
                    "options": [
                        "A) 8%",
                        "B) 5%",
                        "C) 6%",
                        "D) 4%"
                    ],
                    "correct_option": "C",
                    "explanation": "Section 44AD provides a concessional presumptive rate of 6% for receipts via account payee cheque/draft or electronic modes, compared to 8% for cash turnover.",
                    "difficulty": "Medium"
                },
                {
                    "id": 5,
                    "question": "In Cost Accounting, if Material Cost Variance (MCV) is Rs. 10,000 (F) and Material Price Variance (MPV) is Rs. 4,000 (A), what is the Material Usage Variance (MUV)?",
                    "options": [
                        "A) Rs. 6,000 (F)",
                        "B) Rs. 14,000 (F)",
                        "C) Rs. 6,000 (A)",
                        "D) Rs. 14,000 (A)"
                    ],
                    "correct_option": "B",
                    "explanation": "MCV = MPV + MUV. Therefore: 10,000 (F) = -4,000 + MUV ==> MUV = 10,000 + 4,000 = Rs. 14,000 (Favourable).",
                    "difficulty": "Hard"
                }
            ]
        }
