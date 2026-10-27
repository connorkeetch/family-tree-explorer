"""
ARCHIVED (2026-06) -- superseded by the single-stage direct-line refresh
(`pull_line.py -a 200`, parsed alone; see the project root). This frontier /
collateral deeper-pull tool is kept for reference only and is no longer part of
the active pipeline. Its path is now archive/find_frontier.py -- run it with
`python archive/find_frontier.py ...` (still stdlib-only and self-contained).

find_frontier.py  -- dependency-free (stdlib only)

Find the ancestors at the *edge* of an existing pull -- the people whose parents
were never fetched because the original `getmyancestors -a <N>` run stopped
ascending -- and emit ready-to-run commands to pull the next few generations and
merge them back in.

WHY THIS EXISTS
---------------
`getmyancestors -a N` ascends exactly N generations from the start person, then
stops; the deepest people come back as leaves (no parents). There is NO hard cap
on `-a` in getmyancestors, so `getmyancestors -a 20` from the root would also
work -- but it re-fetches everyone already known every time you go deeper. This
script instead collects only the frontier FIDs so a follow-up pull fetches just
the NEW ancestors (`getmyancestors -i <frontier...> -a 5`), which is far cheaper
and repeatable.

The frontier defaults to people at the deepest generation present that still
have fewer than two known parents. Lower --min-gen to also retry shallower
dead-ends (useful only if FamilySearch has gained data since your last pull).

Usage:
    python find_frontier.py --in output/ancestors.json
    python find_frontier.py --in output/wife/ancestors.json --label wife --ascend 5
    python find_frontier.py --in output/ancestors.json --min-gen 14 --chunk 400

Outputs (under output/<label>/, all gitignored):
    frontier_fids.txt   one FamilySearch ID per line
    pull_deeper.ps1     PowerShell script: chunked getmyancestors pulls + merge

It NEVER handles your credentials. The generated commands carry a
<YOUR_FS_USERNAME> placeholder and omit the password, so getmyancestors prompts
for it with hidden entry. Review the script before running it.
"""

import argparse
import json
import sys
from pathlib import Path

# Windows cmd.exe caps a command line at 8191 chars; ~9 chars per FID. 400 FIDs
# (~3.6k chars plus flags) stays comfortably under that with margin to spare.
DEFAULT_CHUNK = 400


def load_people(infile):
    if not Path(infile).exists():
        sys.exit(f"Not found: {infile}. Run parse_gedcom.py first.")
    return json.loads(Path(infile).read_text(encoding="utf-8"))


def find_root_fid(people):
    roots = [p for p in people if p.get("generation") == 0]
    return roots[0].get("fs_id") if roots else None


def find_frontier(people, min_gen=None):
    """People on the direct line, at/below the deepest generation, still missing
    a parent and carrying a usable FamilySearch ID."""
    direct = [p for p in people if p.get("on_direct_line") and p.get("generation") is not None]
    if not direct:
        return [], None
    max_gen = max(p["generation"] for p in direct)
    floor = max_gen if min_gen is None else min_gen
    frontier = [
        p for p in direct
        if p["generation"] >= floor
        and p.get("num_parents_known", 0) < 2
        and p.get("fs_id")
    ]
    # deepest first -- those are the true edge of the pull
    frontier.sort(key=lambda p: (-p["generation"], p["fs_id"]))
    return frontier, max_gen


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


# PowerShell preamble: load FS_USERNAME / FS_PASSWORD from a .env file found by
# walking up from the script's location, falling back to an interactive prompt
# (password hidden) for whichever value is missing. The password is never
# printed; it is passed to getmyancestors via -p (briefly visible to other
# processes on this machine only).
_ENV_LOADER = r"""$ErrorActionPreference = 'Stop'

# --- locate and load .env (walk up from this script) ---
$envDir = $PSScriptRoot
while ($envDir -and -not (Test-Path (Join-Path $envDir '.env'))) {
    $envDir = Split-Path $envDir -Parent
}
if ($envDir) {
    Get-Content (Join-Path $envDir '.env') | ForEach-Object {
        if ($_ -match '^\s*([^#=][^=]*)=(.*)$') {
            $val = $matches[2].Trim()
            if ($val.Length -ge 2 -and
                (($val[0] -eq '"' -and $val[-1] -eq '"') -or
                 ($val[0] -eq "'" -and $val[-1] -eq "'"))) {
                $val = $val.Substring(1, $val.Length - 2)
            }
            Set-Item -Path ("env:" + $matches[1].Trim()) -Value $val
        }
    }
}
$user = $env:FS_USERNAME
$pass = $env:FS_PASSWORD
if (-not $user -or $user -eq 'your_familysearch_username') {
    $user = Read-Host 'FamilySearch username'
}
if (-not $pass -or $pass -eq 'your_familysearch_password') {
    $secure = Read-Host 'FamilySearch password' -AsSecureString
    $pass = [System.Net.NetworkCredential]::new('', $secure).Password
}
New-Item -ItemType Directory -Force -Path data | Out-Null
"""


def write_powershell(path, fid_chunks, root_fid, label, ascend, source_ged,
                     rate_limit=None):
    """Emit a PowerShell script that loads credentials from .env (prompt
    fallback) and pulls + merges. The script never stores or prints the
    password; it reads it from the gitignored .env you create.

    Each pull writes a per-chunk .log next to its .ged (getmyancestors -l) so a
    run measures itself. Afterward, in PowerShell:
        Select-String 'Status code: 429' data/deeper_*_part*.log   # throttle hits
        (Select-String 'Downloading:'  data/deeper_*_part*.log).Count  # total requests
    rate_limit (requests/sec) is OFF by default: getmyancestors already fans out
    ~dozens of concurrent source/note calls, so a cap can only SLOW a run, never
    speed it up -- set one only if a .log shows frequent 429s. The merge globs
    *.ged only, so .log files are never swept into it."""
    outdir = f"output/{label}" if label else "output"
    label_flag = f" --label {label}" if label else ""
    lines = [
        "# pull_deeper.ps1 -- fetch the next generations of ancestors and merge.",
        "#",
        "# Generated by find_frontier.py. Review before running.",
        "# Credentials are read from a .env file (FS_USERNAME / FS_PASSWORD); copy",
        "# .env.example to .env and fill it in. Any value left blank/placeholder is",
        "# prompted for instead (password hidden). The password is passed to",
        "# getmyancestors via -p and is briefly visible to other processes on this",
        "# machine while a pull runs; it is never written elsewhere or committed.",
        "#",
        "# Each pull writes a .log next to its .ged (getmyancestors -l). Afterward:",
        "#   Select-String 'Status code: 429' data/deeper_*_part*.log   # throttle hits",
        "# shows whether FamilySearch throttled you. The merge globs *.ged only, so",
        "# the .log files are never merged in.",
        "#",
        "# Run from the project root with your virtualenv active, e.g.:",
        "#   .\\.venv\\Scripts\\Activate.ps1 ; .\\" + (outdir + "/pull_deeper.ps1").replace("/", "\\"),
        "",
        _ENV_LOADER,
    ]
    rate_flag = f" --rate-limit {rate_limit}" if rate_limit else ""
    part_files = []
    for n, chunk in enumerate(fid_chunks, 1):
        part = f"data/deeper_{label or 'me'}_part{n:02d}.ged"
        log = f"data/deeper_{label or 'me'}_part{n:02d}.log"
        part_files.append(part)
        fids = " ".join(chunk)
        lines.append(f"Write-Host 'Pull {n}/{len(fid_chunks)}: {len(chunk)} frontier individuals -> {part}'")
        lines.append(f"getmyancestors -u $user -p $pass -i {fids} -a {ascend} -o {part} -l {log}{rate_flag}")
        lines.append("")
    # merge original + all new parts, re-parse from the original root
    parts_glob = f"data/deeper_{label or 'me'}_part*.ged"
    root_flag = f" --root {root_fid}" if root_fid else ""
    lines += [
        "# Merge the original tree with every new part and re-parse from the root.",
        f"$parts = Get-ChildItem {parts_glob} | ForEach-Object {{ $_.FullName }}",
        f"python parse_gedcom.py {source_ged} $parts{root_flag}{label_flag}",
        "",
        "Write-Host 'Done. Re-run analyze_origins.py on the updated ancestors.json:'",
        f"Write-Host '  python analyze_origins.py --in {outdir}/ancestors.json --outdir {outdir}'",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return part_files


def main():
    ap = argparse.ArgumentParser(description="Find the pull frontier and emit deeper-pull commands.")
    ap.add_argument("--in", dest="infile", default="output/ancestors.json")
    ap.add_argument("--label", help="tree label -> writes under output/<label>/")
    ap.add_argument("--min-gen", type=int, default=None,
                    help="lowest generation to treat as frontier [deepest present]")
    ap.add_argument("--ascend", type=int, default=5, help="generations to ascend in the deeper pull [5]")
    ap.add_argument("--rate-limit", dest="rate_limit", type=int, default=None,
                    help="cap getmyancestors requests/sec [none]. A cap can only slow a pull "
                         "down, so leave off unless a pull's .log shows frequent 429s; then set "
                         "it just under the rate where they start.")
    ap.add_argument("--chunk", type=int, default=DEFAULT_CHUNK,
                    help=f"FIDs per getmyancestors command [{DEFAULT_CHUNK}]")
    ap.add_argument("--source-ged", default="data/full.ged",
                    help="original GEDCOM to merge the new parts with [data/full.ged]")
    args = ap.parse_args()

    people = load_people(args.infile)
    root_fid = find_root_fid(people)
    frontier, max_gen = find_frontier(people, args.min_gen)

    if not frontier:
        print("No frontier individuals found (everyone has both parents, or no "
              "direct-line people). Nothing to pull.")
        return

    outdir = Path(f"output/{args.label}" if args.label else "output")
    outdir.mkdir(parents=True, exist_ok=True)

    fids = [p["fs_id"] for p in frontier]
    (outdir / "frontier_fids.txt").write_text("\n".join(fids) + "\n", encoding="utf-8")

    chunks = list(chunked(fids, args.chunk))
    ps1 = outdir / "pull_deeper.ps1"
    write_powershell(ps1, chunks, root_fid, args.label, args.ascend, args.source_ged,
                     args.rate_limit)

    # ---- report ----
    by_gen = {}
    for p in frontier:
        by_gen.setdefault(p["generation"], 0)
        by_gen[p["generation"]] += 1
    print(f"Deepest generation present : {max_gen}")
    print(f"Root person FID            : {root_fid or '(unknown)'}")
    print(f"Frontier individuals       : {len(fids)}  (direct-line, <2 known parents)")
    print("  by generation:", {g: by_gen[g] for g in sorted(by_gen)})
    print(f"\nWrote:")
    print(f"  {outdir / 'frontier_fids.txt'}   ({len(fids)} FIDs)")
    print(f"  {ps1}   ({len(chunks)} pull command(s), -a {args.ascend})")
    print("\nNext steps:")
    print(f"  1. Put your login in .env (copy .env.example to .env and fill it in);")
    print(f"     anything left blank is prompted for instead.")
    print(f"  2. Review {ps1}, then run it from the project root with the venv active.")
    print(f"  3. It pulls the new generations, merges, and rewrites ancestors.json.")
    print("\nExact command for the first chunk (placeholder credentials):")
    sample = " ".join(chunks[0][:6]) + (" ..." if len(chunks[0]) > 6 else "")
    print(f"  getmyancestors -u <YOUR_FS_USERNAME> -i {sample} -a {args.ascend} "
          f"-o data/deeper_{args.label or 'me'}_part01.ged")
    print("(omit -u as well and getmyancestors prompts for username + hidden password.)")


if __name__ == "__main__":
    main()
