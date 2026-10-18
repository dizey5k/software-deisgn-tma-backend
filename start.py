import subprocess
import time
import re
import os
import sys

def start():
    print("Starting...")

    tunnel_proc = subprocess.Popen(
        [".\\cloudflared.exe", "tunnel", "--protocol", "http2", "--url", "http://localhost:8000"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="ignore"
    )

    tunnel_url = None
    print("Waiting for tunnel URL...")
    
    for line in tunnel_proc.stdout:
        print(line.strip())
        if "trycloudflare.com" in line:
            match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
            if match:
                tunnel_url = match.group(0)
                print(f"Tunnel started: {tunnel_url}")
                break

    if tunnel_url:
        env_path = ".env"
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        else:
            lines = []
        
        url_updated = False
        with open(env_path, "w", encoding="utf-8") as f:
            for line in lines:
                if line.startswith("WEBHOOK_URL="):
                    f.write(f'WEBHOOK_URL="{tunnel_url}"\n')
                    url_updated = True
                else:
                    f.write(line)
            if not url_updated:
                f.write(f'WEBHOOK_URL="{tunnel_url}"\n')
                
        print("WEBHOOK_URL written to .env")

        print("⏳ Жду 5 секунд стабилизации туннеля...")
        time.sleep(5)

        print("Starting FastAPI...")
        try:
            subprocess.run([sys.executable, "-m", "uvicorn", "app.main:app"])
        except KeyboardInterrupt:
            print("\nStopping processes...")
            tunnel_proc.terminate()
    else:
        print("Failed to start tunnel or retrieve URL. Please check cloudflared logs above.")
        tunnel_proc.terminate()

if __name__ == "__main__":
    start()