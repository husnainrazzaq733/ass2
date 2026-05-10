from flask import Flask, request, jsonify, send_from_directory
import json, os, re, urllib.request, urllib.parse, random, base64
from duckduckgo_search import DDGS
from io import BytesIO
from PIL import Image

app = Flask(__name__, static_folder='.')

# API Key will be taken from Environment Variable (for security)
DEFAULT_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Load book chunks
CHUNKS = []
try:
    with open('chunks.json', 'r', encoding='utf-8') as f:
        CHUNKS = json.load(f)
except Exception as e:
    print(f"Error loading chunks: {e}")

# Groq API Endpoint (OpenAI Compatible)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def search_chunks(query, top_n=8):
    query_words = set(re.findall(r'\w+', query.lower()))
    if len(query_words) < 2: return []
    scored = []
    for chunk in CHUNKS:
        text_lower = chunk['text'].lower()
        words = set(re.findall(r'\w+', text_lower))
        score = len(query_words & words)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:top_n]]

def call_groq(prompt, api_key, model="llama-3.3-70b-versatile", max_tokens=2048, images=None, system_msg=None):
    messages = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    else:
        messages.append({"role": "system", "content": "You are an expert pharmacy exam assistant. Follow the specific instructions in the prompt."})

    if images:
        user_content = [{"type": "text", "text": prompt}]
        for img in images:
            user_content.append({"type": "image_url", "image_url": {"url": img}})
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"} if "JSON" in prompt else {"type": "text"}
    }).encode('utf-8')
    
    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"Groq API Error: {e}")
        raise e

def search_internet(query):
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=4)]
            if not results: return ""
            return "\n\n".join([f"WEB CONTENT:\n{r['body']}" for r in results])
    except Exception as e:
        print(f"Internet search failed: {e}")
        return ""

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'image' not in request.files:
        return jsonify({'error': 'No image uploaded'}), 400
    
    file = request.files['image']
    api_key = request.form.get('api_key', '').strip() or DEFAULT_API_KEY
    if not api_key: return jsonify({'error': 'API Key missing!'}), 400

    try:
        content = file.read()
        if len(content) > 1024 * 1024:
            img = Image.open(BytesIO(content))
            img.thumbnail((1280, 1280))
            output = BytesIO()
            img.save(output, format='JPEG', quality=85)
            content = output.getvalue()
        
        img_base64 = base64.b64encode(content).decode('utf-8')
        data_uri = f"data:image/jpeg;base64,{img_base64}"
        prompt = "Extract all text and questions from this image. If there are multiple questions, list them all. Output ONLY the extracted text."
        extracted_text = call_groq(prompt, api_key, model="llama-3.2-11b-vision-instant", images=[data_uri])
        return jsonify({'extracted_text': extracted_text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    text = data.get('question', '').strip()
    qtype = data.get('type', 'short')
    api_key = data.get('api_key', '').strip() or DEFAULT_API_KEY

    if not text: return jsonify({'error': 'Sawal khali hai!'}), 400

    # Step 1: Detect and Split Questions
    try:
        split_prompt = f"Identify all individual exam questions in the following text. Return them as a JSON object with a key 'questions' which is a list of strings. If there is only one question, still return it in the list. Text: {text}"
        split_res = call_groq(split_prompt, api_key)
        questions = json.loads(split_res).get('questions', [text])
    except:
        questions = [text] # Fallback to single text

    all_answers = []
    final_source = "book"

    for q in questions:
        relevant = search_chunks(q)
        source = "book"
        if not relevant:
            web_context = search_internet(q)
            if web_context:
                context = web_context
                source = "internet"
                final_source = "internet" # Mark as internet if even one is from web
            else:
                all_answers.append(f"**Q: {q}**\nJawab book ya internet par nahi mila.")
                continue
        else:
            context = '\n\n'.join([f"{c['text']}" for c in relevant])

        if qtype == 'short':
            prompt = f"Question: {q}\nContext: {context}\nProvide a 2-mark answer (approx 5-6 lines). Use headings/bold terms. Must be accurate based on context."
        else:
            prompt = f"Question: {q}\nContext: {context}\nProvide a 4-mark detailed answer (approx 12-15 lines). Use multiple headings, bullet points, and bold key terms. Be comprehensive."
        
        try:
            ans = call_groq(prompt, api_key)
            all_answers.append(f"**Q: {q}**\n{ans}")
        except:
            all_answers.append(f"**Q: {q}**\nError generating answer.")

    final_text = "\n\n---\n\n".join(all_answers)
    return jsonify({'answer': final_text, 'source': final_source})

if __name__ == '__main__':
    app.run(debug=False, port=5000)
