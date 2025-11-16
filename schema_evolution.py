#!/usr/bin/env python3
"""
schema_evolution.py - Schema versioning, diffing, and migration system

Handles:
- Schema version tracking
- Change detection (add/remove/rename/type change)
- Migration generation (SQL DDL)
- Backward compatibility via views
- Query translation
"""

import json
import os
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import defaultdict
import hashlib


@dataclass
class FieldChange:
    """Represents a single field change between versions"""
    change_type: str  # 'added', 'removed', 'renamed', 'type_changed', 'nullable_changed'
    field_name: str
    old_value: Any = None
    new_value: Any = None
    breaking: bool = False
    migration_notes: str = ""


@dataclass
class SchemaVersion:
    """Schema version metadata"""
    schema_id: str
    entity_type: str
    version: int
    schema_json: Dict
    created_at: str
    parent_version: Optional[str] = None
    field_mappings: Dict = None  # old_field -> new_field
    changes: List[FieldChange] = None


class SchemaRegistry:
    """Central registry for all schema versions"""

    def __init__(self, storage_path: str = './schema_registry'):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self.registry_file = os.path.join(storage_path, 'registry.json')
        self.versions = self._load_registry()

    def _load_registry(self) -> Dict[str, List[SchemaVersion]]:
        """Load existing registry"""
        if os.path.exists(self.registry_file):
            with open(self.registry_file, 'r') as f:
                data = json.load(f)
                # Convert to SchemaVersion objects
                registry = {}
                for entity_type, versions in data.items():
                    registry[entity_type] = [
                        SchemaVersion(**v) for v in versions
                    ]
                return registry
        return {}

    def _save_registry(self):
        """Persist registry to disk"""
        data = {}
        for entity_type, versions in self.versions.items():
            data[entity_type] = [asdict(v) for v in versions]

        with open(self.registry_file, 'w') as f:
            json.dump(data, f, indent=2)

    def register_schema(self, entity_type: str, schema: Dict,
                        changes: List[FieldChange] = None) -> SchemaVersion:
        """Register a new schema version"""

        if entity_type not in self.versions:
            self.versions[entity_type] = []

        version_num = len(self.versions[entity_type]) + 1

        # Generate schema ID
        schema_hash = hashlib.md5(
            json.dumps(schema, sort_keys=True).encode()
        ).hexdigest()[:8]
        schema_id = f"{entity_type}_v{version_num}_{schema_hash}"

        # Get parent version
        parent_version = None
        if version_num > 1:
            parent_version = self.versions[entity_type][-1].schema_id

        version = SchemaVersion(
            schema_id=schema_id,
            entity_type=entity_type,
            version=version_num,
            schema_json=schema,
            created_at=datetime.now().isoformat(),
            parent_version=parent_version,
            field_mappings={},
            changes=changes or []
        )

        self.versions[entity_type].append(version)
        self._save_registry()

        return version

    def get_latest_version(self, entity_type: str) -> Optional[SchemaVersion]:
        """Get the most recent schema version"""
        if entity_type in self.versions and self.versions[entity_type]:
            return self.versions[entity_type][-1]
        return None

    def get_version(self, schema_id: str) -> Optional[SchemaVersion]:
        """Get specific schema version by ID"""
        for versions in self.versions.values():
            for version in versions:
                if version.schema_id == schema_id:
                    return version
        return None

    def get_all_versions(self, entity_type: str) -> List[SchemaVersion]:
        """Get all versions for an entity type"""
        return self.versions.get(entity_type, [])


class SchemaDiffer:
    """Compare two schema versions and detect changes"""

    @staticmethod
    def diff_schemas(old_schema: Dict, new_schema: Dict) -> List[FieldChange]:
        """
        Compare two schemas and return list of changes

        Detects:
        - Added fields
        - Removed fields
        - Renamed fields (heuristic-based)
        - Type changes
        - Nullability changes
        """
        changes = []

        old_fields = old_schema.get('fields', {})
        new_fields = new_schema.get('fields', {})

        old_field_names = set(old_fields.keys())
        new_field_names = set(new_fields.keys())

        # 1. Detect added fields
        added = new_field_names - old_field_names
        for field_name in added:
            new_type = new_fields[field_name].get('type_info', {}).get('base_type')
            nullable = new_fields[field_name].get('type_info', {}).get('nullable', True)

            changes.append(FieldChange(
                change_type='added',
                field_name=field_name,
                new_value=new_type,
                breaking=not nullable,  # Breaking if NOT NULL without default
                migration_notes=f"New field '{field_name}' added as {new_type}"
            ))

        # 2. Detect removed fields
        removed = old_field_names - new_field_names

        # Before marking as removed, check for renames
        potential_renames = SchemaDiffer._detect_renames(
            old_fields, new_fields, removed, added
        )

        for old_name, new_name in potential_renames.items():
            changes.append(FieldChange(
                change_type='renamed',
                field_name=new_name,
                old_value=old_name,
                new_value=new_name,
                breaking=True,
                migration_notes=f"Field renamed: '{old_name}' → '{new_name}'"
            ))
            removed.discard(old_name)
            added.discard(new_name)

        # Mark remaining as truly removed
        for field_name in removed:
            changes.append(FieldChange(
                change_type='removed',
                field_name=field_name,
                old_value=old_fields[field_name].get('type_info', {}).get('base_type'),
                breaking=True,
                migration_notes=f"Field '{field_name}' removed"
            ))

        # 3. Detect type changes in common fields
        common_fields = old_field_names & new_field_names
        for field_name in common_fields:
            old_type = old_fields[field_name].get('type_info', {}).get('base_type')
            new_type = new_fields[field_name].get('type_info', {}).get('base_type')

            if old_type != new_type:
                breaking = not SchemaDiffer._is_compatible_type_change(old_type, new_type)

                changes.append(FieldChange(
                    change_type='type_changed',
                    field_name=field_name,
                    old_value=old_type,
                    new_value=new_type,
                    breaking=breaking,
                    migration_notes=f"Type changed: {old_type} → {new_type}"
                ))

            # Check nullability change
            old_nullable = old_fields[field_name].get('type_info', {}).get('nullable', True)
            new_nullable = new_fields[field_name].get('type_info', {}).get('nullable', True)

            if old_nullable != new_nullable:
                changes.append(FieldChange(
                    change_type='nullable_changed',
                    field_name=field_name,
                    old_value=old_nullable,
                    new_value=new_nullable,
                    breaking=(old_nullable and not new_nullable),  # nullable → NOT NULL is breaking
                    migration_notes=f"Nullability changed: {old_nullable} → {new_nullable}"
                ))

        return changes

    @staticmethod
    def _detect_renames(old_fields: Dict, new_fields: Dict,
                        removed: set, added: set) -> Dict[str, str]:
        """
        Heuristic-based rename detection

        Strategy:
        - Compare removed vs added field names (fuzzy match)
        - Check type compatibility
        - Look for common patterns (price_usd → price, etc.)
        """
        renames = {}

        for old_name in list(removed):
            best_match = None
            best_score = 0.0

            for new_name in added:
                # Skip if types incompatible
                old_type = old_fields[old_name].get('type_info', {}).get('base_type')
                new_type = new_fields[new_name].get('type_info', {}).get('base_type')

                if not SchemaDiffer._is_compatible_type_change(old_type, new_type):
                    continue

                # Calculate similarity score
                score = SchemaDiffer._name_similarity(old_name, new_name)

                if score > best_score and score > 0.6:  # 60% threshold
                    best_score = score
                    best_match = new_name

            if best_match:
                renames[old_name] = best_match

        return renames

    @staticmethod
    def _name_similarity(name1: str, name2: str) -> float:
        """Calculate field name similarity (0-1)"""
        from difflib import SequenceMatcher

        # Normalize
        n1 = name1.lower().replace('_', '')
        n2 = name2.lower().replace('_', '')

        # Direct substring match
        if n1 in n2 or n2 in n1:
            return 0.8

        # Sequence matcher
        return SequenceMatcher(None, n1, n2).ratio()

    @staticmethod
    def _is_compatible_type_change(old_type: str, new_type: str) -> bool:
        """Check if type change is backward compatible"""

        # Same type = compatible
        if old_type == new_type:
            return True

        # Compatible widening conversions
        compatible_changes = [
            ('integer', 'decimal'),
            ('string', 'identifier'),
            ('date', 'timestamp'),
        ]

        return (old_type, new_type) in compatible_changes


class MigrationGenerator:
    """Generate SQL migration scripts"""

    @staticmethod
    def generate_migration(entity_type: str, changes: List[FieldChange],
                           old_schema: Dict, new_schema: Dict) -> Dict[str, str]:
        """
        Generate migration SQL for PostgreSQL

        Returns:
            {
                'forward': SQL to migrate old→new,
                'rollback': SQL to revert new→old,
                'view': SQL to create compatibility view
            }
        """

        table_name = entity_type.lower() + 's'
        forward_sql = []
        rollback_sql = []

        for change in changes:
            if change.change_type == 'added':
                # Add column
                col_name = change.field_name.lower().replace(' ', '_')
                new_field = new_schema['fields'][change.field_name]
                sql_type = new_field['type_info']['sql_type']
                nullable = "NULL" if new_field['type_info'].get('nullable', True) else "NOT NULL"

                forward_sql.append(
                    f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sql_type} {nullable};"
                )
                rollback_sql.append(
                    f"ALTER TABLE {table_name} DROP COLUMN {col_name};"
                )

            elif change.change_type == 'removed':
                # Drop column (keep in rollback)
                col_name = change.field_name.lower().replace(' ', '_')
                old_field = old_schema['fields'][change.field_name]
                sql_type = old_field['type_info']['sql_type']

                forward_sql.append(
                    f"ALTER TABLE {table_name} DROP COLUMN {col_name};"
                )
                rollback_sql.append(
                    f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sql_type};"
                )

            elif change.change_type == 'renamed':
                # Rename column
                old_name = change.old_value.lower().replace(' ', '_')
                new_name = change.new_value.lower().replace(' ', '_')

                forward_sql.append(
                    f"ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name};"
                )
                rollback_sql.append(
                    f"ALTER TABLE {table_name} RENAME COLUMN {new_name} TO {old_name};"
                )

            elif change.change_type == 'type_changed':
                # Type change (may need data transformation)
                col_name = change.field_name.lower().replace(' ', '_')
                new_type = new_schema['fields'][change.field_name]['type_info']['sql_type']

                if change.breaking:
                    # Create temp column, transform, swap
                    forward_sql.append(f"-- WARNING: Breaking type change for {col_name}")
                    forward_sql.append(f"ALTER TABLE {table_name} ADD COLUMN {col_name}_new {new_type};")
                    forward_sql.append(f"UPDATE {table_name} SET {col_name}_new = CAST({col_name} AS {new_type});")
                    forward_sql.append(f"ALTER TABLE {table_name} DROP COLUMN {col_name};")
                    forward_sql.append(f"ALTER TABLE {table_name} RENAME COLUMN {col_name}_new TO {col_name};")
                else:
                    # Simple ALTER TYPE
                    forward_sql.append(
                        f"ALTER TABLE {table_name} ALTER COLUMN {col_name} TYPE {new_type};"
                    )

        # Generate compatibility view for old schema
        view_sql = MigrationGenerator._generate_compatibility_view(
            entity_type, old_schema, new_schema, changes
        )

        return {
            'forward': '\n'.join(forward_sql),
            'rollback': '\n'.join(reversed(rollback_sql)),
            'view': view_sql
        }

    @staticmethod
    def _generate_compatibility_view(entity_type: str, old_schema: Dict,
                                     new_schema: Dict, changes: List[FieldChange]) -> str:
        """
        Create SQL view that presents new schema with old field names

        Example:
        CREATE VIEW products_v1 AS
        SELECT
            id,
            price AS price_usd,  -- renamed field
            ...
        FROM products;
        """

        table_name = entity_type.lower() + 's'
        view_name = f"{table_name}_v{len(changes)}"  # Versioned view name

        # Build field mapping
        select_fields = []

        # Track renames
        rename_map = {}
        for change in changes:
            if change.change_type == 'renamed':
                rename_map[change.new_value] = change.old_value

        # Build SELECT list with aliases for renamed fields
        for old_field_name in old_schema.get('fields', {}).keys():
            # Check if this field was renamed
            new_field_name = None
            for new_name, old_name in rename_map.items():
                if old_name == old_field_name:
                    new_field_name = new_name
                    break

            if new_field_name:
                # Renamed: SELECT new_name AS old_name
                select_fields.append(
                    f"{new_field_name.lower().replace(' ', '_')} AS "
                    f"{old_field_name.lower().replace(' ', '_')}"
                )
            elif old_field_name in new_schema.get('fields', {}):
                # Unchanged: SELECT field_name
                select_fields.append(old_field_name.lower().replace(' ', '_'))
            # Skip removed fields (can't show in view)

        # Build the SELECT clause
        select_clause = ',\n    '.join(select_fields)

        view_sql = f"""-- Compatibility view for old schema version
    CREATE OR REPLACE VIEW {view_name} AS
    SELECT 
        {select_clause}
    FROM {table_name};
    """

        return view_sql



class QueryTranslator:
    """Translate queries from old schema to new schema"""

    def __init__(self, registry: SchemaRegistry):
        self.registry = registry

    def translate_query(self, query: str, entity_type: str,
                        target_version: Optional[int] = None) -> str:
        """
        Translate SQL query from old schema version to current

        Example:
        Input:  SELECT price_usd FROM products WHERE price_usd < 70
        Output: SELECT price FROM products WHERE price < 70
        """

        # Get current and target versions
        current = self.registry.get_latest_version(entity_type)

        if target_version is None:
            # No translation needed
            return query

        versions = self.registry.get_all_versions(entity_type)
        if target_version >= len(versions):
            return query

        target = versions[target_version - 1]

        # Build field mapping from target → current
        field_map = self._build_field_mapping(target, current)

        # Apply field name replacements
        translated = query
        for old_name, new_name in field_map.items():
            # Word boundary replacement to avoid partial matches
            import re
            pattern = r'\b' + re.escape(old_name) + r'\b'
            translated = re.sub(pattern, new_name, translated, flags=re.IGNORECASE)

        return translated

    def _build_field_mapping(self, old_version: SchemaVersion,
                             new_version: SchemaVersion) -> Dict[str, str]:
        """Build mapping of old field names → new field names"""

        mapping = {}

        # Extract renames from changes
        for change in new_version.changes or []:
            if change.change_type == 'renamed':
                mapping[change.old_value] = change.new_value

        return mapping


class SchemaEvolutionManager:
    """Main interface for schema evolution"""

    def __init__(self, storage_path: str = './schema_registry'):
        self.registry = SchemaRegistry(storage_path)
        self.differ = SchemaDiffer()
        self.migrator = MigrationGenerator()
        self.translator = QueryTranslator(self.registry)

    def process_new_schema(self, entity_type: str, new_schema: Dict) -> Dict[str, Any]:
        """
        Process a new schema version

        Returns:
            {
                'version': SchemaVersion,
                'changes': List[FieldChange],
                'migration': migration SQL dict,
                'breaking_changes': bool
            }
        """

        # Get previous version
        old_version = self.registry.get_latest_version(entity_type)

        if old_version is None:
            # First version - no changes
            version = self.registry.register_schema(entity_type, new_schema)
            return {
                'version': version,
                'changes': [],
                'migration': None,
                'breaking_changes': False,
                'is_initial': True
            }

        # Compare schemas
        changes = self.differ.diff_schemas(old_version.schema_json, new_schema)

        # Check for breaking changes
        breaking = any(c.breaking for c in changes)

        # Generate migration
        migration = self.migrator.generate_migration(
            entity_type, changes, old_version.schema_json, new_schema
        )

        # Register new version
        version = self.registry.register_schema(entity_type, new_schema, changes)

        # Update field mappings
        for change in changes:
            if change.change_type == 'renamed':
                version.field_mappings[change.old_value] = change.new_value

        self.registry._save_registry()

        return {
            'version': version,
            'changes': changes,
            'migration': migration,
            'breaking_changes': breaking,
            'is_initial': False
        }

    def get_schema_history(self, entity_type: str) -> List[Dict]:
        """Get complete schema evolution history"""

        versions = self.registry.get_all_versions(entity_type)

        history = []
        for v in versions:
            history.append({
                'schema_id': v.schema_id,
                'version': v.version,
                'created_at': v.created_at,
                'changes': [asdict(c) for c in (v.changes or [])],
                'parent_version': v.parent_version
            })

        return history

    def translate_query(self, query: str, entity_type: str,
                        from_version: Optional[int] = None) -> str:
        """Translate query from old version to current"""
        return self.translator.translate_query(query, entity_type, from_version)


def main():
    """Example usage"""

    manager = SchemaEvolutionManager('./schema_registry')

    # Example: First schema
    schema_v1 = {
        'entity_id': 'prod-1001',
        'category': 'products',
        'fields': {
            'id': {'type_info': {'base_type': 'identifier', 'sql_type': 'VARCHAR(50)', 'nullable': False}},
            'price_usd': {'type_info': {'base_type': 'decimal', 'sql_type': 'DECIMAL(10,2)', 'nullable': False}},
        }
    }

    result1 = manager.process_new_schema('product', schema_v1)
    print(f"✓ Registered v1: {result1['version'].schema_id}")

    # Example: Evolved schema (renamed field)
    schema_v2 = {
        'entity_id': 'prod-1001',
        'category': 'products',
        'fields': {
            'id': {'type_info': {'base_type': 'identifier', 'sql_type': 'VARCHAR(50)', 'nullable': False}},
            'price': {'type_info': {'base_type': 'decimal', 'sql_type': 'DECIMAL(10,2)', 'nullable': False}},
            'currency': {'type_info': {'base_type': 'string', 'sql_type': 'VARCHAR(10)', 'nullable': True}},
        }
    }

    result2 = manager.process_new_schema('product', schema_v2)
    print(f"✓ Registered v2: {result2['version'].schema_id}")
    print(f"Changes detected: {len(result2['changes'])}")
    print(f"Breaking changes: {result2['breaking_changes']}")

    if result2['migration']:
        print("\nMigration SQL:")
        print(result2['migration']['forward'])

    # Query translation
    old_query = "SELECT id, price_usd FROM products WHERE price_usd < 70"
    new_query = manager.translate_query(old_query, 'product', from_version=1)
    print(f"\nQuery translation:")
    print(f"Old: {old_query}")
    print(f"New: {new_query}")


if __name__ == "__main__":
    main()