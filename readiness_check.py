"""Map the evidence-backed readiness checklist to every personal project and chat.

Run:
    python readiness_check.py

The report records explicit file-content evidence. A filename alone never marks a
check as complete.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

HERE = Path(__file__).resolve().parent
DEFAULT_CHECKLIST = HERE / "readiness_checklists.json"
DEFAULT_PORTFOLIO = Path.home() / "Videos" / "personal_context"
TEXT_SUFFIXES = {
    ".md", ".mdx", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".scss", ".sh",
    ".ps1", ".cmd", ".sql", ".env", ".example", ".xml", ".csv",
}
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build", "coverage",
    ".next", ".turbo", ".wrangler", "target",
}
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_PROJECT_BYTES = 60 * 1024 * 1024

# Each check has a small, distinctive prefilter. It prevents the regex engine
# from scanning every source file for every checklist item while keeping the
# final regex as the source of truth.
PREFILTER_TERMS = {
    "build.target_user_problem": ("target", "icp", "ideal", "job", "customer problem", "user pain"),
    "build.customer_discovery": ("customer", "user", "interview", "survey", "potential customer", "ask 1"),
    "build.scoped_mvp": ("minimum viable product", "mvp", "smallest version", "one-week", "one week", "functional requirement", "scope", "first 20"),
    "build.website": ("http", "landing page", "website structure", "website template", "hosted website", "published website", "deployed website"),
    "build.interactive_demo": ("interactive demo", "live demo", "product demo", "demo day", "working prototype", "product walkthrough"),
    "build.onboarding": ("onboarding", "first value", "time-to-first-value", "time to first value", "quickstart", "quick start", "getting started", "installation guide", "walkthrough"),
    "build.payment_or_waitlist": ("stripe.checkout", "checkout session", "payment system", "payment flow", "payment collection", "pricing plan", "price id", "price_id", "price-id", "priceid", "pricing page", "paid waitlist", "waitlist signup", "sign-up page", "sign up page", "signup page"),
    "build.traction_metrics": ("mrr", "arr", "waitlist", "revenue", "user signed", "user joined", "user active", "users signed", "users joined", "users active", "customer signed", "customer paying", "customers signed", "customers paying", "conversion rate", "retention", "churn", "traction"),
    "build.quality_and_safety": ("unit test", "integration test", "end-to-end test", "end to end test", "pytest", "vitest", "playwright", "cypress", "github/workflows", "continuous integration", "privacy policy", "terms of service", "security policy", "backup", "restore", "mfa", "2fa", "encryption", "rate limit", "deployment pipeline", "ci"),
    "build.feedback_loop": ("customer feedback", "user feedback", "support ticket", "sales call", "customer interview", "what_the_market_is_telling_us", "feature request", "churned customer", "record every sales call"),
    "funding.pitch_deck": ("pitch deck", "investor deck", "data room", "one-pager", "deal memo", "fundraising deck", "investor narrative"),
    "funding.traction_evidence": ("mrr", "arr", "traction", "customer signed", "customer paying", "customers signed", "customers paying", "revenue", "waitlist", "retention", "churn", "conversion rate", "growth rate"),
    "funding.financial_plan": ("financial projection", "use of funds", "cash flow", "runway", "burn rate", "p&l", "profit and loss", "financial model", "budget"),
    "funding.legal_cap_table": ("cap table", "certificate of incorporation", "founder agreement", "founders agreement", "founders' agreement", "ip assignment", "term sheet", "safe", "shareholder agreement", "shareholders agreement", "board minutes"),
    "funding.data_room": ("data room", "due diligence", "customer contract", "bank statement", "patent documentation", "prior safe", "deal memo"),
    "funding.raise_process": ("fundraising", "raise seed", "raise the seed", "raise a seed", "raise pre-seed", "raise the pre-seed", "raise a pre-seed", "raise angel", "raise the angel", "raise an angel", "raise round", "raise the round", "raise a round", "valuation", "investor list", "investor outreach", "investor process", "investor meeting", "lead investor", "use of funds", "target raise"),
    "opportunities.eligibility": ("eligibility", "eligible entity", "eligible applicant", "eligible founder", "eligible company", "application requirement", "submission requirement", "selection criteria", "judging criteria", "deadline"),
    "opportunities.application_assets": ("functional requirement", "technical requirement", "prototype", "working demo", "application material", "application asset", "one-page pitch", "one page pitch", "one-page summary", "one page summary", "project summary", "project description", "budget"),
    "opportunities.demo_day": ("demo-day", "demo day", "judge", "judging", "pitch video", "pitch deck", "pitch script", "presentation deck", "presentation script", "live demo", "elevator pitch"),
    "opportunities.submission_compliance": ("submit application", "submit the application", "submit your application", "submit an application", "submitted application", "submitted the application", "submitted your application", "submitted an application", "submitting application", "submitting the application", "submitting your application", "submitting an application", "submit proposal", "submit the proposal", "submit your proposal", "submit a proposal", "submitted proposal", "submitted the proposal", "submitted your proposal", "submitted a proposal", "submitting proposal", "submitting the proposal", "submitting your proposal", "submitting a proposal", "application form", "application deadline", "application requirement", "application material", "proposal form", "proposal deadline", "proposal requirement", "required document", "submission checklist"),
    "marketing.demand_validation": ("demand already exists", "demand exists", "demand validation", "validate demand", "market demand", "customer demand", "preorder", "250+ emails", "public buying intent"),
    "marketing.launch_plan": ("launch date", "launch plan", "launch checklist", "pre-launch", "pre launch", "prelaunch", "viral launch", "go-to-market", "go to market", "gotomarket", "post-launch", "post launch"),
    "marketing.launch_assets": ("loom", "introduce yourself", "founder video", "video introduction", "launch film", "product video", "demo video", "creator brief", "launch copy"),
    "marketing.presell": ("waitlist", "pre-sell", "pre sell", "presell", "pre-order", "pre order", "preorder", "deposit", "payment collection", "paid waitlist", "checkout"),
    "marketing.audience_community": ("community", "discord", "circle", "whatsapp group", "email list", "newsletter", "skool", "audience", "followers"),
    "marketing.daily_distribution": ("post daily", "daily post", "daily content", "cold email", "linkedin", "reddit", "reply to", "reply with", "build in public", "outbound"),
    "marketing.social_proof": ("case study", "case studies", "testimonial", "social proof", "customer quote", "customer review", "customer reviews", "user review", "user reviews"),
    "marketing.zero_budget_engine": ("zero-budget", "zero budget", "no money", "no funding", "bootstrap", "free tool", "free tools", "cash-flow", "cash flow", "customer revenue", "cold outreach", "first 10 customers", "first customer"),
}


def load_checklist(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for check in data["checks"]:
        check["compiled"] = [re.compile("|".join(f"(?:{pattern})" for pattern in check["patterns"]).lower())]
        # These are conservative literal tokens extracted from the patterns. A
        # check without one of its tokens cannot match, so most source files
        # skip the regex engine entirely.
        tokens = set(PREFILTER_TERMS.get(check["id"], ()))
        if not tokens:
            for pattern in check["patterns"]:
                tokens.update(token.lower() for token in re.findall(r"[A-Za-z]{2,}", pattern))
        check["tokens"] = tokens
    return data


def load_portfolio(root: Path):
    portfolio_path = root / "cold-email" / "portfolio.py"
    spec = importlib.util.spec_from_file_location("personal_portfolio", portfolio_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {portfolio_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def iter_text_files(path: Path) -> Iterable[Path]:
    if not path.exists():
        return
    for base, dirs, files in os.walk(path):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not name.startswith(".")]
        for name in files:
            file_path = Path(base) / name
            if file_path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                if file_path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield file_path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def scan_text(text: str, checks: list[dict], path: str) -> dict[str, list[dict]]:
    found = {check["id"]: [] for check in checks}
    if not checks or not text:
        return found
    lower_text = text.lower()
    for check in checks:
        if not any(token in lower_text for token in check["tokens"]):
            continue
        for regex in check["compiled"]:
            match = regex.search(lower_text)
            if not match:
                continue
            line = text.count("\n", 0, match.start()) + 1 if len(text) <= 500_000 else None
            excerpt = " ".join(match.group(0).split())[:180]
            found[check["id"]].append({"path": path, "line": line, "excerpt": excerpt})
            break
    return found


def scan_project(path: Path, checks: list[dict]) -> tuple[dict[str, list[dict]], int, int]:
    matches = {check["id"]: [] for check in checks}
    files_scanned = 0
    bytes_scanned = 0
    for file_path in iter_text_files(path):
        try:
            size = file_path.stat().st_size
        except OSError:
            continue
        if bytes_scanned + size > MAX_PROJECT_BYTES:
            break
        text = read_text(file_path)
        if not text:
            continue
        files_scanned += 1
        bytes_scanned += size
        relative = str(file_path.resolve())
        for check_id, evidence in scan_text(text, checks, relative).items():
            if len(matches[check_id]) < 3:
                matches[check_id].extend(evidence[: 3 - len(matches[check_id])])
    return matches, files_scanned, bytes_scanned


def alias_strings(name: str) -> list[str]:
    value = name
    if "__" in value:
        value = value.split("__", 1)[1]
    variants = {value, value.replace("-", " "), value.replace("_", " ")}
    variants.add(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value))
    return sorted({item.strip().lower() for item in variants if item.strip()})


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def project_aliases(name: str) -> list[str]:
    aliases = alias_strings(name)
    compact = [normalized(alias) for alias in aliases]
    result = []
    for alias in aliases + compact:
        if alias and alias not in result:
            result.append(alias)
    return result


def chat_title(path: Path, text: str) -> str:
    if path.suffix.lower() == ".md":
        match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if match:
            return match.group(1).strip()
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:160]
    return path.stem


def scan_chats(roots: list[Path], checks: list[dict]) -> list[dict]:
    records = []
    seen = set()
    for root in roots:
        for path in iter_text_files(root):
            resolved = str(path.resolve())
            if resolved in seen or path.name.lower() in {"skill.md", "desktop.ini"}:
                continue
            seen.add(resolved)
            text = read_text(path)
            if not text:
                continue
            matches = scan_text(text, checks, resolved)
            records.append({
                "path": resolved,
                "title": chat_title(path, text),
                "matches": matches,
                "normalized_text": normalized(text),
                "size": len(text),
            })
    return records


def assign_chats(projects: list[dict], chats: list[dict]) -> None:
    aliases_by_project = {
        project["name"]: project_aliases(project["name"])
        for project in projects
    }
    for project in projects:
        relevant = []
        aliases = aliases_by_project[project["name"]]
        for chat in chats:
            hits = [alias for alias in aliases if alias and alias in chat["normalized_text"]]
            if hits:
                relevant.append((chat, hits))
        project["relevant_chats"] = [
            {
                "path": chat["path"],
                "title": chat["title"],
                "matched_aliases": hits,
                "gaps": [
                    check["id"] for check in checks_for_project(project)
                    if not chat["matches"].get(check["id"])
                ],
            }
            for chat, hits in relevant
        ]


def checks_for_project(project: dict) -> list[dict]:
    return project["_checks"]


def build_report(checklist: dict, portfolio_root: Path, chat_roots: list[Path]) -> dict:
    portfolio = load_portfolio(portfolio_root)
    inventory = portfolio.inventory(portfolio_root)
    checks = checklist["checks"]
    projects = []
    for record in inventory:
        project_path = portfolio_root / record["location"]
        scan_root = project_path / "code" if record["kind"] == "repo" else project_path
        matches, files_scanned, bytes_scanned = scan_project(scan_root, checks)
        project = {
            "name": record["name"],
            "location": record["location"],
            "path": str(project_path.resolve()),
            "kind": record["kind"],
            "lane": record["lane"],
            "files_scanned": files_scanned,
            "bytes_scanned": bytes_scanned,
            "matches": matches,
            "gaps": [check["id"] for check in checks if not matches.get(check["id"])],
            "_checks": checks,
        }
        projects.append(project)

    chats = scan_chats(chat_roots, checks)
    assign_chats(projects, chats)

    relevant_paths = {
        chat["path"] for project in projects for chat in project["relevant_chats"]
    }
    chat_rows = []
    for chat in chats:
        if chat["path"] not in relevant_paths:
            continue
        related = [
            project["name"] for project in projects
            if any(item["path"] == chat["path"] for item in project["relevant_chats"])
        ]
        chat_rows.append({
            "path": chat["path"],
            "title": chat["title"],
            "projects": related,
            "gaps": [check["id"] for check in checks if not chat["matches"].get(check["id"])],
        })

    for project in projects:
        project.pop("_checks", None)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checklist_version": checklist["version"],
        "portfolio_root": str(portfolio_root.resolve()),
        "chat_roots": [str(path.resolve()) for path in chat_roots],
        "project_count": len(projects),
        "chat_count": len(chats),
        "relevant_chat_count": len(chat_rows),
        "projects": projects,
        "chats": chat_rows,
    }


def checklist_markdown(checklist: dict) -> str:
    lines = [
        "# Evidence-backed readiness checklists",
        "",
        f"Generated from saved-tweet and Simplenote evidence on {checklist['generated_at']}.",
        "A checker hit means that the project or chat contains matching file content. It does not prove that the work is complete.",
        "",
    ]
    for category in ("build", "funding", "opportunities", "marketing"):
        lines.append(f"## {category.title()}")
        lines.append("")
        for check in (item for item in checklist["checks"] if item["category"] == category):
            lines.append(f"### {check['title']}")
            lines.append("")
            lines.append(check["action"])
            lines.append("")
            lines.append(f"Check ID: `{check['id']}`")
            lines.append("")
            lines.append("Evidence:")
            for evidence in check["evidence"]:
                if evidence["type"] == "tweet":
                    lines.append(f"- [Saved tweet {evidence['id']}]({evidence['url']})")
                else:
                    lines.append(f"- Simplenote `{evidence['id']}`")
            lines.append("")
    lines.append("## Tweet corpora")
    lines.append("")
    for corpus in checklist["source_corpora"]:
        lines.append(f"- `{corpus['path']}`: {corpus['records']} records")
    lines.append("")
    return "\n".join(lines)


def report_markdown(report: dict, checklist: dict) -> str:
    checks = {check["id"]: check for check in checklist["checks"]}
    lines = [
        "# Project and chat readiness gap map",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"Projects covered: {report['project_count']}. Chat sessions scanned: {report['chat_count']}. Relevant chat sessions: {report['relevant_chat_count']}.",
        "",
        "Each gap below means no matching file content was found. A hit is evidence of an artifact or plan, not proof of completion.",
        "",
    ]
    for project in report["projects"]:
        lines.append(f"## {project['name']}")
        lines.append("")
        lines.append(f"Location: `{project['location']}`")
        lines.append("")
        lines.append(f"Evidence files scanned: {project['files_scanned']}. Checklist gaps: {len(project['gaps'])}.")
        lines.append("")
        for category in ("build", "funding", "opportunities", "marketing"):
            gap_ids = [check_id for check_id in project["gaps"] if checks[check_id]["category"] == category]
            lines.append(f"### {category.title()}")
            lines.append("")
            if gap_ids:
                for check_id in gap_ids:
                    lines.append(f"- [ ] {checks[check_id]['title']} (`{check_id}`)")
            else:
                lines.append("- [x] No checklist gap detected.")
            lines.append("")
        lines.append("### Relevant chats")
        lines.append("")
        if project["relevant_chats"]:
            for chat in project["relevant_chats"]:
                gap_titles = [checks[check_id]["title"] for check_id in chat["gaps"]]
                gap_text = ", ".join(gap_titles) if gap_titles else "no checklist gap detected"
                lines.append(f"- {chat['title']} (`{chat['path']}`): {gap_text}")
        else:
            lines.append("- No chat session matched this project name.")
        lines.append("")
    lines.append("## Unmatched chats")
    lines.append("")
    lines.append(f"{report['chat_count'] - report['relevant_chat_count']} chat sessions did not match a project name and remain available in the QMD corpus.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", default=str(DEFAULT_CHECKLIST))
    parser.add_argument("--portfolio-root", default=str(DEFAULT_PORTFOLIO))
    parser.add_argument("--chat-root", action="append", default=[])
    parser.add_argument("--out-dir", default=str(HERE / "out"))
    parser.add_argument("--checklist-md", default=str(HERE / "READINESS-CHECKLISTS.md"))
    args = parser.parse_args()

    checklist = load_checklist(Path(args.checklist))
    portfolio_root = Path(args.portfolio_root)
    chat_roots = [Path(value) for value in args.chat_root]
    if not chat_roots:
        chat_roots = [
            Path.home() / "Documents" / "QMD powered Personal Knowledgebase and Search Engine" / "corpus" / "chats",
            portfolio_root / "my projects (no repos, just specs, usually AI chats and their file outputs, and scratch projects i have not yet deployed to github)" / "redteaming new context files",
        ]

    report = build_report(checklist, portfolio_root, chat_roots)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "readiness_project_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "readiness_project_report.md").write_text(
        report_markdown(report, checklist), encoding="utf-8"
    )
    Path(args.checklist_md).write_text(checklist_markdown(checklist), encoding="utf-8")

    print(json.dumps({
        "projects": report["project_count"],
        "chats_scanned": report["chat_count"],
        "relevant_chats": report["relevant_chat_count"],
        "report": str((out_dir / "readiness_project_report.md").resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
