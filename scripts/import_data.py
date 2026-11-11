"""Convert private exports to a small, explicitly approved public dataset."""
import argparse
import json
import re
import shutil
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CST = timezone(timedelta(hours=8))
IMAGE_DIR = ROOT / "src/public/chronicle-images"

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def stamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError(f"Timestamp requires a timezone: {value}")
    return result.astimezone(CST)

def candidates(source, username, output):
    entries = []
    for issue in read(source):
        comments = [comment for comment in issue["comments"] if (
            (comment.get("author") or comment.get("user") or {}).get("login", "").casefold() == username.casefold()
        )]
        comments.sort(key=lambda comment: stamp(comment.get("createdAt") or comment["created_at"]))
        if comments:
            entries.append({
                "id": int(issue["number"]),
                "date": stamp(comments[0].get("createdAt") or comments[0]["created_at"]).date().isoformat(),
                "visibility": "待审",
                "sensitiveInfoProcessed": False,
                "quote": "",
                "body": "\n\n".join(comment["body"] for comment in comments),
                "images": [],
            })
    output = Path(output)
    if output.exists():
        raise FileExistsError("Choose a new candidate path to preserve previous review decisions")
    write(output, sorted(entries, key=lambda entry: entry["date"], reverse=True))

def chronicle(source, processed_only=False):
    source = Path(source)
    public = []
    images = {}
    ids = set()
    for item in read(source):
        if item.get("visibility") != "公开":
            continue
        processed = item.get("sensitiveInfoProcessed", False)
        if not isinstance(processed, bool):
            raise ValueError("sensitiveInfoProcessed must be a boolean")
        if processed_only and not processed:
            continue
        number = int(item["id"])
        if number <= 0 or number in ids or not item["quote"].strip():
            raise ValueError("Every public entry needs a unique positive Issue ID and a quote")
        ids.add(number)
        published = {
            "id": number, "date": date.fromisoformat(item["date"]).isoformat(),
            "quote": item["quote"], "body": item["body"], "images": [],
            "sensitiveInfoProcessed": processed,
        }
        for index, image in enumerate(item["images"], start=1):
            original = (source.parent / image["file"]).resolve()
            extension = original.suffix.lower()
            if extension not in {".png", ".jpg", ".jpeg", ".gif", ".webp"} or not original.is_file():
                raise ValueError(f"Invalid local image: {original}")
            filename = f"{number}-{index}{extension}"
            images[filename] = original
            published["images"].append({"src": f"/chronicle-images/{filename}", "alt": image.get("alt", "")})
        public.append(published)

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for filename, original in images.items():
        shutil.copyfile(original, IMAGE_DIR / filename)
    write(ROOT / "src/data/chronicle.json", public)
    for stale in IMAGE_DIR.iterdir():
        if stale.is_file() and stale.name not in images:
            stale.unlink()

def upptime(repo, sources, output):
    """Read the selected service histories from a local Upptime clone."""
    def git(*args):
        return subprocess.check_output(["git", "-C", repo, *args], encoding="utf-8")
    services = []
    cutoff = None
    for source in read(sources):
        slug = source["slug"]
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            raise ValueError(f"Invalid Upptime slug: {slug}")
        history = f"history/{slug}.yml"
        daily = {}
        for commit in git("log", "--format=%H", "HEAD", "--", history).splitlines():
            previous = subprocess.run(["git", "-C", repo, "show", f"{commit}:{history}"],
                                      capture_output=True, text=True, encoding="utf-8")
            if previous.returncode:
                if "does not exist" in previous.stderr:
                    continue
                raise RuntimeError(previous.stderr)
            fields = dict(re.findall(r"^(status|lastUpdated):\s*([^\r\n]+)", previous.stdout, re.M))
            if fields.get("status") not in ("up", "down", "degraded") or "lastUpdated" not in fields:
                continue
            checked = stamp(fields["lastUpdated"].strip().strip("'\u0022"))
            cutoff = max(cutoff or checked, checked)
            daily.setdefault(checked.date().isoformat(), set()).add(fields["status"])
        rows = {key: {"state": "ok" if values == {"up"} else "degraded"}
                for key, values in daily.items()}
        services.append({"id": slug, "name": source["name"], "days": rows})
    if cutoff is None:
        raise ValueError("No timestamped probes found for the selected services")
    output = Path(output)
    if output.exists():
        raise FileExistsError("Choose a new archive path to preserve event edits")
    write(output, {"cutoff": cutoff.isoformat(), "services": services})

def archive(source):
    raw = read(source)
    cutoff = stamp(raw["cutoff"])
    approved = {item["id"] for item in read(ROOT / "src/data/chronicle.json")}
    services = []
    for service in raw["services"]:
        days = {}
        for key, row in sorted(service["days"].items()):
            current = date.fromisoformat(key)
            state = row.get("state", "unknown")
            if current > cutoff.date() or state not in {"ok", "degraded", "down", "unknown"}:
                raise ValueError(f"Invalid archive row: {key}")
            events = []
            for event in row.get("events", []):
                public = {"title": event["title"], "summary": event.get("summary", "")}
                for field in ("start", "end"):
                    if event.get(field):
                        public[field] = stamp(event[field]).isoformat()
                if event.get("chronicleId") in approved:
                    public["chronicleId"] = event["chronicleId"]
                events.append(public)
            clean = {"state": state, "events": sorted(events, key=lambda event: event.get("start", ""))}
            if "uptimeSeconds" in row and "coveredSeconds" in row:
                uptime, coverage = row["uptimeSeconds"], row["coveredSeconds"]
                available = (min(datetime.combine(current + timedelta(days=1), time(), CST), cutoff)
                             - datetime.combine(current, time(), CST)).total_seconds()
                if not 0 <= uptime <= coverage <= available:
                    raise ValueError(f"Invalid covered duration: {key}")
                clean.update(uptimeSeconds=uptime, coveredSeconds=coverage)
            days[current.isoformat()] = clean
        services.append({"id": service["id"], "name": service["name"], "days": days})
    write(ROOT / "src/data/archive.json", {"cutoff": cutoff.isoformat(), "services": services})

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)
    candidate = actions.add_parser("candidates")
    candidate.add_argument("source")
    candidate.add_argument("username")
    candidate.add_argument("output")
    history = actions.add_parser("upptime")
    history.add_argument("repo")
    history.add_argument("sources")
    history.add_argument("output")
    for action in ("chronicle", "archive"):
        actions.add_parser(action).add_argument("source")
    actions.choices["chronicle"].add_argument("--processed-only", action="store_true")
    args = parser.parse_args()
    if args.action == "candidates":
        candidates(args.source, args.username, args.output)
    elif args.action == "chronicle":
        chronicle(args.source, args.processed_only)
    elif args.action == "upptime":
        upptime(args.repo, args.sources, args.output)
    else:
        archive(args.source)

