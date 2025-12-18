import requests
import json

def test_annotation(pole_id):
    url = f"http://localhost:8000/api/v2/annotation/llm-stream?image_id={pole_id}&dataset=satellite"
    print(f"Testing {pole_id}...")
    
    with requests.get(url, stream=True) as r:
        boxes = []
        for line in r.iter_lines():
            if line:
                try:
                    data = json.loads(line)
                    if data.get("log"):
                        print(f"[LOG] {data['log']}")
                    if data.get("action") == "saved":
                        print(f"[SUCCESS] Saved {data.get('count')} labels.")
                except:
                    pass

test_annotation("pole_481_SAT")
