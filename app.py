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

def search_chunks(query, top_n=10): # Increased top_n for multiple questions
    # Simple keyword search, but for multiple questions we take more chunks
    query_words = set(re.findall(r'\w+', query.lower()))
    if len(query_words) < 3: return []
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
    if images:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        for img in images:
            messages[0]["content"].append({
                "type": "image_url",
                "image_url": {"url": img} # img already includes data: prefix
            })
    else:
        messages = [
            {"role": "system", "content": "You are an expert pharmacy exam assistant. Follow the specific instructions in the prompt."},
            {"role": "user", "content": prompt}
        ]

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.2,
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
    
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        return result['choices'][0]['message']['content']
    except urllib.error.HTTPError as e:
        err_data = e.read().decode('utf-8')
        print(f"Groq API Error: {err_data}")
        raise Exception(f"Groq API Error: {err_data}")
    except Exception as e:
        print(f"Error: {str(e)}")
        raise e

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
        content = file.read()
        # Resize if large
        if len(content) > 1 * 1024 * 1024:
            img = Image.open(BytesIO(content))
            img.thumbnail((1280, 1280))
            output = BytesIO()
            img.save(output, format='JPEG', quality=85)
            content = output.getvalue()
            mime_type = 'image/jpeg'
        else:
            mime_type = file.content_type or 'image/jpeg'

        img_base64 = base64.b64encode(content).decode('utf-8')
        data_uri = f"data:{mime_type};base64,{img_base64}"
        
        prompt = "Extract all text and questions from this image. If it's a question, provide the question text clearly. Output ONLY the extracted text."
        
        # Use llama-3.2-11b-vision-instant as it replaces preview
        extracted_text = call_groq(prompt, api_key, model="llama-3.2-11b-vision-instant", images=[data_uri])
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
            prompt = f"You are an expert tutor for Applied Sciences I. Below is a text that may contain ONE or MULTIPLE questions. Provide a BRIEF answer (worth 2 marks each) for EVERY question found in the input. Use the provided context ONLY: {context}\n\nINPUT TEXT: {question}\n\nANSWERS:"
        else:
            prompt = f"You are an expert tutor. Below is a text with ONE or MULTIPLE questions. The answers were not in the book, so use your knowledge/internet to provide a BRIEF answer (2 marks each) for EVERY question. \n\nCONTEXT: {context}\n\nINPUT TEXT: {question}\n\nANSWERS (From Internet):"
    else:
        if source == "book":
            prompt = f"You are an expert tutor for Applied Sciences I. Provide DETAILED answers (worth 4 marks each) for EVERY question found in the input. Use the provided context ONLY: {context}\n\nINPUT TEXT: {question}\n\nANSWERS:"
        else:
            prompt = f"You are an expert tutor. Provide DETAILED answers (worth 4 marks each) for EVERY question found in the input based on this context: {context}\n\nINPUT TEXT: {question}\n\nANSWERS (From Internet):"

    try:
        answer = call_groq(prompt, api_key)
        return jsonify({'answer': answer, 'source': source})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False, port=5000)
