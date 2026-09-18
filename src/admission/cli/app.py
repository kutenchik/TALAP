"""The focused TASK-001 command-line surface."""

from pathlib import Path
import os

import typer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from admission.catalog.services import (
    admissions_status,
    discover_official_sources,
    export_admissions,
    export_english_requirements,
    export_institutions,
    export_programs,
    export_sources,
    enrich_english_requirements,
    fetch_official_sources,
    import_bachelors_programs,
    import_admissions,
    import_ipeds,
    program_status,
    seed_manifest,
    status_counts,
    status_rows,
)
from admission.catalog.source_batches import export_source_gaps, resolve_source_selection
from admission.applicants.diagnostics import diagnose_profile
from admission.applicants.models import ApplicantProfile
from admission.applicants.services import export_profile, import_profile, load_profile
from admission.assessment.services import assess_candidates
from admission.recommendation.services import recommend_for_profile
from admission.roadmap.services import build_roadmap_for_profile
from admission.journey.services import build_admission_journey
from admission.llm.alem import AlemGemmaClient, LLMUnavailable, UnavailableEnglishClient

app = typer.Typer(help="Personal Admission Journey CLI")
data_app = typer.Typer(help="Catalog data commands")
profile_app = typer.Typer(help="Applicant profile commands")
assess_app = typer.Typer(help="Applicant and institution assessment commands")
app.add_typer(data_app, name="data")
app.add_typer(profile_app, name="profile")
app.add_typer(assess_app, name="assess")
recommend_app = typer.Typer(help="Evidence-based university review priorities")
app.add_typer(recommend_app, name="recommend")
roadmap_app = typer.Typer(help="Deterministic applicant next-action roadmaps")
app.add_typer(roadmap_app, name="roadmap")
journey_app = typer.Typer(help="Complete deterministic admission journey")
app.add_typer(journey_app, name="journey")


@journey_app.command("run")
def run_journey_command(
    profile_key: str = typer.Argument(...),
    seed_order_start: int = typer.Option(1),
    seed_order_end: int = typer.Option(100),
    recommendation_limit: int | None = typer.Option(None),
) -> None:
    """Emit one diagnostic, recommendation, and roadmap JSON document."""
    try:
        result = build_admission_journey(
            profile_key, seed_order_start, seed_order_end, recommendation_limit,
        )
    except ApplicantProfile.DoesNotExist as exc:
        raise typer.BadParameter(f"unknown profile_key: {profile_key}") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(result.model_dump_json(indent=2))


@roadmap_app.command("build")
def build_roadmap_command(
    profile_key: str = typer.Argument(...),
    seed_order_start: int = typer.Option(1),
    seed_order_end: int = typer.Option(100),
    recommendation_limit: int | None = typer.Option(None),
) -> None:
    """Emit an ordered roadmap from profile gaps and recommendation actions."""
    try:
        result = build_roadmap_for_profile(
            profile_key, seed_order_start, seed_order_end, recommendation_limit,
        )
    except ApplicantProfile.DoesNotExist as exc:
        raise typer.BadParameter(f"unknown profile_key: {profile_key}") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(result.model_dump_json(indent=2))


@recommend_app.command("universities")
def recommend_universities_command(
    profile_key: str = typer.Argument(...),
    seed_order_start: int = typer.Option(1),
    seed_order_end: int = typer.Option(100),
    limit: int | None = typer.Option(None),
) -> None:
    """Emit deterministic review priorities and factual supporting assessments."""
    try:
        result = recommend_for_profile(profile_key, seed_order_start, seed_order_end, limit)
    except ApplicantProfile.DoesNotExist as exc:
        raise typer.BadParameter(f"unknown profile_key: {profile_key}") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(result.model_dump_json(indent=2))


@assess_app.command("candidates")
def assess_candidates_command(
    profile_key: str = typer.Argument(...),
    seed_order_start: int = typer.Option(1),
    seed_order_end: int = typer.Option(100),
) -> None:
    """Emit factual assessments for a deterministic canonical seed range."""
    try:
        result = assess_candidates(profile_key, seed_order_start, seed_order_end)
    except ApplicantProfile.DoesNotExist as exc:
        raise typer.BadParameter(f"unknown profile_key: {profile_key}") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(result.model_dump_json(indent=2))


@profile_app.command("validate")
def validate_profile_command(path: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Validate an applicant profile JSON document without persistence."""
    payload = load_profile(path)
    typer.echo(f"valid profile_key={payload.profile_key}")


@profile_app.command("import")
def import_profile_command(path: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Create or update an applicant profile from validated JSON."""
    profile = import_profile(load_profile(path))
    typer.echo(f"imported profile_key={profile.profile_key}")


@profile_app.command("show")
def show_profile_command(profile_key: str = typer.Argument(...)) -> None:
    """Export a stored applicant profile as deterministic JSON."""
    try:
        payload = export_profile(profile_key)
    except ApplicantProfile.DoesNotExist as exc:
        raise typer.BadParameter(f"unknown profile_key: {profile_key}") from exc
    typer.echo(payload.model_dump_json(indent=2))


@profile_app.command("diagnose")
def diagnose_profile_command(profile_key: str = typer.Argument(...)) -> None:
    """Emit a factual, deterministic diagnostic for a stored profile."""
    try:
        diagnostic = diagnose_profile(profile_key)
    except ApplicantProfile.DoesNotExist as exc:
        raise typer.BadParameter(f"unknown profile_key: {profile_key}") from exc
    typer.echo(diagnostic.model_dump_json(indent=2))


@data_app.command("seed")
def seed(path: Path = typer.Option(Path("data/seed/university_coverage_100.json"), exists=True, readable=True)) -> None:
    """Load and validate the 100-entry coverage manifest."""
    typer.echo(f"Seeded {seed_manifest(path)} entries.")


@data_app.command("import-ipeds")
def import_ipeds_command(
    file: Path = typer.Option(..., exists=True, readable=True, help="Extracted IPEDS HD CSV file."),
    source_url: str = typer.Option("https://nces.ed.gov/ipeds/datacenter/data/HD2024.zip"),
    data_year: str = typer.Option("2024"),
) -> None:
    """Resolve seeded institutions using an official IPEDS HD CSV release."""
    results = import_ipeds(file, source_url=source_url, data_year=data_year)
    typer.echo(" ".join(f"{key}={value}" for key, value in results.items()))


@data_app.command("status")
def status() -> None:
    """Show an auditable resolution table and summary counts."""
    counts = status_counts()
    typer.echo(" ".join(f"{key}={value}" for key, value in counts.items()))
    for row in status_rows():
        issues = ",".join(row["issues"]) or "-"
        typer.echo(f"{row['seed_order']:03d}\t{row['status']}\t{row['ipeds_unitid'] or '-'}\t{row['state']}\t{row['seed_name']}\t{issues}")


@data_app.command("export")
def export(path: Path = typer.Option(Path("data/canonical/institutions.jsonl"))) -> None:
    """Write deterministic canonical institution JSONL."""
    typer.echo(f"Exported {export_institutions(path)} institutions to {path}.")


@data_app.command("import-programs")
def import_programs(
    completions_file: Path = typer.Option(..., exists=True, readable=True, help="Extracted IPEDS C2024_A CSV file."),
    cip_titles_file: Path = typer.Option(..., exists=True, readable=True, help="Official NCES CIP 2020 title CSV export."),
    source_url: str = typer.Option("https://nces.ed.gov/ipeds/datacenter/data/C2024_A.zip"),
    data_year: str = typer.Option("2024"),
) -> None:
    """Import bachelor's-only CIP evidence from IPEDS completions data."""
    results = import_bachelors_programs(
        completions_file,
        cip_titles_file,
        source_url=source_url,
        data_year=data_year,
    )
    typer.echo(" ".join(f"{key}={value}" for key, value in results.items()))


@data_app.command("export-programs")
def export_programs_command(path: Path = typer.Option(Path("data/canonical/programs.jsonl"))) -> None:
    """Write deterministic bachelor's-program CIP coverage JSONL."""
    typer.echo(f"Exported {export_programs(path)} program records to {path}.")


@data_app.command("program-status")
def program_status_command() -> None:
    """Show bachelor's program coverage counts and explicit zero-coverage issues."""
    typer.echo(" ".join(f"{key}={value}" for key, value in program_status().items()))


@data_app.command("import-admissions")
def import_admissions_command(
    admissions_file: Path = typer.Option(..., exists=True, readable=True, help="Extracted IPEDS ADM2024 CSV file."),
    dictionary_file: Path = typer.Option(..., exists=True, readable=True, help="Official IPEDS ADM2024 dictionary file."),
    source_url: str = typer.Option("https://nces.ed.gov/ipeds/complete-data-files/ADM2024.zip"),
    dictionary_url: str = typer.Option("https://nces.ed.gov/ipeds/complete-data-files/ADM2024_Dict.zip"),
    data_year: str = typer.Option("2024"),
) -> None:
    """Import Fall IPEDS admissions/test-score distributions without inferring policy."""
    results = import_admissions(
        admissions_file,
        dictionary_file,
        source_url=source_url,
        dictionary_url=dictionary_url,
        data_year=data_year,
    )
    typer.echo(" ".join(f"{key}={value}" for key, value in results.items()))


@data_app.command("export-admissions")
def export_admissions_command(path: Path = typer.Option(Path("data/canonical/admissions.jsonl"))) -> None:
    """Write deterministic Fall IPEDS admissions/test-score context JSONL."""
    typer.echo(f"Exported {export_admissions(path)} admission records to {path}.")


@data_app.command("admissions-status")
def admissions_status_command() -> None:
    """Show admissions/test-score context coverage without inferring test policy."""
    typer.echo(" ".join(f"{key}={value}" for key, value in admissions_status().items()))


@data_app.command("discover-sources")
def discover_sources_command(
    source_seeds: Path = typer.Option(Path("data/source_seeds/official_urls.jsonl"), exists=True, readable=True),
    unitid: list[int] = typer.Option([], "--unitid", help="Repeat to select a reviewed subset."),
) -> None:
    """Validate and show reviewable official-page source seeds for a subset."""
    seeds = discover_official_sources(source_seeds, set(unitid) or None)
    for seed in seeds:
        typer.echo(f"unitid={seed.institution_ipeds_unitid} url={seed.url} discovery_method={seed.discovery_method}")
    typer.echo(f"sources_discovered={len(seeds)}")


@data_app.command("fetch-sources")
def fetch_sources_command(
    source_seeds: Path = typer.Option(Path("data/source_seeds/official_urls.jsonl"), exists=True, readable=True),
    unitid: list[int] = typer.Option([], "--unitid", help="Repeat to select a reviewed subset."),
    seed_order_start: int | None = typer.Option(None, help="Inclusive first canonical seed order."),
    seed_order_end: int | None = typer.Option(None, help="Inclusive last canonical seed order."),
) -> None:
    """Fetch reviewed official sources with robots checks, retries, and ignored local cache."""
    selected = _source_selection(unitid, seed_order_start, seed_order_end)
    try:
        results = fetch_official_sources(source_seeds, unitids=selected)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(" ".join(f"{key}={value}" for key, value in results.items()))


@data_app.command("enrich-english")
def enrich_english_command(
    source_seeds: Path = typer.Option(Path("data/source_seeds/official_urls.jsonl"), exists=True, readable=True),
    unitid: list[int] = typer.Option([], "--unitid", help="Repeat to select a reviewed subset."),
    seed_order_start: int | None = typer.Option(None, help="Inclusive first canonical seed order."),
    seed_order_end: int | None = typer.Option(None, help="Inclusive last canonical seed order."),
) -> None:
    """Extract bounded English-policy candidates through the isolated Alem adapter."""
    selected = _source_selection(unitid, seed_order_start, seed_order_end)
    try:
        client = AlemGemmaClient.from_environment()
        llm_available = True
    except LLMUnavailable as exc:
        client = UnavailableEnglishClient(str(exc))
        llm_available = False
    try:
        results = enrich_english_requirements(source_seeds, client, unitids=selected)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"llm_available={str(llm_available).lower()} " + " ".join(f"{key}={value}" for key, value in results.items()))


@data_app.command("export-english")
def export_english_command(path: Path = typer.Option(Path("data/canonical/english_requirements.jsonl"))) -> None:
    """Write deterministic reviewable English-policy facts without source bodies."""
    typer.echo(f"Exported {export_english_requirements(path)} English requirement records to {path}.")


@data_app.command("export-sources")
def export_sources_command(path: Path = typer.Option(Path("data/canonical/sources.jsonl"))) -> None:
    """Write deterministic official-source metadata without raw HTML or extracted bodies."""
    typer.echo(f"Exported {export_sources(path)} source records to {path}.")



def _source_selection(unitids: list[int], start: int | None, end: int | None) -> set[int] | list[int] | None:
    try:
        return resolve_source_selection(unitids, start, end)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@data_app.command("source-gaps")
def source_gaps_command(
    seed_order_start: int = typer.Option(..., help="Inclusive first canonical seed order."),
    seed_order_end: int = typer.Option(..., help="Inclusive last canonical seed order."),
    path: Path = typer.Option(..., help="Offline source-gap JSON output."),
    source_seeds: Path = typer.Option(Path("data/source_seeds/official_urls.jsonl"), exists=True, readable=True),
) -> None:
    """Audit the active reviewed source list without HTTP or LLM access."""
    try:
        result = export_source_gaps(source_seeds, path, seed_order_start, seed_order_end)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(" ".join(f"{key}={value}" for key, value in result.items()))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
