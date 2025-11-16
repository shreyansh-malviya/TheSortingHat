#!/usr/bin/env python3
"""
test_evolution.py - Simple script to test schema evolution

Creates 3 test files with progressive changes and processes them
"""

import os
import json
import subprocess
import time

# Create test directory
os.makedirs('./evolution_test', exist_ok=True)

# ============================================================
# TEST FILE 1: Base version
# ============================================================
test1 = '''--- METADATA
source: https://example.com/product/widget-a
scraper: v1

--- JSON
{
  "id": "prod-1001",
  "title": "Widget A",
  "price_usd": "9.99",
  "stock": 120
}

--- CSV
ProductID,Name,Stock
prod-1001,Widget A,120
prod-1002,Widget B,50
'''

with open('./evolution_test/test1_base.txt', 'w') as f:
    f.write(test1)

# ============================================================
# TEST FILE 2: Add new field + rename
# ============================================================
test2 = '''--- METADATA
source: https://example.com/product/widget-a
scraper: v2
publisher: TechCo

--- JSON
{
  "id": "prod-1001",
  "title": "Widget A",
  "price": 9.99,
  "currency": "USD",
  "stock": 120,
  "rating": 4.5
}

--- CSV
ProductID,Name,Stock,Rating
prod-1001,Widget A,120,4.5
prod-1002,Widget B,50,3.8
prod-1003,Widget C,30,4.2
'''

with open('./evolution_test/test2_evolved.txt', 'w') as f:
    f.write(test2)

# ============================================================
# TEST FILE 3: Type change + nested structure
# ============================================================
test3 = '''--- METADATA
source: https://example.com/product/widget-a
scraper: v3
publisher: TechCo

--- JSON
{
  "id": "prod-1001",
  "title": "Widget A",
  "pricing": {
    "amount": 9.99,
    "currency": "USD"
  },
  "stock": 120,
  "rating": 4.5,
  "views": 1024
}

--- CSV
ProductID,Name,Stock,Rating,Views
prod-1001,Widget A,120,4.5,1024
prod-1002,Widget B,50,3.8,532
prod-1003,Widget C,30,4.2,891
'''

with open('./evolution_test/test3_nested.txt', 'w') as f:
    f.write(test3)

print("=" * 60)
print("SCHEMA EVOLUTION TEST")
print("=" * 60)

# Clean old registry
if os.path.exists('./schema_registry'):
    import shutil

    shutil.rmtree('./schema_registry')
    print("✓ Cleaned old registry\n")

# Process each file
files = [
    ('test1_base.txt', 'Base version'),
    ('test2_evolved.txt', 'Field rename + additions'),
    ('test3_nested.txt', 'Nested structure + type change')
]

for filename, description in files:
    print(f"\n{'=' * 60}")
    print(f"Processing: {filename}")
    print(f"Changes: {description}")
    print(f"{'=' * 60}\n")

    # Run main.py
    result = subprocess.run(
        ['python', 'main.py'],
        input=open(f'./evolution_test/{filename}').read(),
        capture_output=True,
        text=True
    )

    # Show only evolution section
    output_lines = result.stdout.split('\n')
    in_evolution = False
    for line in output_lines:
        if 'SCHEMA EVOLUTION' in line:
            in_evolution = True
        if in_evolution:
            print(line)
        if in_evolution and 'Schema registry saved' in line:
            break

    time.sleep(1)  # Brief pause

print("\n" + "=" * 60)
print("CHECKING REGISTRY")
print("=" * 60)

# Load and display registry
if os.path.exists('./schema_registry/registry.json'):
    with open('./schema_registry/registry.json', 'r') as f:
        registry = json.load(f)

    for entity_type, versions in registry.items():
        print(f"\n📦 Entity Type: {entity_type}")
        print(f"   Total versions: {len(versions)}")

        for v in versions:
            print(f"\n   Version {v['version']}: {v['schema_id']}")
            print(f"   Created: {v['created_at']}")

            if v['changes']:
                print(f"   Changes ({len(v['changes'])}):")
                for change in v['changes']:
                    symbol = "⚠" if change['breaking'] else "→"
                    print(f"      {symbol} {change['change_type']}: {change['field_name']}")
            else:
                print(f"   (Initial version - no changes)")

print("\n" + "=" * 60)
print("CHECKING MIGRATIONS")
print("=" * 60)

if os.path.exists('./migrations'):
    for entity_dir in os.listdir('./migrations'):
        entity_path = os.path.join('./migrations', entity_dir)
        if os.path.isdir(entity_path):
            print(f"\n📁 {entity_dir}/")
            for file in sorted(os.listdir(entity_path)):
                filepath = os.path.join(entity_path, file)
                size = os.path.getsize(filepath)
                print(f"   - {file} ({size} bytes)")

print("\n" + "=" * 60)
print("TEST COMPLETE!")
print("=" * 60)
print("\nTo inspect in detail:")
print("  cat ./schema_registry/registry.json | python -m json.tool")
print("  cat ./migrations/*/v*_forward.sql")