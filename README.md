# :pushpin: :lock: Certificate :pushpin: :lock:
A repository for known pinned certificates hostnames out on the internet.

# tl;dr
Download the file relevant to your needs:

Hosted on Cloudflare:
* The [compiled-with-comments.txt](https://lists.broda.io/pinned-certificates/compiled-with-comments.txt) file contains the headers and hostnames to help navigate the list. Multi-level wildcards are collapsed (see [Wildcards](#wildcards)).
* The [compiled-without-comments.txt](https://lists.broda.io/pinned-certificates/compiled-without-comments.txt) file contains only the hostnames, deduplicated, with multi-level wildcards collapsed (see [Wildcards](#wildcards)).
* The [panw-compiled-without-comments.txt](https://lists.broda.io/pinned-certificates/panw-compiled-without-comments.txt) file contains only the hostnames, deduplicated, and is specific to Palo Alto Networks devices (PAN-OS URL categories). Multi-level wildcards are kept as-is and every entry ends with `/`.
* The [ftgt-compiled-without-comments.txt](https://lists.broda.io/pinned-certificates/ftgt-compiled-without-comments.txt) file contains only the hostnames, deduplicated, and is specific to Fortinet FortiGate devices (FortiGuard Category External Feed). Every wildcard is moved to the beginning of the hostname, and entries already covered by a wildcard are removed.
* The [file-validation.hash](https://lists.broda.io/pinned-certificates/file-validation.hash) file contains a sha256 hash of the 4 text files above.

# Disclaimer
By downloading any file linked in this repository/or externally you accept full responsibility for its use and agree that the maintainers bear no liability for any outcomes.

# Directory Structure
```
data/
  -> category/
     -> application-name/
        -> hostnames
        -> header
```
* The `hostnames` file contains a list of known hostnames that use certificate pinning, one per line. A note can be added after an entry with `#` (e.g. `default.exp-tas.com # AB testing`); it is stripped from the compiled files. Entries are lowercased and blank lines are ignored.
* The `header` file contains a single-line header that is added to the `compiled-with-comments.txt` file when compilation of all contents of the data parsed.
* A vendor with several applications can nest them one level deeper, e.g. `data/vendors/apple/apple-pay/`.

# Wildcards
Vendors interpret wildcards differently, so the `hostnames` files keep the most specific form and each compiled file is adjusted for its audience:

| Source entry | `compiled-with-comments.txt` / `compiled-without-comments.txt` | `panw-compiled-without-comments.txt` | `ftgt-compiled-without-comments.txt` |
| --- | --- | --- | --- |
| `*.example.com` | `*.example.com` | `*.example.com/` | `*.example.com` |
| `*.*.example.com` | `*.example.com` | `*.*.example.com/` | `*.example.com` |
| `derp*.example.com` | `derp*.example.com` | `derp*.example.com/` | `*.example.com` |
| `gsp*-ssl.example.com` | `gsp*-ssl.example.com` | `gsp*-ssl.example.com/` | `*-ssl.example.com` |

* In PAN-OS URL categories each `*` matches exactly one label, so `*.example.com/` matches `a.example.com` but not `a.b.example.com`. Multi-level wildcards are therefore kept for Palo Alto Networks devices, and the trailing `/` anchors the match to the hostname.
* Most other vendors treat a leading `*.` as matching any number of subdomain levels, so `*.*.example.com` is collapsed to `*.example.com`.
* FortiGate external category feeds only accept a wildcard at the beginning of the hostname, so everything up to and including the last `*` is replaced by a single leading `*` (e.g. `derp*.tailscale.com` becomes `*.tailscale.com`). These entries match more hostnames than the source entry.
* Wildcards inside a label (e.g. `derp*.tailscale.com`) are otherwise left untouched.

When adding a vendor that needs multiple subdomain levels covered, use the multi-level form (e.g. `*.*.example.com`) in the `hostnames` file.

# Duplicates
The same hostname can be used by more than one application (e.g. `fe3cr.delivery.mp.microsoft.com` for both Windows Store and WSL).
* `compiled-with-comments.txt` lists a shared hostname under each application that uses it, but only once within an application.
* `compiled-without-comments.txt`, `panw-compiled-without-comments.txt` and `ftgt-compiled-without-comments.txt` list every entry once. Deduplication happens after wildcards are collapsed, so `*.*.example.com` and `*.example.com` become a single `*.example.com` in the generic and FortiGate files while both are kept in the Palo Alto Networks file.

`compile.py` prints the duplicates it removed and their sources, any malformed entries, the entries broadened for FortiGate, and entries already covered by a wildcard in each file (e.g. `cdn.signal.org` under `*.signal.org`). Covered entries are reported only and kept in every file except `ftgt-compiled-without-comments.txt`, where they are removed (e.g. `*.cloud.zoom.us` under `*.zoom.us`). The `hostnames` files are never changed.

# Testing
Run the tests before submitting changes to `compile.py` or the `data/` directory:
```
python3 -m unittest test_compile
```


# Contributions
If you would like to contribute to this list, please feel to create a pull request and submit the following information to support the request:
* Vendor
* Application Name
* Application Category - ideally use one of the existing categories defined, but opent to creating a new one.
* Public URL (if applicable) that mentions pinned certificate hostnames or wildcard domains.
* (Optional/Preferred) Wireshark capture showing the TLS handshake failing and the Fatal error. Need to see the hostname being established in the handshake to make a correlation.
