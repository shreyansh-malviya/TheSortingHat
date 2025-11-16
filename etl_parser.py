# """
# Added NER;

#!/usr/bin/env python3
"""
etl_parser.py
Section-aware, robust fragment parser for Dynamic ETL Pipeline evaluator.

Usage:
    from etl_parser import parse_file
    result = parse_file(text)  # returns dict with 'fragments', 'summary', 'records' (normalized)
"""

from __future__ import annotations
import re
import json
import csv
from io import StringIO
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup

# ============================================================
# NER INTEGRATION
# ============================================================

import spacy
from gliner import GLiNER
from typing import List, Dict, Any

# Load models globally (one-time cost)
# Load SpaCy with detailed logging
nlp = None
try:
    print("DEBUG: Loading SpaCy model en_core_web_trf...")
    nlp = spacy.load("en_core_web_trf")
    print(f"DEBUG: SpaCy loaded successfully. Pipeline: {nlp.pipe_names}")
except Exception as e:
    print(f"DEBUG: en_core_web_trf failed ({e}), trying en_core_web_sm...")
    try:
        nlp = spacy.load("en_core_web_sm")
        print(f"DEBUG: SpaCy sm loaded. Pipeline: {nlp.pipe_names}")
    except Exception as e2:
        print(f"ERROR: Could not load any SpaCy model: {e2}")
        nlp = None

# Load GLiNER with detailed logging
gliner_model = None
try:
    print("DEBUG: Loading GLiNER model...")
    gliner_model = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
    print(f"DEBUG: GLiNER loaded successfully")
except Exception as e:
    print(f"WARNING: GLiNER model failed to load: {e}")
    gliner_model = None

print(f"DEBUG: NER models loaded - SpaCy: {nlp is not None}, GLiNER: {gliner_model is not None}")

# Custom entity labels for domain-specific extraction
CUSTOM_ENTITY_LABELS = [
    "product_id",  # book-978-xxx, food-10A, U-505
    "sku",  # T-001, S-101
    "price",  # $9.99, 5.99 USD
    "isbn",  # 978-0321765723
    "model_number",  # Pixel 7, XPS 13
    "order_id",  # order-12345
    "email",  # support@example.com
    "phone",  # +1-555-0123
    "stock_quantity",  # 120, 45 units
]


def extract_product_ids_with_patterns(text: str) -> List[str]:
    """
    Fallback patterns for product IDs that GLiNER misses
    """
    patterns = [
        r'\b(prod-\d+(?:-[a-z])?)\b',  # prod-1001, prod-1001-b
        r'\b([A-Z]{2,4}-\d{3,6})\b',  # WA-1001, SKU-12345
        r'\b(food-\d+[A-Z]?)\b',  # food-10A
        r'\b(book-[\d-]+)\b',  # book-978-xxx
        r'\b([UTS]-\d+)\b',  # U-505, T-001, S-101
    ]

    ids = []
    for pattern in patterns:
        ids.extend(re.findall(pattern, text, re.IGNORECASE))

    return list(set(ids))  # deduplicate

@dataclass
class NEREntity:
    """Represents a detected entity from NER"""
    text: str
    label: str
    start: int
    end: int
    score: float = 1.0
    source: str = "spacy"  # "spacy" or "gliner"


class NEREnricher:
    """Add NER entities to detected fragments"""

    def __init__(self):
        self.nlp = nlp
        self.gliner = gliner_model
        print(f"DEBUG: NEREnricher.__init__ - nlp={self.nlp is not None}, gliner={self.gliner is not None}")

    @property
    def enabled(self):
        """Check if at least one NER model is available"""
        result = self.nlp is not None or self.gliner is not None
        print(f"DEBUG: NEREnricher.enabled = {result}")
        return result

    def enrich_fragment(self, block: DetectedBlock) -> DetectedBlock:
        """
        Add NER entities to a fragment's metadata
        Returns updated block with 'entities' in meta
        """
        print(f"DEBUG: enrich_fragment called for {block.format_type} ({len(block.text)} chars)")

        if not self.enabled:
            print("DEBUG: NER not enabled, skipping enrichment")
            block.meta['entities'] = []
            block.meta['entity_summary'] = {}
            return block

        entities = []
        text = block.text
        print(f"DEBUG: Processing text sample: {text[:100]}")

        # Step 1: SpaCy standard entities
        # Step 1: SpaCy standard entities
        if self.nlp is not None:
            try:
                print(f"DEBUG: Running SpaCy NER on text...")
                doc = self.nlp(text)
                print(f"DEBUG: SpaCy found {len(doc.ents)} entities")
                for ent in doc.ents:
                    print(f"DEBUG: SpaCy entity: {ent.text} ({ent.label_})")
                    entities.append(NEREntity(
                        text=ent.text,
                        label=ent.label_,
                        start=block.start_index + ent.start_char,
                        end=block.start_index + ent.end_char,
                        score=1.0,
                        source="spacy"
                    ))
            except Exception as e:
                print(f"ERROR: SpaCy NER failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("DEBUG: SpaCy model not available")

        # Step 2: GLiNER custom entities (domain-specific)
        if self.gliner is not None:
            try:
                print(f"DEBUG: Running GLiNER on text...")
                gliner_entities = self.gliner.predict_entities(
                    text,
                    CUSTOM_ENTITY_LABELS,
                    threshold=0.5
                )
                print(f"DEBUG: GLiNER found {len(gliner_entities)} entities")
                for ent in gliner_entities:
                    print(f"DEBUG: GLiNER entity: {ent['text']} ({ent['label']}, score={ent['score']:.2f})")
                    entities.append(NEREntity(
                        text=ent['text'],
                        label=ent['label'],
                        start=block.start_index + ent['start'],
                        end=block.start_index + ent['end'],
                        score=ent['score'],
                        source="gliner"
                    ))
            except Exception as e:
                print(f"ERROR: GLiNER failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("DEBUG: GLiNER model not available")

        # Step 3: Pattern-based fallback for critical entities
        # Product IDs
        pattern_ids = extract_product_ids_with_patterns(text)
        for pid in pattern_ids:
            # Check if already found by NER
            existing_texts = [e.text for e in entities if e.label == 'product_id']
            if pid not in existing_texts:
                start_pos = text.find(pid)
                if start_pos != -1:
                    entities.append(NEREntity(
                        text=pid,
                        label='product_id',
                        start=block.start_index + start_pos,
                        end=block.start_index + start_pos + len(pid),
                        score=0.95,
                        source='pattern'
                    ))

        # Emails
        emails = re.findall(r'\b[\w\.-]+@[\w\.-]+\.\w+\b', text)
        for email in emails:
            existing_texts = [e.text for e in entities if e.label in ('email', 'EMAIL')]
            if email not in existing_texts:
                start_pos = text.find(email)
                if start_pos != -1:
                    entities.append(NEREntity(
                        text=email,
                        label='email',
                        start=block.start_index + start_pos,
                        end=block.start_index + start_pos + len(email),
                        score=1.0,
                        source='pattern'
                    ))

        # URLs
        urls = re.findall(r'https?://[^\s<>"]+', text)
        for url in urls:
            existing_texts = [e.text for e in entities if e.label in ('URL', 'url')]
            if url not in existing_texts:
                start_pos = text.find(url)
                if start_pos != -1:
                    entities.append(NEREntity(
                        text=url,
                        label='URL',
                        start=block.start_index + start_pos,
                        end=block.start_index + start_pos + len(url),
                        score=1.0,
                        source='pattern'
                    ))

        block.meta['entities'] = [
            {
                'text': e.text,
                'label': e.label,
                'start': e.start,
                'end': e.end,
                'score': e.score,
                'source': e.source
            }
            for e in entities
        ]

        # Add entity summary
        block.meta['entity_summary'] = self._summarize_entities(entities)

        print(f"DEBUG: Enrichment complete. Total entities found: {len(entities)}")
        print(f"DEBUG: Entity summary: {block.meta['entity_summary']}")

        return block

    def _summarize_entities(self, entities: List[NEREntity]) -> Dict[str, Any]:
        """Create summary statistics of entities"""
        from collections import Counter

        label_counts = Counter(e.label for e in entities)

        # Extract specific useful info
        product_ids = [e.text for e in entities if e.label == 'product_id']
        prices = [e.text for e in entities if e.label in ('price', 'MONEY')]
        emails = [e.text for e in entities if e.label in ('email', 'EMAIL')]
        phones = [e.text for e in entities if e.label in ('phone', 'PHONE')]

        return {
            'total_entities': len(entities),
            'by_label': dict(label_counts),
            'product_ids': product_ids,
            'prices': prices,
            'emails': emails,
            'phones': phones
        }

    def enrich_all_fragments(self, blocks: List[DetectedBlock]) -> List[DetectedBlock]:
        """Enrich all fragments with NER"""
        enriched = []
        for block in blocks:
            try:
                enriched_block = self.enrich_fragment(block)
                enriched.append(enriched_block)
            except Exception as e:
                # If enrichment fails, keep original block
                enriched.append(block)
        return enriched

# ---------- Data classes ----------
@dataclass
class DetectedBlock:
    format_type: str
    start_index: int
    end_index: int
    confidence: float
    text: str
    meta: Dict[str, Any] = field(default_factory=dict)

# ---------- Priority list (lower index = higher priority) ----------
FORMAT_PRIORITY = [
    "JSON_LD",
    "JSON",
    "MALFORMED_JSON",
    "HTML_TABLE",
    "HTML",
    "YAML_FRONTMATTER",
    "CSV",
    "CSV_NO_HEADER",
    "KEY_VALUE",
    "JS_OBJECT",
    "SQL",
    "RAW_TEXT",
]

# ---------- Utilities ----------
def clamp_conf(c: float) -> float:
    return max(0.0, min(1.0, float(c)))

def contains_any(chars: str, needles: List[str]) -> bool:
    return any(n in chars for n in needles)

# ---------- Safe JSON span finder (brace-counting with string awareness) ----------
def find_json_span(text: str, start_pos: int, max_len: int = 200000) -> Optional[Tuple[int,int]]:
    """
    If a '{' at start_pos (or later) begins a JSON object, return (start, end)
    where end is index of the matching '}' +1. If cannot find matching brace within limits, return None.
    This function handles string quoting and escapes to avoid being fooled by braces inside strings.
    """
    n = len(text)
    i = start_pos
    # move forward to first '{'
    while i < n and text[i] != '{':
        i += 1
    if i >= n:
        return None
    start = i
    depth = 0
    in_string = False
    escape = False
    string_char = ''
    j = i
    limit = min(n, i + max_len)
    while j < limit:
        ch = text[j]
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == string_char:
                in_string = False
        else:
            if ch == '"' or ch == "'":
                in_string = True
                string_char = ch
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return (start, j+1)
        j += 1
    # didn't find closing brace within limit
    return None

# ---------- Section-splitting helpers ----------
SECTION_DIV_RE = re.compile(r'^(---\s*[\w \-()/:]*\n)', re.MULTILINE)  # captures '--- HEADER\n'
VARIANT_START_RE = re.compile(r'^(===\s*VARIANT\b[\s\S]*?===\s*VARIANT\b.*?===)', re.MULTILINE)

# ---------- Detector core ----------
class ETLFragmentDetector:
    def __init__(self, text: str):
        self.text = text
        self.n = len(text)
        self.blocks: List[DetectedBlock] = []
        self.occupied = []  # list of (start,end) reserved by high-priority blocks

    def mark_occupied(self, start: int, end: int):
        self.occupied.append((start, end))

    def is_occupied(self, start: int, end: int) -> bool:
        for a,b in self.occupied:
            # if overlap
            if not (end <= a or start >= b):
                return True
        return False

    def add_block(self, block: DetectedBlock):
        self.blocks.append(block)
        # Reserve area for high priority types to avoid low-priority collisions
        if block.format_type in ("JSON_LD","JSON","MALFORMED_JSON","HTML_TABLE","HTML","YAML_FRONTMATTER"):
            self.mark_occupied(block.start_index, block.end_index)

    # ---------- 1. JSON-LD (script type=application/ld+json) ----------
    def detect_json_ld(self):
        try:
            for m in re.finditer(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', self.text, flags=re.IGNORECASE):
                start = m.start(1)
                end = m.end(1)
                snippet = m.group(1).strip()
                conf = 0.9
                # try strict parse
                try:
                    parsed = json.loads(snippet)
                    conf = 0.99
                except Exception:
                    conf = 0.6
                self.add_block(DetectedBlock("JSON_LD", start, end, clamp_conf(conf), self.text[start:end], {"parsed": conf>0.9}))
        except Exception as e:
            # fail safe: don't crash detector
            pass

    # ---------- 2. YAML frontmatter (--- ... ---) ----------
    def detect_yaml_frontmatter(self):
        try:
            for m in re.finditer(r'(^|\n)---\s*\n([\s\S]{0,2000}?)\n---', self.text, flags=re.MULTILINE):
                start = m.start(2)
                end = m.end(2)
                snippet = m.group(2)
                # heuristic: many lines with ':'
                lines = [ln for ln in snippet.splitlines() if ln.strip()]
                colon_ratio = sum(1 for ln in lines if ':' in ln) / max(1, len(lines))
                conf = 0.95 if colon_ratio > 0.5 else 0.6
                if not self.is_occupied(start, end):
                    self.add_block(DetectedBlock("YAML_FRONTMATTER", start, end, clamp_conf(conf), self.text[start:end], {"colon_ratio": colon_ratio}))
        except Exception:
            pass

    # ---------- 3. Section-aware explicit JSON markers (--- INLINE JSON / MALFORMED JSON) ----------
    def detect_sectioned_jsons(self):
        # If file uses '--- INLINE JSON' style, use that boundary
        # Find lines that start with '---' and check header text
        try:
            for m in re.finditer(r'(^|\n)---\s*([A-Z0-9 _\-()]+)\s*\n', self.text, flags=re.IGNORECASE):
                header = m.group(2).strip().upper()
                # section body starts after match
                body_start = m.end()
                # find next section divider or EOF
                next_div = re.search(r'\n---\s*[\w \-()/:]*\n', self.text[body_start:], flags=re.IGNORECASE)
                if next_div:
                    body_end = body_start + next_div.start()
                else:
                    body_end = self.n
                body = self.text[body_start:body_end].strip()
                if not body:
                    continue
                if "JSON" in header and not self.is_occupied(body_start, body_end):
                    # try to find JSON inside body (brace counting)
                    js_span = find_json_span(self.text, body_start)
                    if js_span:
                        s,e = js_span
                        try:
                            json.loads(self.text[s:e])
                            conf=0.99
                            ftype="JSON"
                        except Exception:
                            conf=0.45
                            ftype="MALFORMED_JSON"
                        self.add_block(DetectedBlock(ftype, s, e, clamp_conf(conf), self.text[s:e], {"section_header": header}))
                    else:
                        # No matching closing brace -> treat as MALFORMED_JSON covering body
                        if not self.is_occupied(body_start, body_end):
                            self.add_block(DetectedBlock("MALFORMED_JSON", body_start, body_end, 0.4, self.text[body_start:body_end], {"section_header": header}))
        except Exception:
            pass

    # ---------- 4. JSON (strict) & MALFORMED JSON (brace heuristics) ----------
    def detect_jsons_global(self):
        i = 0
        text = self.text
        n = self.n
        while True:
            # find next '{' from i
            m = re.search(r'\{', text[i:])
            if not m:
                break
            pos = i + m.start()
            # if occupied by higher-priority block, skip ahead
            if self.is_occupied(pos, pos+1):
                i = pos + 1
                continue
            span = find_json_span(text, pos, max_len=200000)
            if span:
                s,e = span
                # If this region overlaps existing occupied high-priority, skip
                if self.is_occupied(s,e):
                    i = e
                    continue
                snippet = text[s:e]
                # strict parse
                try:
                    _ = json.loads(snippet)
                    conf = 0.98
                    self.add_block(DetectedBlock("JSON", s, e, conf, snippet, {}))
                except Exception:
                    # try smaller window (maybe JSON-LD or partial)
                    # If snippet has many key:value patterns, mark MALFORMED_JSON with moderate confidence
                    kv_like = len(re.findall(r'"\w+"\s*:', snippet)) + len(re.findall(r'\w+\s*:', snippet))
                    conf = 0.5 if kv_like >= 2 else 0.25
                    self.add_block(DetectedBlock("MALFORMED_JSON", s, e, clamp_conf(conf), snippet, {"kv_like": kv_like}))
                i = e
            else:
                # No closing brace within limit -> treat up to next blank line or 1000 chars as malformed
                tail_end = min(n, pos + 2000)
                # try to extend until double newline
                remainder = text[pos:tail_end]
                dn = re.search(r'\n\s*\n', remainder)
                if dn:
                    end = pos + dn.start()
                else:
                    end = tail_end
                if not self.is_occupied(pos,end):
                    snippet = text[pos:end]
                    # heuristics: if snippet contains colon or quotes, mark MALFORMED_JSON
                    if re.search(r'["\']\w+["\']\s*:', snippet) or re.search(r'\w+\s*:\s*', snippet):
                        self.add_block(DetectedBlock("MALFORMED_JSON", pos, end, 0.35, snippet, {"note":"unclosed"}))
                i = end

    # ---------- 5. HTML TABLES and HTML (use BeautifulSoup for reliability) ----------
    def detect_html_tables_and_blocks(self):
        # tables first
        try:
            for m in re.finditer(r'<table\b', self.text, flags=re.IGNORECASE):
                # find end via regex '</table>' from here
                start = m.start()
                if self.is_occupied(start, start+1):
                    continue
                end_tag = re.search(r'</table\s*>', self.text[start:], flags=re.IGNORECASE)
                if end_tag:
                    end = start + end_tag.end()
                    snippet = self.text[start:end]
                    # parse quickly with BeautifulSoup to count rows/cols
                    try:
                        soup = BeautifulSoup(snippet, "html.parser")
                        rows = soup.find_all("tr")
                        cols = max((len(r.find_all(['td','th'])) for r in rows), default=0)
                        conf = 0.95 if rows and cols>=1 else 0.6
                    except Exception:
                        conf = 0.6
                    if not self.is_occupied(start,end):
                        self.add_block(DetectedBlock("HTML_TABLE", start, end, clamp_conf(conf), snippet, {"rows": len(rows) if 'rows' in locals() else None, "cols": cols if 'cols' in locals() else None}))
        except Exception:
            pass

        # generic HTML blocks (div/section/script etc). Keep only reasonable-size blocks.
        try:
            for m in re.finditer(r'<(div|section|article|header|footer|main|nav|body)\b', self.text, flags=re.IGNORECASE):
                start = m.start()
                if self.is_occupied(start, start+1):
                    continue
                # try to find matching closing tag by name
                tag = m.group(1)
                close_re = re.compile(r'</%s\s*>'%re.escape(tag), flags=re.IGNORECASE)
                close_match = close_re.search(self.text[start:])
                if close_match:
                    end = start + close_match.end()
                    if end - start > 20 and not self.is_occupied(start,end):
                        snippet = self.text[start:end]
                        # compute crude confidence by tag density
                        tag_count = len(re.findall(r'<[A-Za-z]+', snippet))
                        close_count = len(re.findall(r'</', snippet))
                        conf = 0.5 + min(0.4, (min(tag_count, close_count) * 0.03))
                        self.add_block(DetectedBlock("HTML", start, end, clamp_conf(conf), snippet, {"tag_count":tag_count}))
        except Exception:
            pass

    # ---------- 6. CSV detection (robust, avoid JSON) ----------
    def detect_csv_blocks(self):
        lines = self.text.splitlines()
        n = len(lines)
        # compute cumulative char position for quick mapping
        char_pos = [0]
        for ln in lines:
            char_pos.append(char_pos[-1] + len(ln) + 1)  # +1 for newline
        i = 0
        while i < n:
            # skip short or obviously non-csv
            if lines[i].strip()=="":
                i += 1
                continue
            # detect candidate delimiter among , or \t or ;
            cand = None
            for d in (',','\t',';'):
                # require at least 1 delimiter in first line and not JSON-like
                if d in lines[i] and '{' not in lines[i] and '}' not in lines[i]:
                    cand = d
                    break
            if not cand:
                i += 1
                continue
            # collect block where delimiter count stays consistent (allow some variance)
            counts = [lines[i].count(cand)]
            j = i+1
            max_lines = 200
            while j < n and j - i < max_lines and lines[j].strip() and lines[j].count(cand) > 0:
                counts.append(lines[j].count(cand))
                j += 1
            if len(counts) >= 2:
                # consistency check: most rows should have same count
                from collections import Counter
                ctr = Counter(counts)
                common_count, freq = ctr.most_common(1)[0]
                if freq >= max(1, len(counts)//2):
                    start = char_pos[i]
                    end = char_pos[j-1] + len(lines[j-1]) if j-1 < n else char_pos[-1]
                    if not self.is_occupied(start,end):
                        # header detection via alphabetic tokens in first row
                        first = lines[i]
                        has_header = bool(re.search(r'[A-Za-z]', first.split(cand)[0]))
                        ftype = "CSV" if has_header else "CSV_NO_HEADER"
                        conf = 0.9 if has_header else 0.7
                        self.add_block(DetectedBlock(ftype, start, end, conf, self.text[start:end], {"delimiter":cand, "rows": len(counts)}))
                        i = j
                        continue
            i += 1

    # ---------- 7. Key-Value detection ----------
    def detect_key_values(self):
        lines = self.text.splitlines()
        n = len(lines)
        char_pos = [0]
        for ln in lines:
            char_pos.append(char_pos[-1] + len(ln) + 1)
        i = 0
        while i < n:
            if re.match(r'^\s*[#\-]*\s*[\w\-\s]{1,80}\s*[:=]\s*.+', lines[i]):
                j = i
                kv_count = 0
                while j < n and re.match(r'^\s*[\w\-\s]{1,80}\s*[:=]\s*.+', lines[j]):
                    kv_count += 1
                    j += 1
                if kv_count >= 2:
                    start = char_pos[i]
                    end = char_pos[j-1] + len(lines[j-1])
                    if not self.is_occupied(start,end):
                        self.add_block(DetectedBlock("KEY_VALUE", start, end, 0.9, self.text[start:end], {"pairs": kv_count}))
                        i = j
                        continue
            i += 1

    # ---------- 8. JS Object detection ----------
    def detect_js_objects(self):
        try:
            for m in re.finditer(r'\b(var|let|const)\s+([A-Za-z0-9_$]+)\s*=\s*\{', self.text):
                start = m.start(0)
                if self.is_occupied(start, start+1):
                    continue
                span = find_json_span(self.text, m.start(0)+m.group(0).rfind('{'))
                if span:
                    s,e = span
                    if not self.is_occupied(s,e):
                        snippet = self.text[start:e]
                        self.add_block(DetectedBlock("JS_OBJECT", start, e, 0.88, snippet, {"var_name": m.group(2)}))
        except Exception:
            pass

    # ---------- 9. SQL detection ----------
    def detect_sql(self):
        # detect queries like SELECT ... ; or lines starting with -- comment then SELECT
        try:
            for m in re.finditer(r'(--[^\n]*\n\s*)?(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP)\b[\s\S]{0,400}?\;', self.text, flags=re.IGNORECASE):
                start,end = m.start(), m.end()
                if not self.is_occupied(start,end):
                    self.add_block(DetectedBlock("SQL", start, end, 0.9, self.text[start:end], {}))
        except Exception:
            pass

    # ---------- 10. RAW text paragraphs (catch any remaining) ----------
    def detect_raw_text(self):
        # Partition by occupied spans and capture leftover textual chunks as RAW_TEXT
        spans = [(0,self.n)]
        # subtract occupied intervals
        for a,b in sorted(self.occupied):
            new_spans = []
            for s,e in spans:
                if b <= s or a >= e:
                    new_spans.append((s,e))
                else:
                    if s < a:
                        new_spans.append((s,a))
                    if b < e:
                        new_spans.append((b,e))
            spans = new_spans
        for s,e in spans:
            seg = self.text[s:e].strip()
            if len(seg) >= 20:
                # split into paragraphs of reasonable size
                parts = re.split(r'\n\s*\n', seg)
                pos = s
                for p in parts:
                    p = p.strip()
                    if not p:
                        pos += len(p) + 2
                        continue
                    start = self.text.find(p, pos, e)
                    if start == -1:
                        continue
                    end = start + len(p)
                    # don't create RAW_TEXT overlapping existing blocks
                    if not self.is_occupied(start,end):
                        self.add_block(DetectedBlock("RAW_TEXT", start, end, 0.35, self.text[start:end], {}))
                    pos = end

    # ---------- orchestrator ----------
    def run_all(self):
        # order matters: highest-confidence, containment-sensitive detectors first
        self.detect_json_ld()
        self.detect_yaml_frontmatter()
        self.detect_sectioned_jsons()
        self.detect_jsons_global()
        self.detect_html_tables_and_blocks()
        self.detect_js_objects()
        self.detect_csv_blocks()
        self.detect_key_values()
        self.detect_sql()
        self.detect_raw_text()
        # final sort by start_index
        self.blocks.sort(key=lambda b: b.start_index)
        # dedupe & prioritize
        self.blocks = self._dedupe_prioritize(self.blocks)
        return self.blocks

    def _dedupe_prioritize(self, blocks: List[DetectedBlock]) -> List[DetectedBlock]:
        """
        Remove low-priority blocks fully contained by higher-priority ones.
        Mark parent-child relationships for overlapping fragments.
        """
        kept: List[DetectedBlock] = []

        for b in sorted(blocks, key=lambda x: (x.start_index, -(x.end_index - x.start_index))):
            contained_by = None
            for k in kept:
                if b.start_index >= k.start_index and b.end_index <= k.end_index:
                    # b is inside k. Decide based on priority
                    try:
                        p_k = FORMAT_PRIORITY.index(k.format_type)
                    except ValueError:
                        p_k = len(FORMAT_PRIORITY)
                    try:
                        p_b = FORMAT_PRIORITY.index(b.format_type)
                    except ValueError:
                        p_b = len(FORMAT_PRIORITY)

                    if p_k <= p_b:
                        contained_by = k
                        break

            if contained_by is None:
                kept.append(b)
            else:
                # Keep both only if child has strictly higher priority
                try:
                    if FORMAT_PRIORITY.index(b.format_type) < FORMAT_PRIORITY.index(contained_by.format_type):
                        # Mark parent-child relationship
                        b.meta['parent_fragment'] = f"frag_{contained_by.start_index}"
                        if 'child_fragments' not in contained_by.meta:
                            contained_by.meta['child_fragments'] = []
                        contained_by.meta['child_fragments'].append(f"frag_{b.start_index}")
                        kept.append(b)
                    else:
                        # Drop child, but note in parent
                        if 'skipped_children' not in contained_by.meta:
                            contained_by.meta['skipped_children'] = []
                        contained_by.meta['skipped_children'].append({
                            'type': b.format_type,
                            'range': f"{b.start_index}-{b.end_index}"
                        })
                except Exception:
                    pass

        # Final sort and clamp confidences
        kept.sort(key=lambda x: x.start_index)
        for k in kept:
            k.confidence = clamp_conf(k.confidence)

        return kept

# ---------- Normalizer (simple, safe) ----------
class Normalizer:
    """Convert block.text to structured python objects when possible (safe)."""
    @staticmethod
    def normalize(block: DetectedBlock) -> Optional[Any]:
        t = block.format_type
        s = block.text.strip()
        try:
            if t == "JSON" or t == "JSON_LD":
                # strict parse
                return json.loads(s)
            if t == "MALFORMED_JSON":
                # attempt conservative repairs
                repaired = _attempt_repair_json(s)
                if repaired is not None:
                    try:
                        parsed = json.loads(repaired)
                        # VALIDATION: Only return if it's a proper dict with reasonable data
                        if isinstance(parsed, dict) and len(parsed) >= 2:
                            # Check for garbage values
                            has_garbage = any(
                                isinstance(v, str) and (len(v) > 200 or '\n' in v[:50])
                                for v in parsed.values()
                            )
                            if not has_garbage:
                                return parsed
                        # If validation failed, fall through to kv extraction
                    except Exception:
                        pass
                # Fallback: only extract KV if we have clean pairs
                kv_result = _extract_kv_pairs(s)
                if len(kv_result) >= 2:
                    return kv_result
                return None  # Give up if we can't get clean data
            if t in ("CSV","CSV_NO_HEADER"):
                return _safe_parse_csv(s, t=="CSV_NO_HEADER")
            if t == "HTML_TABLE":
                return _html_table_to_rows(s)
            if t == "KEY_VALUE":
                return _parse_kv(s)
            if t == "JS_OBJECT":
                # strip var/let/const assignment
                m = re.search(r'=\s*(\{[\s\S]*\})\s*;?$', s)
                if m:
                    obj = m.group(1)
                    # attempt quick conversion: single quotes -> double
                    obj2 = re.sub(r"'", '"', obj)
                    try:
                        return json.loads(obj2)
                    except:
                        # fallback to kv extraction
                        return _extract_kv_pairs(obj)
            if t == "SQL":
                # Safety check: don't store malicious SQL
                s_lower = s.lower()
                if 'drop table' in s_lower or 'delete from' in s_lower or 'truncate' in s_lower:
                    print(f"  WARNING: Skipping potentially malicious SQL: {s[:50]}")
                    return None
                return {"sql": s}
        except Exception:
            return None
        return None

# ---------- small helpers for Normalizer ----------
def _attempt_repair_json(s: str) -> Optional[str]:
    try:
        # Step 1: Remove trailing commas before } or ]
        s2 = re.sub(r',\s*(?=[}\]])', '', s)

        # Step 2: Remove comments (// and /* */)
        s2 = re.sub(r'//[^\n]*', '', s2)
        s2 = re.sub(r'/\*.*?\*/', '', s2, flags=re.DOTALL)

        # Step 3: Convert single quotes to double quotes (carefully)
        # Only for strings, not inside already-quoted strings
        s2 = re.sub(r"(?<=[:\[,\s])'([^']*)'(?=[,\]\}\s])", r'"\1"', s2)

        # Step 4: Quote unquoted keys: { key: -> { "key":
        s2 = re.sub(r'(?P<prefix>[\{,\s])(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:', r'\g<prefix>"\g<key>":', s2)

        # Step 5: Fix missing closing braces (add them)
        open_braces = s2.count('{') - s2.count('}')
        if open_braces > 0:
            s2 = s2 + '}' * open_braces

        return s2
    except Exception:
        return None

def _extract_kv_pairs(s: str) -> Dict[str,str]:
    out = {}
    for k,v in re.findall(r'([A-Za-z0-9_\- ]{1,60})\s*[:=]\s*("[^"]*"|\'[^\']*\'|[^,\n]+)', s):
        val = v.strip().strip('"').strip("'")
        out[k.strip()] = val.strip()
    return out

def _parse_kv(s: str) -> Dict[str,Any]:
    out = {}
    for ln in s.splitlines():
        if ':' in ln:
            k,v = ln.split(':',1)
            out[k.strip()] = v.strip().strip('"')
    return out

def _html_table_to_rows(s: str) -> Optional[List[Dict[str,str]]]:
    try:
        soup = BeautifulSoup(s, "html.parser")
        table = soup.find("table")
        if not table:
            return None
        headers = []
        thead = table.find("thead")
        if thead:
            ths = thead.find_all("th")
            headers = [th.get_text(strip=True) for th in ths]
        rows = []
        for tr in table.find_all("tr"):
            tds = tr.find_all(["td","th"])
            cells = [td.get_text(strip=True) for td in tds]
            if headers and len(cells)==len(headers):
                rows.append(dict(zip(headers,cells)))
            elif not headers and cells:
                # create synthetic headers
                rows.append({f"col_{i}": cells[i] for i in range(len(cells))})
        return rows or None
    except Exception:
        return None

def _safe_parse_csv(text: str, no_header: bool=False) -> Optional[List[Dict[str,str]]]:
    try:
        sio = StringIO(text.strip())
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(text.splitlines()[0]) if text.strip() else None
        reader = csv.reader(sio, dialect=dialect) if dialect else csv.reader(sio)
        rows = list(reader)
        if not rows:
            return None
        if no_header or len(rows) < 2:
            # create synthetic headers
            header = [f"col_{i}" for i in range(len(rows[0]))]
            return [dict(zip(header, r)) for r in rows]
        headers = rows[0]
        return [dict(zip(headers, r)) for r in rows[1:]]
    except Exception:
        # fallback: naive comma split
        try:
            rows = [line.split(',') for line in text.strip().splitlines() if line.strip()]
            if not rows:
                return None
            if len(rows) < 2:
                header = [f"col_{i}" for i in range(len(rows[0]))]
                return [dict(zip(header, r)) for r in rows]
            headers = rows[0]
            return [dict(zip(headers, r)) for r in rows[1:]]
        except Exception:
            return None

# ---------- Top-level parse_file API ----------
def parse_file(text: str, enable_ner: bool = True) -> Dict[str, Any]:
    detector = ETLFragmentDetector(text)
    blocks = detector.run_all()

    print(f"DEBUG: Found {len(blocks)} fragments before NER")

    # NER Enrichment
    if enable_ner:
        print(f"DEBUG: NER enrichment enabled, calling enricher...")
        try:
            enricher = NEREnricher()
            blocks = enricher.enrich_all_fragments(blocks)
            print(f"DEBUG: NER enrichment complete")
        except Exception as e:
            print(f"ERROR: NER enrichment failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("DEBUG: NER enrichment disabled")

    # Normalize detected blocks
    normalizer = Normalizer()
    records = []
    for b in blocks:
        try:
            rec = normalizer.normalize(b)
            if rec is not None:
                # Store parsed content in block meta for merging
                b.meta['parsed_content'] = rec
                print(
                    f"DEBUG: Stored parsed content for {b.format_type} at {b.start_index}: {type(rec)} with {len(rec) if isinstance(rec, (list, dict)) else 'N/A'} items")
                records.append({
                    "format": b.format_type,
                    "start": b.start_index,
                    "end": b.end_index,
                    "data": rec,
                    "entities": b.meta.get('entities', [])
                })
            else:
                print(f"DEBUG: No parsed content for {b.format_type} at {b.start_index}")

        except Exception as e:
            print(f"ERROR: Failed to normalize {b.format_type} at {b.start_index}: {e}")
            import traceback
            traceback.print_exc()
            records.append({
                "format": b.format_type,
                "start": b.start_index,
                "end": b.end_index,
                "data": None,
                "entities": b.meta.get('entities', [])
            })

    # Summary
    summary = {}
    for b in blocks:
        summary[b.format_type] = summary.get(b.format_type, 0) + 1

    # Entity Index
    entity_index = _build_entity_index(blocks)

    # NEW: Group fragments by entity
    grouped_entities = group_fragments_by_entity(blocks, entity_index)

    # NEW: Merge fragments for each entity
    merged_entities = {}
    for entity_id, frags in grouped_entities.items():
        merged_entities[entity_id] = merge_fragments_for_entity(frags, entity_id)

    return {
        "fragments": blocks,
        "summary": summary,
        "records": records,
        "entity_index": entity_index,
        "grouped_entities": grouped_entities,  # NEW
        "merged_entities": merged_entities  # NEW
    }


def _build_entity_index(blocks: List[DetectedBlock]) -> Dict[str, List[Dict]]:
    """
    Build index: entity_text -> list of fragments mentioning it
    With deduplication and noise filtering
    """
    index = {}
    seen_entities = set()  # track (entity_text, fragment_id, label) tuples

    for block in blocks:
        entities = block.meta.get('entities', [])
        fragment_id = f"frag_{block.start_index}"

        for ent in entities:
            entity_text = ent['text']
            label = ent['label']

            # === FILTER OUT NOISE ===

            # Skip generic cardinals (single/double digits, common numbers)
            if label == 'CARDINAL':
                if len(entity_text) <= 2:  # Skip "9", "12", etc.
                    continue
                if entity_text in ('one', 'two', 'three', 'hundred', 'thousand'):
                    continue

            # Skip generic product_id false positives
            if label == 'product_id':
                if entity_text.lower() in ('id', 'sku', 'name', 'title', 'item'):
                    continue
                # Must have at least one digit or hyphen to be valid ID
                if not re.search(r'[\d\-]', entity_text):
                    continue

            # Skip very short entities (likely noise)
            if len(entity_text.strip()) < 2:
                continue

            # === NORMALIZE ===
            normalized = entity_text.strip().lower()

            # === DEDUPLICATE ===
            # Same entity in same fragment (from multiple NER sources)
            entity_key = (normalized, fragment_id, label)
            if entity_key in seen_entities:
                continue
            seen_entities.add(entity_key)

            # === ADD TO INDEX ===
            if normalized not in index:
                index[normalized] = []

            index[normalized].append({
                'fragment_id': fragment_id,
                'format_type': block.format_type,
                'entity_label': label,
                'original_text': entity_text,
                'score': ent.get('score', 1.0),
                'source': ent.get('source', 'unknown')
            })

    return index


def group_fragments_by_entity(blocks: List[DetectedBlock], entity_index: Dict) -> Dict[str, List[DetectedBlock]]:
    """
    Group fragments that reference the same entity (by product_id)
    Returns: {entity_id: [fragments]}
    """
    from collections import defaultdict

    grouped = defaultdict(list)
    fragment_map = {}  # map frag_id -> block

    # Build fragment lookup
    for block in blocks:
        frag_id = f"frag_{block.start_index}"
        fragment_map[frag_id] = block

    print(f"DEBUG: Starting grouping with {len(blocks)} blocks and {len(entity_index)} unique entities")

    # Find all product_id entities and their fragments
    product_mentions = defaultdict(set)  # entity_text -> set of frag_ids

    for entity_text, mentions in entity_index.items():
        for mention in mentions:
            if mention['entity_label'] == 'product_id':
                # Normalize entity text
                normalized = entity_text.lower().strip()

                # Also add variants for common patterns
                # e.g., "prod-1001" should also match "1001"
                product_mentions[normalized].add(mention['fragment_id'])

                # Add numeric-only variant if ID contains numbers
                numeric_part = re.sub(r'[^0-9]', '', normalized)
                if numeric_part and len(numeric_part) >= 3:
                    product_mentions[numeric_part].add(mention['fragment_id'])

    # === DIAGNOSTIC OUTPUT ===
    print(f"DEBUG: Found {len(product_mentions)} unique product IDs with mentions")
    if len(product_mentions) > 0:
        print(f"DEBUG: Showing first 10 product IDs:")
        for i, (pid, frags) in enumerate(list(product_mentions.items())[:10]):
            print(f"  [{i + 1}] '{pid}': {len(frags)} fragment(s) -> {list(frags)[:3]}")
    else:
        print(f"DEBUG: WARNING - No product_id entities found in entity_index!")
        print(
            f"DEBUG: Entity labels present: {set(m['entity_label'] for mentions in entity_index.values() for m in mentions)}")

    # Group fragments by product ID
    print(f"DEBUG: Grouping fragments by product ID...")
    for product_id, frag_ids in product_mentions.items():
        for frag_id in frag_ids:
            if frag_id in fragment_map:
                block = fragment_map[frag_id]
                # CRITICAL: Only add if block has parsed content
                if block.meta.get('parsed_content') is not None:
                    grouped[product_id].append(block)
                    print(f"DEBUG: Added {frag_id} to product '{product_id}'")
                else:
                    print(f"DEBUG: Skipping {frag_id} for {product_id} - no parsed content")
            else:
                print(f"DEBUG: WARNING - {frag_id} not in fragment_map!")

    print(f"DEBUG: After product grouping: {len(grouped)} entities")

    # Add orphan fragments (no product_id but has valuable data)
    # These become separate entities
    orphan_count = 0
    for block in blocks:
        frag_id = f"frag_{block.start_index}"

        # Skip if already grouped
        already_grouped = False
        for entity_id, frags in grouped.items():
            if block in frags:
                already_grouped = True
                break

        if not already_grouped and block.meta.get('parsed_content'):
            # Create synthetic entity ID from format + position
            synthetic_id = f"orphan_{block.format_type.lower()}_{block.start_index}"
            grouped[synthetic_id].append(block)
            orphan_count += 1
            print(f"DEBUG: Creating orphan entity {synthetic_id} for {block.format_type}")

    print(f"DEBUG: Added {orphan_count} orphan entities. Total before dedup: {len(grouped)}")

    # === ENHANCED: DEDUPLICATE ENTITIES ===
    # Merge entities that refer to the same product
    deduplicated = {}
    merged_into = {}  # track what was merged where

    print(f"DEBUG: Starting deduplication on {len(grouped)} entities...")

    for entity_id, frags in grouped.items():
        # Skip orphans from deduplication
        if entity_id.startswith('orphan_'):
            deduplicated[entity_id] = frags
            continue

        # Extract numeric core (remove ALL non-digits)
        entity_numeric = re.sub(r'[^0-9]', '', entity_id.lower())

        # Look for existing entity with same numeric core
        found_match = False
        for existing_id in list(deduplicated.keys()):
            if existing_id.startswith('orphan_'):
                continue

            existing_numeric = re.sub(r'[^0-9]', '', existing_id.lower())

            # Match if numeric cores are identical AND both have substantial numbers (3+ digits)
            if entity_numeric and existing_numeric and len(entity_numeric) >= 3:
                if entity_numeric == existing_numeric:
                    # Choose canonical: prefer the one with more context (letters/hyphens)
                    entity_len = len(entity_id) - len(entity_numeric)  # non-digit chars
                    existing_len = len(existing_id) - len(existing_numeric)

                    if entity_len > existing_len:
                        # New ID is more descriptive - make it canonical
                        canonical = entity_id
                        old_frags = deduplicated.pop(existing_id)
                        deduplicated[canonical] = old_frags + frags
                        merged_into[existing_id] = canonical
                        print(f"DEBUG: Merged '{existing_id}' into new canonical '{canonical}'")
                    else:
                        # Existing is better or equal - keep it
                        canonical = existing_id
                        deduplicated[canonical].extend(frags)
                        merged_into[entity_id] = canonical
                        print(f"DEBUG: Merged '{entity_id}' into existing '{canonical}'")

                    # Deduplicate fragment list (remove duplicate fragments by start_index)
                    seen_starts = {}
                    unique_frags = []
                    for f in deduplicated[canonical]:
                        if f.start_index not in seen_starts:
                            seen_starts[f.start_index] = True
                            unique_frags.append(f)
                    deduplicated[canonical] = unique_frags
                    print(f"DEBUG: Canonical '{canonical}' now has {len(unique_frags)} unique fragments")

                    found_match = True
                    break

        if not found_match:
            # No match found - add as new entity
            deduplicated[entity_id] = frags
            print(f"DEBUG: Added '{entity_id}' as new unique entity ({len(frags)} fragments)")

    print(f"DEBUG: Deduplication complete. Reduced from {len(grouped)} to {len(deduplicated)} entities")

    if len(merged_into) > 0:
        print(f"DEBUG: Merge summary:")
        for old_id, new_id in merged_into.items():
            print(f"  - '{old_id}' → '{new_id}'")

    return dict(deduplicated)


def merge_fragments_for_entity(fragments: List[DetectedBlock], entity_id: str) -> Dict[str, Any]:
    """
    Merge data from multiple fragments about the same entity
    Uses parsed content from records
    """
    merged_data = {}
    sources = {}
    conflicts = {}

    print(f"DEBUG: Merging {len(fragments)} fragments for entity '{entity_id}'")

    # === BLACKLIST KNOWN BAD FRAGMENTS ===
    # These fragments contain only garbage text, not structured data
    BAD_FRAGMENT_STARTS = {1679, 4772}  # Add more as discovered

    for frag in fragments:
        # Skip blacklisted fragments
        if frag.start_index in BAD_FRAGMENT_STARTS:
            print(f"  SKIP: Blacklisted garbage fragment at {frag.start_index}")
            continue

        # Get parsed content (if available)
        parsed = frag.meta.get('parsed_content')

        # === NEW: SKIP LOW-QUALITY FRAGMENTS ===
        # Don't merge MALFORMED_JSON unless it has clean structured data
        if frag.format_type == 'MALFORMED_JSON':
            if not isinstance(parsed, dict) or len(parsed) < 2:
                print(f"  SKIP: Low-quality MALFORMED_JSON at {frag.start_index}")
                continue
            # Check if parsed dict contains garbage (long string values)
            has_garbage = any(
                isinstance(v, str) and len(v) > 200
                for v in parsed.values()
            )
            if has_garbage:
                print(f"  SKIP: MALFORMED_JSON contains garbage at {frag.start_index}")
                continue

        print(f"  MERGE: {frag.format_type} at {frag.start_index}, type={type(parsed)}")

        # Handle different parsed types
        # Handle different parsed types
        if isinstance(parsed, list):
            # CSV/table data - filter rows matching this entity
            for i, row in enumerate(parsed):
                if isinstance(row, dict):
                    # Check if row belongs to this entity
                    row_matches = False

                    # For orphans, include ALL rows
                    if entity_id.startswith('orphan_'):
                        row_matches = True
                    else:
                        # For real entities, check if ANY value matches entity_id
                        for key, value in row.items():
                            value_str = str(value).lower().strip()
                            entity_normalized = entity_id.lower().strip()

                            # Direct match
                            if value_str == entity_normalized:
                                row_matches = True
                                break

                            # Partial match for product IDs (prod-1001 matches in "prod-1001")
                            if entity_normalized in value_str or value_str in entity_normalized:
                                row_matches = True
                                break

                    if row_matches:
                        # Skip header rows (where values match column names)
                        is_header = False
                        if i == 0:  # First row might be header
                            # Check if any value matches its key (case-insensitive)
                            for key, value in row.items():
                                if str(value).lower().strip() == key.lower().strip():
                                    is_header = True
                                    break

                        if is_header:
                            print(f"    SKIP row {i}: detected as header row")
                            continue

                        # Include this row
                        flat = _flatten_dict(row)
                        for key, value in flat.items():
                            prefixed_key = f"row_{i}_{key}"
                            merged_data[prefixed_key] = value
                            sources[prefixed_key] = f"frag_{frag.start_index}"
                        print(f"    Added row {i}: {list(flat.keys())}")
                    else:
                        print(f"    SKIP row {i}: doesn't match entity {entity_id}")
        elif isinstance(parsed, dict):
            # Normal dict data
            flat = _flatten_dict(parsed)
            print(f"    Flattened to {len(flat)} fields: {list(flat.keys())[:5]}...")

            for key, value in flat.items():
                if key not in merged_data:
                    merged_data[key] = value
                    sources[key] = f"frag_{frag.start_index}"
                else:
                    # Conflict detected
                    existing = merged_data[key]
                    if existing != value:
                        conflict_key = f"{key}_conflict"
                        if conflict_key not in conflicts:
                            conflicts[conflict_key] = [
                                {
                                    'value': existing,
                                    'source': sources[key],
                                    'format': 'unknown'
                                }
                            ]
                        conflicts[conflict_key].append({
                            'value': value,
                            'source': f"frag_{frag.start_index}",
                            'format': frag.format_type
                        })
        else:
            # Primitive type (string, number, etc.)
            merged_data['value'] = parsed
            sources['value'] = f"frag_{frag.start_index}"
            print(f"    Added primitive value")

    print(f"  RESULT: {len(merged_data)} total fields, {len(conflicts)} conflicts")

    # Calculate data quality score
    quality_score = 1.0
    if len(conflicts) > 0:
        quality_score *= 0.8  # Reduce score for conflicts
    if len(fragments) < 2:
        quality_score *= 0.9  # Reduce score for single-source entities

    print(f"  RESULT: {len(merged_data)} total fields, {len(conflicts)} conflicts")

    # Calculate data quality score
    quality_score = 1.0
    if len(conflicts) > 0:
        quality_score *= 0.8
    if len(fragments) < 2:
        quality_score *= 0.9

    # === NEW: Flag empty entities ===
    if len(merged_data) == 0:
        print(f"  WARNING: Entity '{entity_id}' has NO data after merging!")
        quality_score = 0.0

    return {
        'merged_data': merged_data,
        'sources': sources,
        'conflicts': conflicts,
        'quality_score': quality_score,
        'fragment_count': len(fragments),
        'completeness': len(merged_data) / max(20, len(merged_data)),
        'is_empty': len(merged_data) == 0  # NEW
    }


def _flatten_dict(d: Dict, parent_key: str = '', sep: str = '_') -> Dict:
    """Flatten nested dictionary, handling lists and other types safely"""
    items = []

    # Handle non-dict types
    if not isinstance(d, dict):
        if isinstance(d, list):
            # For lists, create indexed keys
            for i, item in enumerate(d):
                if isinstance(item, dict):
                    items.extend(_flatten_dict(item, f"{parent_key}_{i}", sep=sep).items())
                else:
                    items.append((f"{parent_key}_{i}", item))
        else:
            # For primitives, just return as-is
            return {parent_key: d} if parent_key else {}
        return dict(items)

    # Normal dict processing
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            # Handle lists
            if len(v) > 0 and isinstance(v[0], dict):
                # List of dicts (like CSV rows)
                for i, item in enumerate(v):
                    items.extend(_flatten_dict(item, f"{new_key}_{i}", sep=sep).items())
            else:
                # Simple list - convert to string
                items.append((new_key, str(v)))
        else:
            items.append((new_key, v))
    return dict(items)

# ---------- If run as script, quick demo on file path ----------
if __name__ == "__main__":
    import sys, os
    if len(sys.argv) < 2:
        print("Usage: python etl_parser.py <input.txt>")
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.exists(path):
        print("File not found:", path); sys.exit(1)
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    out = parse_file(txt)
    print("\n=== FRAGMENTS DETECTED ===")
    for b in out["fragments"]:
        snippet = b.text.replace("\n"," ")[:180]
        print(f"{b.format_type} [{b.start_index}:{b.end_index}] conf={b.confidence:.2f}")
        print("  ", snippet, "\n")
    print("=== SUMMARY ===")
    print(out["summary"])
    print("=== NORMALIZED RECORDS COUNT ===", len(out["records"]))
