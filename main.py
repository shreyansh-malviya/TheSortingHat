from etl_parser import parse_file
from schema_generator import generate_schemas_from_etl_result
from schema_evolution import SchemaEvolutionManager
import json
import os

# Initialize schema evolution manager
schema_manager = SchemaEvolutionManager('./schema_registry')

with open("input.txt", "r") as f:
    text = f.read()

print("Calling parse_file with enable_ner=True...")
result = parse_file(text, enable_ner=True)
print(f"✓ Parsing complete. Found {len(result['fragments'])} fragments\n")

print("=" * 60)
print("FRAGMENT ANALYSIS WITH NER")
print("=" * 60)

# Access fragments with NER
for frag in result['fragments']:
    print(f"\n{frag.format_type} [{frag.start_index}:{frag.end_index}]")
    print(f"Confidence: {frag.confidence}")

    # Show detected entities
    entities = frag.meta.get('entities', [])
    if entities:
        print(f"✓ Entities found: {len(entities)}")
        for ent in entities[:10]:  # Show first 10
            print(f"  [{ent['source']}] {ent['label']}: {ent['text']} (score: {ent['score']:.2f})")
    else:
        print("  (no entities)")

    # Show entity summary
    summary = frag.meta.get('entity_summary', {})
    if summary.get('product_ids'):
        print(f"  → Product IDs: {summary['product_ids']}")
    if summary.get('prices'):
        print(f"  → Prices: {summary['prices'][:5]}")  # First 5
    if summary.get('emails'):
        print(f"  → Emails: {summary['emails']}")

    # Show parent-child relationships if any
    if 'parent_fragment' in frag.meta:
        print(f"  ⤷ Child of: {frag.meta['parent_fragment']}")
    if 'child_fragments' in frag.meta:
        print(f"  ⤶ Has children: {frag.meta['child_fragments']}")

# Check entity index
print("\n" + "=" * 60)
print("ENTITY INDEX (entities appearing 2+ times)")
print("=" * 60)
for entity_text, mentions in sorted(result['entity_index'].items()):
    if len(mentions) >= 2:  # Only show entities appearing multiple times
        labels = set(m['entity_label'] for m in mentions)
        sources = set(m['source'] for m in mentions)
        print(f"\n'{entity_text}' [{', '.join(labels)}]")
        print(f"  Appears {len(mentions)} times | Sources: {', '.join(sources)}")
        for m in mentions:
            print(f"    - {m['format_type']} (frag: {m['fragment_id']}, score: {m['score']:.2f})")

# Summary statistics
print("\n" + "=" * 60)
print("SUMMARY STATISTICS")
print("=" * 60)
print(f"Total fragments: {len(result['fragments'])}")
print(f"Fragment types: {result['summary']}")
print(f"Total unique entities in index: {len(result['entity_index'])}")
print(f"Entities appearing 2+ times: {sum(1 for v in result['entity_index'].values() if len(v) >= 2)}")

# Detailed entity breakdown
all_entities = []
for frag in result['fragments']:
    all_entities.extend(frag.meta.get('entities', []))

from collections import Counter

entity_type_counts = Counter(e['label'] for e in all_entities)
print(f"\nEntity types detected:")
for label, count in entity_type_counts.most_common():
    print(f"  {label}: {count}")

# NEW: Show merged entities
if result.get('merged_entities'):
    print("\n" + "=" * 60)
    print("MERGED ENTITIES (Cross-Fragment Resolution)")
    print("=" * 60)

    for entity_id, merged in result['merged_entities'].items():
        print(f"\nEntity: {entity_id}")
        print(f"   Sources: {len(result['grouped_entities'][entity_id])} fragments")

        # Show merged data
        data = merged['merged_data']
        print(f"   Merged fields: {len(data)}")
        for key, value in list(data.items())[:10]:  # Show first 10 fields
            print(f"      {key}: {value}")

        # Show conflicts if any
        if merged['conflicts']:
            print(f"      Conflicts detected: {len(merged['conflicts'])}")
            for conflict_key, values in merged['conflicts'].items():
                print(f"      {conflict_key}:")
                for v in values:
                    print(f"         - {v['value']} (from {v['source']}, {v['format']})")

# NEW: Generate schemas
schemas = generate_schemas_from_etl_result(result, output_dir='./schemas')

print(f"\n✓ Generated {len(schemas)} schemas")
print("Check ./schemas/ directory for SQL and JSON files")

# NEW: Phase 3 - Schema Evolution
print("\n" + "=" * 60)
print("SCHEMA EVOLUTION TRACKING")
print("=" * 60)

for entity_id, schema in schemas.items():
    entity_type = schema.get('category', entity_id)

    # Register schema and detect changes
    evolution_result = schema_manager.process_new_schema(entity_type, schema)

    if evolution_result['is_initial']:
        print(f"✓ {entity_id}: Initial version (v{evolution_result['version'].version})")
    else:
        version = evolution_result['version']
        changes = evolution_result['changes']

        print(f"\n✓ {entity_id}: Version {version.version}")
        print(f"  Changes: {len(changes)}")

        if evolution_result['breaking_changes']:
            print(f"  ⚠ BREAKING CHANGES DETECTED")

        # Show changes
        for change in changes[:5]:
            symbol = "⚠" if change.breaking else "→"
            print(f"    {symbol} {change.change_type}: {change.field_name}")

        # Save migration if there are changes
        if evolution_result['migration'] and changes:
            migration_dir = f"./migrations/{entity_id}"
            os.makedirs(migration_dir, exist_ok=True)

            # Save forward migration
            with open(f"{migration_dir}/v{version.version}_forward.sql", 'w') as f:
                f.write(evolution_result['migration']['forward'])

            # Save view
            with open(f"{migration_dir}/v{version.version}_view.sql", 'w') as f:
                f.write(evolution_result['migration']['view'])

            print(f"    → Migration saved: {migration_dir}/")

print(f"\n✓ Schema registry saved to: ./schema_registry/")

# ============================================================
# ADD THIS AT THE END OF YOUR EXISTING main.py
# (After the Schema Evolution section)
# ============================================================

# NEW: Phase 4 - Query Translation Demo
# print("\n" + "=" * 60)
# print("PHASE 4: NATURAL LANGUAGE QUERY DEMO")
# print("=" * 60)
#
# try:
#     from query_translator import NaturalLanguageQuerySystem
#
#     query_system = NaturalLanguageQuerySystem('./schema_registry')
#
#     # Demo queries
#     demo_queries = [
#         "Show me all products with price less than 50",
#         "Find items with stock greater than 100",
#         "List products ordered by rating descending"
#     ]
#
#     print("\nDemo: Translating natural language to SQL\n")
#
#     for i, nl_query in enumerate(demo_queries[:2], 1):  # Show first 2
#         print(f"{i}. Query: \"{nl_query}\"")
#
#         result = query_system.query(nl_query, database_type='postgresql')
#
#         if result['success']:
#             print(f"   SQL: {result['query']}")
#             print(f"   ✓ Valid query generated\n")
#         else:
#             print(f"   ✗ Error: {result['error']}\n")
#
#     print("💡 To test more queries interactively:")
#     print("   python query_translator.py")
#
# except ImportError:
#     print("\n⚠ query_translator.py not found")
#     print("Make sure query_translator.py is in the same directory")
# except Exception as e:
#     print(f"\n⚠ Query translation failed: {e}")
#
# print("\n" + "=" * 60)
# print("ALL PHASES COMPLETE!")
# print("=" * 60)
# print("""
# Summary:
#   ✓ Phase 1: Format detection + NER extraction
#   ✓ Phase 2: Schema generation (PostgreSQL + MongoDB)
#   ✓ Phase 3: Schema evolution tracking + migrations
#   ✓ Phase 4: Natural language query translation
#
# Next Steps:
#   1. Test query translation: python query_translator.py
#   2. Test evolution: python test_evolution.py
#   3. View results: cat ./schema_registry/registry.json
# """)

