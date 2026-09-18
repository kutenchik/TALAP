import csv
from pathlib import Path

from django.test import TestCase

from admission.catalog.models import DataIssue, Institution, InstitutionAlias, SeedInstitution, SourceDocument
from admission.catalog.services import export_institutions, import_ipeds


HEADERS = ["UNITID", "INSTNM", "CITY", "STABBR", "CONTROL", "WEBADDR", "CYACTIVE", "UGOFFER", "HLOFFER", "DEGGRANT"]


class ImportExportTests(TestCase):
    def write_ipeds_csv(self, path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows([
                {"UNITID": "100001", "INSTNM": "Example University", "CITY": "Example City", "STABBR": "CA", "CONTROL": "1", "WEBADDR": "example.edu", "CYACTIVE": "1", "UGOFFER": "1", "HLOFFER": "9", "DEGGRANT": "1"},
                {"UNITID": "100002", "INSTNM": "Mismatch University", "CITY": "Other City", "STABBR": "NY", "CONTROL": "1", "WEBADDR": "", "CYACTIVE": "1", "UGOFFER": "1", "HLOFFER": "9", "DEGGRANT": "1"},
            ])

    def test_import_is_idempotent_and_state_mismatch_is_explicit(self) -> None:
        SeedInstitution.objects.create(seed_order=1, name="Example University", state="CA", expected_ownership="public")
        SeedInstitution.objects.create(seed_order=2, name="Mismatch University", state="CA", expected_ownership="public")
        path = Path(self._testMethodName + ".csv")
        self.addCleanup(path.unlink, missing_ok=True)
        self.write_ipeds_csv(path)

        result = import_ipeds(path, source_url="https://nces.ed.gov/example.csv", data_year="2024")
        import_ipeds(path, source_url="https://nces.ed.gov/example.csv", data_year="2024")

        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["unresolved"], 1)
        self.assertEqual(Institution.objects.count(), 1)
        self.assertEqual(InstitutionAlias.objects.count(), 1)
        self.assertEqual(SourceDocument.objects.count(), 1)
        self.assertEqual(SeedInstitution.objects.get(seed_order=1).institution.ipeds_unitid, 100001)
        self.assertEqual(SeedInstitution.objects.get(seed_order=2).status, SeedInstitution.Status.UNRESOLVED)
        self.assertTrue(DataIssue.objects.filter(issue_type=DataIssue.IssueType.STATE_MISMATCH).exists())

    def test_export_is_stable_and_contains_provenance(self) -> None:
        source = SourceDocument.objects.create(
            url="https://nces.ed.gov/example.csv", publisher="IPEDS", source_type="institutional_characteristics",
            data_year="2024", retrieved_at="2024-01-01T00:00:00Z", content_hash="a" * 64,
        )
        institution = Institution.objects.create(
            ipeds_unitid=100001, name="Example University", state="CA", city="Example City", country="US",
            ownership="public", official_website="https://example.edu", operating_status="active", bachelors_granting=True,
            bachelors_granting_evidence="UGOFFER=1; HLOFFER=9; DEGGRANT=1", source=source, source_locator="HD2024.csv UNITID 100001",
        )
        InstitutionAlias.objects.create(institution=institution, alias="Example U", alias_type="seed_name")
        first = Path(self._testMethodName + "-one.jsonl")
        second = Path(self._testMethodName + "-two.jsonl")
        self.addCleanup(first.unlink, missing_ok=True)
        self.addCleanup(second.unlink, missing_ok=True)

        assert export_institutions(first) == 1
        assert export_institutions(second) == 1

        self.assertEqual(first.read_bytes(), second.read_bytes())
        contents = first.read_text(encoding="utf-8")
        self.assertIn('"ipeds_unitid":100001', contents)
        self.assertIn('"content_hash":"' + "a" * 64 + '"', contents)
