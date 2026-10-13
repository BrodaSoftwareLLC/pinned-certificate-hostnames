# 2026-10-13
## Enhancements :rocket:
* Multi-level wildcards (e.g. `*.*.fna.fbcdn.net`) are kept as-is in `panw-compiled-without-comments.txt` and collapsed to a single wildcard (e.g. `*.fna.fbcdn.net`) in `compiled-with-comments.txt` and `compiled-without-comments.txt`.
* Duplicate hostnames are removed from `compiled-without-comments.txt` and `panw-compiled-without-comments.txt`, including hostnames shared by several applications and duplicates created by collapsing wildcards. `compiled-with-comments.txt` still lists a shared hostname under each application.
* `compile.py` reports removed duplicates and their sources, malformed entries, and entries already covered by a wildcard (report only).
* `hostnames` files support inline comments after an entry with `#`, and entries are lowercased.
* Added `test_compile.py` unit tests.

## Fixes :wrench:
* Fixed `default.exp-tas.com # AB testing` being published with its comment, which produced an invalid Palo Alto Networks entry.
* Removed duplicate Spotify hostnames and lowercased `www-glz.api.concursolutions.com`.
* Removed the stray `data/media/spotify/test` and `data/vendors/apple/apple-pay/hostnames.bak` files.
* Added a `.gitignore` for `__pycache__/`.


# 2024-02-09
## Enhancements :rocket:
* Added a print statement to `compile.py` to display the number of hostnames found in the hostnames files.
* Added a sha256 hash calculation of the `compiled-with-comments.txt` and `compiled-without-comments.txt`. Hashes are added to `file-validation.hash`.
* Added several other pinned certificate websites.


# 2024-02-07
## Enhancements :rocket:
* Added `compile.py` to recursively walk through a supplied directory and build 2 files:
  * `compiled-with-comments.txt` which is a concatenation of all the header and hostnames files
  * `compiled-without-comments.txt` which only lists the hostnames that need to be excluded.
