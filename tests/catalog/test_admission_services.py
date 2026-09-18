import csv
from decimal import Decimal
from pathlib import Path
import tempfile

from django.test import TestCase

from admission.catalog.models import AdmissionSnapshot, DataIssue, Institution, SeedInstitution, SourceDocument
from admission.catalog.services import export_admissions, import_admissions


FIELDS = [
    "APPLCN", "ADMSSN", "ENRLT", "SATNUM", "SATPCT", "ACTNUM", "ACTPCT",
    "SATVR25", "SATVR75", "SATMT25", "SATMT75", "ACTCM25", "ACTCM75",
]
HEADERS = ["UNITID", *[item for field in FIELDS for item in (f"X{field}", field)]]


class AdmissionsImportTests(TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.admissions_path = self.root / "ADM2024.csv"
        self.dictionary_path = self.root / "ADM2024_Dict.xlsx"
        self.dictionary_path.write_text("official dictionary fixture", encoding="utf-8")
        source = SourceDocument.objects.create(
            url="https://nces.ed.gov/ipeds/complete-data-files/HD2024.zip",
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
                bachelors_granting_evidence="C2024_A evidence",
                source=source,
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

    def row(self, unitid: int = 100001, **values: str) -> dict[str, str]:
        row = {"UNITID": str(unitid)}
        for field in FIELDS:
            row[f"X{field}"] = "A"
            row[field] = ""
        for field, value in values.items():
            row[f"X{field}"] = "R"
            row[field] = value
        return row

    def write_admissions(self, rows: list[dict[str, str]]) -> None:
        with self.admissions_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(rows)

    def import_rows(self) -> dict[str, int]:
        return import_admissions(
            self.admissions_path,
            self.dictionary_path,
            source_url="https://nces.ed.gov/ipeds/complete-data-files/ADM2024.zip",
            dictionary_url="https://nces.ed.gov/ipeds/complete-data-files/ADM2024_Dict.zip",
            data_year="2024",
        )

    def snapshot(self, unitid: int = 100001) -> AdmissionSnapshot:
        return AdmissionSnapshot.objects.get(institution__ipeds_unitid=unitid)

    def test_valid_counts_rate_and_sat_act_percentiles_import(self) -> None:
        self.write_admissions([self.row(
            APPLCN="100", ADMSSN="50", ENRLT="25", SATNUM="30", SATPCT="60", ACTNUM="20", ACTPCT="40",
            SATVR25="500", SATVR75="700", SATMT25="510", SATMT75="710", ACTCM25="20", ACTCM75="30",
        )])

        self.import_rows()
        snapshot = self.snapshot()

        self.assertEqual((snapshot.applicant_count, snapshot.admitted_count, snapshot.enrolled_count), (100, 50, 25))
        self.assertEqual(snapshot.admission_rate, Decimal("0.500000"))
        self.assertEqual((snapshot.sat_ebrw_25, snapshot.sat_ebrw_75, snapshot.sat_math_25, snapshot.sat_math_75), (500, 700, 510, 710))
        self.assertEqual((snapshot.act_composite_25, snapshot.act_composite_75), (20, 30))
        self.assertEqual((snapshot.sat_submission_count, snapshot.sat_submission_percent), (30, 60))
        self.assertEqual((snapshot.act_submission_count, snapshot.act_submission_percent), (20, 40))
        self.assertEqual(snapshot.source_flags["applicant_count"], "R")

    def test_missing_test_data_remains_not_applicable_without_policy_claim(self) -> None:
        self.write_admissions([self.row(APPLCN="100", ADMSSN="50", ENRLT="25")])

        self.import_rows()
        snapshot = self.snapshot()

        self.assertIsNone(snapshot.sat_ebrw_25)
        self.assertIsNone(snapshot.act_composite_25)
        self.assertEqual(snapshot.sat_data_status, "not_applicable")
        self.assertEqual(snapshot.act_data_status, "not_applicable")
        self.assertEqual(snapshot.test_data_status, "not_applicable")
        self.assertNotIn("optional", snapshot.evidence.casefold())
        self.assertFalse(DataIssue.objects.filter(seed_entry__seed_order=1, issue_type=DataIssue.IssueType.INVALID_ADMISSIONS_RECORD).exists())

    def test_analyst_corrected_reported_value_preserves_c_flag(self) -> None:
        row = self.row(APPLCN="100")
        row["XAPPLCN"] = "C"
        self.write_admissions([row])

        self.import_rows()
        snapshot = self.snapshot()

        self.assertEqual(snapshot.applicant_count, 100)
        self.assertEqual(snapshot.admissions_data_status, "reported")
        self.assertEqual(snapshot.source_flags["applicant_count"], "C")

    def test_nearest_neighbor_imputation_is_preserved(self) -> None:
        row = self.row(APPLCN="100")
        row["XAPPLCN"] = "N"
        self.write_admissions([row])

        self.import_rows()
        snapshot = self.snapshot()

        self.assertEqual(snapshot.applicant_count, 100)
        self.assertEqual(snapshot.admissions_data_status, "imputed")
        self.assertEqual(snapshot.source_flags["applicant_count"], "N")

    def test_carry_forward_and_group_median_imputations_are_preserved(self) -> None:
        row = self.row(APPLCN="100", ADMSSN="50", ENRLT="25")
        row["XAPPLCN"] = "P"
        row["XADMSSN"] = "L"
        row["XENRLT"] = "P"
        self.write_admissions([row])

        self.import_rows()
        snapshot = self.snapshot()

        self.assertEqual((snapshot.applicant_count, snapshot.admitted_count, snapshot.enrolled_count), (100, 50, 25))
        self.assertEqual(snapshot.admissions_data_status, "imputed")
        self.assertEqual(snapshot.source_flags["applicant_count"], "P")
        self.assertEqual(snapshot.source_flags["admitted_count"], "L")

    def test_implied_zero_is_numeric_for_count_and_percentage_fields(self) -> None:
        row = self.row(APPLCN="0", ADMSSN="0", ENRLT="0", SATNUM="0", SATPCT="0")
        for field in ("APPLCN", "ADMSSN", "ENRLT", "SATNUM", "SATPCT"):
            row[f"X{field}"] = "Z"
        self.write_admissions([row])

        self.import_rows()
        snapshot = self.snapshot()

        self.assertEqual((snapshot.applicant_count, snapshot.admitted_count, snapshot.enrolled_count), (0, 0, 0))
        self.assertEqual((snapshot.sat_submission_count, snapshot.sat_submission_percent), (0, 0))
        self.assertEqual(snapshot.admissions_data_status, "implied_zero")
        self.assertEqual(snapshot.sat_data_status, "implied_zero")
        self.assertEqual(snapshot.source_flags["sat_submission_percent"], "Z")

    def test_implied_zero_never_becomes_a_test_score(self) -> None:
        row = self.row(SATVR25="0")
        row["XSATVR25"] = "Z"
        self.write_admissions([row])

        self.import_rows()
        snapshot = self.snapshot()

        self.assertIsNone(snapshot.sat_ebrw_25)
        self.assertEqual(snapshot.source_flags["sat_ebrw_25"], "Z")
        self.assertFalse(DataIssue.objects.filter(seed_entry__seed_order=1, issue_type=DataIssue.IssueType.INVALID_ADMISSIONS_RECORD).exists())

    def test_documented_missing_unknown_and_unusable_flags_are_not_issues(self) -> None:
        row = self.row()
        row["XAPPLCN"] = "B"
        row["XADMSSN"] = "D"
        row["XENRLT"] = "H"
        self.write_admissions([row])

        self.import_rows()
        snapshot = self.snapshot()

        self.assertIsNone(snapshot.applicant_count)
        self.assertEqual(snapshot.source_flags["applicant_count"], "B")
        self.assertEqual(snapshot.source_flags["admitted_count"], "D")
        self.assertEqual(snapshot.source_flags["enrolled_count"], "H")
        self.assertFalse(DataIssue.objects.filter(seed_entry__seed_order=1, issue_type=DataIssue.IssueType.INVALID_ADMISSIONS_RECORD).exists())

    def test_undocumented_flag_is_reported_as_invalid_not_as_reported_data(self) -> None:
        row = self.row(APPLCN="100")
        row["XAPPLCN"] = "Q"
        self.write_admissions([row])

        self.import_rows()

        self.assertFalse(AdmissionSnapshot.objects.filter(institution__ipeds_unitid=100001).exists())
        self.assertTrue(DataIssue.objects.filter(seed_entry__seed_order=1, issue_type=DataIssue.IssueType.INVALID_ADMISSIONS_RECORD).exists())

    def test_invalid_sat_range_is_reported(self) -> None:
        self.write_admissions([self.row(APPLCN="100", ADMSSN="50", ENRLT="25", SATVR25="900", SATVR75="700")])

        self.import_rows()

        self.assertFalse(AdmissionSnapshot.objects.filter(institution__ipeds_unitid=100001).exists())
        self.assertTrue(DataIssue.objects.filter(seed_entry__seed_order=1, issue_type=DataIssue.IssueType.INVALID_ADMISSIONS_RECORD).exists())

    def test_invalid_act_range_is_reported(self) -> None:
        self.write_admissions([self.row(APPLCN="100", ADMSSN="50", ENRLT="25", ACTCM25="0", ACTCM75="30")])

        self.import_rows()

        self.assertTrue(DataIssue.objects.filter(seed_entry__seed_order=1, issue_type=DataIssue.IssueType.INVALID_ADMISSIONS_RECORD).exists())

    def test_percentile_ordering_is_reported(self) -> None:
        self.write_admissions([self.row(APPLCN="100", ADMSSN="50", ENRLT="25", SATVR25="700", SATVR75="600")])

        self.import_rows()

        self.assertTrue(DataIssue.objects.filter(seed_entry__seed_order=1, issue_type=DataIssue.IssueType.INVALID_ADMISSIONS_RECORD).exists())

    def test_admitted_cannot_exceed_applicants(self) -> None:
        self.write_admissions([self.row(APPLCN="100", ADMSSN="101", ENRLT="25")])

        self.import_rows()

        self.assertTrue(DataIssue.objects.filter(seed_entry__seed_order=1, issue_type=DataIssue.IssueType.INVALID_ADMISSIONS_RECORD).exists())

    def test_malformed_numeric_value_is_reported(self) -> None:
        self.write_admissions([self.row(APPLCN="not-a-number", ADMSSN="50", ENRLT="25")])

        self.import_rows()

        self.assertFalse(AdmissionSnapshot.objects.filter(institution__ipeds_unitid=100001).exists())
        self.assertTrue(DataIssue.objects.filter(seed_entry__seed_order=1, issue_type=DataIssue.IssueType.INVALID_ADMISSIONS_RECORD).exists())

    def test_duplicate_reimport_is_idempotent(self) -> None:
        self.write_admissions([self.row(APPLCN="100", ADMSSN="50", ENRLT="25", SATVR25="500", SATVR75="700")])

        first = self.import_rows()
        second = self.import_rows()

        self.assertEqual(first["duplicate_records"], 0)
        self.assertEqual(second["duplicate_records"], 0)
        self.assertEqual(AdmissionSnapshot.objects.count(), 100)
        self.assertEqual(self.snapshot().admission_rate, Decimal("0.500000"))

    def test_admission_export_is_deterministic(self) -> None:
        self.write_admissions([self.row(APPLCN="100", ADMSSN="50", ENRLT="25", SATVR25="500", SATVR75="700")])
        self.import_rows()
        first = self.root / "admissions-one.jsonl"
        second = self.root / "admissions-two.jsonl"

        self.assertEqual(export_admissions(first), 100)
        self.assertEqual(export_admissions(second), 100)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        contents = first.read_text(encoding="utf-8")
        self.assertIn('"sat_ebrw_25":500', contents)
        self.assertNotIn("test_optional", contents)
