import os
import re
from typing import List, Dict, Any, Optional
import pypdf
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

STUDY_MATERIALS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "study_materials")

# Pre-packaged sample high-yield study knowledge for instant testing without uploading files
SAMPLE_KNOWLEDGE_BASE = [
    {
        "subject": "CA_Inter_Taxation",
        "doc_name": "ICAI_Income_Tax_Chapter4_Salaries_Deductions.pdf",
        "page": 42,
        "section": "Sec 115BAC (Default Tax Regime)",
        "content": (
            "Section 115BAC (Concessional / Default Tax Regime): "
            "From Assessment Year 2024-25 onwards, Section 115BAC is the default tax regime for Individuals, HUFs, AOP, BOI, and AJP. "
            "Tax Slabs under Sec 115BAC(1A): "
            "Up to Rs. 3,00,000: Nil; Rs. 3,00,001 to Rs. 6,00,000: 5%; Rs. 6,00,001 to Rs. 9,00,000: 10%; "
            "Rs. 9,00,001 to Rs. 12,00,000: 15%; Rs. 12,00,001 to Rs. 15,00,000: 20%; Above Rs. 15,00,000: 30%. "
            "Rebate under Section 87A: Under the new regime, rebate is available up to Rs. 25,000 for total income up to Rs. 7,00,000 (tax becomes Nil). "
            "Standard Deduction under Sec 16(ia) is allowed up to Rs. 75,000 (amended by Finance Act). "
            "Deductions NOT allowed under 115BAC: Section 80C, 80D, 80TTA, HRA under Sec 10(13A), LTA under Sec 10(5)."
        )
    },
    {
        "subject": "CA_Inter_Taxation",
        "doc_name": "ICAI_Income_Tax_Chapter5_PGBP.pdf",
        "page": 89,
        "section": "Sec 44AD (Presumptive Taxation for Business)",
        "content": (
            "Section 44AD: Presumptive Taxation Scheme for Eligible Business. "
            "Eligibility: Resident Individual, HUF, or Partnership Firm (excluding LLP). "
            "Turnover limit: Up to Rs. 2 Crore (increased to Rs. 3 Crore if cash receipts do not exceed 5% of total turnover). "
            "Presumptive Income Rate: 8% of total turnover/gross receipts; or 6% in respect of amount received through account payee cheque, "
            "bank draft, ECS, or prescribed electronic modes on or before the due date of filing return under Section 139(1). "
            "Advance Tax: The assessee is required to pay 100% of advance tax in a single installment on or before 15th March of the financial year. "
            "Audit requirement under Sec 44AB does not apply if income is declared at 8% / 6% or higher."
        )
    },
    {
        "subject": "CA_Inter_Corporate_Law",
        "doc_name": "ICAI_Companies_Act_2013_Share_Capital.pdf",
        "page": 115,
        "section": "Sec 68 (Buyback of Securities)",
        "content": (
            "Section 68 of Companies Act, 2013: Power of Company to Purchase its Own Securities (Buy-back). "
            "Sources of Buy-Back: Free reserves, Securities Premium account, or proceeds of any shares or specified securities. "
            "Conditions: "
            "1. Authorized by Articles of Association (AoA). "
            "2. Special Resolution passed at General Meeting (Board Resolution is sufficient if buyback is <= 10% of total paid-up equity capital and free reserves). "
            "3. Quantum limit: Maximum 25% of the aggregate of paid-up capital and free reserves in any financial year. Buy-back of equity shares in any financial year cannot exceed 25% of total paid-up equity capital. "
            "4. Debt-Equity Ratio post buy-back should not exceed 2:1. "
            "5. Fully paid-up shares only. "
            "6. Solvency Declaration (Form SH-9) must be signed by at least 2 directors (one must be MD if any) and verified by affidavit."
        )
    },
    {
        "subject": "CA_Inter_Corporate_Law",
        "doc_name": "ICAI_Companies_Act_2013_Management_Admin.pdf",
        "page": 178,
        "section": "Sec 135 (Corporate Social Responsibility)",
        "content": (
            "Section 135: Corporate Social Responsibility (CSR). "
            "Applicability: Every company having Net Worth >= Rs. 500 Crore, OR Turnover >= Rs. 1000 Crore, OR Net Profit >= Rs. 5 Crore during immediately preceding financial year. "
            "CSR Committee: 3 or more directors, with at least 1 Independent Director (where company is not required to have ID, 2 or more directors). "
            "CSR Expenditure: Company must spend at least 2% of the average net profits made during the 3 immediately preceding financial years in pursuance of its CSR policy (Schedule VII activities). "
            "Unspent CSR amount: If relating to ongoing project, transfer within 30 days to Unspent CSR Account in scheduled bank, and spend within 3 financial years, else transfer to Fund specified in Schedule VII within 30 days of completion of 3rd FY."
        )
    },
    {
        "subject": "CA_Inter_Costing",
        "doc_name": "ICAI_Cost_Accounting_Standard_Costing.pdf",
        "page": 210,
        "section": "Standard Costing - Material & Labour Variances",
        "content": (
            "Material Cost Variance (MCV) = Standard Cost - Actual Cost = (SQ x SP) - (AQ x AP). "
            "Material Price Variance (MPV) = Actual Quantity x (Standard Price - Actual Price) = AQ x (SP - AP). "
            "Material Usage Variance (MUV) = Standard Price x (Standard Quantity - Actual Quantity) = SP x (SQ - AQ). "
            "Verification: MCV = MPV + MUV. "
            "Labour Cost Variance (LCV) = (SH x SR) - (AH x AR). "
            "Labour Rate Variance (LRV) = AH x (SR - AR). "
            "Labour Efficiency Variance (LEV) = SR x (SH - AH)."
        )
    },
    {
        "subject": "CA_Inter_Auditing",
        "doc_name": "ICAI_Auditing_Standards_SA200_Series.pdf",
        "page": 35,
        "section": "SA 240 (Auditor's Responsibilities Relating to Fraud)",
        "content": (
            "SA 240: The Auditor's Responsibilities Relating to Fraud in an Audit of Financial Statements. "
            "Definition of Fraud: An intentional act by one or more individuals among management, those charged with governance, employees, or third parties, involving deception to obtain an unjust or illegal advantage. "
            "Two types of intentional misstatements relevant to the auditor: "
            "1. Misstatements resulting from fraudulent financial reporting (e.g. manipulation, falsification, alteration of records). "
            "2. Misstatements resulting from misappropriation of assets (e.g. embezzling receipts, stealing assets). "
            "Primary responsibility for prevention and detection of fraud rests with both TCWG (Those Charged with Governance) and Management. "
            "Auditor's objective: Maintain professional skepticism throughout the audit, recognizing that fraud may involve sophisticated schemes to conceal it."
        )
    }
]


class RAGEngine:
    def __init__(self, storage_dir: str = STUDY_MATERIALS_DIR, auto_load: bool = False):
        self.storage_dir = storage_dir
        self.chunks: List[Dict[str, Any]] = list(SAMPLE_KNOWLEDGE_BASE)
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        os.makedirs(self.storage_dir, exist_ok=True)
        self._fit_vectorizer()
        if auto_load:
            self.load_all_materials()

    def get_subject_folders(self) -> List[str]:
        """Returns list of all subject folders inside study_materials."""
        if not os.path.exists(self.storage_dir):
            return []
        items = [d for d in os.listdir(self.storage_dir) if os.path.isdir(os.path.join(self.storage_dir, d))]
        # Ensure default subjects exist
        default_subjects = [
            "CA_Inter_Taxation",
            "CA_Inter_Corporate_Law",
            "CA_Inter_Costing",
            "CA_Inter_Auditing",
            "CS_Executive_Company_Law",
            "CMA_Direct_Tax"
        ]
        for sub in default_subjects:
            sub_path = os.path.join(self.storage_dir, sub)
            os.makedirs(sub_path, exist_ok=True)
            if sub not in items:
                items.append(sub)
        return sorted(items)

    def extract_text_from_pdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extracts text per page from a PDF file."""
        pages_data = []
        try:
            reader = pypdf.PdfReader(pdf_path)
            doc_name = os.path.basename(pdf_path)
            for page_idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                clean_text = re.sub(r'\s+', ' ', text).strip()
                if len(clean_text) > 40:  # Skip blank or header-only pages
                    pages_data.append({
                        "doc_name": doc_name,
                        "page": page_idx + 1,
                        "text": clean_text
                    })
        except Exception as e:
            print(f"Error parsing PDF {pdf_path}: {e}")
        return pages_data

    def chunk_text(self, text: str, chunk_size: int = 400, overlap: int = 50) -> List[str]:
        """Splits long text into overlapping chunks."""
        words = text.split()
        if len(words) <= chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            start += chunk_size - overlap
        return chunks

    def _fit_vectorizer(self):
        if self.chunks:
            corpus = [f"{c['subject']} {c.get('section', '')} {c['content']}" for c in self.chunks]
            self.vectorizer = TfidfVectorizer(stop_words='english', max_features=10000, ngram_range=(1, 2))
            self.tfidf_matrix = self.vectorizer.fit_transform(corpus)

    def load_all_materials(self):
        """Loads and indexes both prepackaged sample knowledge and all uploaded PDFs."""
        self.chunks = []

        # 1. Load built-in sample knowledge base
        for sample in SAMPLE_KNOWLEDGE_BASE:
            self.chunks.append({
                "subject": sample["subject"],
                "doc_name": sample["doc_name"],
                "page": sample["page"],
                "section": sample.get("section", ""),
                "content": sample["content"]
            })

        # 2. Ingest uploaded PDFs from each subject directory
        subjects = self.get_subject_folders()
        for subject in subjects:
            subj_dir = os.path.join(self.storage_dir, subject)
            if not os.path.exists(subj_dir):
                continue
            for file_name in os.listdir(subj_dir):
                if file_name.lower().endswith(".pdf"):
                    pdf_path = os.path.join(subj_dir, file_name)
                    pages = self.extract_text_from_pdf(pdf_path)
                    for p in pages:
                        sub_chunks = self.chunk_text(p["text"])
                        for sc in sub_chunks:
                            self.chunks.append({
                                "subject": subject,
                                "doc_name": p["doc_name"],
                                "page": p["page"],
                                "section": f"Page {p['page']}",
                                "content": sc
                            })

        # 3. Fit TF-IDF Vectorizer for fast hybrid semantic/keyword search
        if self.chunks:
            corpus = [f"{c['subject']} {c.get('section', '')} {c['content']}" for c in self.chunks]
            self.vectorizer = TfidfVectorizer(stop_words='english', max_features=10000, ngram_range=(1, 2))
            self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
            print(f"[RAG] Indexed {len(self.chunks)} knowledge chunks across {len(subjects)} subjects.")

    def search(self, query: str, subject: Optional[str] = None, top_k: int = 4) -> List[Dict[str, Any]]:
        """Searches indexed study material using query and returns relevant excerpts."""
        if not self.chunks or self.vectorizer is None or self.tfidf_matrix is None:
            return []

        # Filter indices by subject if specified
        indices = list(range(len(self.chunks)))
        if subject and subject != "All":
            indices = [i for i, c in enumerate(self.chunks) if c["subject"].lower() == subject.lower()]
            if not indices:  # Fallback if subject has no specific chunks
                indices = list(range(len(self.chunks)))

        try:
            query_vec = self.vectorizer.transform([query])
            sub_matrix = self.tfidf_matrix[indices]
            scores = cosine_similarity(query_vec, sub_matrix).flatten()

            top_sub_indices = np.argsort(scores)[::-1][:top_k]
            results = []
            for rank, sub_idx in enumerate(top_sub_indices):
                score = float(scores[sub_idx])
                actual_idx = indices[sub_idx]
                chunk = self.chunks[actual_idx]
                results.append({
                    "subject": chunk["subject"],
                    "doc_name": chunk["doc_name"],
                    "page": chunk["page"],
                    "section": chunk.get("section", ""),
                    "content": chunk["content"],
                    "relevance_score": round(score, 3)
                })
            return results
        except Exception as e:
            print(f"[RAG Search Error] {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Returns statistics on loaded documents and pages."""
        stats = {
            "total_chunks": len(self.chunks),
            "subjects": {},
            "total_pdfs": 0
        }
        for sub in self.get_subject_folders():
            subj_dir = os.path.join(self.storage_dir, sub)
            pdfs = [f for f in os.listdir(subj_dir) if f.lower().endswith(".pdf")] if os.path.exists(subj_dir) else []
            chunk_count = sum(1 for c in self.chunks if c["subject"] == sub)
            stats["subjects"][sub] = {
                "pdf_count": len(pdfs),
                "pdf_files": pdfs,
                "chunks": chunk_count
            }
            stats["total_pdfs"] += len(pdfs)
        return stats
