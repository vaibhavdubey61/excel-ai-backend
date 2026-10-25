"""
Syllabus configuration and namespace resolution for CA, CS, and CMA exams.
NOTE: The owner must verify these against the current ICAI, ICSI, and ICMAI scheme.
"""
from typing import Dict, List, Optional, Tuple

SYLLABUS: Dict[str, Dict[str, List[str]]] = {
    # Chartered Accountancy (ICAI) - New Scheme
    "CA": {
        "Foundation": [
            "Accounting",
            "Business Laws",
            "Quantitative Aptitude",
            "Business Economics",
            "Business and Commercial Knowledge"
        ],
        "Inter": [
            "Advanced Accounting",
            "Corporate and Other Laws",
            "Taxation",
            "Cost and Management Accounting",
            "Auditing and Ethics",
            "Financial Management and Strategic Management"
        ],
        "Final": [
            "Financial Reporting",
            "Advanced Financial Management",
            "Advanced Auditing and Professional Ethics",
            "Direct Tax Laws and International Taxation",
            "Indirect Tax Laws",
            "Integrated Business Solutions"
        ]
    },
    # Company Secretary (ICSI) - TODO: Owner will verify and update official ICSI syllabus
    "CS": {
        "Executive": [
            # TODO: Add full CS Executive Group 1 & 2 subjects
            "Jurisprudence, Interpretation and General Laws",
            "Company Law and Practice",
            "Setting up of Business, Industrial and Labour Laws",
            "Corporate Accounting and Financial Management",
            "Capital Market and Securities Laws",
            "Economic, Commercial and Intellectual Property Laws",
            "Tax Laws and Practice"
        ],
        "Professional": [
            # TODO: Add full CS Professional Group 1 & 2 subjects
            "Environmental, Social and Governance (ESG) - Principles & Practice",
            "Drafting, Pleadings and Appearances",
            "Compliance Management, Audit & Due Diligence",
            "Strategic Management & Corporate Finance",
            "Corporate Restructuring, Valuation and Insolvency"
        ]
    },
    # Cost and Management Accountancy (ICMAI) - TODO: Owner will verify and update official ICMAI syllabus
    "CMA": {
        "Foundation": [
            # TODO: Add full CMA Foundation subjects
            "Fundamentals of Business Laws and Business Communication",
            "Fundamentals of Financial and Cost Accounting",
            "Fundamentals of Business Mathematics and Statistics",
            "Fundamentals of Business Economics and Management"
        ],
        "Inter": [
            # TODO: Add full CMA Intermediate subjects
            "Financial Accounting",
            "Corporate Laws and Practice",
            "Direct and Indirect Taxation",
            "Cost Accounting",
            "Operations Management and Strategic Management",
            "Corporate Accounting and Auditing",
            "Financial Management and Business Data Analytics",
            "Management Accounting"
        ],
        "Final": [
            # TODO: Add full CMA Final subjects
            "Corporate and Economic Laws",
            "Strategic Financial Management",
            "Strategic Cost Management",
            "Direct Tax Laws and International Taxation",
            "Corporate Financial Reporting",
            "Indirect Tax Laws and Practice",
            "Cost and Management Audit",
            "Strategic Performance Management and Business Valuation"
        ]
    }
}

def normalize_course(course: str) -> str:
    """Normalizes course name to matching syllabus key (e.g. 'ca' -> 'CA')."""
    c = (course or "").strip().upper()
    for valid in SYLLABUS.keys():
        if c == valid.upper():
            return valid
    return c

def normalize_level(course: str, level: str) -> str:
    """Normalizes level name to matching syllabus key (e.g. 'foundation' -> 'Foundation', 'inter' -> 'Inter')."""
    norm_c = normalize_course(course)
    levels = SYLLABUS.get(norm_c, {})
    l = (level or "").strip().lower().replace("_", " ").replace("-", " ")
    for valid_lvl in levels.keys():
        if l == valid_lvl.lower().replace("_", " ").replace("-", " "):
            return valid_lvl
    return (level or "").strip()

def namespace(course: str, level: str) -> str:
    """
    Returns normalized Pinecone vector store namespace.
    Examples:
        namespace('CA', 'Foundation') -> 'ca-foundation'
        namespace('CA', 'Inter') -> 'ca-inter'
        namespace('CA', 'Final') -> 'ca-final'
        namespace('CS', 'Executive') -> 'cs-executive'
    """
    c_clean = (course or "").strip().lower().replace("_", "-").replace(" ", "-")
    l_clean = (level or "").strip().lower().replace("_", "-").replace(" ", "-")
    return f"{c_clean}-{l_clean}"

def is_valid_course_level(course: str, level: str) -> bool:
    """Validates whether a course and level pair exists in SYLLABUS."""
    norm_c = normalize_course(course)
    if norm_c not in SYLLABUS:
        return False
    norm_l = normalize_level(norm_c, level)
    return norm_l in SYLLABUS[norm_c]

def get_subjects(course: str, level: str) -> List[str]:
    """Retrieves the list of subjects for a given course and level."""
    norm_c = normalize_course(course)
    norm_l = normalize_level(norm_c, level)
    return list(SYLLABUS.get(norm_c, {}).get(norm_l, []))
