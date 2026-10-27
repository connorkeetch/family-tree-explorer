# Kinwhere third-party notices

The project's original source is covered by [MIT](LICENSE). Dependencies and
external services retain their own terms.

The build writes the full license notices for installed browser dependencies to
`/third-party-licenses.txt`, alongside the website. These include React and React
DOM (MIT), React Router (MIT), Leaflet (BSD-2-Clause), Supercluster and its indexing
dependencies (ISC), and their applicable dependencies. The notices are generated
from the exact packages installed by `web/package-lock.json`.

Country boundaries in `web/public/world-countries.geojson` come from
[Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/), whose data
is in the public domain. The file records its source URL and pinned upstream
commit. Property fields were reduced to the country name and canonical ISO code;
the geographic coordinates were retained.

Map tiles are requested from OpenStreetMap. The map preserves visible attribution
and uses normal browser caching. See [OpenStreetMap copyright and attribution](https://www.openstreetmap.org/copyright)
and the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/).
The public tile service is best effort; bulk downloading and offline prefetching
are not supported.

Python packages are installed from `api/requirements.txt`; their distributions
retain their license files in the Python installation. Most use MIT, BSD, or
Apache licenses. The optional Postgres driver `psycopg2-binary` uses LGPL with
exceptions; see [Psycopg's license](https://www.psycopg.org/docs/license.html) and
the notices included in its installed distribution. The default app uses SQLite.

The source release does not bundle FamilySearch data, getmyancestors, Docker,
the Python interpreter, or a user's records. Those tools/services have their own
licenses and terms when installed or used separately.
