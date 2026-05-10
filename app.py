from flask import Flask, request, jsonify, send_from_directory
import json, os, re, urllib.request, urllib.parse, random, base64
from duckduckgo_search import DDGS

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

def search_chunks(query, top_n=6):
    query_words = set(re.findall(r'\w+', query.lower()))
    scored = []
    for chunk in CHUNKS:
        text_lower = chunk['text'].lower()
        words = set(re.findall(r'\w+', text_lower))
        score = len(query_words & words)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:top_n]]

def call_groq(prompt, api_key, model="llama-3.3-70b-versatile", max_tokens=2048, images=None):
    messages = [
        {"role": "system", "content": "You are an expert pharmacy exam assistant. Follow the specific instructions in the prompt."},
        {"role": "user", "content": []}
    ]
    
    if images:
        # Groq Vision format
        messages[1]["content"].append({"type": "text", "text": prompt})
        for img in images:
            messages[1]["content"].append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img}"}
            })
    else:
        messages[1]["content"] = prompt

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": max_tokens
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
    
    with urllib.request.urlopen(req, timeout=45) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    
    return result['choices'][0]['message']['content']

def search_internet(query):
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=5)]
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
    
    if not api_key:
        return jsonify({'error': 'API Key missing!'}), 400

    try:
        img_base64 = base64.b64encode(file.read()).decode('utf-8')
        # Use Llama 3.2 Vision to extract text
        prompt = "Extract all text and questions from this image. If it's a question, just provide the question text clearly. Output only the extracted text."
        extracted_text = call_groq(prompt, api_key, model="llama-3.2-11b-vision-preview", images=[img_base64])
        return jsonify({'extracted_text': extracted_text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    question = data.get('question', '').strip()
    qtype    = data.get('type', 'short')
    api_key  = data.get('api_key', '').strip() or DEFAULT_API_KEY

    if not question:
        return jsonify({'error': 'Sawal khali hai!'}), 400

    relevant = search_chunks(question)
    source = "book"
    
    if not relevant:
        # Fallback to internet search
        web_context = search_internet(question)
        if web_context:
            context = web_context
            source = "internet"
        else:
            return jsonify({'answer': 'Is sawal ka jawab na book mein mila na internet par.'})
    else:
        context = '\n\n'.join([f"[Page {c['page']}]\n{c['text']}" for c in relevant])

    if qtype == 'short':
        if source == "book":
            prompt = f"You are an expert tutor for Applied Sciences I. Provide a BRIEF answer (worth 2 marks, 3-5 lines) based ONLY on this content: {context}\n\nQUESTION: {question}\nSHORT ANSWER:"
        else:
            prompt = f"You are an expert tutor. The answer was not in the book, so use this internet content to provide a BRIEF answer (worth 2 marks, 3-5 lines): {context}\n\nQUESTION: {question}\nSHORT ANSWER (From Internet):"
    else:
        if source == "book":
            prompt = f"You are an expert tutor for Applied Sciences I. Provide a detailed answer (worth 4 marks) based ONLY on this content: {context}\n\nQUESTION: {question}\nLONG ANSWER:"
        else:
            prompt = f"You are an expert tutor. The answer was not in the book, so use this internet content to provide a detailed answer (worth 4 marks): {context}\n\nQUESTION: {question}\nLONG ANSWER (From Internet):"

    try:
        answer = call_groq(prompt, api_key)
        return jsonify({'answer': answer, 'source': source})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 50)
    print("  Chat with AS-I (Powered by Groq)")
    print("  Open: http://localhost:5000")
    print("=" * 50)
    app.run(debug=False, port=5000)
