#!/usr/bin/env python3
"""
query_translator.py - Natural Language to SQL Query Translation using LLM

Features:
- Natural language → SQL translation
- Schema-aware query generation
- Multi-database support (PostgreSQL, MongoDB)
- Query validation
- Result formatting
"""

import json
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import subprocess


@dataclass
class QueryResult:
    """Query execution result"""
    success: bool
    query: str
    results: List[Dict] = None
    error: str = None
    execution_time_ms: float = 0.0
    rows_affected: int = 0


class LLMQueryTranslator:
    """Translate natural language to SQL using local LLM (Phi3:mini)"""

    def __init__(self, model: str = "phi3:mini"):
        self.model = model
        self._check_ollama()

    def _check_ollama(self):
        """Verify Ollama is running"""
        try:
            result = subprocess.run(
                ['ollama', 'list'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if self.model not in result.stdout:
                print(f"⚠ Warning: Model '{self.model}' not found. Run: ollama pull {self.model}")
        except Exception as e:
            print(f"⚠ Warning: Ollama not available: {e}")

    def translate_to_sql(self, natural_query: str, schema: Dict,
                         database_type: str = "postgresql") -> Tuple[str, str]:
        """
        Translate natural language to SQL

        Returns:
            (sql_query, explanation)
        """

        # Build schema context
        schema_context = self._build_schema_context(schema, database_type)

        # Create prompt
        prompt = self._create_translation_prompt(
            natural_query,
            schema_context,
            database_type
        )

        # Call LLM
        response = self._call_ollama(prompt)

        # Parse response
        sql_query, explanation = self._parse_llm_response(response)

        return sql_query, explanation

    def translate_to_mongodb(self, natural_query: str, schema: Dict) -> Tuple[Dict, str]:
        """
        Translate natural language to MongoDB query

        Returns:
            (mongo_query_dict, explanation)
        """

        schema_context = self._build_schema_context(schema, "mongodb")

        prompt = f"""You are a MongoDB query expert. Convert natural language to MongoDB query.

Schema (Collection structure):
{json.dumps(schema_context, indent=2)}

Natural language query: "{natural_query}"

Generate MongoDB query. Return ONLY valid JSON in this format:
{{
  "collection": "collection_name",
  "operation": "find|aggregate|count",
  "query": {{}},
  "projection": {{}},
  "sort": {{}},
  "limit": null,
  "explanation": "What the query does"
}}

MongoDB Query:"""

        response = self._call_ollama(prompt)

        # Parse JSON response
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                mongo_query = json.loads(json_match.group(0))
                explanation = mongo_query.get('explanation', 'MongoDB query generated')
                return mongo_query, explanation
            else:
                return None, "Failed to parse MongoDB query"
        except json.JSONDecodeError as e:
            return None, f"JSON parsing error: {e}"

    def _build_schema_context(self, schema: Dict, db_type: str) -> Dict:
        """Build concise schema context for LLM"""

        entity_id = schema.get('entity_id', 'unknown')
        category = schema.get('category', 'unknown')

        # Extract field info
        fields_info = []
        for field_name, field_data in schema.get('fields', {}).items():
            type_info = field_data.get('type_info', {})

            field_type = type_info.get('sql_type' if db_type == 'postgresql' else 'mongo_type', 'TEXT')
            nullable = type_info.get('nullable', True)
            example = field_data.get('example_value')

            fields_info.append({
                'name': field_name,
                'type': field_type,
                'nullable': nullable,
                'example': str(example)[:50] if example else None
            })

        # Determine table/collection name
        table_name = category.lower() + 's' if category != 'unknown' else entity_id.lower()

        return {
            'table_name': table_name,
            'entity_type': category,
            'fields': fields_info,
            'primary_keys': schema.get('primary_key_candidates', []),
            'indexes': schema.get('suggested_indexes', [])
        }

    def _create_translation_prompt(self, natural_query: str,
                                   schema_context: Dict, db_type: str) -> str:
        """Create LLM prompt for SQL generation"""

        prompt = f"""You are an expert SQL query generator for {db_type.upper()}.

Database Schema:
Table: {schema_context['table_name']}
Columns:
{self._format_columns_for_prompt(schema_context['fields'])}

Primary Keys: {', '.join(schema_context['primary_keys']) if schema_context['primary_keys'] else 'None'}

Natural Language Query: "{natural_query}"

Generate a {db_type.upper()} query. Follow these rules:
1. Use ONLY columns that exist in the schema
2. Use proper SQL syntax for {db_type}
3. Include appropriate WHERE clauses, JOINs if needed
4. Use LIMIT for queries that might return many rows
5. Return ONLY the SQL query and a brief explanation

Format your response EXACTLY like this:
SQL: <your query here>
EXPLANATION: <brief explanation>

Response:"""

        return prompt

    def _format_columns_for_prompt(self, fields: List[Dict]) -> str:
        """Format column info for prompt"""
        lines = []
        for field in fields:
            nullable = "NULL" if field['nullable'] else "NOT NULL"
            example = f" (e.g., {field['example']})" if field['example'] else ""
            lines.append(f"  - {field['name']} {field['type']} {nullable}{example}")
        return '\n'.join(lines)

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama API"""
        try:
            # Use subprocess to call ollama
            result = subprocess.run(
                ['ollama', 'run', self.model],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                return result.stdout
            else:
                return f"Error: {result.stderr}"

        except subprocess.TimeoutExpired:
            return "Error: LLM request timed out"
        except Exception as e:
            return f"Error calling Ollama: {e}"

    def _parse_llm_response(self, response: str) -> Tuple[str, str]:
        """Extract SQL and explanation from LLM response"""

        # Try to extract SQL: ... and EXPLANATION: ...
        sql_match = re.search(r'SQL:\s*(.+?)(?:EXPLANATION:|$)', response, re.DOTALL | re.IGNORECASE)
        exp_match = re.search(r'EXPLANATION:\s*(.+?)$', response, re.DOTALL | re.IGNORECASE)

        if sql_match:
            sql = sql_match.group(1).strip()
            # Clean up SQL
            sql = re.sub(r'^```sql\s*', '', sql)
            sql = re.sub(r'```\s*$', '', sql)
            sql = sql.strip()
        else:
            # Fallback: look for SELECT/INSERT/UPDATE/DELETE
            sql_match = re.search(r'(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)[\s\S]+?;', response, re.IGNORECASE)
            sql = sql_match.group(0).strip() if sql_match else response.strip()

        explanation = exp_match.group(1).strip() if exp_match else "Query generated from natural language"

        return sql, explanation


class QueryValidator:
    """Validate generated queries before execution"""

    @staticmethod
    def validate_sql(query: str, schema: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate SQL query

        Returns:
            (is_valid, error_message)
        """

        # Check for dangerous operations
        dangerous_keywords = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER']
        query_upper = query.upper()

        for keyword in dangerous_keywords:
            if keyword in query_upper and 'TABLE' in query_upper:
                return False, f"Dangerous operation detected: {keyword}"

        # Check if query references valid columns
        fields = set(schema.get('fields', {}).keys())

        # Extract column names from query (simple regex)
        mentioned_cols = re.findall(r'\b([a-z_][a-z0-9_]*)\b', query, re.IGNORECASE)

        # Filter out SQL keywords
        sql_keywords = {'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'ORDER', 'BY', 'LIMIT',
                        'JOIN', 'ON', 'AS', 'IN', 'NOT', 'NULL', 'IS', 'LIKE', 'GROUP'}

        mentioned_cols = [c for c in mentioned_cols if c.upper() not in sql_keywords]

        # Check if all mentioned columns exist
        invalid_cols = [c for c in mentioned_cols if c not in fields and c != '*']

        if invalid_cols:
            return False, f"Unknown columns: {', '.join(invalid_cols[:3])}"

        return True, None

    @staticmethod
    def validate_mongodb(query: Dict) -> Tuple[bool, Optional[str]]:
        """Validate MongoDB query"""

        required_fields = ['collection', 'operation']

        for field in required_fields:
            if field not in query:
                return False, f"Missing required field: {field}"

        valid_operations = ['find', 'aggregate', 'count', 'findOne', 'distinct']
        if query['operation'] not in valid_operations:
            return False, f"Invalid operation: {query['operation']}"

        return True, None


class QueryExecutor:
    """Execute validated queries (mock for now, can connect to real DB)"""

    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string
        self.mock_mode = connection_string is None

    def execute_sql(self, query: str, schema: Dict) -> QueryResult:
        """
        Execute SQL query

        For now: Mock execution (return sample data)
        Later: Connect to real PostgreSQL
        """

        if self.mock_mode:
            return self._mock_execute_sql(query, schema)
        else:
            return self._real_execute_sql(query)

    def _mock_execute_sql(self, query: str, schema: Dict) -> QueryResult:
        """Mock execution - return sample data based on schema"""

        import time
        start = time.time()

        # Generate mock results based on schema
        fields = list(schema.get('fields', {}).keys())[:5]  # First 5 fields

        mock_rows = [
            {field: schema['fields'][field].get('example_value', 'N/A')
             for field in fields}
            for _ in range(3)  # Return 3 sample rows
        ]

        execution_time = (time.time() - start) * 1000

        return QueryResult(
            success=True,
            query=query,
            results=mock_rows,
            execution_time_ms=execution_time,
            rows_affected=len(mock_rows)
        )

    def _real_execute_sql(self, query: str) -> QueryResult:
        """Execute on real PostgreSQL (implement when needed)"""
        # TODO: Use psycopg2 or sqlalchemy
        pass


class NaturalLanguageQuerySystem:
    """Complete NL → SQL system"""

    def __init__(self, schema_registry_path: str = './schema_registry'):
        self.translator = LLMQueryTranslator()
        self.validator = QueryValidator()
        self.executor = QueryExecutor()  # Mock mode
        self.registry_path = schema_registry_path
        self.schemas = self._load_schemas()

    def _load_schemas(self) -> Dict:
        """Load all schemas from registry"""
        registry_file = f"{self.registry_path}/registry.json"

        try:
            with open(registry_file, 'r') as f:
                registry = json.load(f)

            # Extract latest schema for each entity
            schemas = {}
            for entity_type, versions in registry.items():
                if versions:
                    latest = versions[-1]  # Last version is latest
                    schemas[entity_type] = latest['schema_json']

            return schemas

        except FileNotFoundError:
            print(f"⚠ Schema registry not found: {registry_file}")
            return {}

    def query(self, natural_query: str, entity_type: Optional[str] = None,
              database_type: str = "postgresql") -> Dict[str, Any]:
        """
        Main query interface

        Args:
            natural_query: Natural language query
            entity_type: Target entity (auto-detect if None)
            database_type: "postgresql" or "mongodb"

        Returns:
            {
                'success': bool,
                'sql': str,
                'explanation': str,
                'results': List[Dict],
                'error': str
            }
        """

        # Auto-detect entity type if not provided
        if entity_type is None:
            entity_type = self._detect_entity_type(natural_query)

        if entity_type not in self.schemas:
            return {
                'success': False,
                'error': f"Entity type '{entity_type}' not found in schema registry",
                'available_entities': list(self.schemas.keys())
            }

        schema = self.schemas[entity_type]

        # Translate
        if database_type == "postgresql":
            sql, explanation = self.translator.translate_to_sql(
                natural_query, schema, database_type
            )
            query_str = sql

            # Validate
            is_valid, error = self.validator.validate_sql(sql, schema)
        else:
            mongo_query, explanation = self.translator.translate_to_mongodb(
                natural_query, schema
            )
            query_str = json.dumps(mongo_query, indent=2)

            is_valid, error = self.validator.validate_mongodb(mongo_query)

        if not is_valid:
            return {
                'success': False,
                'query': query_str,
                'explanation': explanation,
                'error': f"Validation failed: {error}"
            }

        # Execute (mock for now)
        if database_type == "postgresql":
            result = self.executor.execute_sql(sql, schema)
        else:
            result = QueryResult(
                success=True,
                query=query_str,
                results=[{"note": "MongoDB execution not implemented yet"}]
            )

        return {
            'success': result.success,
            'query': result.query,
            'explanation': explanation,
            'results': result.results,
            'rows_affected': result.rows_affected,
            'execution_time_ms': result.execution_time_ms,
            'error': result.error
        }

    def _detect_entity_type(self, query: str) -> str:
        """Auto-detect which entity type the query refers to"""

        query_lower = query.lower()

        # Simple keyword matching
        keywords = {
            'documents': ['book', 'document', 'title', 'author', 'isbn'],
            'products': ['product', 'price', 'stock', 'widget'],
            'services': ['service', 'subscription', 'plan'],
            'foods': ['food', 'ingredient', 'recipe']
        }

        scores = {}
        for entity_type, kws in keywords.items():
            score = sum(1 for kw in kws if kw in query_lower)
            if score > 0:
                scores[entity_type] = score

        if scores:
            return max(scores, key=scores.get)

        # Default to first available
        return list(self.schemas.keys())[0] if self.schemas else 'unknown'


def main():
    """Interactive query interface"""

    print("=" * 60)
    print("NATURAL LANGUAGE QUERY SYSTEM")
    print("=" * 60)

    system = NaturalLanguageQuerySystem()

    if not system.schemas:
        print("\n⚠ No schemas found! Run main.py first to generate schemas.")
        return

    print(f"\nAvailable entities: {', '.join(system.schemas.keys())}")
    print("\nExample queries:")
    print("  - Show me all products with price less than 50")
    print("  - Find documents with rating above 4.0")
    print("  - List products ordered by stock descending")
    print("  - Count how many items have views greater than 1000")
    print("\nType 'quit' to exit\n")

    while True:
        try:
            nl_query = input("📝 Query: ").strip()

            if nl_query.lower() in ['quit', 'exit', 'q']:
                break

            if not nl_query:
                continue

            print("\n⏳ Translating query...")

            result = system.query(nl_query, database_type="postgresql")

            print("\n" + "=" * 60)

            if result['success']:
                print("✓ Query generated successfully\n")
                print(f"SQL Query:")
                print(f"  {result['query']}\n")
                print(f"Explanation:")
                print(f"  {result['explanation']}\n")
                print(f"Results: ({result['rows_affected']} rows)")

                if result['results']:
                    for i, row in enumerate(result['results'][:5], 1):
                        print(f"  Row {i}: {row}")
            else:
                print("✗ Query failed\n")
                print(f"Error: {result['error']}")

            print("=" * 60 + "\n")

        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")


if __name__ == "__main__":
    main()