# Pulling another person's ancestry and choosing a biological line

This covers two things:

1. pulling another person's ancestry into separate outputs, and
2. following a **biological** line when a record has adoptive or uncertain parents.

The spouse and adoption examples below are hypothetical workflows, not a
description of the maintainer's family.

As always: **you run every FamilySearch command yourself**, with hidden password
entry. The scripts never store, print, or commit your credentials.

## 1. You can pull her ancestry from YOUR OWN login

FamilySearch is a **single shared tree**. Any signed-in user can traverse
**deceased** people anywhere in it. So you do **not** need your wife's account to
pull her ancestry — you start `getmyancestors` at a person on her line:

```powershell
getmyancestors -u <YOUR_FS_USERNAME> -i <HER_ANCESTOR_FID> -a 8 -o data/wife.ged
```

### The one real limit: living people are private

Living people are private to each account. Through your login you generally
**cannot** see your wife herself or her living parents unless they are shared
with you (or she is already linked to you in the tree). Practical consequences:

- **Best start point: a deceased ancestor on her line** — e.g. a deceased
  grandparent. Their FID gives you everything above them.
- If your wife *is* linked to you in the tree and you can see her record, you can
  start at her FID directly.
- The few living people at the very bottom of her tree may need to be added by
  hand afterward; no pull can fetch another account's living relatives.

### Finding a start FID

Open the person on familysearch.org; the FID is in the URL:
`https://www.familysearch.org/tree/person/details/`**`XXXX-XXX`** — the
`XXXX-XXX` token is the FID (`[A-Z0-9]{4}-[A-Z0-9]{3}`).

### Keep her tree in its own outputs

Parameterize the parse by root FID and a label so her tree never overwrites
yours:

```powershell
python parse_gedcom.py data/wife.ged --root <HER_ROOT_FID> --label wife
# -> output/wife/ancestors.json, output/wife/ancestors.csv

python analyze_origins.py --in output/wife/ancestors.json --outdir output/wife
# (optional, archived) deeper frontier pull -- the tool now lives in archive/:
python archive/find_frontier.py --in output/wife/ancestors.json --label wife --source-ged data/wife.ged
```

Everything in [DEEPER_PULL.md](../archive/DEEPER_PULL.md) (archived) works for her
tree too — just keep the `--label wife` and `--source-ged data/wife.ged` flags.

## 2. Biological vs adoptive lines

Suppose an ancestor has adoptive parents recorded, and you want to follow a
documented biological-parent relationship instead. Here are the available tools.

### What FamilySearch stores, and what getmyancestors exports

FamilySearch can record **multiple** parent-child relationships per person, each
with a lineage **type** (Biological, Adopted, Step, Foster, Guardian). In GEDCOM
that type is normally a `PEDI` tag under the child's `FAMC` pointer
(`2 PEDI adopted` vs `2 PEDI birth`).

**Important, verified limitation:** the installed `getmyancestors` (v1.1.2)
**does not export `PEDI` at all.** It captures *every* parent couple (it does not
silently drop one) and writes a separate `FAMC`/`FAM` for each — but it never
labels which couple is biological. Check the exporter version and GEDCOM tags
before relying on pedigree labels.

So on a real pull there is **no pedigree label to read**. That shapes everything
below.

### How `parse_gedcom.py` chooses the parents

`father_xref` and `mother_xref` select the two biological slots, including an
unknown father or mother. `parent_xrefs` retains alternate claims for inspection.
When a person has more than one couple, the parser
chooses the preferred one **deterministically**:

1. an explicit **override** always wins (see below);
2. otherwise a couple whose `FAMC` carries `PEDI birth` (or a **blank** PEDI,
   which is what getmyancestors emits) beats one tagged `PEDI adopted` / step /
   foster / guardian;
3. ties break on a stable sort of the parents' FIDs (so the result is
   reproducible — previously the choice was effectively random set-iteration
   order, which could silently pick the adoptive couple).

> **Be clear-eyed about rule 2.** Because getmyancestors emits no `PEDI`, the
> birth-over-adopted step **never fires on a real getmyancestors pull** — every
> couple looks blank. Rule 2 exists and is unit-tested for hand-edited or
> future GEDCOMs that *do* carry pedigree tags, but the mechanisms that actually
> steer the biological line on **real** data are the two below.

### Mechanism A — start the pull at the biological parent's FID

If you know the biological father (or grandfather) on FamilySearch, the simplest
and most reliable approach is to pull starting **at his FID**:

```powershell
getmyancestors -u <YOUR_FS_USERNAME> -i <BIO_PARENT_FID> -a 6 -o data/wife_bio.ged
```

This fetches the biological line directly and sidesteps the whole
preferred-couple question — you are explicitly asking for *that* person's
ancestry.

### Mechanism B — inject the biological edge with an override

One possible situation: **FamilySearch does not link the adopted father to
his biological parents at all** (the birth link was never made, or is sealed). A
pull starting at the biological parent's FID then comes back as a **disconnected
component** — those people exist in the data but nothing connects them to the
adopted father, so BFS from your wife's root never reaches them and they get no
generation.

Reordering couples cannot fix this (there is no biological couple on the adopted
father to reorder *to*). You have to **assert the edge**. The override does
exactly that — it *creates* a parent relationship even when none exists in
FamilySearch:

Create `wife_bio.json`:

```json
{
  "<ADOPTED_FATHER_FID>": {
    "father": "<BIO_GRANDFATHER_FID>",
    "mother": "<BIO_GRANDMOTHER_FID>",
    "pedigree": "biological"
  }
}
```

Then merge her tree with the biological pull and apply the override:

```powershell
python parse_gedcom.py data/wife.ged data/wife_bio.ged `
    --root <HER_ROOT_FID> --label wife --parent-overrides wife_bio.json
```

Now the adopted father is connected to his biological parents: he is no longer a
leaf, `father_xref` / `mother_xref` select the biological couple, and generations flow up the
biological line into the analysis. (`father`/`mother` are each optional, so you
can inject just one side if that is all you know.)

If an override names a FID that was never pulled, `parse_gedcom.py` prints a
warning listing the missing parent(s) — that is your cue to pull starting at that
FID first.

### The honest limit: when no pull can help

If the biological parents/grandparents are **not in FamilySearch at all** — no
record, no FID — then **no pull can retrieve them.** Nothing in this repo can
conjure data that the shared tree does not contain. At that point you are in
**DNA / original-research territory** (DNA matches, adoption records, vital
records). The code's job ends where FamilySearch's data ends; recognize that
boundary so you don't spend time scripting around missing source data.

## Quick reference

| Goal | Command |
| --- | --- |
| Pull her line (deceased ancestor as start) | `getmyancestors -u <USER> -i <FID> -a 8 -o data/wife.ged` |
| Parse into her own outputs | `python parse_gedcom.py data/wife.ged --root <HER_FID> --label wife` |
| Pull the biological line | `getmyancestors -u <USER> -i <BIO_FID> -a 6 -o data/wife_bio.ged` |
| Merge + inject biological edge | `python parse_gedcom.py data/wife.ged data/wife_bio.ged --root <HER_FID> --label wife --parent-overrides wife_bio.json` |
| Analyze her origins | `python analyze_origins.py --in output/wife/ancestors.json --outdir output/wife` |
