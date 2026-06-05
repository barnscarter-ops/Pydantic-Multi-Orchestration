import urllib.request
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GATEWAY_URL = "http://localhost:8000"
TEST_FILE_PATH = os.path.abspath("pacc-gateway/tests/test_file.txt")

def test_file_apis():
    print("🚀 Starting Filesystem API Verification...")

    # 1. Test POST /file (Save Content)
    print("\n[1/2] Saving file content via POST /file...")
    payload = {
        "path": TEST_FILE_PATH,
        "content": "Hello Maverick Command Center! This is a filesystem API test."
    }
    
    req = urllib.request.Request(
        f"{GATEWAY_URL}/file",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"✅ POST response: {data}")
            if data.get("status") == "success" and data.get("path") == TEST_FILE_PATH:
                print("✅ File save verified.")
            else:
                print("❌ File save failed (unexpected response).")
                return
    except Exception as e:
        print(f"❌ POST request failed: {e}")
        return

    # Verify file was created locally
    if not os.path.exists(TEST_FILE_PATH):
        print("❌ File was not created on disk.")
        return
    print("✅ Verified file exists on disk.")

    # 2. Test GET /file (Read Content)
    print("\n[2/2] Reading file content via GET /file...")
    url_encoded_path = urllib.parse.quote(TEST_FILE_PATH)
    url = f"{GATEWAY_URL}/file?path={url_encoded_path}"
    
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"✅ GET response: {data}")
            if data.get("path") == TEST_FILE_PATH and "Maverick Command Center" in data.get("content", ""):
                print("✅ File read content verified.")
            else:
                print("❌ File read content mismatch.")
                return
    except Exception as e:
        print(f"❌ GET request failed: {e}")
        return

    # Clean up test file
    try:
        os.remove(TEST_FILE_PATH)
        print("\n🧹 Cleaned up test file.")
    except Exception as e:
        print(f"⚠️ Failed to remove test file: {e}")

    print("\n🎉 Filesystem API Verification Passed!")

if __name__ == "__main__":
    test_file_apis()
