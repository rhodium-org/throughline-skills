# How two graphs share one repository

Verified on 2026-09-12 against `tl 2.2.1` and `tl-compose 0.16.4 (throughline
2.2.1)`. Re-verify against the installed tool before trusting any line here;
`tl --help` and `tl-compose --version` are authoritative over this file.

## How the tool locates a graph

- A graph is a directory holding `throughline.toml`. `tl` looks **only** at the
  current directory or the one named by `-C PATH`. There is no upward search,
  no environment variable and no config-file discovery.
- `tl init` refuses to create a graph inside an existing one (it walks up
  looking for a `throughline.toml`) unless `--force` is passed. Two graphs that
  are *siblings* under a directory holding no `throughline.toml` of its own are
  not nested, so `idd/shaping/` beside `idd/<name>/` needs no override.
- `tl-compose` accepts the same commands as `tl` and adds source composition.
  Any graph whose `throughline.toml` declares `[[sources]]` must be driven with
  `tl-compose`; bare `tl` on it reports on local items alone.

## What `tl init` produces — and what this skill does not reproduce

| Form | Writes |
|---|---|
| `tl init` | `throughline.toml`, five registers (`vision/INT`, `requirements/REQ`, `nonfunctional/NFR`, `non-goals/NG`, `tests/TEST`), one demo item in each, `docs/overview.md` |
| `tl init --no-demo` | the config and the same five registers, no items |
| `tl init --bare` (= `--no-defaults`) | `throughline.toml` only |

The register set is the guess this skill replaces. `--bare` carries none of it
and only writes the schema (statuses, roles, transitions, grounding, the
coverage rule), so the script uses `--bare` for both graphs rather than keeping
a drifting copy of that schema. Registers come from `tl register new PREFIX DIR`
and item types, attributes and roots from `tl schema ...`, every one of which
records a `--because` comment in the config.

## The pointer from shaping to the named graph

The name of the second directory is recorded twice, on purpose:

1. As the **name decision** in the shaping graph — a `decision` item with
   `kind = name` and `dir = <name>`. This is the ratifiable record.
2. As a **`path` source** in `idd/shaping/throughline.toml`:

   ```toml
   [[sources]]
   namespace = "<name>"
   path = "../<name>"
   ```

   `tl-compose` already understands this, so no new config format is needed:
   `tl-compose -C idd/shaping context` shows the whole picture, and a source
   holding zero items composes cleanly (verified). Unknown keys in
   `throughline.toml` are tolerated by the loader, but a native source is a
   pointer tooling already follows, so that is the one used.

Because of (2) the shaping graph takes `tl-compose` from the moment the second
graph is written. The script picks the binary per graph by looking for
`[[sources]]`.

## Facts the check gate enforces that shape the design

- **An empty graph is an error.** A graph with registers but no items fails
  `tl check` with `empty-graph`. So a second graph cannot be handed back with
  registers alone: the skill seeds its root intent there before checking.
- **Strict fails on any proposed AI item.** `unratified` is a warning under
  `tl check` and an error under `--strict`. A graph the skill has only ever
  proposed into therefore cannot pass strict until a human ratifies; the gate
  the skill hands back on is zero errors under `tl check`, and `--strict` is
  the gate *after* ratification.
- **A second graph holding only its intent reports `unserved-root`.** An
  intent is a delivery root, and a delivery root nothing derives from is an
  error. So a graph the skill has seeded with its intent and stopped at
  registers cannot report zero errors; it reports exactly that one finding,
  and the hand-off names it as the next step rather than silencing it.
- **A delivery root that nothing derives from is an error.** `intent`,
  `business_need`, `risk` and `constraint` are delivery roots by default. An
  inherited team standard recorded as a `constraint` must therefore have the
  register decisions it mandates grounded in it, which is the right reading:
  a standard nobody follows is a finding.
- **Undeclared item types are tolerated** by `tl new` and `tl check`, but an
  attribute can only be declared on a declared type, so the script declares
  every type it uses (including default roots such as `constraint`) before
  giving it an `origin` attribute.
- **A malformed link missing `target`** is reported as `malformed-link`, not a
  crash, on 2.2.1. Nothing here hand-writes YAML in any case.
