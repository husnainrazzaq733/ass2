from flask import Flask, request, jsonify, send_from_directory
import json, os, re, urllib.request, urllib.parse, random

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

def call_groq(prompt, api_key, max_tokens=2048):
    # Using Llama 3.3 70B for best results on Groq
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are an expert pharmacy exam assistant for Applied Sciences I. You must ONLY answer using the provided context."},
            {"role": "user", "content": prompt}
        ],
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

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    question = data.get('question', '').strip()
    qtype    = data.get('type', 'short')
    api_key  = data.get('api_key', '').strip() or DEFAULT_API_KEY

    if not question:
        return jsonify({'error': 'Sawal khali hai!'}), 400

    relevant = search_chunks(question)
    if not relevant:
        return jsonify({'answer': 'Is sawal ka jawab book mein nahi mila.'})

    context = '\n\n'.join([f"[Page {c['page']}]\n{c['text']}" for c in relevant])

    if qtype == 'short':
        prompt = f"""You are an expert tutor for Applied Sciences I. Provide a BRIEF answer (worth 2 marks, 3-5 lines) to the question.

RULES:
- You must ONLY use the provided content to answer.
- If the answer cannot be found in the CONTENT, reply EXACTLY with: "Is sawal ka jawab AS-I book mein nahi hai."
- Do NOT use your general outside knowledge to answer.
- Use **Bold** for key terms and headings.
- No page numbers or source mentions.
- Answer directly based on this content: {context}

QUESTION: {question}
SHORT ANSWER:"""
    else:
        prompt = f"""You are an expert tutor for Applied Sciences I. Provide a detailed answer (worth 4 marks) to the question.

RULES:
- You must ONLY use the provided content to answer.
- If the answer cannot be found in the CONTENT, reply EXACTLY with: "Is sawal ka jawab AS-I book mein nahi hai."
- Do NOT use your general outside knowledge to answer.
- Use **Bold Headings** and sub-headings.
- Use bullet points if helpful for classification.
- Keep the answer focused and comprehensive enough for 4 marks.
- No page numbers or source mentions.
- Answer directly based on this content: {context}

QUESTION: {question}
LONG ANSWER (4 Marks):"""

    try:
        answer = call_groq(prompt, api_key)
        return jsonify({'answer': answer})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 50)
    print("  Chat with AS-I (Powered by Groq)")
    print("  Open: http://localhost:5000")
    print("=" * 50)
    app.run(debug=False, port=5000)
