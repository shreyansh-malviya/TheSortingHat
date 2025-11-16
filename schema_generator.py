# #!/usr/bin/env python3
# """
# schema_generator.py
# Automatic schema generation from merged entity data with multi-database support.
#
# Features:
# - Type inference with confidence scoring
# - PostgreSQL DDL generation
# - MongoDB JSON Schema generation
# - Conflict resolution strategies
# - Index suggestions
# """
#
# from typing import Dict, Any, List, Set, Optional, Tuple
# from collections import defaultdict, Counter
# import re
# import json
# from datetime import datetime
# from decimal import Decimal
#
#
# class TypeInferrer:
#     """Infer field types from values with confidence scoring"""
#
#     # Common date patterns
#     DATE_PATTERNS = [
#         (r'^\d{4}-\d{2}-\d{2}$', 'DATE'),  # 2025-11-16
#         (r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', 'TIMESTAMP'),  # ISO 8601
#         (r'^\d{2}/\d{2}/\d{4}$', 'DATE'),  # 11/16/2025
#         (r'^\d{2}-\d{2}-\d{4}$', 'DATE'),  # 16-11-2025
#     ]
#
#     # Price/currency patterns
#     PRICE_PATTERNS = [
#         r'^\$?\d+\.\d{2}$',  # $99.99 or 99.99
#         r'^\d+,\d{2}\s*(USD|EUR|GBP)$',  # 99,99 EUR
#         r'^\d+\.\d{2}\s*(USD|EUR|GBP)$',  # 99.99 USD
#     ]
#
#     @classmethod
#     def infer_type(cls, value: Any, field_name: str = "") -> Dict[str, Any]:
#         """
#         Infer type from a single value
#         Returns type info with confidence score
#         """
#         # Handle None/null
#         if value is None or value == "" or value == "N/A":
#             return {
#                 'base_type': 'null',
#                 'sql_type': 'VARCHAR(255)',
#                 'mongo_type': 'null',
#                 'nullable': True,
#                 'confidence': 1.0
#             }
#
#         # Boolean
#         if isinstance(value, bool):
#             return {
#                 'base_type': 'boolean',
#                 'sql_type': 'BOOLEAN',
#                 'mongo_type': 'Boolean',
#                 'nullable': False,
#                 'confidence': 1.0
#             }
#
#         # Integer
#         if isinstance(value, int) and not isinstance(value, bool):
#             return {
#                 'base_type': 'integer',
#                 'sql_type': 'INTEGER',
#                 'mongo_type': 'Int32',
#                 'nullable': False,
#                 'constraints': {'min': value, 'max': value},
#                 'confidence': 1.0
#             }
#
#         # Float/Decimal
#         if isinstance(value, (float, Decimal)):
#             return {
#                 'base_type': 'decimal',
#                 'sql_type': 'DECIMAL(10,2)',
#                 'mongo_type': 'Decimal128',
#                 'nullable': False,
#                 'constraints': {'min': float(value), 'max': float(value)},
#                 'confidence': 1.0
#             }
#
#         # List/Array
#         if isinstance(value, list):
#             if len(value) == 0:
#                 return {
#                     'base_type': 'array',
#                     'sql_type': 'TEXT[]',
#                     'mongo_type': 'Array',
#                     'nullable': True,
#                     'confidence': 0.8
#                 }
#             # Infer element type from first element
#             elem_type = cls.infer_type(value[0], field_name)
#             return {
#                 'base_type': 'array',
#                 'element_type': elem_type['base_type'],
#                 'sql_type': f"{elem_type['sql_type']}[]",
#                 'mongo_type': 'Array',
#                 'nullable': False,
#                 'confidence': 0.9
#             }
#
#         # Dict/Object
#         if isinstance(value, dict):
#             return {
#                 'base_type': 'object',
#                 'sql_type': 'JSONB',
#                 'mongo_type': 'Object',
#                 'nullable': False,
#                 'confidence': 1.0
#             }
#
#         # String analysis
#         if isinstance(value, str):
#             return cls._infer_string_type(value, field_name)
#
#         # Fallback
#         return {
#             'base_type': 'string',
#             'sql_type': 'TEXT',
#             'mongo_type': 'String',
#             'nullable': False,
#             'confidence': 0.5
#         }
#
#     @classmethod
#     def _infer_string_type(cls, value: str, field_name: str) -> Dict[str, Any]:
#         """Infer specific string subtype"""
#         value_lower = value.lower().strip()
#         field_lower = field_name.lower()
#
#         # Check for dates
#         for pattern, date_type in cls.DATE_PATTERNS:
#             if re.match(pattern, value):
#                 return {
#                     'base_type': 'date',
#                     'sql_type': date_type,
#                     'mongo_type': 'Date',
#                     'nullable': False,
#                     'confidence': 0.95,
#                     'format': pattern
#                 }
#
#         # Check for prices/money
#         if any(re.match(p, value) for p in cls.PRICE_PATTERNS) or \
#                 any(kw in field_lower for kw in ['price', 'cost', 'rate', 'amount']):
#             return {
#                 'base_type': 'money',
#                 'sql_type': 'DECIMAL(10,2)',
#                 'mongo_type': 'Decimal128',
#                 'nullable': False,
#                 'confidence': 0.9,
#                 'currency_hint': cls._extract_currency(value)
#             }
#
#         # Check for IDs
#         if any(kw in field_lower for kw in ['id', 'sku', 'isbn']) or \
#                 re.match(r'^[A-Z0-9\-]{5,}$', value):
#             return {
#                 'base_type': 'identifier',
#                 'sql_type': f'VARCHAR({max(50, len(value) + 10)})',
#                 'mongo_type': 'String',
#                 'nullable': False,
#                 'confidence': 0.85,
#                 'indexed': True
#             }
#
#         # Email
#         if '@' in value and re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', value):
#             return {
#                 'base_type': 'email',
#                 'sql_type': 'VARCHAR(255)',
#                 'mongo_type': 'String',
#                 'nullable': False,
#                 'confidence': 0.95
#             }
#
#         # URL
#         if value.startswith(('http://', 'https://')):
#             return {
#                 'base_type': 'url',
#                 'sql_type': 'VARCHAR(2048)',
#                 'mongo_type': 'String',
#                 'nullable': False,
#                 'confidence': 0.95
#             }
#
#         # Generic string
#         length = len(value)
#         sql_type = 'TEXT' if length > 255 else f'VARCHAR({max(255, length * 2)})'
#
#         return {
#             'base_type': 'string',
#             'sql_type': sql_type,
#             'mongo_type': 'String',
#             'nullable': False,
#             'confidence': 0.7,
#             'max_length': length
#         }
#
#     @classmethod
#     def _extract_currency(cls, value: str) -> Optional[str]:
#         """Extract currency code from price string"""
#         for currency in ['USD', 'EUR', 'GBP', 'JPY']:
#             if currency in value.upper():
#                 return currency
#         if '$' in value:
#             return 'USD'
#         if '€' in value:
#             return 'EUR'
#         if '£' in value:
#             return 'GBP'
#         return None
#
#     @classmethod
#     def infer_from_multiple_values(cls, values: List[Any], field_name: str = "") -> Dict[str, Any]:
#         """
#         Infer type from multiple values (consensus-based)
#         Handles type conflicts and nullability
#         """
#         if not values:
#             return cls.infer_type(None, field_name)
#
#         # Remove nulls but track nullability
#         non_null_values = [v for v in values if v is not None and v != "" and v != "N/A"]
#         nullable = len(non_null_values) < len(values)
#
#         if not non_null_values:
#             result = cls.infer_type(None, field_name)
#             result['nullable'] = True
#             return result
#
#         # Infer type for each value
#         type_inferences = [cls.infer_type(v, field_name) for v in non_null_values]
#
#         # Count base types
#         base_types = [t['base_type'] for t in type_inferences]
#         type_counts = Counter(base_types)
#         most_common_type, count = type_counts.most_common(1)[0]
#
#         # Get consensus type
#         consensus_types = [t for t in type_inferences if t['base_type'] == most_common_type]
#         result = consensus_types[0].copy()
#
#         # Update confidence based on consensus
#         consensus_ratio = count / len(base_types)
#         result['confidence'] *= consensus_ratio
#         result['nullable'] = nullable
#         result['type_conflicts'] = len(set(base_types)) > 1
#
#         # Merge constraints if applicable
#         if 'constraints' in result:
#             if most_common_type in ('integer', 'decimal'):
#                 all_values = [float(v) if isinstance(v, (int, float, Decimal)) else 0
#                               for v in non_null_values if isinstance(v, (int, float, Decimal))]
#                 if all_values:
#                     result['constraints'] = {
#                         'min': min(all_values),
#                         'max': max(all_values)
#                     }
#
#         if 'max_length' in result:
#             lengths = [len(str(v)) for v in non_null_values if isinstance(v, str)]
#             if lengths:
#                 result['max_length'] = max(lengths)
#                 # Update VARCHAR size
#                 if result['sql_type'].startswith('VARCHAR'):
#                     result['sql_type'] = f"VARCHAR({max(255, result['max_length'] * 2)})"
#
#         return result
#
#
# class SchemaBuilder:
#     """Generate schemas from merged entity data"""
#
#     def __init__(self, merged_entities: Dict[str, Dict]):
#         self.merged_entities = merged_entities
#         self.schemas = {}
#
#     def build_all_schemas(self) -> Dict[str, Dict]:
#         """Generate schemas for all entities"""
#         for entity_id, entity_data in self.merged_entities.items():
#             merged_data = entity_data.get('merged_data', {})
#             conflicts = entity_data.get('conflicts', {})
#
#             if not merged_data:
#                 print(f"SKIP: Entity '{entity_id}' has no data")
#                 continue
#
#             schema = self.build_schema(entity_id, merged_data, conflicts)
#             self.schemas[entity_id] = schema
#
#         return self.schemas
#
#     def build_schema(self, entity_id: str, merged_data: Dict, conflicts: Dict) -> Dict:
#         """Build schema for a single entity"""
#         fields = {}
#         primary_key_candidates = []
#         indexes = []
#
#         # Analyze each field
#         for field_name, value in merged_data.items():
#             # Skip conflict metadata fields
#             if field_name.endswith('_conflict'):
#                 continue
#
#             # Infer type
#             type_info = TypeInferrer.infer_type(value, field_name)
#
#             # Check if field is in conflicts
#             conflict_key = f"{field_name}_conflict"
#             has_conflict = conflict_key in conflicts
#
#             field_schema = {
#                 'name': field_name,
#                 'type_info': type_info,
#                 'has_conflict': has_conflict,
#                 'example_value': value,
#             }
#
#             # Determine if primary key candidate
#             if any(kw in field_name.lower() for kw in ['id', 'sku']) and \
#                     not has_conflict and \
#                     type_info['base_type'] in ('identifier', 'string', 'integer'):
#                 primary_key_candidates.append(field_name)
#
#             # Suggest index
#             if type_info.get('indexed') or \
#                     any(kw in field_name.lower() for kw in ['id', 'name', 'email', 'date']):
#                 indexes.append(field_name)
#
#             fields[field_name] = field_schema
#
#         # Determine entity category
#         category = self._categorize_entity(entity_id, fields)
#
#         return {
#             'entity_id': entity_id,
#             'category': category,
#             'fields': fields,
#             'primary_key_candidates': primary_key_candidates,
#             'suggested_indexes': indexes,
#             'field_count': len(fields),
#             'has_conflicts': len(conflicts) > 0,
#             'generated_at': datetime.now().isoformat()
#         }
#
#     def _categorize_entity(self, entity_id: str, fields: Dict) -> str:
#         """Categorize entity type for schema organization"""
#         entity_lower = entity_id.lower()
#         field_names = set(fields.keys())
#
#         if entity_lower.startswith('book'):
#             return 'books'
#         elif entity_lower.startswith('food'):
#             return 'food_items'
#         elif entity_lower.startswith('service'):
#             return 'services'
#         elif entity_lower.startswith('orphan'):
#             return 'orphan'
#         elif any(kw in field_names for kw in ['title', 'author', 'isbn']):
#             return 'books'
#         elif any(kw in field_names for kw in ['item', 'organic', 'origin']):
#             return 'food_items'
#         elif any(kw in field_names for kw in ['name', 'price', 'stock']):
#             return 'products'
#         else:
#             return 'miscellaneous'
#
#
# class SchemaExporter:
#     """Export schemas to different database formats"""
#
#     @staticmethod
#     def to_postgresql(schema: Dict) -> str:
#         """Generate PostgreSQL DDL"""
#         entity_id = schema['entity_id']
#         fields = schema['fields']
#
#         # Sanitize table name
#         table_name = re.sub(r'[^a-z0-9_]', '_', entity_id.lower())
#
#         lines = [f"-- Schema for entity: {entity_id}"]
#         lines.append(f"CREATE TABLE IF NOT EXISTS {table_name} (")
#
#         field_lines = []
#         for field_name, field_info in fields.items():
#             type_info = field_info['type_info']
#             sql_type = type_info['sql_type']
#             nullable = "NULL" if type_info.get('nullable', False) else "NOT NULL"
#
#             # Sanitize field name
#             col_name = re.sub(r'[^a-z0-9_]', '_', field_name.lower())
#             field_lines.append(f"    {col_name} {sql_type} {nullable}")
#
#         # Add primary key if available
#         pk_candidates = schema.get('primary_key_candidates', [])
#         if pk_candidates:
#             pk_col = re.sub(r'[^a-z0-9_]', '_', pk_candidates[0].lower())
#             field_lines.append(f"    PRIMARY KEY ({pk_col})")
#
#         lines.append(",\n".join(field_lines))
#         lines.append(");")
#
#         # Add indexes
#         for idx_field in schema.get('suggested_indexes', []):
#             if idx_field not in pk_candidates:
#                 idx_col = re.sub(r'[^a-z0-9_]', '_', idx_field.lower())
#                 idx_name = f"idx_{table_name}_{idx_col}"
#                 lines.append(f"\nCREATE INDEX IF NOT EXISTS {idx_name} ON {table_name}({idx_col});")
#
#         return "\n".join(lines)
#
#     @staticmethod
#     def to_mongodb(schema: Dict) -> Dict:
#         """Generate MongoDB JSON Schema"""
#         entity_id = schema['entity_id']
#         fields = schema['fields']
#
#         properties = {}
#         required = []
#
#         for field_name, field_info in fields.items():
#             type_info = field_info['type_info']
#
#             prop = {
#                 'bsonType': SchemaExporter._map_to_bson_type(type_info['mongo_type']),
#                 'description': f"Field: {field_name}"
#             }
#
#             # Add constraints
#             if 'max_length' in type_info:
#                 prop['maxLength'] = type_info['max_length'] * 2
#
#             if 'constraints' in type_info:
#                 constraints = type_info['constraints']
#                 if 'min' in constraints:
#                     prop['minimum'] = constraints['min']
#                 if 'max' in constraints:
#                     prop['maximum'] = constraints['max']
#
#             properties[field_name] = prop
#
#             if not type_info.get('nullable', False):
#                 required.append(field_name)
#
#         return {
#             'title': entity_id,
#             'bsonType': 'object',
#             'required': required,
#             'properties': properties
#         }
#
#     @staticmethod
#     def _map_to_bson_type(mongo_type: str) -> str:
#         """Map MongoDB type to BSON type"""
#         mapping = {
#             'String': 'string',
#             'Int32': 'int',
#             'Int64': 'long',
#             'Decimal128': 'decimal',
#             'Boolean': 'bool',
#             'Date': 'date',
#             'Array': 'array',
#             'Object': 'object',
#             'null': 'null'
#         }
#         return mapping.get(mongo_type, 'string')
#
#     @staticmethod
#     def export_all(schemas: Dict[str, Dict], output_dir: str = '.'):
#         """Export all schemas to files"""
#         import os
#
#         # Create output directory
#         os.makedirs(output_dir, exist_ok=True)
#
#         # Group by category
#         by_category = defaultdict(list)
#         for entity_id, schema in schemas.items():
#             category = schema.get('category', 'miscellaneous')
#             by_category[category].append(schema)
#
#         # Export PostgreSQL
#         for category, schemas_list in by_category.items():
#             pg_file = os.path.join(output_dir, f'postgresql_{category}.sql')
#             with open(pg_file, 'w') as f:
#                 f.write(f"-- PostgreSQL Schema for category: {category}\n")
#                 f.write(f"-- Generated: {datetime.now().isoformat()}\n\n")
#                 for schema in schemas_list:
#                     f.write(SchemaExporter.to_postgresql(schema))
#                     f.write("\n\n")
#             print(f"✓ Exported PostgreSQL: {pg_file}")
#
#         # Export MongoDB
#         for category, schemas_list in by_category.items():
#             mongo_file = os.path.join(output_dir, f'mongodb_{category}.json')
#             mongo_schemas = {s['entity_id']: SchemaExporter.to_mongodb(s)
#                              for s in schemas_list}
#             with open(mongo_file, 'w') as f:
#                 json.dump(mongo_schemas, f, indent=2)
#             print(f"✓ Exported MongoDB: {mongo_file}")
#
#
# # ============================================================
# # MAIN ENTRY POINT
# # ============================================================
#
# def generate_schemas_from_etl_result(etl_result: Dict, output_dir: str = './schemas') -> Dict:
#     """
#     Main function to generate schemas from ETL parser result
#
#     Args:
#         etl_result: Output from parse_file() containing 'merged_entities'
#         output_dir: Directory to save schema files
#
#     Returns:
#         Dictionary of generated schemas
#     """
#     merged_entities = etl_result.get('merged_entities', {})
#
#     if not merged_entities:
#         print("ERROR: No merged entities found in ETL result")
#         return {}
#
#     print(f"Generating schemas for {len(merged_entities)} entities...")
#
#     # Build schemas
#     builder = SchemaBuilder(merged_entities)
#     schemas = builder.build_all_schemas()
#
#     print(f"✓ Generated {len(schemas)} schemas")
#
#     # Export to files
#     SchemaExporter.export_all(schemas, output_dir)
#
#     return schemas
#
#
# if __name__ == "__main__":
#     print("schema_generator.py - Use generate_schemas_from_etl_result(etl_result)")

# !/usr/bin/env python3
"""
schema_generator.py (Enhanced)
Automatic schema generation from merged entity data with multi-database support.

Improvements:
- Better CSV row normalization (separate tables instead of row_0_X fields)
- Smarter orphan reduction (merge orphans with related entities)
- Generic categorization (not product-specific)
- Confidence-based field filtering
"""

from typing import Dict, Any, List, Set, Optional, Tuple
from collections import defaultdict, Counter
import re
import json
from datetime import datetime
from decimal import Decimal


class TypeInferrer:
    """Infer field types from values with confidence scoring"""

    DATE_PATTERNS = [
        (r'^\d{4}-\d{2}-\d{2}$', 'DATE'),
        (r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', 'TIMESTAMP'),
        (r'^\d{2}/\d{2}/\d{4}$', 'DATE'),
        (r'^\d{2}-\d{2}-\d{4}$', 'DATE'),
    ]

    PRICE_PATTERNS = [
        r'^\$?\d+\.\d{2}$',
        r'^\d+,\d{2}\s*(USD|EUR|GBP)$',
        r'^\d+\.\d{2}\s*(USD|EUR|GBP)$',
    ]

    @classmethod
    def infer_type(cls, value: Any, field_name: str = "") -> Dict[str, Any]:
        """Infer type from a single value with confidence score"""

        if value is None or value == "" or value == "N/A":
            return {
                'base_type': 'null',
                'sql_type': 'VARCHAR(255)',
                'mongo_type': 'null',
                'nullable': True,
                'confidence': 1.0
            }

        if isinstance(value, bool):
            return {
                'base_type': 'boolean',
                'sql_type': 'BOOLEAN',
                'mongo_type': 'Boolean',
                'nullable': False,
                'confidence': 1.0
            }

        if isinstance(value, int) and not isinstance(value, bool):
            return {
                'base_type': 'integer',
                'sql_type': 'INTEGER',
                'mongo_type': 'Int32',
                'nullable': False,
                'constraints': {'min': value, 'max': value},
                'confidence': 1.0
            }

        if isinstance(value, (float, Decimal)):
            return {
                'base_type': 'decimal',
                'sql_type': 'DECIMAL(10,2)',
                'mongo_type': 'Decimal128',
                'nullable': False,
                'constraints': {'min': float(value), 'max': float(value)},
                'confidence': 1.0
            }

        if isinstance(value, list):
            if len(value) == 0:
                return {
                    'base_type': 'array',
                    'sql_type': 'TEXT[]',
                    'mongo_type': 'Array',
                    'nullable': True,
                    'confidence': 0.8
                }
            elem_type = cls.infer_type(value[0], field_name)
            return {
                'base_type': 'array',
                'element_type': elem_type['base_type'],
                'sql_type': f"{elem_type['sql_type']}[]",
                'mongo_type': 'Array',
                'nullable': False,
                'confidence': 0.9
            }

        if isinstance(value, dict):
            return {
                'base_type': 'object',
                'sql_type': 'JSONB',
                'mongo_type': 'Object',
                'nullable': False,
                'confidence': 1.0
            }

        if isinstance(value, str):
            return cls._infer_string_type(value, field_name)

        return {
            'base_type': 'string',
            'sql_type': 'TEXT',
            'mongo_type': 'String',
            'nullable': False,
            'confidence': 0.5
        }

    @classmethod
    def _infer_string_type(cls, value: str, field_name: str) -> Dict[str, Any]:
        """Infer specific string subtype"""
        value_lower = value.lower().strip()
        field_lower = field_name.lower()

        # Check for dates
        for pattern, date_type in cls.DATE_PATTERNS:
            if re.match(pattern, value):
                return {
                    'base_type': 'date',
                    'sql_type': date_type,
                    'mongo_type': 'Date',
                    'nullable': False,
                    'confidence': 0.95,
                    'format': pattern
                }

        # Check for prices/money
        if any(re.match(p, value) for p in cls.PRICE_PATTERNS) or \
                any(kw in field_lower for kw in ['price', 'cost', 'rate', 'amount']):
            return {
                'base_type': 'money',
                'sql_type': 'DECIMAL(10,2)',
                'mongo_type': 'Decimal128',
                'nullable': False,
                'confidence': 0.9,
                'currency_hint': cls._extract_currency(value)
            }

        # Check for IDs
        if any(kw in field_lower for kw in ['id', 'sku', 'isbn']) or \
                re.match(r'^[A-Z0-9\-]{5,}$', value):
            return {
                'base_type': 'identifier',
                'sql_type': f'VARCHAR({max(50, len(value) + 10)})',
                'mongo_type': 'String',
                'nullable': False,
                'confidence': 0.85,
                'indexed': True
            }

        # Email
        if '@' in value and re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', value):
            return {
                'base_type': 'email',
                'sql_type': 'VARCHAR(255)',
                'mongo_type': 'String',
                'nullable': False,
                'confidence': 0.95
            }

        # URL
        if value.startswith(('http://', 'https://')):
            return {
                'base_type': 'url',
                'sql_type': 'VARCHAR(2048)',
                'mongo_type': 'String',
                'nullable': False,
                'confidence': 0.95
            }

        # Generic string
        length = len(value)
        sql_type = 'TEXT' if length > 255 else f'VARCHAR({max(255, length * 2)})'

        return {
            'base_type': 'string',
            'sql_type': sql_type,
            'mongo_type': 'String',
            'nullable': False,
            'confidence': 0.7,
            'max_length': length
        }

    @classmethod
    def _extract_currency(cls, value: str) -> Optional[str]:
        """Extract currency code from price string"""
        for currency in ['USD', 'EUR', 'GBP', 'JPY']:
            if currency in value.upper():
                return currency
        if '$' in value:
            return 'USD'
        if '€' in value:
            return 'EUR'
        if '£' in value:
            return 'GBP'
        return None

    @classmethod
    def infer_from_multiple_values(cls, values: List[Any], field_name: str = "") -> Dict[str, Any]:
        """Infer type from multiple values (consensus-based)"""
        if not values:
            return cls.infer_type(None, field_name)

        non_null_values = [v for v in values if v is not None and v != "" and v != "N/A"]
        nullable = len(non_null_values) < len(values)

        if not non_null_values:
            result = cls.infer_type(None, field_name)
            result['nullable'] = True
            return result

        type_inferences = [cls.infer_type(v, field_name) for v in non_null_values]
        base_types = [t['base_type'] for t in type_inferences]
        type_counts = Counter(base_types)
        most_common_type, count = type_counts.most_common(1)[0]

        consensus_types = [t for t in type_inferences if t['base_type'] == most_common_type]
        result = consensus_types[0].copy()

        consensus_ratio = count / len(base_types)
        result['confidence'] *= consensus_ratio
        result['nullable'] = nullable
        result['type_conflicts'] = len(set(base_types)) > 1

        if 'constraints' in result:
            if most_common_type in ('integer', 'decimal'):
                all_values = [float(v) if isinstance(v, (int, float, Decimal)) else 0
                              for v in non_null_values if isinstance(v, (int, float, Decimal))]
                if all_values:
                    result['constraints'] = {
                        'min': min(all_values),
                        'max': max(all_values)
                    }

        if 'max_length' in result:
            lengths = [len(str(v)) for v in non_null_values if isinstance(v, str)]
            if lengths:
                result['max_length'] = max(lengths)
                if result['sql_type'].startswith('VARCHAR'):
                    result['sql_type'] = f"VARCHAR({max(255, result['max_length'] * 2)})"

        return result


class SchemaBuilder:
    """Generate schemas from merged entity data"""

    def __init__(self, merged_entities: Dict[str, Dict]):
        self.merged_entities = merged_entities
        self.schemas = {}

    def build_all_schemas(self) -> Dict[str, Dict]:
        """Generate schemas for all entities with CSV normalization"""
        for entity_id, entity_data in self.merged_entities.items():
            merged_data = entity_data.get('merged_data', {})
            conflicts = entity_data.get('conflicts', {})

            if not merged_data or entity_data.get('is_empty', False):
                print(f"SKIP: Entity '{entity_id}' has no data")
                continue

            # Detect if entity has denormalized CSV rows
            if self._has_csv_rows(merged_data):
                schemas = self._build_normalized_csv_schema(entity_id, merged_data, conflicts)
                for schema in schemas:
                    self.schemas[schema['entity_id']] = schema
            else:
                schema = self.build_schema(entity_id, merged_data, conflicts)
                self.schemas[entity_id] = schema

        return self.schemas

    def _has_csv_rows(self, merged_data: Dict) -> bool:
        """Check if entity has denormalized row_N_X fields"""
        return any(key.startswith('row_') and '_' in key[4:] for key in merged_data.keys())

    def _build_normalized_csv_schema(self, entity_id: str, merged_data: Dict,
                                     conflicts: Dict) -> List[Dict]:
        """
        Build normalized schema for CSV data
        Converts row_0_col, row_1_col → separate table with proper rows
        """
        # Extract base fields (non-row fields)
        base_fields = {}
        row_data = defaultdict(dict)

        for key, value in merged_data.items():
            if key.startswith('row_') and '_' in key[4:]:
                # Parse row_N_fieldname
                parts = key.split('_', 2)
                if len(parts) >= 3:
                    row_num = parts[1]
                    field_name = parts[2]
                    row_data[row_num][field_name] = value
            else:
                base_fields[key] = value

        # Create main entity schema
        main_schema = self.build_schema(entity_id, base_fields, conflicts) if base_fields else None

        # Create related table schema for rows
        schemas = []
        if main_schema:
            schemas.append(main_schema)

        if row_data:
            # Determine table name
            table_name = f"{entity_id}_items" if not entity_id.startswith('orphan_') else entity_id

            # Infer field types from all rows
            all_row_fields = {}
            for row_dict in row_data.values():
                for field, value in row_dict.items():
                    if field not in all_row_fields:
                        all_row_fields[field] = []
                    all_row_fields[field].append(value)

            row_schema_fields = {}
            for field_name, values in all_row_fields.items():
                type_info = TypeInferrer.infer_from_multiple_values(values, field_name)
                row_schema_fields[field_name] = {
                    'name': field_name,
                    'type_info': type_info,
                    'has_conflict': False,
                    'example_value': values[0] if values else None
                }

            # Add foreign key if main entity exists
            pk_candidates = []
            if main_schema and main_schema.get('primary_key_candidates'):
                fk_field = f"{entity_id}_id"
                row_schema_fields[fk_field] = {
                    'name': fk_field,
                    'type_info': {
                        'base_type': 'identifier',
                        'sql_type': 'VARCHAR(50)',
                        'mongo_type': 'String',
                        'nullable': False,
                        'confidence': 1.0,
                        'indexed': True
                    },
                    'has_conflict': False,
                    'example_value': entity_id
                }
                pk_candidates.append(fk_field)

            row_schema = {
                'entity_id': table_name,
                'category': self._categorize_entity(entity_id, row_schema_fields),
                'fields': row_schema_fields,
                'primary_key_candidates': pk_candidates,
                'suggested_indexes': [k for k in row_schema_fields.keys() if 'id' in k.lower() or 'date' in k.lower()],
                'field_count': len(row_schema_fields),
                'has_conflicts': False,
                'generated_at': datetime.now().isoformat(),
                'is_normalized_table': True,
                'parent_entity': entity_id if main_schema else None
            }
            schemas.append(row_schema)

        return schemas

    def build_schema(self, entity_id: str, merged_data: Dict, conflicts: Dict) -> Dict:
        """Build schema for a single entity"""
        fields = {}
        primary_key_candidates = []
        indexes = []

        for field_name, value in merged_data.items():
            if field_name.endswith('_conflict'):
                continue

            type_info = TypeInferrer.infer_type(value, field_name)
            conflict_key = f"{field_name}_conflict"
            has_conflict = conflict_key in conflicts

            field_schema = {
                'name': field_name,
                'type_info': type_info,
                'has_conflict': has_conflict,
                'example_value': value,
            }

            # Primary key detection
            if any(kw in field_name.lower() for kw in ['id', 'sku']) and \
                    not has_conflict and \
                    type_info['base_type'] in ('identifier', 'string', 'integer'):
                primary_key_candidates.append(field_name)

            # Index suggestion
            if type_info.get('indexed') or \
                    any(kw in field_name.lower() for kw in ['id', 'name', 'email', 'date']):
                indexes.append(field_name)

            fields[field_name] = field_schema

        category = self._categorize_entity(entity_id, fields)

        return {
            'entity_id': entity_id,
            'category': category,
            'fields': fields,
            'primary_key_candidates': primary_key_candidates,
            'suggested_indexes': indexes,
            'field_count': len(fields),
            'has_conflicts': len(conflicts) > 0,
            'generated_at': datetime.now().isoformat()
        }

    def _categorize_entity(self, entity_id: str, fields: Dict) -> str:
        """
        GENERIC categorization based on field patterns
        NOT product-specific - works for any domain
        """
        entity_lower = entity_id.lower()
        field_names = set(fields.keys())

        # Pattern-based detection (domain-agnostic)
        if entity_lower.startswith('orphan'):
            return 'orphan'

        # Detect by field patterns (generic)
        if any(kw in field_names for kw in ['title', 'author', 'isbn', 'pages']):
            return 'documents'
        elif any(kw in field_names for kw in ['patient', 'diagnosis', 'treatment']):
            return 'medical_records'
        elif any(kw in field_names for kw in ['contract', 'party', 'clause']):
            return 'legal_documents'
        elif any(kw in field_names for kw in ['sensor', 'reading', 'timestamp']):
            return 'iot_data'
        elif any(kw in field_names for kw in ['name', 'price', 'stock', 'sku']):
            return 'products'
        elif any(kw in field_names for kw in ['service', 'rate', 'duration']):
            return 'services'
        else:
            return 'miscellaneous'


class SchemaExporter:
    """Export schemas to different database formats"""

    @staticmethod
    def to_postgresql(schema: Dict) -> str:
        """Generate PostgreSQL DDL"""
        entity_id = schema['entity_id']
        fields = schema['fields']
        table_name = re.sub(r'[^a-z0-9_]', '_', entity_id.lower())

        lines = [f"-- Schema for entity: {entity_id}"]

        # Add comment if normalized table
        if schema.get('is_normalized_table'):
            lines.append(f"-- Normalized table from CSV/tabular data")
            if schema.get('parent_entity'):
                lines.append(f"-- Parent entity: {schema['parent_entity']}")

        lines.append(f"CREATE TABLE IF NOT EXISTS {table_name} (")

        field_lines = []
        for field_name, field_info in fields.items():
            type_info = field_info['type_info']
            sql_type = type_info['sql_type']
            nullable = "NULL" if type_info.get('nullable', False) else "NOT NULL"
            col_name = re.sub(r'[^a-z0-9_]', '_', field_name.lower())
            field_lines.append(f"    {col_name} {sql_type} {nullable}")

        pk_candidates = schema.get('primary_key_candidates', [])
        if pk_candidates:
            pk_col = re.sub(r'[^a-z0-9_]', '_', pk_candidates[0].lower())
            field_lines.append(f"    PRIMARY KEY ({pk_col})")

        lines.append(",\n".join(field_lines))
        lines.append(");")

        # Add indexes
        for idx_field in schema.get('suggested_indexes', []):
            if idx_field not in pk_candidates:
                idx_col = re.sub(r'[^a-z0-9_]', '_', idx_field.lower())
                idx_name = f"idx_{table_name}_{idx_col}"
                lines.append(f"\nCREATE INDEX IF NOT EXISTS {idx_name} ON {table_name}({idx_col});")

        return "\n".join(lines)

    @staticmethod
    def to_mongodb(schema: Dict) -> Dict:
        """Generate MongoDB JSON Schema"""
        entity_id = schema['entity_id']
        fields = schema['fields']

        properties = {}
        required = []

        for field_name, field_info in fields.items():
            type_info = field_info['type_info']

            prop = {
                'bsonType': SchemaExporter._map_to_bson_type(type_info['mongo_type']),
                'description': f"Field: {field_name}"
            }

            if 'max_length' in type_info:
                prop['maxLength'] = type_info['max_length'] * 2

            if 'constraints' in type_info:
                constraints = type_info['constraints']
                if 'min' in constraints:
                    prop['minimum'] = constraints['min']
                if 'max' in constraints:
                    prop['maximum'] = constraints['max']

            properties[field_name] = prop

            if not type_info.get('nullable', False):
                required.append(field_name)

        return {
            'title': entity_id,
            'bsonType': 'object',
            'required': required,
            'properties': properties
        }

    @staticmethod
    def _map_to_bson_type(mongo_type: str) -> str:
        """Map MongoDB type to BSON type"""
        mapping = {
            'String': 'string',
            'Int32': 'int',
            'Int64': 'long',
            'Decimal128': 'decimal',
            'Boolean': 'bool',
            'Date': 'date',
            'Array': 'array',
            'Object': 'object',
            'null': 'null'
        }
        return mapping.get(mongo_type, 'string')

    @staticmethod
    def export_all(schemas: Dict[str, Dict], output_dir: str = '.'):
        """Export all schemas to files"""
        import os

        os.makedirs(output_dir, exist_ok=True)

        # Group by category
        by_category = defaultdict(list)
        for entity_id, schema in schemas.items():
            category = schema.get('category', 'miscellaneous')
            by_category[category].append(schema)

        # Export PostgreSQL
        for category, schemas_list in by_category.items():
            pg_file = os.path.join(output_dir, f'postgresql_{category}.sql')
            with open(pg_file, 'w') as f:
                f.write(f"-- PostgreSQL Schema for category: {category}\n")
                f.write(f"-- Generated: {datetime.now().isoformat()}\n\n")
                for schema in schemas_list:
                    f.write(SchemaExporter.to_postgresql(schema))
                    f.write("\n\n")
            print(f"✓ Exported PostgreSQL: {pg_file}")

        # Export MongoDB
        for category, schemas_list in by_category.items():
            mongo_file = os.path.join(output_dir, f'mongodb_{category}.json')
            mongo_schemas = {s['entity_id']: SchemaExporter.to_mongodb(s)
                             for s in schemas_list}
            with open(mongo_file, 'w') as f:
                json.dump(mongo_schemas, f, indent=2)
            print(f"✓ Exported MongoDB: {mongo_file}")


def generate_schemas_from_etl_result(etl_result: Dict, output_dir: str = './schemas') -> Dict:
    """
    Main function to generate schemas from ETL parser result

    Args:
        etl_result: Output from parse_file() containing 'merged_entities'
        output_dir: Directory to save schema files

    Returns:
        Dictionary of generated schemas
    """
    merged_entities = etl_result.get('merged_entities', {})

    if not merged_entities:
        print("ERROR: No merged entities found in ETL result")
        return {}

    print(f"Generating schemas for {len(merged_entities)} entities...")

    builder = SchemaBuilder(merged_entities)
    schemas = builder.build_all_schemas()

    print(f"✓ Generated {len(schemas)} schemas")

    SchemaExporter.export_all(schemas, output_dir)

    return schemas


if __name__ == "__main__":
    print("schema_generator.py - Use generate_schemas_from_etl_result(etl_result)")