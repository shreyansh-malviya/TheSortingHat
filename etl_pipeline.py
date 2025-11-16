# Dynamic ETL Pipeline - File to Schema Generator
# Run this on your local machine to process unstructured files
# 
# Requirements:
# pip install fastapi uvicorn python-multipart psycopg2-binary pymongo
#
# Built using Unstructured-IO
#
# Usage:
# python etl_pipeline.py
# Then visit http://localhost:8005/docs for interactive API

import json
import re
import os
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, asdict, field
from collections import defaultdict
from datetime import datetime
import hashlib
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
import uvicorn

# ============================================================================
# PART 1: Data Models
# ============================================================================

@dataclass
class Element:
    """Represents a parsed element from a document"""
    type: str  # 'Title', 'NarrativeText', 'Table', 'Code', 'ListItem', etc.
    text: str
    page: int = 0
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FieldSchema:
    """Schema for a single field"""
    name: str
    type: str
    nullable: bool
    null_count: int
    example_value: Optional[str]
    confidence: float
    observed_types: Dict[str, int]
    is_union: bool
    source_offsets: List[str]


@dataclass
class DocumentSchema:
    """Complete schema for a document"""
    schema_id: str
    generated_at: str
    source_id: str
    compatible_dbs: List[str]
    fields: List[Dict[str, Any]]
    primary_key_candidates: List[str]
    migration_notes: str


# ============================================================================
# PART 2: Parser (Simulates Unstructured)
# ============================================================================

def parse_text_file(text: str) -> List[Element]:
    """Parse plain text file into elements"""
    elements = []
    lines = text.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            i += 1
            continue
        
        # Section headers
        if line.startswith('---'):
            section_name = line.replace('-', '').strip()
            if section_name:
                elements.append(Element(
                    type='Title',
                    text=section_name,
                    metadata={'section': section_name}
                ))
            i += 1
            continue
        
        # Key-value pairs
        if ': ' in line and not line.startswith('{') and not line.startswith('['):
            kv_lines = [line]
            i += 1
            while i < len(lines) and ': ' in lines[i] and not lines[i].strip().startswith('{'):
                kv_lines.append(lines[i].strip())
                i += 1
            elements.append(Element(
                type='KeyValuePairs',
                text='\n'.join(kv_lines),
                metadata={'kv_count': len(kv_lines)}
            ))
            continue
        
        # JSON blocks
        if line.startswith('{') or line.startswith('['):
            json_lines = [line]
            i += 1
            brace_count = line.count('{') - line.count('}')
            bracket_count = line.count('[') - line.count(']')
            
            while i < len(lines) and (brace_count > 0 or bracket_count > 0):
                json_lines.append(lines[i])
                brace_count += lines[i].count('{') - lines[i].count('}')
                bracket_count += lines[i].count('[') - lines[i].count(']')
                i += 1
            
            json_text = '\n'.join(json_lines)
            is_well_formed = False
            try:
                json.loads(json_text)
                is_well_formed = True
            except:
                pass
            
            elements.append(Element(
                type='Code',
                text=json_text,
                metadata={'format': 'json', 'well_formed': is_well_formed}
            ))
            continue
        
        # HTML snippets
        if '<' in line and '>' in line:
            html_lines = [line]
            i += 1
            while i < len(lines) and '<' in lines[i]:
                html_lines.append(lines[i])
                i += 1
            elements.append(Element(
                type='HTML',
                text='\n'.join(html_lines),
                metadata={'format': 'html'}
            ))
            continue
        
        # Default: narrative text
        text_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith('---'):
            text_lines.append(lines[i].strip())
            i += 1
        
        elements.append(Element(
            type='NarrativeText',
            text=' '.join(text_lines)
        ))
    
    return elements


# ============================================================================
# PART 3: Fragment Detection & Extraction
# ============================================================================

def extract_fragments(elements: List[Element]) -> Dict[str, Any]:
    """Detect and count fragment types"""
    fragments = {
        'json_fragments': [],
        'html_tables': [],
        'csv_sections': [],
        'kv_pairs': [],
        'narratives': []
    }
    
    for idx, elem in enumerate(elements):
        if elem.type == 'Code' and elem.metadata.get('format') == 'json':
            fragments['json_fragments'].append({
                'index': idx,
                'well_formed': elem.metadata.get('well_formed'),
                'text_preview': elem.text[:100]
            })
        elif elem.type == 'HTML' and '<table>' in elem.text.lower():
            fragments['html_tables'].append({
                'index': idx,
                'text_preview': elem.text[:100]
            })
        elif elem.type == 'KeyValuePairs':
            fragments['kv_pairs'].append({
                'index': idx,
                'count': elem.metadata.get('kv_count'),
                'text_preview': elem.text[:100]
            })
        elif elem.type == 'NarrativeText':
            fragments['narratives'].append({
                'index': idx,
                'text_preview': elem.text[:100]
            })
    
    return {
        'summary': {
            'json_fragments': len(fragments['json_fragments']),
            'html_tables': len(fragments['html_tables']),
            'csv_sections': len(fragments['csv_sections']),
            'kv_pairs': len(fragments['kv_pairs']),
            'narratives': len(fragments['narratives'])
        },
        'details': fragments
    }


def parse_json_safe(text: str) -> Dict[str, Any]:
    """Try to parse JSON, handling malformed cases"""
    try:
        return json.loads(text)
    except:
        # Try to fix trailing commas
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)
        try:
            return json.loads(text)
        except:
            return {}


def parse_kv_pairs(text: str) -> Dict[str, str]:
    """Parse key: value lines"""
    result = {}
    for line in text.split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            result[key.strip()] = val.strip()
    return result


def extract_records(elements: List[Element]) -> List[Dict[str, Any]]:
    """Convert elements into canonical records"""
    records = []
    
    for idx, elem in enumerate(elements):
        if elem.type == 'Code' and elem.metadata.get('format') == 'json':
            data = parse_json_safe(elem.text)
            if data:
                data['_source'] = f'json_fragment_{idx}'
                data['_confidence'] = 0.95 if elem.metadata.get('well_formed') else 0.7
                records.append(data)
        
        elif elem.type == 'KeyValuePairs':
            data = parse_kv_pairs(elem.text)
            if data:
                data['_source'] = f'kv_fragment_{idx}'
                data['_confidence'] = 0.85
                records.append(data)
    
    return records


# ============================================================================
# PART 4: Schema Inference
# ============================================================================

def infer_type(value: Any) -> Tuple[str, float]:
    """Infer type and confidence of a value"""
    if value is None or value == '' or value == 'N/A':
        return ('null', 1.0)
    
    if isinstance(value, bool):
        return ('boolean', 1.0)
    
    if isinstance(value, (int, float)):
        return ('number', 1.0)
    
    if isinstance(value, str):
        val_lower = value.lower()
        
        if re.match(r'\d{4}-\d{2}-\d{2}', value):
            return ('date', 0.95)
        if re.match(r'\d{1,2}/\d{1,2}/\d{4}', value):
            return ('date', 0.7)
        if re.match(r'^-?\d+(\.\d+)?$', value):
            return ('number', 0.8)
        if val_lower in ('true', 'false', '0', '1'):
            return ('boolean', 0.7)
        if value.startswith('http'):
            return ('url', 0.95)
        
        return ('string', 1.0)
    
    if isinstance(value, dict):
        return ('object', 0.9)
    if isinstance(value, list):
        return ('array', 0.9)
    
    return ('unknown', 0.5)


def build_schema_from_records(records: List[Dict[str, Any]], source_id: str) -> DocumentSchema:
    """Build schema from records"""
    field_stats = defaultdict(lambda: {
        'types': defaultdict(int),
        'examples': [],
        'null_count': 0,
        'total_seen': 0,
        'source_offsets': []
    })
    
    for rec_idx, record in enumerate(records):
        for key, value in record.items():
            if key.startswith('_'):
                continue
            
            field_stats[key]['total_seen'] += 1
            field_stats[key]['source_offsets'].append(f"record_{rec_idx}")
            
            inferred_type, confidence = infer_type(value)
            field_stats[key]['types'][inferred_type] += 1
            
            if inferred_type != 'null':
                if len(field_stats[key]['examples']) < 3:
                    field_stats[key]['examples'].append(str(value))
            else:
                field_stats[key]['null_count'] += 1
    
    # Build fields
    fields = []
    for field_name, stats in sorted(field_stats.items()):
        if not stats['types']:
            canonical_type = 'string'
            confidence = 0.5
        else:
            most_common_type = max(stats['types'].items(), key=lambda x: x[1])[0]
            type_count = stats['types'][most_common_type]
            confidence = type_count / stats['total_seen']
            canonical_type = most_common_type if confidence >= 0.6 else 'string'
        
        is_union = len(stats['types']) > 1
        
        fields.append({
            'name': field_name,
            'type': canonical_type,
            'nullable': stats['null_count'] > 0,
            'null_count': stats['null_count'],
            'example_value': stats['examples'][0] if stats['examples'] else None,
            'confidence': round(confidence, 2),
            'observed_types': dict(stats['types']),
            'is_union': is_union,
            'source_offsets': list(set(stats['source_offsets']))
        })
    
    schema = DocumentSchema(
        schema_id=f"schema_v{datetime.now().strftime('%s')[-3:]}",
        generated_at=datetime.now().isoformat(),
        source_id=source_id,
        compatible_dbs=['postgresql', 'mongodb'],
        fields=fields,
        primary_key_candidates=[],
        migration_notes='Initial schema from inferred types'
    )
    
    # Heuristic: find ID-like fields
    for field in fields:
        if field['name'].lower() in ('id', 'slug', 'product_id', 'prod_id'):
            schema.primary_key_candidates.append(field['name'])
    
    return schema


# ============================================================================
# PART 5: DB Schema Generation
# ============================================================================

def generate_postgres_ddl(schema: DocumentSchema) -> str:
    """Generate PostgreSQL DDL"""
    table_name = schema.source_id.replace('-', '_')
    ddl_lines = [f"CREATE TABLE IF NOT EXISTS {table_name} ("]
    
    type_map = {
        'string': 'TEXT',
        'number': 'NUMERIC',
        'integer': 'INTEGER',
        'boolean': 'BOOLEAN',
        'date': 'DATE',
        'array': 'JSONB',
        'object': 'JSONB',
        'null': 'TEXT',
        'url': 'TEXT'
    }
    
    for field in schema.fields:
        col_name = field['name'].replace('.', '_').lower()
        col_type = type_map.get(field['type'], 'TEXT')
        nullable = 'NULL' if field['nullable'] else 'NOT NULL'
        ddl_lines.append(f"    {col_name} {col_type} {nullable},")
    
    ddl_lines[-1] = ddl_lines[-1].rstrip(',')
    
    if schema.primary_key_candidates:
        pk_cols = ', '.join([f.replace('.', '_').lower() for f in schema.primary_key_candidates])
        ddl_lines.append(f",\n    PRIMARY KEY ({pk_cols})")
    
    ddl_lines.append(");")
    return '\n'.join(ddl_lines)


def generate_mongo_schema(schema: DocumentSchema) -> Dict[str, Any]:
    """Generate MongoDB JSON Schema"""
    type_map = {
        'string': 'string',
        'number': 'number',
        'integer': 'integer',
        'boolean': 'boolean',
        'date': 'string',
        'array': 'array',
        'object': 'object',
        'null': 'null',
        'url': 'string'
    }
    
    properties = {}
    required = []
    
    for field in schema.fields:
        field_name = field['name']
        mongo_type = type_map.get(field['type'], 'string')
        properties[field_name] = {'type': mongo_type, 'description': f"Confidence: {field['confidence']}"}
        
        if not field['nullable']:
            required.append(field_name)
    
    return {
        'bsonType': 'object',
        'properties': properties,
        'required': required
    }


# ============================================================================
# PART 6: In-Memory Storage
# ============================================================================

class InMemoryStore:
    """Simple in-memory storage for files and schemas"""
    def __init__(self):
        self.files = {}  # file_id -> {content, metadata}
        self.schemas = {}  # source_id -> [schema_v1, schema_v2, ...]
        self.records = {}  # source_id -> [records]
        self.schema_history = {}  # source_id -> [history entries]
    
    def store_file(self, source_id: str, file_id: str, content: str):
        self.files[file_id] = {
            'source_id': source_id,
            'content': content,
            'uploaded_at': datetime.now().isoformat()
        }
    
    def store_schema(self, source_id: str, schema: DocumentSchema, records: List[Dict]):
        if source_id not in self.schemas:
            self.schemas[source_id] = []
            self.records[source_id] = []
            self.schema_history[source_id] = []
        
        self.schemas[source_id].append(schema)
        self.records[source_id] = records
        
        # Track history
        if len(self.schemas[source_id]) > 1:
            prev_schema = self.schemas[source_id][-2]
            self.schema_history[source_id].append({
                'timestamp': datetime.now().isoformat(),
                'schema_id': schema.schema_id,
                'previous_schema_id': prev_schema.schema_id,
                'changes': f"Evolved from {prev_schema.schema_id}"
            })
    
    def get_latest_schema(self, source_id: str) -> Optional[DocumentSchema]:
        if source_id in self.schemas and self.schemas[source_id]:
            return self.schemas[source_id][-1]
        return None
    
    def get_records(self, source_id: str) -> List[Dict]:
        return self.records.get(source_id, [])


# ============================================================================
# PART 7: FastAPI Application
# ============================================================================

app = FastAPI(
    title="Dynamic ETL Pipeline",
    description="Convert unstructured files to JSON schemas and database structures",
    version="1.0.0"
)

store = InMemoryStore()


@app.post("/upload")
async def upload_file(
    source_id: str,
    file: UploadFile = File(...)
):
    """
    Upload a .txt, .pdf, or .md file and generate schema
    
    Returns:
    - source_id: identifier for the source
    - file_id: unique file identifier
    - schema_id: generated schema identifier
    - parsed_fragments_summary: counts of detected fragments
    """
    try:
        # Read file
        content = await file.read()
        text = content.decode('utf-8')
        
        # Generate file ID
        file_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        file_id = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_hash}"
        
        # Store file
        store.store_file(source_id, file_id, text)
        
        # Parse
        elements = parse_text_file(text)
        
        # Fragment detection
        fragments_info = extract_fragments(elements)
        
        # Extract records
        records = extract_records(elements)
        
        # Build schema
        schema = build_schema_from_records(records, source_id)
        
        # Store schema and records
        store.store_schema(source_id, schema, records)
        
        return {
            'status': 'ok',
            'source_id': source_id,
            'file_id': file_id,
            'schema_id': schema.schema_id,
            'parsed_fragments_summary': fragments_info['summary']
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/schema")
async def get_schema(source_id: str):
    """
    Get the current schema for a source_id
    """
    schema = store.get_latest_schema(source_id)
    if not schema:
        raise HTTPException(status_code=404, detail=f"No schema found for {source_id}")
    
    return {
        'schema_id': schema.schema_id,
        'generated_at': schema.generated_at,
        'source_id': schema.source_id,
        'compatible_dbs': schema.compatible_dbs,
        'fields': schema.fields,
        'primary_key_candidates': schema.primary_key_candidates,
        'migration_notes': schema.migration_notes
    }


@app.get("/schema/history")
async def get_schema_history(source_id: str):
    """
    Get schema version history for a source_id
    """
    history = store.schema_history.get(source_id, [])
    if not history:
        raise HTTPException(status_code=404, detail=f"No history found for {source_id}")
    
    return {
        'source_id': source_id,
        'history': history
    }


@app.get("/records")
async def get_records(
    source_id: str,
    query_id: Optional[str] = Query(None)
):
    """
    Get extracted records for a source_id
    """
    records = store.get_records(source_id)
    if not records:
        raise HTTPException(status_code=404, detail=f"No records found for {source_id}")
    
    return {
        'source_id': source_id,
        'query_id': query_id or 'raw_extract',
        'record_count': len(records),
        'records': records
    }


@app.get("/schema/postgres-ddl")
async def get_postgres_ddl(source_id: str):
    """
    Get PostgreSQL DDL for a source_id
    """
    schema = store.get_latest_schema(source_id)
    if not schema:
        raise HTTPException(status_code=404, detail=f"No schema found for {source_id}")
    
    ddl = generate_postgres_ddl(schema)
    
    return {
        'source_id': source_id,
        'schema_id': schema.schema_id,
        'ddl': ddl
    }


@app.get("/schema/mongo-schema")
async def get_mongo_schema(source_id: str):
    """
    Get MongoDB JSON Schema for a source_id
    """
    schema = store.get_latest_schema(source_id)
    if not schema:
        raise HTTPException(status_code=404, detail=f"No schema found for {source_id}")
    
    mongo_schema = generate_mongo_schema(schema)
    
    return {
        'source_id': source_id,
        'schema_id': schema.schema_id,
        'mongo_schema': mongo_schema
    }


@app.get("/")
async def root():
    """API root with basic info"""
    return {
        'name': 'Dynamic ETL Pipeline',
        'version': '1.0.0',
        'docs': 'http://localhost:8000/docs'
    }


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 80)
    print("Starting Dynamic ETL Pipeline")
    print("=" * 80)
    print()
    print("API Documentation available at: http://localhost:8005/docs")
    print("Alternative docs at: http://localhost:8005/redoc")
    print()
    
    uvicorn.run(app, host='0.0.0.0', port=8005)
