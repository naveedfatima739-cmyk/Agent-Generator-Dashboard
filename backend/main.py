from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
import json
import os
import re
import shutil
import hashlib
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import httpx
from database import init_db, create_agent, get_agents, get_agent, update_agent, delete_agent
from schemas import AgentCreate, TrainRequest, AgentUpdate
from crawler import save_dataset, _domain_slug

# ── Gemini API Configuration ────────────────────────────────────────────
GEMINI_API_KEY = "AIzaSyAxCnvD92KF2tqlk_kep8Yt8R3DAgMdQaQ"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# Thread pool for running blocking crawl jobs without blocking the event loop
_train_executor = ThreadPoolExecutor(max_workers=4)

app = FastAPI()
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Admin Secret (change this in production) ──────────────────────────────
ADMIN_SECRET = "kfuet-admin-2024"

class ChatRequest(BaseModel):
    message: str

class AdminChatRequest(BaseModel):
    message: str
    agent_id: str
    admin_token: str

class UserChatRequest(BaseModel):
    message: str

class DatasetUpdateRequest(BaseModel):
    admin_token: str
    instruction: str  # Natural language instruction like "add info about fees"
    content: str      # The actual content to add

# ═══════════════════════════════════════════════════════════════════════════
#  BUILT-IN AI ENGINE (unchanged from original)
# ═══════════════════════════════════════════════════════════════════════════

STOP_WORDS = {
    "the","is","are","was","were","what","which","who","how","when","where",
    "can","you","tell","me","about","and","for","with","this","that","does",
    "have","has","will","your","give","please","its","also","more","some",
    "any","all","get","just","from","they","been","would","could","should",
    "our","their","there","here","than","then","but","not","into","onto",
    "mujhe","batao","kya","hai","ka","ki","ke","aur","main","mein","se",
    "ko","ne","bhi","koi","nahi","hain","tha","thi","the","yeh","woh",
    "ap","aap","hum","tum","isko","usko","karo","karna","chahiye","liye",
    "kuch","sab","sirf","bas","phir","lekin","magar","agar","toh","jo"
}

GREETINGS = {
    "hello","hi","hey","salam","assalam","assalamualaikum","walaikum",
    "good morning","good evening","good afternoon","good night",
    "how are you","howdy","hiya","sup","whats up","what's up",
    "aoa","aslam","slm","helo","hii","hiii","heya",
    "adaab","namaskar","sat sri akal"
}

THANKS_WORDS = {
    "thanks","thank you","thankyou","shukriya","jazakallah",
    "shukria","bahut shukriya","bohat shukriya","ty","thx"
}

GOODBYE_WORDS = {
    "bye","goodbye","good bye","see you","later","alvida","khuda hafiz",
    "allah hafiz","take care","cya","bb","baad mein milte hain"
}

HELP_WORDS = {
    "help","madad","karo","chahiye","guide","guidance","batayen",
    "samjhao","explain","what can you do","kya kar sakte"
}


def tokenize(text: str) -> list:
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return [w for w in text.split() if len(w) > 1]


def get_query_words(text: str) -> list:
    tokens = tokenize(text)
    return [w for w in tokens if w not in STOP_WORDS and len(w) > 2]


def detect_intent(message: str) -> str:
    msg = message.lower().strip()
    words = set(tokenize(msg))
    # Use word boundary matching to avoid substring matches
    for g in GREETINGS:
        if g in words:
            return "greeting"
        # Also check if the word starts with greeting prefix (for "hi" at start of sentences)
        if msg.startswith(g):
            return "greeting"
    # Check for exact word matches in the message
    msg_words = set(msg.split())
    for t in THANKS_WORDS:
        if t in msg_words:
            return "thanks"
    for g in GOODBYE_WORDS:
        if g in msg_words:
            return "goodbye"
    for h in HELP_WORDS:
        if h in msg_words:
            return "help"
    return "query"


def detect_language(text: str) -> str:
    roman_urdu_words = {
        "kya","hai","ka","ki","ke","aur","main","mein","se","ko","ne",
        "bhi","koi","nahi","hain","yeh","woh","ap","aap","hum","tum",
        "kuch","sab","sirf","phir","lekin","agar","toh","jo","mujhe",
        "batao","chahiye","liye","fees","admission","course","program",
        "kitni","kitna","kahan","kab","kyun","kaisa","kaisi","wala",
        "bata","batain"," batao","karo","karna","chaiye","hona","hote"
    }
    words = set(tokenize(text.lower()))
    roman_count = len(words & roman_urdu_words)
    return "roman_urdu" if roman_count >= 2 else "english"


def score_record(record: dict, query_words: list) -> float:
    payload = record.get("record_payload") or {}
    content = (payload.get("content") or "").lower()
    title   = (payload.get("title")   or "").lower()
    if not content:
        return 0.0
    content_words = tokenize(content)
    content_len   = max(len(content_words), 1)
    score         = 0.0
    for word in query_words:
        tf = content.count(word) / content_len
        title_boost = 6.0 if word in title else 1.0
        score += tf * title_boost * 100
        if word in content[:500]:
            score += 2.0
    return score


def extract_best_sentences(content: str, query_words: list, max_sentences: int = 5) -> list:
    raw_sentences = re.split(r'(?<=[.!?])\s+', content)
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 40]
    if not sentences:
        return []
    scored = []
    for sentence in sentences:
        s_lower = sentence.lower()
        score   = 0
        for word in query_words:
            if word in s_lower:
                score += s_lower.count(word) * 2
                if s_lower.startswith(word):
                    score += 3
        if score > 0:
            scored.append((score, sentence))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [s for _, s in scored[:max_sentences]]
    original_order = []
    for sentence in sentences:
        if sentence in top:
            original_order.append(sentence)
        if len(original_order) == len(top):
            break
    return original_order if original_order else top


def build_response(query: str, records: list, agent_name: str, lang: str) -> str:
    query_words = get_query_words(query)
    if not query_words:
        if lang == "roman_urdu":
            return f"Meherbani karke apna sawal thoda detail mein poochein. Main {agent_name} ke baare mein kuch bhi batane mein madad kar sakta hoon!"
        return f"Could you please elaborate? I can help you with any information about {agent_name}."

    scored_records = []
    for record in records:
        score = score_record(record, query_words)
        if score > 0:
            scored_records.append((score, record))
    scored_records.sort(key=lambda x: x[0], reverse=True)

    if not scored_records:
        if lang == "roman_urdu":
            return f"Mujhe is topic ke baare mein information nahi mili. Koi aur sawal poochein ya seedha {agent_name} se rabta karein."
        return f"I couldn't find specific information about that. Please try asking differently or contact {agent_name} directly."

    top_records = scored_records[:3]
    is_simple   = len(query_words) <= 2

    if is_simple:
        best_payload  = top_records[0][1].get("record_payload") or {}
        best_content  = best_payload.get("content") or ""
        best_title    = best_payload.get("title")   or ""
        best_url      = best_payload.get("url")     or ""
        sentences = extract_best_sentences(best_content, query_words, max_sentences=3)
        if sentences:
            answer = re.sub(r'\s+', ' ', " ".join(sentences)).strip()
            response = f"**{best_title}**\n\n{answer}"
            if best_url:
                response += f"\n\n🔗 {best_url}"
            return response

    response_parts = []
    for i, (score, record) in enumerate(top_records):
        payload = record.get("record_payload") or {}
        content = payload.get("content") or ""
        title   = payload.get("title")   or ""
        url     = payload.get("url")     or ""
        sentences = extract_best_sentences(content, query_words, max_sentences=4)
        if not sentences:
            continue
        section_text = re.sub(r'\s+', ' ', " ".join(sentences)).strip()
        is_list_content = (
            len(sentences) >= 3 and
            any(w in query.lower() for w in ["list","all","what are","kya hain","courses","programs","departments","faculty"])
        )
        if is_list_content:
            bullet_sentences = [f"• {s.strip()}" for s in sentences if len(s.strip()) > 20]
            section = f"**{title}**\n" + "\n".join(bullet_sentences)
        else:
            section = f"**{title}**\n{section_text}"
        if url:
            section += f"\n🔗 {url}"
        response_parts.append(section)

    if not response_parts:
        if lang == "roman_urdu":
            return f"Is topic par mujhe kuch relevant information nahi mili. Koi aur andaaz mein poochein."
        return f"I found some pages but couldn't extract a clear answer. Please try rephrasing your question."

    full_response = "\n\n".join(response_parts)
    if len(response_parts) > 1:
        intro = "Yahan aapke sawal ka jawab hai:\n\n" if lang == "roman_urdu" else "Here's what I found:\n\n"
        full_response = intro + full_response
    return full_response


# ═══════════════════════════════════════════════════════════════════════════
#  GEMINI AI ENGINE
# ═══════════════════════════════════════════════════════════════════════════

async def query_gemini(prompt: str, dataset_context: str, agent_name: str, lang: str) -> str:
    """
    Query Gemini API with the user question and relevant dataset content.
    Falls back to built-in keyword search if Gemini fails.
    """
    # Check if context has meaningful content
    has_real_content = (
        dataset_context 
        and len(dataset_context) > 100 
        and "No knowledge base" not in dataset_context
        and "No relevant information" not in dataset_context
    )
    
    # If no real content, provide honest response
    if not has_real_content:
        fallback_msg = {
            "english": (
                f"I'm {agent_name}, your KFUEIT assistant. I don't have information about that topic in my knowledge base. "
                f"Please try asking about:\n"
                f"• Programs and degrees\n"
                f"• Scholarships and financial aid\n"
                f"• Faculty and departments\n"
                f"• Events and news\n\n"
                f"For other information, contact:\n"
                f"📧 Email: info@kfueit.edu.pk\n"
                f"📞 Phone: +92-68-588000\n"
                f"🌐 Website: https://kfueit.edu.pk"
            ),
            "roman_urdu": (
                f"Main {agent_name} hoon, aapka KFUEIT assistant. Mujhe is topic ke baare mein meri knowledge base mein information nahi hai. "
                f"Aap ye pooch sakte hain:\n"
                f"• Programs aur degrees\n"
                f"• Scholarships aur financial aid\n"
                f"• Faculty aur departments\n"
                f"• Events aur news\n\n"
                f"Doosri information ke liye contact karein:\n"
                f"📧 Email: info@kfueit.edu.pk\n"
                f"📞 Phone: +92-68-588000\n"
                f"🌐 Website: https://kfueit.edu.pk"
            )
        }
        return fallback_msg.get(lang, fallback_msg["english"])
    
    # Check relevance of context to the query
    query_words = get_query_words(prompt)
    
    # Check if any context is actually relevant
    relevant_found = False
    for word in query_words:
        if word in dataset_context.lower() and len(word) > 3:
            relevant_found = True
            break
    
    # If no relevant content found, be honest
    if not relevant_found:
        no_info_msg = {
            "english": (
                f"I'm {agent_name}, your KFUEIT assistant. I don't have specific information about that topic in my knowledge base. "
                f"Please try asking about:\n"
                f"• Programs and degrees\n"
                f"• Scholarships and financial aid\n"
                f"• Faculty and departments\n"
                f"• Events and news\n\n"
                f"For other information, contact:\n"
                f"📧 Email: info@kfueit.edu.pk\n"
                f"📞 Phone: +92-68-588000\n"
                f"🌐 Website: https://kfueit.edu.pk"
            ),
            "roman_urdu": (
                f"Main {agent_name} hoon, aapka KFUEIT assistant. Mujhe is topic ke baare mein specific information nahi hai mere paas. "
                f"Aap ye pooch sakte hain:\n"
                f"• Programs aur degrees\n"
                f"• Scholarships aur financial aid\n"
                f"• Faculty aur departments\n"
                f"• Events aur news\n\n"
                f"Doosri information ke liye contact karein:\n"
                f"📧 Email: info@kfueit.edu.pk\n"
                f"📞 Phone: +92-68-588000\n"
                f"🌐 Website: https://kfueit.edu.pk"
            )
        }
        return no_info_msg.get(lang, no_info_msg["english"])
    
    # Try Gemini API
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
                json={
                    "contents": [
                        {"parts": [{"text": f"Context: {dataset_context}\n\nQuestion: {prompt}\n\nAnswer based only on context above. If info not in context, say 'I don't have that info'."}]}
                    ],
                    "generationConfig": {
                        "temperature": 0.3,
                        "maxOutputTokens": 2048
                    }
                },
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
            
            # If Gemini fails, fall back to built-in search
            if response.status_code == 429:
                return use_fallback_search(prompt, dataset_context, agent_name, lang)
            
    except Exception:
        pass
    
    # Fall back to built-in keyword search
    return use_fallback_search(prompt, dataset_context, agent_name, lang)


def use_fallback_search(prompt: str, dataset_context: str, agent_name: str, lang: str) -> str:
    """
    Use built-in keyword search when Gemini fails.
    """
    query_words = get_query_words(prompt)
    
    if not query_words:
        fallback = {
            "english": f"I'm {agent_name}. Please ask a specific question about KFUEIT.",
            "roman_urdu": f"Main {agent_name} hoon. Koi specific sawal poochein KFUEIT ke baare mein."
        }
        return fallback.get(lang, fallback["english"])
    
    # Parse the dataset context to extract relevant information
    lines = dataset_context.split('\n')
    relevant_lines = []
    
    for line in lines:
        line_lower = line.lower()
        for word in query_words:
            if word in line_lower and len(word) > 2:
                relevant_lines.append(line)
                break
    
    if relevant_lines:
        # Format the response
        response = f"**{agent_name} - Response:**\n\n"
        seen = set()
        for line in relevant_lines[:15]:
            if line not in seen and len(line) > 20:
                seen.add(line)
                response += f"• {line.strip()}\n"
        
        response += f"\n📧 More info: info@kfueit.edu.pk | 🌐 kfueit.edu.pk"
        return response
    else:
        no_info = {
            "english": (
                f"I'm {agent_name}, your KFUEIT assistant. I don't have information about that topic in my knowledge base. "
                f"Please try asking about:\n"
                f"• Programs and degrees\n"
                f"• Scholarships and financial aid\n"
                f"• Faculty and departments\n"
                f"• Events and news"
            ),
            "roman_urdu": (
                f"Main {agent_name} hoon, aapka KFUEIT assistant. Mujhe is topic ke baare mein information nahi hai. "
                f"Aap ye pooch sakte hain:\n"
                f"• Programs aur degrees\n"
                f"• Scholarships aur financial aid\n"
                f"• Faculty aur departments\n"
                f"• Events aur news"
            )
        }
        return no_info.get(lang, no_info["english"])


async def build_context_from_dataset(records: list, query: str, query_words: list) -> str:
    """
    Build a context string from the dataset records that are relevant to the query.
    """
    if not records:
        return "No knowledge base available."
    
    scored_records = []
    for record in records:
        score = score_record(record, query_words)
        if score > 0:
            scored_records.append((score, record))
    scored_records.sort(key=lambda x: x[0], reverse=True)
    
    top_records = scored_records[:10]
    
    context_parts = []
    for score, record in top_records:
        payload = record.get("record_payload") or {}
        title = payload.get("title", "")
        content = payload.get("content", "")
        url = payload.get("url", "")
        section = record.get("source_section_label", "")
        
        if content and len(content) > 30:
            context_parts.append({
                'score': score,
                'title': title or section or 'Unknown',
                'content': content,
                'url': url
            })
    
    if not context_parts:
        return "No relevant information found in the knowledge base."
    
    context_str = ""
    for item in context_parts:
        title = item['title']
        content = item['content']
        url = item['url']
        
        context_str += f"\n--- Information about: {title} ---\n"
        context_str += f"{content}\n"
        if url:
            context_str += f"Source: {url}\n"
    
    # Add default KFUEIT information if query is about fee, admission, etc.
    query_lower = query.lower()
    if any(word in query_lower for word in ['fee', 'fees', 'admission', 'register', 'cost', 'tution']):
        context_str += """
\n--- Default KFUEIT Admission Information ---\nKFUEIT offers 108+ Academic Programs including 25 Engineering Programs.
Admissions are based on merit. Students must meet specific academic requirements and pass the university's entry test (KFAT/KFEAT/KFGAT) followed by an interview.
The university offers substantial number of scholarships and financial assistance to facilitate talented and needy students.
Contact: Khwaja Fareed University of Engineering and Information Technology, Rahim Yar Khan
Email: info@kfueit.edu.pk | Phone: +92-68-588000
For exact fee structure, please visit: https://www.eportal.kfueit.edu.pk or contact the admissions office.
"""
    
    return context_str if context_str else "No relevant information found in the knowledge base."


# ═══════════════════════════════════════════════════════════════════════════
#  DATASET UPDATE ENGINE (Admin Only)
# ═══════════════════════════════════════════════════════════════════════════

def parse_admin_update_command(instruction: str, content: str) -> dict:
    """
    Parse admin instructions to determine what kind of update to make.
    Returns action info.
    """
    inst_lower = instruction.lower()
    
    if any(w in inst_lower for w in ["add", "insert", "include", "append"]):
        action = "add"
    elif any(w in inst_lower for w in ["update", "change", "modify", "edit", "replace"]):
        action = "update"
    elif any(w in inst_lower for w in ["remove", "delete", "erase"]):
        action = "remove"
    else:
        action = "add"  # default
    
    return {"action": action, "instruction": instruction, "content": content}


def apply_dataset_update(agent_id: str, instruction: str, content: str) -> dict:
    """
    Apply admin update to the dataset JSON.
    Adds/updates/removes records based on admin prompt.
    """
    path = get_dataset_path(agent_id)
    if not os.path.exists(path):
        return {"success": False, "message": "Dataset not found. Train the agent first."}
    
    with open(path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    
    cmd = parse_admin_update_command(instruction, content)
    action = cmd["action"]
    
    if action == "remove":
        # Find and remove records matching content keywords
        keywords = get_query_words(instruction + " " + content)
        before_count = len(dataset["records"])
        dataset["records"] = [
            r for r in dataset["records"]
            if not any(kw in r["record_payload"].get("content", "").lower() or
                      kw in r["record_payload"].get("title", "").lower()
                      for kw in keywords)
        ]
        removed = before_count - len(dataset["records"])
        msg = f"Removed {removed} records matching the criteria."
    
    elif action == "update":
        # Update records that match, or add if not found
        keywords = get_query_words(instruction)
        updated = 0
        for r in dataset["records"]:
            payload = r["record_payload"]
            if any(kw in payload.get("title", "").lower() or
                   kw in payload.get("content", "")[:200].lower()
                   for kw in keywords):
                payload["content"] = content + "\n\n" + payload.get("content", "")
                payload["last_updated"] = datetime.now().isoformat()
                updated += 1
                if updated >= 3:  # limit updates
                    break
        if updated == 0:
            # Add as new record
            _add_record(dataset, instruction, content)
            msg = f"No matching records found. Added as new knowledge entry."
        else:
            msg = f"Updated {updated} existing records with new information."
    
    else:  # add
        _add_record(dataset, instruction, content)
        msg = f"Successfully added new knowledge entry to the dataset."
    
    dataset["last_updated_by_admin"] = datetime.now().isoformat()
    dataset["admin_update_count"] = dataset.get("admin_update_count", 0) + 1
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    
    return {"success": True, "message": msg, "action": action, "record_count": len(dataset["records"])}


def _add_record(dataset: dict, instruction: str, content: str):
    """Add a new record to the dataset."""
    record_id = f"admin:{hashlib.md5((instruction + content).encode()).hexdigest()[:12]}"
    new_record = {
        "record_id": record_id,
        "record_type": "admin_added",
        "source_url": "admin_update",
        "source_section_id": "admin-content",
        "source_section_label": instruction[:100],
        "source_locator": "admin",
        "source_authority_tier": 1,  # highest priority
        "conflict_scope_id": record_id,
        "dedupe_key": f"admin:{hash(content)}",
        "cycle_label": None,
        "year_confidence": datetime.now().year,
        "record_payload": {
            "title": instruction[:100],
            "content": content,
            "prompt": instruction,
            "url": "",
            "added_by": "admin",
            "added_at": datetime.now().isoformat()
        }
    }
    dataset["records"].insert(0, new_record)  # Insert at front for priority


def get_dataset_stats(agent_id: str) -> dict:
    """Get statistics about the dataset."""
    path = get_dataset_path(agent_id)
    if not os.path.exists(path):
        return {"exists": False}
    with open(path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    records = dataset.get("records", [])
    admin_records = [r for r in records if r.get("record_type") == "admin_added"]
    return {
        "exists": True,
        "total_records": len(records),
        "crawled_records": len(records) - len(admin_records),
        "admin_added_records": len(admin_records),
        "total_pages_crawled": dataset.get("total_pages_crawled", 0),
        "created_at": dataset.get("created_at", ""),
        "last_updated": dataset.get("last_updated_by_admin", "Never"),
        "admin_update_count": dataset.get("admin_update_count", 0),
        "sources": [s.get("source_url", "") for s in dataset.get("sources", [])]
    }


# ═══════════════════════════════════════════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════════════════════════════════════════

def get_dataset_path(agent_id: str) -> str:
    """
    The agent's working JSON is stored inside its website's bundle folder.
    We search all bundle folders for a file named {agent_id}.json.
    Falls back to the legacy top-level path for old datasets.
    """
    base         = os.path.dirname(os.path.abspath(__file__))
    datasets_dir = os.path.join(base, "datasets")

    # Search inside bundle folders first (new structure)
    if os.path.isdir(datasets_dir):
        for entry in os.listdir(datasets_dir):
            if entry.endswith("-bundle"):
                candidate = os.path.join(datasets_dir, entry, f"{agent_id}.json")
                if os.path.exists(candidate):
                    return candidate

    # Legacy fallback — loose file at top level (old structure)
    return os.path.join(datasets_dir, f"{agent_id}.json")


def verify_admin(token: str):
    if token != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin token")


# ── Agent CRUD (unchanged) ────────────────────────────────────────────────

@app.post("/agents")
def create_agent_endpoint(agent: AgentCreate):
    agent_id = str(uuid.uuid4())
    create_agent(agent_id, agent.name, agent.description)
    return {"id": agent_id, **agent.dict()}

@app.get("/agents")
def list_agents():
    return get_agents()

@app.get("/agents/{agent_id}")
def get_agent_endpoint(agent_id: str):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent

@app.put("/agents/{agent_id}")
def update_agent_endpoint(agent_id: str, agent: AgentUpdate):
    update_agent(agent_id, **agent.dict(exclude_unset=True))
    return get_agent(agent_id)

@app.delete("/agents/{agent_id}")
def delete_agent_endpoint(agent_id: str):
    # Fetch agent BEFORE deleting so we can read train_url
    agent = get_agent(agent_id)

    delete_agent(agent_id)

    # Remove the agent's working JSON (now lives inside bundle folder)
    path = get_dataset_path(agent_id)
    if os.path.exists(path):
        os.remove(path)

    # Remove the guide-compliant bundle folder ({site_slug}-bundle/) ONLY if
    # no other agent JSON files remain inside it (multiple agents may share a bundle)
    if agent and agent.get("train_url"):
        try:
            site_slug  = _domain_slug(agent["train_url"])
            base       = os.path.dirname(os.path.abspath(__file__))
            bundle_dir = os.path.join(base, "datasets", f"{site_slug}-bundle")
            if os.path.isdir(bundle_dir):
                # Check if any other agent JSONs remain in this bundle
                remaining = [f for f in os.listdir(bundle_dir) if f.endswith(".json") and f not in ("manifest.json", "sources.json")]
                if not remaining:
                    shutil.rmtree(bundle_dir)
        except Exception:
            pass  # Never block deletion if bundle cleanup fails

    return {"status": "deleted"}

@app.post("/agents/{agent_id}/train")
def train_agent(agent_id: str, req: TrainRequest):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    dataset_path = save_dataset(agent_id, req.url, req.prompt, req.description)
    # Store train_url so delete can find and remove the bundle folder later
    update_agent(agent_id, dataset_path=dataset_path, train_url=req.url)
    return {"status": "trained", "dataset_path": dataset_path}


# ── Dataset Stats ─────────────────────────────────────────────────────────

@app.get("/agents/{agent_id}/stats")
def get_agent_stats(agent_id: str):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return get_dataset_stats(agent_id)


# ── Admin: Update Dataset via Prompt ─────────────────────────────────────

@app.post("/agents/{agent_id}/admin/update-dataset")
def admin_update_dataset(agent_id: str, req: DatasetUpdateRequest):
    verify_admin(req.admin_token)
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    result = apply_dataset_update(agent_id, req.instruction, req.content)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


# ── Admin Chat (can discuss and update dataset) ──────────────────────────

@app.post("/agents/{agent_id}/admin/chat")
def admin_chat(agent_id: str, req: AdminChatRequest):
    verify_admin(req.admin_token)
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    dataset_path = get_dataset_path(agent_id)
    if not os.path.exists(dataset_path):
        return {"reply": "⚠️ Agent not trained yet. Please crawl a website first.", "role": "admin"}

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    records     = dataset.get("records", [])
    agent_name  = agent.get("name", "Assistant")
    message     = req.message.strip()
    lang        = detect_language(message)

    # Check if admin is making a dataset update command
    update_keywords = ["add info", "add information", "update info", "change info", "remove info",
                       "delete record", "add record", "insert", "add knowledge", "update knowledge",
                       "add data", "update data", "remove", "correct the", "fix the"]
    
    is_update_command = any(kw in message.lower() for kw in update_keywords)
    
    if is_update_command:
        reply = (
            "📝 **Admin Update Mode**\n\n"
            "To update the dataset, use the **Dataset Manager** panel on the left.\n"
            "You can:\n"
            "• **Add** new information with a title and content\n"
            "• **Update** existing records by keyword\n"
            "• **Remove** records matching criteria\n\n"
            "The changes take effect immediately for all users! 🚀"
        )
        return {"reply": reply, "role": "admin"}

    # Otherwise answer the query from dataset (same as user but with admin badge)
    intent = detect_intent(message)
    
    if intent == "greeting":
        reply = f"👨‍💼 Admin Mode Active. I'm {agent_name}. Dataset has **{len(records)} records**. Ask anything or manage the dataset from the left panel."
        return {"reply": reply, "role": "admin"}
    
    if intent == "help":
        stats = get_dataset_stats(agent_id)
        reply = (
            f"**Admin Dashboard - {agent_name}**\n\n"
            f"📊 Dataset Stats:\n"
            f"• Total Records: {stats.get('total_records', 0)}\n"
            f"• Crawled Records: {stats.get('crawled_records', 0)}\n"
            f"• Admin-Added: {stats.get('admin_added_records', 0)}\n"
            f"• Updates Made: {stats.get('admin_update_count', 0)}\n\n"
            f"You can test any query below, or manage the dataset using the Dataset Manager panel."
        )
        return {"reply": reply, "role": "admin"}

    reply = build_response(message, records, agent_name, lang)
    return {"reply": reply, "role": "admin"}


# ── User Chat (read-only, no dataset changes) ────────────────────────────

@app.post("/agents/{agent_id}/chat")
async def chat_with_agent(agent_id: str, req: ChatRequest):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    dataset_path = get_dataset_path(agent_id)
    if not os.path.exists(dataset_path):
        raise HTTPException(status_code=404, detail="Agent not trained yet.")

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    records     = dataset.get("records", [])
    agent_name  = agent.get("name", "Assistant")
    message     = req.message.strip()
    intent      = detect_intent(message)
    lang        = detect_language(message)

    if intent == "greeting":
        if lang == "roman_urdu":
            reply = f"Walaikum Assalam! 👋 Main {agent_name} hoon, aapka AI assistant. Aap mujhse kuch bhi pooch sakte hain. Batain kya jaanna chahte hain?"
        else:
            reply = f"Hello! 👋 I'm {agent_name}, your AI assistant. Feel free to ask me anything. What would you like to know?"
        return {"reply": reply}

    if intent == "thanks":
        if lang == "roman_urdu":
            reply = "Aapka shukriya! 😊 Koi aur sawal ho toh zaroor poochein."
        else:
            reply = "You're welcome! 😊 Feel free to ask if you have any other questions."
        return {"reply": reply}

    if intent == "goodbye":
        if lang == "roman_urdu":
            reply = f"Allah Hafiz! 👋 Jab bhi koi sawal ho, main yahan hoon."
        else:
            reply = f"Goodbye! 👋 Feel free to come back anytime. {agent_name} is always here to help!"
        return {"reply": reply}

    if intent == "help":
        if lang == "roman_urdu":
            reply = f"Main {agent_name} ka AI assistant hoon. Aap mujhse pooch sakte hain:\n\n• Admissions aur enrollment\n• Programs aur courses\n• Fees aur scholarships\n• Faculty aur departments\n• Campus aur facilities\n• Events aur news\n\nKya poochna chahte hain?"
        else:
            reply = f"I'm the AI assistant for {agent_name}. You can ask me about:\n\n• Admissions & enrollment\n• Programs & courses\n• Fees & scholarships\n• Faculty & departments\n• Campus & facilities\n• Latest news & events\n\nWhat would you like to know?"
        return {"reply": reply}

    if not records:
        return {"reply": "I'm not trained yet. Please contact the administrator."}

    query_words = get_query_words(message)
    context = await build_context_from_dataset(records, message, query_words)
    
    reply = await query_gemini(message, context, agent_name, lang)
    
    return {"reply": reply}


# ── Admin: Verify Token ───────────────────────────────────────────────────

@app.post("/admin/verify")
def verify_admin_token(req: dict):
    token = req.get("token", "")
    if token == ADMIN_SECRET:
        return {"valid": True}
    return {"valid": False}


# ── Embed Code (unchanged) ────────────────────────────────────────────────

@app.get("/agents/{agent_id}/embed-code")
def get_embed_code(agent_id: str):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    embed_code = """<!-- KFUET Chatbot Widget -->
<script>
(function() {
    const agentId = "AGENT_ID";
    const backendUrl = "http://localhost:8000";
    const btn = document.createElement('button');
    btn.style = "position:fixed;bottom:20px;right:20px;width:60px;height:60px;border-radius:50%;background:linear-gradient(135deg,#1a1a2e,#16213e);border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 20px rgba(0,0,0,0.4);z-index:9999;";
    btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="#00d4ff"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>';
    btn.onclick = function() {
        if (document.getElementById('kfuet-widget')) return;
        const w = document.createElement('div');
        w.id = 'kfuet-widget';
        w.style = "position:fixed;bottom:90px;right:20px;width:360px;height:520px;background:#0d0d1a;border-radius:16px;box-shadow:0 8px 40px rgba(0,0,0,0.5);z-index:9998;display:flex;flex-direction:column;overflow:hidden;font-family:'Segoe UI',sans-serif;border:1px solid #1e3a5f;";
        w.innerHTML = `
            <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);color:#00d4ff;padding:14px 18px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1e3a5f;">
                <div><div style="font-weight:700;font-size:15px;letter-spacing:1px;">AGENT_NAME</div><div style="font-size:11px;opacity:0.7;color:#7ec8e3;">🟢 AI Assistant • Online</div></div>
                <button onclick="document.getElementById('kfuet-widget').remove()" style="background:rgba(0,212,255,0.1);border:1px solid #1e3a5f;color:#00d4ff;cursor:pointer;width:28px;height:28px;border-radius:50%;font-size:16px;">×</button>
            </div>
            <div id="kfuet-msgs" style="flex:1;padding:14px;overflow-y:auto;display:flex;flex-direction:column;gap:10px;background:#0d0d1a;"></div>
            <div style="padding:10px 12px;border-top:1px solid #1e3a5f;display:flex;gap:8px;background:#0d0d1a;align-items:center;">
                <input id="kfuet-inp" type="text" placeholder="Ask anything..." style="flex:1;padding:10px 16px;background:#16213e;border:1px solid #1e3a5f;border-radius:24px;outline:none;font-size:14px;color:#e0e0e0;" onkeydown="if(event.key==='Enter')window.kfuetSend()"/>
                <button onclick="window.kfuetSend()" style="background:#00d4ff;color:#0d0d1a;border:none;border-radius:50%;min-width:40px;height:40px;cursor:pointer;font-size:18px;font-weight:bold;">➤</button>
            </div>
        `;
        document.body.appendChild(w);
        const msgs = document.getElementById('kfuet-msgs');
        function addMsg(text, isBot) {
            const d = document.createElement('div');
            d.style = isBot
                ? "align-self:flex-start;background:#16213e;color:#e0e0e0;padding:10px 14px;border-radius:4px 16px 16px 16px;max-width:88%;font-size:14px;line-height:1.6;border:1px solid #1e3a5f;white-space:pre-wrap;"
                : "align-self:flex-end;background:#00d4ff;color:#0d0d1a;padding:10px 14px;border-radius:16px 4px 16px 16px;max-width:88%;font-size:14px;line-height:1.5;";
            d.innerHTML = text.replace(/\\*\\*(.*?)\\*\\*/g,'<strong>$1</strong>').replace(/\\n/g,'<br>');
            msgs.appendChild(d);
            msgs.scrollTop = msgs.scrollHeight;
            return d;
        }
        addMsg('👋 Hello! I am AGENT_NAME. Ask me anything in English or Roman Urdu!', true);
        window.kfuetSend = async function() {
            const inp = document.getElementById('kfuet-inp');
            const msg = inp.value.trim();
            if (!msg) return;
            addMsg(msg, false);
            inp.value = '';
            const t = addMsg('• • •', true);
            t.style.color = '#555';
            try {
                const res = await fetch(backendUrl + '/agents/AGENT_ID/chat', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})});
                const data = await res.json();
                t.remove();
                addMsg(data.reply || 'No response', true);
            } catch(e) { t.remove(); addMsg('❌ Connection error.', true); }
        };
    };
    document.body.appendChild(btn);
})();
</script>""".replace("AGENT_ID", agent_id).replace("AGENT_NAME", agent["name"])
    update_agent(agent_id, embed_code=embed_code)
    return {"embed_code": embed_code}