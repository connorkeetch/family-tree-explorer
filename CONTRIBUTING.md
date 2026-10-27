# Contributing

Bug reports, documentation fixes, and small focused pull requests are welcome.
Use the [development guide](docs/DEVELOPMENT.md) to run the app and its checks.

Before reporting a bug, search the existing issues and try the fictional example
tree. Include the release version, operating system, installation method, steps
to reproduce, and what you expected to happen. For installation problems, include
the relevant error and `docker compose ps` output.

Public issues and pull requests are visible to everyone. Use fictional records
when demonstrating a problem. Do not attach a real GEDCOM, database, backup,
`.env`, password, API key, or identifiable family information. Review log excerpts
and screenshots before posting them.

Keep changes focused on one problem. Add a small regression test when fixing
parsing, ancestry calculations, authentication, storage, or other non-trivial
behavior. Run the checks in the development guide before opening a pull request.
Explain the user-visible change, the reason for it, and how you checked it.

The project's original code is MIT-licensed. Contribute only work you have the
right to share, and preserve the notices and licenses of third-party material.
