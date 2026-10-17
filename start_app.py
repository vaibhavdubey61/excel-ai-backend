import socket
import uvicorn
import os

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == "__main__":
    local_ip = get_local_ip()
    port = int(os.getenv("PORT", 8000))

    print("=" * 65)
    print("   🎓 EXCEL EDUCATIONAL INSTITUTE - EXCEL AI COACH PROTOTYPE   ")
    print("=" * 65)
    print(f"\n[1] Open on THIS PC:")
    print(f"    --> http://localhost:{port}")
    print(f"\n[2] Open on ANY PHONE or PC on the SAME Wi-Fi / Office Network:")
    print(f"    --> http://{local_ip}:{port}")
    print(f"\n[3] Open on ANY PC in the WORLD via Free Public Tunnel:")
    print(f"    Run in a second terminal:")
    print(f"    cloudflared tunnel --url http://localhost:{port}")
    print("=" * 65 + "\n")

    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
