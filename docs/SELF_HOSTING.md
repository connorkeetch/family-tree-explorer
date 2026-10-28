# Run your own Kinwhere

The default installation is for your own computer. Docker runs the website, API,
and SQLite database together. You do not need Python, Node, a separate database,
FamilySearch credentials, an invite, or an AI account to start.

## Start

1. Install Docker Desktop on Windows or macOS, or Docker Engine with the Compose
   plugin on Linux. Start Docker and use Linux containers.
2. Download and extract a source release, or clone this repository. Open a
   terminal in the folder containing `compose.yaml`.
3. Run:

   ```sh
   docker compose up --build -d
   ```

4. Open [http://localhost:8000](http://localhost:8000), create an app account,
   and try the fictional example or upload a GEDCOM file.

The first build downloads dependencies and can take several minutes. Check
`docker compose ps` for readiness. If it fails, `docker compose logs --tail=100 app`
shows recent startup messages. Review logs before sharing them; do not post
credentials or family records in a public issue.

The app listens on `127.0.0.1`, so the port is not deliberately exposed to your
network. An app account protects access within your installation; it is separate
from your FamilySearch account. Registration is open on the local installation
by default.

## Account recovery

Accounts belong to this installation, separate from FamilySearch. Kinwhere does
not send email or password reset links. If you forget a password, the person
running the installation can reset the existing account from its terminal:

```sh
docker compose exec app python -m api.reset_password person@example.com
```

Replace `person@example.com` with the account's email. Run this in the folder
containing this installation's `compose.yaml`, and use the same Compose project
name if you selected a different one. The command asks twice for the new
password with hidden input; do not put the password in the command. Passwords
must have at least eight characters. A missing account or mismatched password
changes nothing. This keeps the account and all its saved trees.

Existing browser sessions remain signed in after a password reset. On a shared
installation, verify the account holder before resetting their password. This
operator tool requires access to the installation; it is not an email recovery
service. For a direct Python installation, use the same environment and
`DATABASE_URL` as the app and run `python -m api.reset_password person@example.com`.

## Settings

No `.env` file is required. To change settings, copy `.env.example` to `.env`,
edit the values, and run `docker compose up -d` again. Keep `.env` private and
preserve an existing file rather than replacing it.

| Setting | Default | When to change it |
| --- | --- | --- |
| `APP_PORT` | `8000` | Another app already uses that port; open the new port in your browser. |
| `SESSION_SECRET` | Generated once in app data | Supply a long random secret when using external storage or several app processes. Keep it stable. |
| `SESSION_HTTPS_ONLY` | `0` | Set `1` when serving the site through HTTPS. |
| `INVITE_CODE` | Blank | Optional registration gate for an instance you share with others. |
| `OPENROUTER_API_KEY` | Blank, AI off | Enable optional paid AI analysis after reading the privacy notes. |
| `MAX_UPLOAD_MB` | `512` | Set the combined GEDCOM upload limit in MiB. |

Compose passes these settings to the app. Running Python directly does not
automatically load `.env`.

Compose stores the database, generated session secret, and AI answer cache in
the named `app-data` volume mounted at `/app/api_store`. The stable project name
`family-tree` is retained from v0.1.0 so Kinwhere continues using existing storage,
even if the source folder is renamed. To run a second independent installation on
the same Docker host, use a different project name
(`docker compose -p another-tree ...`) and a different `APP_PORT` consistently for
that installation.

## Stop, restart, and update

```sh
docker compose stop
docker compose start
```

`docker compose down` removes the container and network while retaining the
named data volume. `docker compose up -d` recreates them with the saved data.
**Do not use `docker compose down --volumes` for an update or troubleshooting:**
it deletes the installation's accounts, trees, secret, and cache.

Before updating, make a backup using the next section. Download the next release
or update your checkout, preserve your private `.env`, and rebuild:

```sh
docker compose up --build -d
```

Check `docker compose ps`, sign in, and open a saved tree. Release notes must
state any database compatibility changes; do not assume an older app can read a
database written by a newer version. If you need to roll back, use the prior
release together with its compatible pre-update backup.

## Back up the full installation

The app's JSON download is an analysis export, not a complete installation
backup. It does not include accounts and cannot be imported through the GEDCOM
upload. Keep your original GEDCOM as source material too.

For a consistent SQLite backup, stop the app before copying its data. Choose a
fresh backup folder name every time; the following example uses
`family-tree-backup` in the current folder:

```sh
docker compose stop app
docker compose cp app:/app/api_store ./family-tree-backup
docker compose start app
```

Save a private copy of `.env` alongside the backup if you use it. The backup
contains family information, account password hashes, and the session secret;
store it somewhere you control. The example backup folder is excluded from Git
and the Docker build. Keep another copy outside this computer, and test a
restore before relying on it.

## Restore into an empty installation

Use the matching release, its Compose file, and the private configuration from
the backup. Ensure this is the intended installation and not a populated app
you want to preserve. The following commands create a stopped container, copy
the saved directory contents into its volume, then start it:

```sh
docker compose create app
docker compose cp ./family-tree-backup/. app:/app/api_store
docker compose up -d
```

Sign in with an account from the backup and check saved trees. Retain the backup
until that verification succeeds. These instructions apply to the default
SQLite setup. For an external Postgres database, use that database's backup and
restore tools and also preserve the app configuration and persistent secret.

## Optional AI and internet access

The core analysis works without an AI key. If `OPENROUTER_API_KEY` is set,
imports also send selected records not classified as likely living to OpenRouter for AI-assisted
place mapping, parent-claim comparison, and duplicate suggestions. The README's
privacy explanation describes those fields. The answer cache lives in the data
volume so container replacement does not discard it.

AI being off does not make the app fully offline. Country boundaries are bundled,
but the map requests tiles from OpenStreetMap; those requests reveal
ordinary connection information and the requested map area to their providers.

## Optional remote hosting

Remote access is a separate operator choice. Keep the default local port
binding and put a correctly configured HTTPS reverse proxy in front of the
app, or use a hosting service with HTTPS and persistent storage. Supply a
stable `SESSION_SECRET`, set `SESSION_HTTPS_ONLY=1`, and set `INVITE_CODE` if
registration should be limited to people you choose. Back up both data and
configuration.

The API accepts `DATABASE_URL` for an external Postgres database; Compose also
passes an explicitly configured `DATABASE_URL` through. Check proxy upload-size
limits and timeouts for large GEDCOMs and optional AI processing. Opening a
router port alone does not provide HTTPS, account recovery, or backups.
