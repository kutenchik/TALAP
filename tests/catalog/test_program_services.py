import csv
from pathlib import Path
import tempfile

from django.test import TestCase

from admission.catalog.models import DataIssue, Institution, ProgramOffering, SeedInstitution, SourceDocument
from admission.catalog.services import export_programs, import_bachelors_programs


COMPLETION_HEADERS = ["UNITID", "CIPCODE", "MAJORNUM", "AWLEVEL", "CTOTALT"]
CIP_HEADERS = ["CIPCode", "CIPTitle"]


class ProgramImportTests(TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.completions_path = self.root / "C2024_A.csv"
        self.cip_titles_path = self.root / "CIPCode2020.csv"
        self.source = SourceDocument.objects.create(
            url="https://nces.ed.gov/ipeds/datacenter/data/HD2024.zip",
            publisher="IPEDS",
            source_type="institutional_characteristics",
            data_year="2024",
            retrieved_at="2024-01-01T00:00:00Z",
            content_hash="a" * 64,
        )
        for order in range(1, 101):
            institution = Institution.objects.create(
                ipeds_unitid=100000 + order,
                name=f"Example University {order}",
                state="CA",
                city="Example City",
                country="US",
                ownership="public",
                official_website="https://example.edu",
                operating_status="active",
                bachelors_granting=True,
                bachelors_granting_evidence="HLOFFER=9",
                source=self.source,
                source_locator=f"HD2024.csv UNITID {100000 + order}",
            )
            SeedInstitution.objects.create(
                seed_order=order,
                name=institution.name,
                state="CA",
                expected_ownership="public",
                status=SeedInstitution.Status.RESOLVED,
                institution=institution,
            )
        with self.cip_titles_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CIP_HEADERS)
            writer.writeheader()
            writer.writerows([
                {"CIPCode": '="11.0701"', "CIPTitle": "Computer Science."},
                {"CIPCode": '="11.0702"', "CIPTitle": "Computer Software Engineering."},
            ])

    def write_completions(self, rows: list[dict[str, str]]) -> None:
        with self.completions_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COMPLETION_HEADERS)
            writer.writeheader()
            writer.writerows(rows)

    def import_programs(self) -> dict[str, int]:
        return import_bachelors_programs(
            self.completions_path,
            self.cip_titles_path,
            source_url="https://nces.ed.gov/ipeds/datacenter/data/C2024_A.zip",
            data_year="2024",
        )

    def test_bachelors_records_import_as_aggregated_cip_coverage(self) -> None:
        self.write_completions([
            {"UNITID": "100001", "CIPCODE": "11.0701", "MAJORNUM": "1", "AWLEVEL": "5", "CTOTALT": "3"},
            {"UNITID": "100001", "CIPCODE": "11.0701", "MAJORNUM": "2", "AWLEVEL": "5", "CTOTALT": "4"},
        ])

        result = self.import_programs()
        program = ProgramOffering.objects.get()

        self.assertEqual(result["program_records"], 1)
        self.assertEqual(program.cip_code, "11.0701")
        self.assertEqual(program.cip_title, "Computer Science.")
        self.assertEqual(program.credential_level, "bachelors_degree")
        self.assertEqual(program.award_level, 5)
        self.assertEqual(program.completion_count, 7)
        self.assertEqual(program.program_name, "")

    def test_non_bachelors_award_levels_are_excluded_from_coverage(self) -> None:
        self.write_completions([
            {"UNITID": "100001", "CIPCODE": "11.0701", "MAJORNUM": "1", "AWLEVEL": "3", "CTOTALT": "9"},
            {"UNITID": "100001", "CIPCODE": "11.0701", "MAJORNUM": "2", "AWLEVEL": "7", "CTOTALT": "9"},
        ])

        self.import_programs()

        self.assertEqual(ProgramOffering.objects.count(), 0)
        self.assertTrue(
            DataIssue.objects.filter(
                seed_entry__seed_order=1,
                issue_type=DataIssue.IssueType.ZERO_BACHELOR_PROGRAMS,
            ).exists()
        )

    def test_official_summary_rows_are_ignored_without_invalid_issue(self) -> None:
        self.write_completions([
            {"UNITID": "100001", "CIPCODE": "11.0701", "MAJORNUM": "1", "AWLEVEL": "5", "CTOTALT": "3"},
            {"UNITID": "100001", "CIPCODE": "99", "MAJORNUM": "1", "AWLEVEL": "5", "CTOTALT": "3"},
            {"UNITID": "100001", "CIPCODE": "99.0000", "MAJORNUM": "2", "AWLEVEL": "5", "CTOTALT": "3"},
        ])

        result = self.import_programs()

        self.assertEqual(result["summary_rows_ignored"], 2)
        self.assertEqual(ProgramOffering.objects.count(), 1)
        self.assertFalse(
            DataIssue.objects.filter(
                seed_entry__seed_order=1,
                issue_type=DataIssue.IssueType.INVALID_PROGRAM_RECORD,
            ).exists()
        )

    def test_duplicate_reimport_is_idempotent(self) -> None:
        self.write_completions([
            {"UNITID": "100001", "CIPCODE": "11.0701", "MAJORNUM": "1", "AWLEVEL": "5", "CTOTALT": "3"},
            {"UNITID": "100001", "CIPCODE": "99", "MAJORNUM": "2", "AWLEVEL": "5", "CTOTALT": "3"},
        ])

        first = self.import_programs()
        second = self.import_programs()

        self.assertEqual(first["duplicate_records"], 0)
        self.assertEqual(second["duplicate_records"], 0)
        self.assertEqual(first["summary_rows_ignored"], 1)
        self.assertEqual(second["summary_rows_ignored"], 1)
        self.assertEqual(ProgramOffering.objects.count(), 1)
        self.assertEqual(ProgramOffering.objects.get().completion_count, 3)

    def test_invalid_or_unknown_cip_and_award_values_create_an_issue(self) -> None:
        self.write_completions([
            {"UNITID": "100001", "CIPCODE": "99.9999", "MAJORNUM": "1", "AWLEVEL": "5", "CTOTALT": "2"},
            {"UNITID": "100001", "CIPCODE": "11.0701", "MAJORNUM": "2", "AWLEVEL": "99", "CTOTALT": "2"},
            {"UNITID": "100001", "CIPCODE": "11.0701", "MAJORNUM": "3", "AWLEVEL": "not-a-number", "CTOTALT": "2"},
            {"UNITID": "100001", "CIPCODE": "11.0702", "MAJORNUM": "4", "AWLEVEL": "5", "CTOTALT": "not-a-number"},
        ])

        result = self.import_programs()
        issue = DataIssue.objects.get(
            seed_entry__seed_order=1,
            issue_type=DataIssue.IssueType.INVALID_PROGRAM_RECORD,
        )

        self.assertEqual(result["invalid_records"], 4)
        self.assertIn("unknown AWLEVEL=99", issue.detail)
        self.assertIn("missing or non-numeric AWLEVEL", issue.detail)
        self.assertIn("invalid bachelor's row", issue.detail)
        self.assertEqual(ProgramOffering.objects.count(), 0)

    def test_zero_program_institution_is_explicitly_reported(self) -> None:
        self.write_completions([
            {"UNITID": "100001", "CIPCODE": "11.0701", "MAJORNUM": "1", "AWLEVEL": "5", "CTOTALT": "1"},
        ])

        result = self.import_programs()

        self.assertEqual(result["institutions_processed"], 100)
        self.assertEqual(result["institutions_with_programs"], 1)
        self.assertEqual(result["institutions_zero_programs"], 99)
        self.assertTrue(
            DataIssue.objects.filter(
                seed_entry__seed_order=2,
                issue_type=DataIssue.IssueType.ZERO_BACHELOR_PROGRAMS,
            ).exists()
        )

    def test_program_export_is_deterministic(self) -> None:
        self.write_completions([
            {"UNITID": "100001", "CIPCODE": "11.0702", "MAJORNUM": "1", "AWLEVEL": "5", "CTOTALT": "1"},
            {"UNITID": "100001", "CIPCODE": "11.0701", "MAJORNUM": "1", "AWLEVEL": "5", "CTOTALT": "2"},
        ])
        self.import_programs()
        first = self.root / "programs-one.jsonl"
        second = self.root / "programs-two.jsonl"

        self.assertEqual(export_programs(first), 2)
        self.assertEqual(export_programs(second), 2)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertIn('"cip_code":"11.0701"', first.read_text(encoding="utf-8"))
