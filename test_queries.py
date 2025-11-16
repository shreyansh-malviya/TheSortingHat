#!/usr/bin/env python3
"""
test_queries.py - Test natural language query translation
"""

from query_translator import NaturalLanguageQuerySystem

# Initialize system
system = NaturalLanguageQuerySystem()

print("=" * 60)
print("TESTING QUERY TRANSLATION")
print("=" * 60)

if not system.schemas:
    print("\n⚠ No schemas found!")
    print("Run this first: python main.py")
    exit(1)

print(f"\nLoaded schemas: {', '.join(system.schemas.keys())}\n")

# Test queries
test_queries = [
    {
        'query': 'Show me all products with price less than 50',
        'entity': None  # Auto-detect
    },
    {
        'query': 'Find items with stock greater than 100',
        'entity': None
    },
    {
        'query': 'List all products ordered by rating descending',
        'entity': None
    },
    {
        'query': 'Count how many products have views above 1000',
        'entity': None
    },
    {
        'query': 'Show products where title contains "Widget"',
        'entity': None
    }
]

for i, test in enumerate(test_queries, 1):
    print(f"\n{'=' * 60}")
    print(f"Test {i}/{len(test_queries)}")
    print(f"{'=' * 60}")
    print(f"Natural Language: {test['query']}")

    result = system.query(
        test['query'],
        entity_type=test['entity'],
        database_type='postgresql'
    )

    if result['success']:
        print(f"\n✓ SUCCESS")
        print(f"\nGenerated SQL:")
        print(f"  {result['query']}")
        print(f"\nExplanation:")
        print(f"  {result['explanation']}")

        if result.get('results'):
            print(f"\nSample Results:")
            for row in result['results'][:2]:
                print(f"  {row}")
    else:
        print(f"\n✗ FAILED")
        print(f"Error: {result['error']}")

print("\n" + "=" * 60)
print("TESTS COMPLETE")
print("=" * 60)
print("\nTo run interactively:")
print("  python query_translator.py")