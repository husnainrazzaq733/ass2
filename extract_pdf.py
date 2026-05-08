import pypdf
import json
import os

# New PDF path provided by user
pdf_path = r'C:\Users\HP\Downloads\Documents\AS-I.pdf'
reader = pypdf.PdfReader(pdf_path)

chunks = []
for i in range(len(reader.pages)):
    text = reader.pages[i].extract_text()
    if text and text.strip() and len(text.strip()) > 50:
        # Clean text
        clean_text = text.strip().replace('\r\n', '\n').replace('  ', ' ')
        chunks.append({
            'page': i + 1,
            'text': clean_text
        })

print(f'Total chunks extracted: {len(chunks)}')

# Save to chunks.json
with open('chunks.json', 'w', encoding='utf-8') as f:
    json.dump(chunks, f, ensure_ascii=False, indent=2)

print('Saved chunks.json successfully!')

# Also create a combined text file for reference
all_text = '\n\n'.join([f"[PAGE {c['page']}]\n{c['text']}" for c in chunks])
with open('book_full_text.txt', 'w', encoding='utf-8') as f:
    f.write(all_text)

print(f'Total characters: {len(all_text)}')
print('Done processing AS-I.pdf!')

