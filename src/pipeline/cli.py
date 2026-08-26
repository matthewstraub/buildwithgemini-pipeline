"""Command-Line Interface for the Job Pipeline Agent (`pipeline`)."""

from datetime import date
from pathlib import Path
import re
import sys
from typing import List, Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import yaml

from pipeline.cadence import compute_next_action
from pipeline.digest import build_daily_digest, build_monday_summary, send_ntfy_notification
from pipeline.drafting import generate_followup_draft
from pipeline.holidays import count_business_days_between
from pipeline.models import Application, SourceEnum, StageEnum, VettingInput, VettingVerdictEnum
from pipeline.vetting import vet_recruiter_message

app = typer.Typer(
    name="pipeline",
    help="Job Pipeline Agent — Track applications, cadence nudges, recruiter vetting & draft generation.",
    add_completion=False,
)
console = Console()
STATE_DIR = Path("state/applications")


def load_all_applications(state_dir: Path = STATE_DIR) -> List[Application]:
    """Loads all application YAML records from state directory. Seeds sample files if empty."""
    if not state_dir.exists():
        state_dir.mkdir(parents=True, exist_ok=True)

    yaml_files = list(state_dir.glob("*.yaml"))
    if not yaml_files:
        sample_dir = Path("examples/sample-applications")
        if sample_dir.exists():
            import shutil
            for sample_file in sample_dir.glob("*.yaml"):
                shutil.copy(sample_file, state_dir / sample_file.name)
            yaml_files = list(state_dir.glob("*.yaml"))

    apps = []
    for filepath in sorted(yaml_files):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data:
                    apps.append(Application(**data))
        except Exception as e:
            console.print(f"[bold red]Error loading {filepath}: {e}[/bold red]")
    return apps



def save_application(app_obj: Application, state_dir: Path = STATE_DIR):
    """Saves an application record to state directory as YAML."""
    state_dir.mkdir(parents=True, exist_ok=True)
    filepath = state_dir / f"{app_obj.slug}.yaml"
    data = app_obj.model_dump(exclude_none=True, mode="json")
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, default_flow_style=False)


@app.command(name="status")
def status_cmd(
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Output cleanly formatted Markdown with Mermaid diagram."),
):
    """Display the current job pipeline board and attention items."""
    apps = load_all_applications()
    if not apps:
        console.print("[yellow]No application records found in state/applications/.[/yellow]")
        return

    today = date.today()

    if markdown:
        console.print(generate_markdown_pipeline(apps, today=today))
        return

    table = Table(title="Job Application Pipeline Board", title_style="bold magenta", expand=True)

    table.add_column("Company", style="cyan bold", no_wrap=True)
    table.add_column("Role", style="white")
    table.add_column("Location", style="yellow")
    table.add_column("Stage", style="bold")
    table.add_column("Source", style="dim")
    table.add_column("Last Contact", style="gray50")
    table.add_column("Quiet (BD)", justify="right")
    table.add_column("Next Action", style="green")

    need_attention_count = 0

    for a in apps:
        a = compute_next_action(a, today=today)
        ref_date = a.stage_changed_on
        if a.last_contact and a.last_contact.date > ref_date:
            ref_date = a.last_contact.date
        quiet_bd = count_business_days_between(ref_date, today)

        stage_color = "white"
        if a.stage == StageEnum.APPLIED:
            stage_color = "blue"
        elif a.stage in (StageEnum.SCREEN_SCHEDULED, StageEnum.ONSITE_SCHEDULED):
            stage_color = "yellow"
        elif a.stage in (StageEnum.SCREEN_DONE, StageEnum.ONSITE_DONE):
            stage_color = "magenta"
        elif a.stage == StageEnum.OFFER:
            stage_color = "bold green"
        elif a.stage == StageEnum.REJECTED:
            stage_color = "red dim"
        elif a.stage == StageEnum.STALE:
            stage_color = "bright_black"

        stage_text = f"[{stage_color}]{a.stage.value}[/{stage_color}]"

        action_str = a.next_action or "-"
        if "Draft" in action_str or "nudge" in action_str.lower():
            action_str = f"[bold yellow]⚠️ {action_str}[/bold yellow]"
            need_attention_count += 1
        elif "stale" in action_str.lower():
            action_str = f"[dim red]{action_str}[/dim red]"

        last_c_str = f"{a.last_contact.date}" if a.last_contact else f"{a.stage_changed_on}"

        table.add_row(
            a.company,
            a.role,
            a.location_type.value,
            stage_text,
            a.source.value,
            last_c_str,
            str(quiet_bd),
            action_str,
        )

    console.print(table)
    console.print(
        f"\n[bold]Total Applications:[/bold] {len(apps)} | "
        f"[bold yellow]Need Attention Today:[/bold yellow] {need_attention_count}\n"
    )


def generate_markdown_pipeline(apps: List[Application], today: Optional[date] = None) -> str:
    """Generates GitHub Flavored Markdown table and Mermaid graph representation of the pipeline."""
    if today is None:
        today = date.today()

    lines = ["## Job Application Pipeline Board\n"]

    # Mermaid diagram
    lines.append("```mermaid")
    lines.append("graph LR")
    lines.append("    subgraph Active Pipeline")

    need_attention = []

    for a in apps:
        a = compute_next_action(a, today=today)
        if a.next_action and ("Draft" in a.next_action or "nudge" in a.next_action.lower()):
            need_attention.append(a)

        clean_comp = a.company.replace(" ", "_")
        clean_role = a.role.replace(" ", "_").replace(",", "")
        node_id = f"{clean_comp}_{clean_role}"
        label = f'"{a.company} ({a.role})<br/><b>{a.stage.value}</b>"'

        if a.stage == StageEnum.APPLIED:
            lines.append(f"        {node_id}[{label}]:::applied")
        elif a.stage in (StageEnum.SCREEN_SCHEDULED, StageEnum.SCREEN_DONE):
            lines.append(f"        {node_id}[{label}]:::screen")
        elif a.stage in (StageEnum.ONSITE_SCHEDULED, StageEnum.ONSITE_DONE):
            lines.append(f"        {node_id}[{label}]:::onsite")
        elif a.stage == StageEnum.OFFER:
            lines.append(f"        {node_id}[{label}]:::offer")
        elif a.stage == StageEnum.REJECTED:
            lines.append(f"        {node_id}[{label}]:::rejected")
        elif a.stage == StageEnum.STALE:
            lines.append(f"        {node_id}[{label}]:::stale")

    lines.append("    end")
    lines.append("    classDef applied fill:#1e3a8a,stroke:#3b82f6,color:#ffffff;")
    lines.append("    classDef screen fill:#713f12,stroke:#eab308,color:#ffffff;")
    lines.append("    classDef onsite fill:#581c87,stroke:#a855f7,color:#ffffff;")
    lines.append("    classDef offer fill:#14532d,stroke:#22c55e,color:#ffffff;")
    lines.append("    classDef rejected fill:#450a0a,stroke:#ef4444,color:#991b1b;")
    lines.append("    classDef stale fill:#262626,stroke:#737373,color:#a3a3a3;")
    lines.append("```\n")

    # Markdown Table
    lines.append("| Company | Role | Location | Stage | Source | Last Contact | Quiet (BD) | Next Action |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |")

    stage_badges = {
        StageEnum.APPLIED: "🔵 `applied`",
        StageEnum.SCREEN_SCHEDULED: "🟡 `screen_scheduled`",
        StageEnum.SCREEN_DONE: "🟣 `screen_done`",
        StageEnum.ONSITE_SCHEDULED: "🟠 `onsite_scheduled`",
        StageEnum.ONSITE_DONE: "🟣 `onsite_done`",
        StageEnum.OFFER: "🟢 `offer`",
        StageEnum.REJECTED: "🔴 `rejected`",
        StageEnum.STALE: "⚪ `stale`",
        StageEnum.RESEARCHING: "⚪ `researching`",
    }

    for a in apps:
        ref_date = a.stage_changed_on
        if a.last_contact and a.last_contact.date > ref_date:
            ref_date = a.last_contact.date
        quiet_bd = count_business_days_between(ref_date, today)

        badge = stage_badges.get(a.stage, f"`{a.stage.value}`")
        last_c_str = f"{a.last_contact.date}" if a.last_contact else f"{a.stage_changed_on}"

        action_str = a.next_action or "-"
        if "Draft" in action_str or "nudge" in action_str.lower():
            action_str = f"⚠️ **{action_str}**"

        lines.append(
            f"| **[{a.company}]({a.url or '#'})** | {a.role} | `{a.location_type.value}` | {badge} | {a.source.value} | {last_c_str} | {quiet_bd} | {action_str} |"
        )

    lines.append(f"\n**Total Applications:** {len(apps)} | **Need Attention Today:** {len(need_attention)}\n")
    return "\n".join(lines)


@app.command(name="vet")
def vet_cmd(
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Path to text/eml file containing inbound message."),
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Raw message text string."),
    sender: Optional[str] = typer.Option(None, "--sender", "-s", help="Sender email address."),
    reply_to: Optional[str] = typer.Option(None, "--reply-to", "-r", help="Reply-to email address."),
    company: Optional[str] = typer.Option(None, "--company", "-c", help="Claimed company name."),
    role: Optional[str] = typer.Option(None, "--role", help="Claimed role title."),
):
    """Vet an inbound recruiter outreach message for legitimacy vs fraud."""
    raw_message = ""
    if file and file.exists():
        raw_message = file.read_text(encoding="utf-8")
    elif text:
        raw_message = text
    elif not sys.stdin.isatty():
        raw_message = sys.stdin.read()
    else:
        console.print("[yellow]Paste inbound recruiter message below (press Ctrl+D when finished):[/yellow]\n")
        raw_message = sys.stdin.read()

    if not raw_message.strip():
        console.print("[bold red]Error: No message text provided for vetting.[/bold red]")
        raise typer.Exit(code=1)

    if not sender and "From:" in raw_message:
        match = re.search(r"From:\s*(?:.*<)?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", raw_message)
        if match:
            sender = match.group(1)

    if not reply_to and "Reply-To:" in raw_message:
        match = re.search(r"Reply-To:\s*(?:.*<)?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", raw_message)
        if match:
            reply_to = match.group(1)

    v_input = VettingInput(
        sender_email=sender,
        reply_to_email=reply_to,
        claimed_company=company,
        claimed_role=role,
        message_text=raw_message,
    )

    console.print("\n[bold cyan]🔍 Running Recruiter Vetting Checks...[/bold cyan]\n")
    res = vet_recruiter_message(v_input)

    verdict_style = "bold green"
    if res.verdict == VettingVerdictEnum.NEEDS_VERIFICATION:
        verdict_style = "bold yellow"
    elif res.verdict == VettingVerdictEnum.LIKELY_FRAUDULENT:
        verdict_style = "bold red"

    content = []
    content.append(f"VERDICT: [{verdict_style}]{res.verdict.value.upper()}[/{verdict_style}]\n")

    if res.role_legitimate is not None or res.channel_safe is not None:
        content.append(
            f"Role Legitimacy: {'✅ Real' if res.role_legitimate else '⚠️ Unverified/Fake'} | "
            f"Channel Safety: {'✅ Safe' if res.channel_safe else '🚨 Suspicious'}\n"
        )

    if res.signals_against:
        content.append("[bold red]Signals Against:[/bold red]")
        for s in res.signals_against:
            content.append(f"  • {s}")
        content.append("")

    if res.signals_for:
        content.append("[bold green]Signals For:[/bold green]")
        for s in res.signals_for:
            content.append(f"  • {s}")
        content.append("")

    if res.recommended_action:
        content.append("[bold blue]Recommended Action:[/bold blue]")
        for a in res.recommended_action:
            content.append(f"  • {a}")

    console.print(Panel("\n".join(content), title="Recruiter Vetting Analysis", border_style="cyan"))


@app.command(name="cadence")
def cadence_cmd():
    """Evaluate cadence rules across all applications and update next actions."""
    apps = load_all_applications()
    today = date.today()
    updated_count = 0

    for a in apps:
        old_action = a.next_action
        old_stage = a.stage
        a = compute_next_action(a, today=today)
        if a.next_action != old_action or a.stage != old_stage:
            save_application(a)
            updated_count += 1

    console.print(f"[green]Evaluated {len(apps)} applications. Updated {updated_count} records.[/green]")


@app.command(name="draft")
def draft_cmd(
    slug: Optional[str] = typer.Argument(None, help="Application slug (e.g. northwind-devices-solutions-consultant). If omitted, drafts for all applications needing attention."),
    context: Optional[str] = typer.Option(None, "--context", "-ctx", help="Optional thread context string."),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactively prompt for thread context."),
):
    """Generate AI follow-up draft(s) for applications requiring outreach."""
    apps = load_all_applications()
    today = date.today()

    targets = []
    if slug:
        targets = [a for a in apps if a.slug == slug]
        if not targets:
            console.print(f"[bold red]Application slug '{slug}' not found.[/bold red]")
            raise typer.Exit(code=1)
    else:
        for a in apps:
            a = compute_next_action(a, today=today)
            if a.next_action and ("Draft" in a.next_action or "nudge" in a.next_action.lower()):
                targets.append(a)

    if not targets:
        console.print("[yellow]No applications currently require draft generation.[/yellow]")
        return

    for a in targets:
        thread_ctx = context
        thread_file = Path("threads") / f"{a.slug}.md"

        if not thread_ctx and thread_file.exists():
            thread_ctx = thread_file.read_text(encoding="utf-8")
        elif not thread_ctx and interactive:
            console.print(f"\n[yellow]Enter/paste thread context for {a.company} ({a.role}) below (Ctrl+D when finished):[/yellow]")
            thread_ctx = sys.stdin.read()

        console.print(f"[cyan]Generating follow-up draft for {a.company} ({a.role})...[/cyan]")
        path = generate_followup_draft(a, thread_context=thread_ctx)
        console.print(f"  [bold green]✓ Saved draft to {path}[/bold green]")


@app.command(name="digest")
def digest_cmd(
    notify: bool = typer.Option(False, "--notify", "-n", help="Send digest notification via ntfy."),
    topic: str = typer.Option("matt-job-pipeline", "--topic", help="ntfy topic name."),
):
    """Generate daily pipeline digest."""
    apps = load_all_applications()
    digest_text, attn_apps = build_daily_digest(apps)

    console.print(Panel(digest_text, title="Daily Digest", border_style="magenta"))

    if notify:
        success = send_ntfy_notification(topic, digest_text)
        if success:
            console.print("[bold green]✓ Successfully sent ntfy notification.[/bold green]")
        else:
            console.print("[bold red]Failed to send ntfy notification (check network or NTFY_URL).[/bold red]")


@app.command(name="summary")
def summary_cmd():
    """Generate full Monday morning pipeline summary."""
    apps = load_all_applications()
    summary_text = build_monday_summary(apps)
    console.print(Panel(summary_text, title="Monday Pipeline Summary Report", border_style="blue"))


@app.command(name="serve")
def serve_cmd(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host address to bind."),
    port: int = typer.Option(8000, "--port", "-p", help="Port to listen on."),
):
    """Launch the Web Interface Dashboard server."""
    from pipeline.server import start_server
    console.print(f"[bold cyan]⚡ Starting Job Pipeline Dashboard on http://{host}:{port}[/bold cyan]")
    start_server(host=host, port=port)


if __name__ == "__main__":
    app()

