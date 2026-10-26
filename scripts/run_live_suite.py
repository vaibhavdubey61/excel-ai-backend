import sys
import time
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"

def test_suite():
    print("=" * 60)
    print("      EXCEL AI COACH - LIVE SYSTEM VERIFICATION      ")
    print("=" * 60)

    # 1. Health check
    print("\n[Test 1] Health Endpoint Check...")
    t0 = time.time()
    try:
        r = httpx.get(f"{BASE_URL}/api/health", timeout=5.0)
        dt = time.time() - t0
        print(f"Status: {r.status_code} in {dt:.2f}s")
        print(f"Data: {r.json()}")
        assert r.status_code == 200
        print("[PASS] Health check PASSED")
    except Exception as e:
        print(f"[FAIL] Health check FAILED: {e}")

    # 2. CA Foundation Question (Accounts)
    print("\n[Test 2] CA Foundation Chat (Bank Reconciliation)...")
    payload_fnd = {
        "message": "What is Bank Reconciliation Statement and why do we prepare it?",
        "course": "CA",
        "level": "Foundation"
    }
    t0 = time.time()
    try:
        r = httpx.post(f"{BASE_URL}/api/chat", data=payload_fnd, timeout=30.0)
        dt = time.time() - t0
        print(f"Status: {r.status_code} in {dt:.2f}s")
        if r.status_code == 200:
            reply = r.json().get("reply", "")
            print(f"Reply Length: {len(reply)} chars")
            print(f"Preview:\n{reply[:350]}...\n")
            print("[PASS] CA Foundation chat PASSED")
        else:
            print(f"[FAIL] CA Foundation chat FAILED: {r.text}")
    except Exception as e:
        print(f"[FAIL] CA Foundation chat ERROR: {e}")

    # 3. CA Intermediate Question (Corporate Law)
    print("\n[Test 3] CA Intermediate Chat (Sec 68 Buyback of Securities)...")
    payload_inter = {
        "message": "What are the statutory limits and conditions for Buyback of Securities under Section 68 of Companies Act 2013?",
        "course": "CA",
        "level": "Inter"
    }
    t0 = time.time()
    try:
        r = httpx.post(f"{BASE_URL}/api/chat", data=payload_inter, timeout=30.0)
        dt = time.time() - t0
        print(f"Status: {r.status_code} in {dt:.2f}s")
        if r.status_code == 200:
            reply = r.json().get("reply", "")
            print(f"Reply Length: {len(reply)} chars")
            print(f"Preview:\n{reply[:350]}...\n")
            print("[PASS] CA Intermediate chat PASSED")
        else:
            print(f"[FAIL] CA Intermediate chat FAILED: {r.text}")
    except Exception as e:
        print(f"[FAIL] CA Intermediate chat ERROR: {e}")

    # 4. Live Internet Research Query
    print("\n[Test 4] Live Internet Research Query...")
    payload_web = {
        "message": "Search the internet for latest ICAI exam dates schedule",
        "course": "CA",
        "level": "Inter"
    }
    t0 = time.time()
    try:
        r = httpx.post(f"{BASE_URL}/api/chat", data=payload_web, timeout=30.0)
        dt = time.time() - t0
        print(f"Status: {r.status_code} in {dt:.2f}s")
        if r.status_code == 200:
            reply = r.json().get("reply", "")
            print(f"Reply Length: {len(reply)} chars")
            print(f"Preview:\n{reply[:350]}...\n")
            print("[PASS] Web Research Chat PASSED")
        else:
            print(f"[FAIL] Web Research Chat FAILED: {r.text}")
    except Exception as e:
        print(f"[FAIL] Web Research Chat ERROR: {e}")

    # 5. Interactive MCQ Generation
    print("\n[Test 5] Interactive MCQ Generation...")
    payload_mcq = {
        "course": "CA",
        "level": "Inter",
        "subject": "Corporate and Other Laws",
        "topic": "Share Capital and Debentures",
        "count": 3
    }
    t0 = time.time()
    try:
        r = httpx.post(f"{BASE_URL}/api/mcq/generate", json=payload_mcq, timeout=30.0)
        dt = time.time() - t0
        print(f"Status: {r.status_code} in {dt:.2f}s")
        if r.status_code == 200:
            data = r.json()
            questions = data.get("questions", [])
            print(f"Generated {len(questions)} MCQs in {dt:.2f}s:")
            for i, q in enumerate(questions, 1):
                print(f"  Q{i}: {q.get('question', '')[:90]}... (Answer: Option {q.get('correct_answer')})")
            print("[PASS] MCQ Generation PASSED")
        else:
            print(f"[FAIL] MCQ Generation FAILED: {r.text}")
    except Exception as e:
        print(f"[FAIL] MCQ Generation ERROR: {e}")

    print("\n" + "=" * 60)
    print("             ALL LIVE TESTS COMPLETED               ")
    print("=" * 60)

if __name__ == "__main__":
    test_suite()
