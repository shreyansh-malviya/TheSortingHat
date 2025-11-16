#!/usr/bin/env python3
"""
phase2_testing.py - Comprehensive Schema Generation & Validation Tests

Phase 2 Focus:
- Schema generation validation
- Type inference accuracy
- Primary key detection
- Index suggestions
- Multi-database compatibility
- Confidence scoring
"""

import json
import os
from typing import Dict, List, Any
from datetime import datetime
from etl_parser import parse_file
from schema_generator import generate_schemas_from_etl_result


class Phase2Tester:
    """Automated testing for Phase 2: Schema Generation"""

    def __init__(self, output_dir: str = './test_results'):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        self.test_results = {
            'timestamp': datetime.now().isoformat(),
            'phase': 'Phase 2 - Schema Generation',
            'tests': [],
            'summary': {
                'total': 0,
                'passed': 0,
                'failed': 0,
                'warnings': 0
            }
        }

    def run_all_tests(self, input_file: str):
        """Execute all Phase 2 tests"""
        print("\n" + "=" * 80)
        print("PHASE 2 TESTING: SCHEMA GENERATION & VALIDATION")
        print("=" * 80)

        # Parse input file
        print(f"\n[1/7] Parsing input file: {input_file}")
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()

        parse_result = parse_file(content, enable_ner=True)

        # Generate schemas
        print(f"[2/7] Generating schemas...")
        schemas = generate_schemas_from_etl_result(
            parse_result,
            output_dir=f'{self.output_dir}/schemas'
        )

        # Run tests
        print(f"[3/7] Running schema validation tests...")
        self.test_schema_metadata(schemas)

        print(f"[4/7] Testing type inference accuracy...")
        self.test_type_inference(schemas, parse_result)

        print(f"[5/7] Testing primary key detection...")
        self.test_primary_key_detection(schemas)

        print(f"[6/7] Testing database compatibility...")
        self.test_database_compatibility(schemas)

        print(f"[7/7] Testing field confidence scoring...")
        self.test_confidence_scoring(schemas, parse_result)

        # Generate report
        self.generate_report()

        return self.test_results

    def test_schema_metadata(self, schemas: Dict):
        """Test 2.1: Schema metadata completeness"""
        test_name = "Schema Metadata Completeness"
        print(f"\n  → {test_name}")

        passed = True
        issues = []

        for entity_id, schema in schemas.items():
            # Required fields
            required = [
                'entity_id', 'category', 'fields',
                'primary_key_candidates', 'suggested_indexes',
                'field_count', 'generated_at'
            ]

            for field in required:
                if field not in schema:
                    passed = False
                    issues.append(f"Missing '{field}' in schema: {entity_id}")

            # Validate fields structure
            if 'fields' in schema:
                for field_name, field_info in schema['fields'].items():
                    if 'type_info' not in field_info:
                        passed = False
                        issues.append(
                            f"Missing 'type_info' for field '{field_name}' in {entity_id}"
                        )
                    else:
                        type_info = field_info['type_info']
                        if 'sql_type' not in type_info or 'mongo_type' not in type_info:
                            passed = False
                            issues.append(
                                f"Missing type mappings for '{field_name}' in {entity_id}"
                            )

        self._record_test(test_name, passed, issues)
        print(f"    {'✓ PASS' if passed else '✗ FAIL'}: {len(schemas)} schemas checked")
        if issues:
            for issue in issues[:5]:  # Show first 5
                print(f"      - {issue}")

    def test_type_inference(self, schemas: Dict, parse_result: Dict):
        """Test 2.2: Type inference accuracy with NER hints"""
        test_name = "Type Inference Accuracy"
        print(f"\n  → {test_name}")

        passed = True
        issues = []
        warnings = []

        # Expected type mappings from NER
        expected_types = {
            'price': ['DECIMAL', 'MONEY'],
            'email': ['VARCHAR', 'String'],
            'date': ['DATE', 'TIMESTAMP'],
            'id': ['VARCHAR', 'String'],
            'stock': ['INTEGER', 'Int32'],
            'rating': ['DECIMAL']
        }

        correct_inferences = 0
        total_fields = 0

        for entity_id, schema in schemas.items():
            for field_name, field_info in schema.get('fields', {}).items():
                total_fields += 1
                type_info = field_info.get('type_info', {})
                sql_type = type_info.get('sql_type', '')

                # Check against expected types
                field_name_lower = field_name.lower()
                for keyword, expected_type_list in expected_types.items():
                    if keyword in field_name_lower:
                        if any(exp in sql_type for exp in expected_type_list):
                            correct_inferences += 1
                        else:
                            warnings.append(
                                f"Field '{field_name}' has type '{sql_type}', "
                                f"expected one of {expected_type_list}"
                            )
                        break

                # Validate confidence exists
                if 'confidence' not in type_info:
                    issues.append(
                        f"Missing confidence score for field '{field_name}' in {entity_id}"
                    )
                    passed = False

        accuracy = (correct_inferences / total_fields * 100) if total_fields > 0 else 0

        # Pass if accuracy > 80%
        if accuracy < 80:
            passed = False
            issues.append(f"Type inference accuracy {accuracy:.1f}% < 80% threshold")

        self._record_test(test_name, passed, issues, warnings)
        print(f"    {'✓ PASS' if passed else '✗ FAIL'}: {accuracy:.1f}% accuracy")
        print(f"      {correct_inferences}/{total_fields} fields correctly typed")

    def test_primary_key_detection(self, schemas: Dict):
        """Test 2.3: Primary key candidate detection"""
        test_name = "Primary Key Detection"
        print(f"\n  → {test_name}")

        passed = True
        issues = []

        for entity_id, schema in schemas.items():
            pk_candidates = schema.get('primary_key_candidates', [])
            fields = schema.get('fields', {})

            # Non-orphan entities should have PK candidates
            if not entity_id.startswith('orphan_'):
                if not pk_candidates:
                    # Check if there are ID-like fields that should be PKs
                    id_fields = [
                        f for f in fields.keys()
                        if 'id' in f.lower() or 'sku' in f.lower()
                    ]
                    if id_fields:
                        passed = False
                        issues.append(
                            f"Entity '{entity_id}' has ID fields {id_fields} "
                            f"but no PK candidates"
                        )

            # Validate PK candidates are actually in fields
            for pk in pk_candidates:
                if pk not in fields:
                    passed = False
                    issues.append(
                        f"PK candidate '{pk}' not found in fields for {entity_id}"
                    )

        self._record_test(test_name, passed, issues)
        print(f"    {'✓ PASS' if passed else '✗ FAIL'}")
        if issues:
            for issue in issues[:3]:
                print(f"      - {issue}")

    def test_database_compatibility(self, schemas: Dict):
        """Test 2.4: Multi-database type mapping"""
        test_name = "Database Compatibility"
        print(f"\n  → {test_name}")

        passed = True
        issues = []

        required_db_types = ['sql_type', 'mongo_type']

        for entity_id, schema in schemas.items():
            for field_name, field_info in schema.get('fields', {}).items():
                type_info = field_info.get('type_info', {})

                for db_type in required_db_types:
                    if db_type not in type_info:
                        passed = False
                        issues.append(
                            f"Missing '{db_type}' for field '{field_name}' "
                            f"in entity '{entity_id}'"
                        )
                    elif not type_info[db_type]:
                        passed = False
                        issues.append(
                            f"Empty '{db_type}' for field '{field_name}' "
                            f"in entity '{entity_id}'"
                        )

        # Check if SQL/MongoDB exports exist
        schema_dir = f'{self.output_dir}/schemas'
        sql_files = [f for f in os.listdir(schema_dir) if f.endswith('.sql')]
        mongo_files = [f for f in os.listdir(schema_dir) if f.endswith('.json')]

        if not sql_files:
            passed = False
            issues.append("No PostgreSQL schema files generated")

        if not mongo_files:
            passed = False
            issues.append("No MongoDB schema files generated")

        self._record_test(test_name, passed, issues)
        print(f"    {'✓ PASS' if passed else '✗ FAIL'}")
        print(f"      PostgreSQL: {len(sql_files)} file(s)")
        print(f"      MongoDB: {len(mongo_files)} file(s)")

    def test_confidence_scoring(self, schemas: Dict, parse_result: Dict):
        """Test 2.5: Confidence scoring presence and validity"""
        test_name = "Confidence Scoring"
        print(f"\n  → {test_name}")

        passed = True
        issues = []
        warnings = []

        low_confidence_threshold = 0.5
        low_confidence_count = 0
        total_fields = 0

        for entity_id, schema in schemas.items():
            for field_name, field_info in schema.get('fields', {}).items():
                total_fields += 1
                type_info = field_info.get('type_info', {})
                confidence = type_info.get('confidence')

                if confidence is None:
                    passed = False
                    issues.append(
                        f"No confidence score for '{field_name}' in {entity_id}"
                    )
                elif not (0.0 <= confidence <= 1.0):
                    passed = False
                    issues.append(
                        f"Invalid confidence {confidence} for '{field_name}' in {entity_id}"
                    )
                elif confidence < low_confidence_threshold:
                    low_confidence_count += 1
                    warnings.append(
                        f"Low confidence ({confidence:.2f}) for '{field_name}' in {entity_id}"
                    )

        # Warn if >30% of fields have low confidence
        if total_fields > 0:
            low_conf_ratio = low_confidence_count / total_fields
            if low_conf_ratio > 0.3:
                warnings.append(
                    f"{low_conf_ratio * 100:.1f}% of fields have low confidence (<{low_confidence_threshold})"
                )

        self._record_test(test_name, passed, issues, warnings)
        print(f"    {'✓ PASS' if passed else '✗ FAIL'}")
        print(f"      {total_fields - low_confidence_count}/{total_fields} fields with high confidence")

    def _record_test(self, name: str, passed: bool, issues: List[str],
                     warnings: List[str] = None):
        """Record test result"""
        result = {
            'name': name,
            'passed': passed,
            'issues': issues,
            'warnings': warnings or []
        }

        self.test_results['tests'].append(result)
        self.test_results['summary']['total'] += 1

        if passed:
            self.test_results['summary']['passed'] += 1
        else:
            self.test_results['summary']['failed'] += 1

        if warnings:
            self.test_results['summary']['warnings'] += len(warnings)

    def generate_report(self):
        """Generate test report"""
        report_path = f'{self.output_dir}/phase2_report.json'

        with open(report_path, 'w') as f:
            json.dump(self.test_results, f, indent=2)

        # Generate human-readable report
        txt_path = f'{self.output_dir}/phase2_report.txt'
        with open(txt_path, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("PHASE 2 TEST REPORT: SCHEMA GENERATION\n")
            f.write("=" * 80 + "\n\n")

            summary = self.test_results['summary']
            f.write(f"Timestamp: {self.test_results['timestamp']}\n")
            f.write(f"Total Tests: {summary['total']}\n")
            f.write(f"Passed: {summary['passed']}\n")
            f.write(f"Failed: {summary['failed']}\n")
            f.write(f"Warnings: {summary['warnings']}\n\n")

            # Overall status
            if summary['failed'] == 0:
                f.write("✓ OVERALL STATUS: PASS\n\n")
            else:
                f.write("✗ OVERALL STATUS: FAIL\n\n")

            # Detailed results
            f.write("-" * 80 + "\n")
            f.write("DETAILED TEST RESULTS\n")
            f.write("-" * 80 + "\n\n")

            for test in self.test_results['tests']:
                status = "✓ PASS" if test['passed'] else "✗ FAIL"
                f.write(f"{status}: {test['name']}\n")

                if test['issues']:
                    f.write("  Issues:\n")
                    for issue in test['issues']:
                        f.write(f"    - {issue}\n")

                if test['warnings']:
                    f.write("  Warnings:\n")
                    for warning in test['warnings']:
                        f.write(f"    - {warning}\n")

                f.write("\n")

        print(f"\n{'=' * 80}")
        print("TEST SUMMARY")
        print(f"{'=' * 80}")
        print(f"Total: {summary['total']}")
        print(f"Passed: {summary['passed']} ✓")
        print(f"Failed: {summary['failed']} ✗")
        print(f"Warnings: {summary['warnings']} ⚠")

        if summary['failed'] == 0:
            print(f"\n✓ ALL TESTS PASSED")
        else:
            print(f"\n✗ {summary['failed']} TEST(S) FAILED")

        print(f"\nReports saved to:")
        print(f"  - {report_path}")
        print(f"  - {txt_path}")


def main():
    """Run Phase 2 tests"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python phase2_testing.py <input_file>")
        print("\nExample: python phase2_testing.py input.txt")
        sys.exit(1)

    input_file = sys.argv[1]

    if not os.path.exists(input_file):
        print(f"ERROR: File not found: {input_file}")
        sys.exit(1)

    tester = Phase2Tester(output_dir='./test_results_phase2')
    results = tester.run_all_tests(input_file)

    # Exit with appropriate code
    if results['summary']['failed'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()