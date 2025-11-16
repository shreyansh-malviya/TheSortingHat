# The Sorting Hat - Intelligent ETL Pipeline with Schema Evolution

A comprehensive data processing system that automatically extracts, transforms, and loads data from unstructured files, generates schemas, tracks schema evolution, and enables natural language querying.

## 📋 Table of Contents

- [Overview](#overview)
- [Directory Structure](#directory-structure)
- [System Architecture](#system-architecture)
- [Code Flow](#code-flow)
- [Module Details](#module-details)
- [Usage Examples](#usage-examples)
- [API Endpoints](#api-endpoints)

---

## 🎯 Overview

**The Sorting Hat** is an intelligent ETL (Extract, Transform, Load) pipeline that:

1. **Parses** unstructured files (HTML, JSON, CSV, etc.) and detects data formats
2. **Extracts** entities using Named Entity Recognition (NER)
3. **Generates** database schemas automatically
4. **Tracks** schema evolution over time
5. **Translates** natural language queries to SQL

### Key Features

- 🔍 **Multi-format Detection**: JSON, CSV, HTML tables, YAML, Key-Value pairs, SQL, and more
- 🤖 **NER Integration**: SpaCy and GLiNER for entity extraction
- 📊 **Automatic Schema Generation**: PostgreSQL and MongoDB schemas
- 🔄 **Schema Evolution Tracking**: Version control for schemas with migration scripts
- 💬 **Natural Language Queries**: Convert plain English to SQL queries

---

## 📁 Directory Structure

```
TheSortingHat/
│
├── 📄 Core Python Files
│   ├── backend.py              # FastAPI REST API server
│   ├── etl_parser.py           # File parsing and format detection
│   ├── schema_generator.py     # Schema generation from parsed data
│   ├── schema_evolution.py     # Schema versioning and evolution tracking
│   ├── query_translator.py     # Natural language to SQL translation
│   └── main.py                 # Standalone script for testing
│
├── 📂 Data Directories (auto-created)
│   ├── uploads/                # Uploaded files storage
│   ├── schemas/                # Generated schema files (SQL/JSON)
│   ├── records/                # Query results and ETL summaries
│   └── schema_registry/        # Schema version registry (JSON)
│
└── 📄 Input Files (examples)
    ├── input.txt
    ├── input2.html
    └── input3.txt
```

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User/Client Request                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    backend.py (FastAPI)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ POST /upload │  │ GET /schema  │  │ POST /query  │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
└─────────┼──────────────────┼──────────────────┼─────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  etl_parser.py  │  │schema_evolution │  │query_translator │
│                 │  │      .py        │  │      .py        │
│  • Parse file   │  │                 │  │                 │
│  • Detect       │  │  • Track        │  │  • Translate    │
│    formats      │  │    versions     │  │    NL → SQL     │
│  • Extract      │  │  • Generate     │  │  • Execute      │
│    entities     │  │    migrations   │  │    queries      │
└────────┬────────┘  └─────────────────┘  └─────────────────┘
         │
         ▼
┌─────────────────┐
│schema_generator │
│      .py        │
│                 │
│  • Infer types  │
│  • Generate     │
│    schemas      │
│  • Export DDL   │
└─────────────────┘
```

---

## 🔄 Code Flow

### Complete ETL Pipeline Flow

```
1. FILE UPLOAD
   └─> backend.py: POST /upload
       │
       ├─> Save file to uploads/
       │
       └─> Parse file content
           │
           ▼
2. ETL PARSING (etl_parser.py)
   │
   ├─> ETLFragmentDetector.run_all()
   │   ├─> Detect JSON, CSV, HTML, YAML, etc.
   │   ├─> Extract fragments with confidence scores
   │   └─> Mark parent-child relationships
   │
   ├─> NEREnricher.enrich_all_fragments()
   │   ├─> SpaCy: Standard entity recognition
   │   ├─> GLiNER: Domain-specific entities (product_id, price, etc.)
   │   └─> Pattern matching: Emails, URLs, product IDs
   │
   ├─> Normalizer.normalize()
   │   └─> Convert fragments to structured data (dicts/lists)
   │
   ├─> group_fragments_by_entity()
   │   └─> Group fragments by product_id or entity
   │
   └─> merge_fragments_for_entity()
       └─> Merge data from multiple fragments
           │
           ▼
3. SCHEMA GENERATION (schema_generator.py)
   │
   ├─> SchemaBuilder.build_all_schemas()
   │   ├─> TypeInferrer.infer_type()
   │   │   └─> Infer data types (string, integer, date, etc.)
   │   │
   │   ├─> Detect primary keys and indexes
   │   │
   │   └─> Categorize entities (products, documents, etc.)
   │
   └─> SchemaExporter.export_all()
       ├─> Generate PostgreSQL DDL
       └─> Generate MongoDB JSON Schema
           │
           ▼
4. SCHEMA EVOLUTION (schema_evolution.py)
   │
   ├─> SchemaEvolutionManager.process_new_schema()
   │   │
   │   ├─> SchemaRegistry.register_schema()
   │   │   └─> Save to schema_registry/registry.json
   │   │
   │   ├─> SchemaDiffer.diff_schemas()
   │   │   ├─> Compare with previous version
   │   │   ├─> Detect: added/removed/renamed fields
   │   │   └─> Detect: type changes, nullability changes
   │   │
   │   └─> MigrationGenerator.generate_migration()
   │       ├─> Generate forward migration SQL
   │       ├─> Generate rollback SQL
   │       └─> Generate compatibility views
   │
   └─> Return evolution results
       │
       ▼
5. RESPONSE
   └─> Return JSON with:
       ├─> Processing summary
       ├─> Fragments detected
       ├─> Entities found
       ├─> Schemas generated
       └─> Schema evolution info
```

### Query Flow

```
1. NATURAL LANGUAGE QUERY
   └─> backend.py: POST /query
       │
       └─> NaturalLanguageQuerySystem.query()
           │
           ├─> Load schemas from registry
           │
           ├─> LLMQueryTranslator.translate_to_sql()
           │   └─> Use Ollama (phi3:mini) to convert NL → SQL
           │
           ├─> QueryValidator.validate_sql()
           │   └─> Check for dangerous operations
           │   └─> Validate column names
           │
           └─> QueryExecutor.execute_sql()
               └─> Execute query (mock or real DB)
                   │
                   ▼
2. RESPONSE
   └─> Return:
       ├─> Translated SQL query
       ├─> Query results
       ├─> Execution time
       └─> Query ID for later retrieval
```

---

## 📚 Module Details

### 1. `etl_parser.py` - File Parser & Format Detector

**Purpose**: Parse unstructured files and detect data formats

**Key Classes**:
- `ETLFragmentDetector`: Detects different data formats in text
- `NEREnricher`: Adds Named Entity Recognition to fragments
- `Normalizer`: Converts fragments to structured data
- `DetectedBlock`: Data class representing a detected fragment

**Format Detection Priority**:
1. JSON-LD (highest priority)
2. JSON
3. YAML Frontmatter
4. HTML Tables
5. CSV
6. Key-Value pairs
7. JavaScript Objects
8. SQL
9. Raw Text (lowest priority)

**Output**:
```python
{
    'fragments': [DetectedBlock, ...],
    'summary': {'JSON': 5, 'CSV': 2, ...},
    'records': [...],
    'entity_index': {...},
    'grouped_entities': {...},
    'merged_entities': {...}
}
```

**Key Functions**:
- `parse_file(text, enable_ner=True)`: Main entry point

---

### 2. `schema_generator.py` - Schema Generator

**Purpose**: Generate database schemas from parsed entity data

**Key Classes**:
- `TypeInferrer`: Infers data types from values
- `SchemaBuilder`: Builds schemas from merged entities
- `SchemaExporter`: Exports schemas to PostgreSQL/MongoDB

**Type Inference**:
- Detects: integers, decimals, strings, dates, booleans, arrays, objects
- Special handling: emails, URLs, prices, product IDs
- Confidence scoring for type inference

**Output**:
- PostgreSQL DDL files: `postgresql_<category>.sql`
- MongoDB JSON Schema files: `mongodb_<category>.json`

**Key Functions**:
- `generate_schemas_from_etl_result(etl_result, output_dir)`: Main entry point

---

### 3. `schema_evolution.py` - Schema Versioning

**Purpose**: Track schema changes over time and generate migrations

**Key Classes**:
- `SchemaRegistry`: Central registry for all schema versions
- `SchemaDiffer`: Compares schemas and detects changes
- `MigrationGenerator`: Generates SQL migration scripts
- `SchemaEvolutionManager`: Main interface for schema evolution

**Change Detection**:
- Field added/removed
- Field renamed (heuristic-based)
- Type changes
- Nullability changes
- Breaking vs non-breaking changes

**Output**:
- `schema_registry/registry.json`: Version history
- Migration SQL files (forward, rollback, views)

**Key Functions**:
- `SchemaEvolutionManager.process_new_schema()`: Process new schema version
- `SchemaEvolutionManager.get_schema_history()`: Get version history

---

### 4. `query_translator.py` - Natural Language Query System

**Purpose**: Translate natural language queries to SQL

**Key Classes**:
- `LLMQueryTranslator`: Uses Ollama LLM to translate queries
- `QueryValidator`: Validates generated SQL queries
- `QueryExecutor`: Executes queries (mock or real DB)
- `NaturalLanguageQuerySystem`: Complete NL query system

**Translation Process**:
1. Load schema from registry
2. Build schema context for LLM
3. Generate SQL using LLM (Ollama phi3:mini)
4. Validate SQL query
5. Execute query

**Key Functions**:
- `NaturalLanguageQuerySystem.query()`: Main entry point

---

### 5. `backend.py` - FastAPI REST API

**Purpose**: REST API server that orchestrates all modules

**Endpoints**:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload and process file through ETL pipeline |
| `GET` | `/schema` | Get schema(s) by source_id or entity_type |
| `GET` | `/schema/history` | Get schema evolution history |
| `POST` | `/query` | Execute natural language query |
| `GET` | `/records` | Get query results or source summaries |
| `GET` | `/entities` | List all available entity types |
| `GET` | `/health` | Health check endpoint |
| `GET` | `/` | API information |

**Key Features**:
- File upload with size validation
- CORS enabled
- Error handling
- JSON responses

---

### 6. `main.py` - Standalone Test Script

**Purpose**: Example script showing how to use the modules directly

**Usage**:
```bash
python main.py
```

**What it does**:
1. Reads `input2.html`
2. Parses with NER enabled
3. Generates schemas
4. Tracks schema evolution
5. Prints detailed analysis

---

## 💻 Usage Examples

### Example 1: Using the API

```bash
# Start the server
python backend.py

# Upload a file
curl -X POST "http://localhost:5000/upload" \
  -F "file=@input2.html" \
  -F "source_id=test-001"

# Get schema
curl "http://localhost:5000/schema?entity_type=products"

# Query with natural language
curl -X POST "http://localhost:5000/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me all products with price less than 50"}'
```

### Example 2: Using Python Directly

```python
from etl_parser import parse_file
from schema_generator import generate_schemas_from_etl_result
from schema_evolution import SchemaEvolutionManager

# Parse file
with open("input2.html", "r") as f:
    text = f.read()

result = parse_file(text, enable_ner=True)

# Generate schemas
schemas = generate_schemas_from_etl_result(result, output_dir='./schemas')

# Track evolution
schema_manager = SchemaEvolutionManager('./schema_registry')
for entity_id, schema in schemas.items():
    entity_type = schema.get('category', entity_id)
    evolution_result = schema_manager.process_new_schema(entity_type, schema)
    print(f"Schema version: {evolution_result['version'].version}")
```

### Example 3: Natural Language Queries

```python
from query_translator import NaturalLanguageQuerySystem

query_system = NaturalLanguageQuerySystem('./schema_registry')

# Query
result = query_system.query(
    "Show me all products with price less than 50",
    entity_type="products",
    database_type="postgresql"
)

print(result['query'])  # Generated SQL
print(result['results'])  # Query results
```

---

## 🔌 API Endpoints

### POST /upload

Upload and process a file through the ETL pipeline.

**Request**:
- `file`: File to upload (multipart/form-data)
- `source_id`: Optional source identifier
- `version`: Optional version string
- `enable_ner`: Enable NER (default: true)

**Response**:
```json
{
  "success": true,
  "data": {
    "source_id": "...",
    "filename": "...",
    "file_size": 12345
  },
  "processing": {
    "fragments_detected": 10,
    "entities_found": 5,
    "schemas_generated": 3
  }
}
```

### GET /schema

Get schema(s) by source_id or entity_type.

**Query Parameters**:
- `source_id`: Optional source ID
- `entity_type`: Optional entity type

**Response**:
```json
{
  "success": true,
  "entity_type": "products",
  "version": 1,
  "schema": {...}
}
```

### POST /query

Execute a natural language query.

**Request Body**:
```json
{
  "query": "Show me all products with price less than 50",
  "entity_type": "products",
  "database_type": "postgresql"
}
```

**Response**:
```json
{
  "success": true,
  "query_id": "...",
  "translated_query": "SELECT * FROM products WHERE price < 50",
  "results": [...]
}
```

---

## 🚀 Getting Started

### Prerequisites

```bash
# Install Python dependencies
pip install fastapi uvicorn beautifulsoup4 python-multipart

# Optional: For NER features
pip install spacy gliner
python -m spacy download en_core_web_sm

# Optional: For query translation
# Install Ollama and pull model
ollama pull phi3:mini
```

### Running the Server

```bash
# Start the API server
python backend.py

# Or using uvicorn directly
uvicorn backend:app --host 0.0.0.0 --port 5000

# Or using FastAPI CLI
fastapi run backend.py --port 5000
```

### Accessing the API

- **API Documentation**: http://localhost:5000/docs
- **Alternative Docs**: http://localhost:5000/redoc
- **Health Check**: http://localhost:5000/health

---

## 📊 Data Flow Summary

```
Input File
    ↓
[etl_parser.py] → Fragments + Entities
    ↓
[schema_generator.py] → Database Schemas
    ↓
[schema_evolution.py] → Versioned Schemas
    ↓
[query_translator.py] → Natural Language Queries
    ↓
Query Results
```

---

## 🔍 Key Concepts

### Fragments
Detected data blocks in the input file (JSON objects, CSV rows, HTML tables, etc.)

### Entities
Named entities extracted from fragments (product IDs, prices, emails, etc.)

### Merged Entities
Multiple fragments grouped together by entity ID (e.g., all fragments mentioning "prod-1001")

### Schema Evolution
Tracking changes to schemas over time, generating migrations, and maintaining backward compatibility

### Natural Language Queries
Converting plain English questions into SQL queries using LLM

---

## 📝 Notes

- NER models (SpaCy, GLiNER) are optional - the system works without them
- Query translation requires Ollama with phi3:mini model
- Schema registry is stored in JSON format in `schema_registry/`
- All generated files are saved in respective directories

---

## 🤝 Contributing

This is a comprehensive ETL pipeline system. Each module can be used independently or together through the FastAPI backend.

---

## 📄 License

[Your License Here]

