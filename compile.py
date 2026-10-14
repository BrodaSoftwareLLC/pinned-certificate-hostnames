import argparse
import os
import re
import hashlib
from datetime import datetime
import pytz

COMPILED_WITH_COMMENTS = 'compiled-with-comments.txt'
COMPILED_WITHOUT_COMMENTS = 'compiled-without-comments.txt'
PANW_COMPILED_WITHOUT_COMMENTS = 'panw-compiled-without-comments.txt'
FTGT_COMPILED_WITHOUT_COMMENTS = 'ftgt-compiled-without-comments.txt'
HASH_FILE = 'file-validation.hash'

VALID_HOSTNAME = re.compile(r'^[a-z0-9*-]+(\.[a-z0-9*-]+)+$')
LEADING_WILDCARDS = re.compile(r'^(\*\.)+')


def read_file_content(file_path: str) -> str:
    """Reads and returns the content of a file."""
    with open(file_path, 'r') as file:
        return file.read()

def calculate_file_hash(file_path: str) -> str:
    """Calculates and returns the SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, 'rb') as file:
        for byte_block in iter(lambda: file.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def parse_hostnames(file_path: str) -> list:
    """
    Parses a 'hostnames' file into a list of normalized entries.

    Inline comments ('host # note') and full-line comments are stripped, entries are
    lowercased, and blank lines are skipped.
    """
    hostnames = []
    for line in read_file_content(file_path).splitlines():
        hostname = line.split('#', 1)[0].strip().lower()
        if hostname:
            hostnames.append(hostname)
    return hostnames

def validate_hostname(hostname: str) -> str:
    """Returns a warning message if the hostname is malformed, otherwise an empty string."""
    if not VALID_HOSTNAME.match(hostname):
        return f"invalid characters or structure: {hostname!r}"
    return ""


def collapse_wildcards(hostname: str) -> str:
    """
    Collapses leading multi-level wildcards to a single one, e.g. '*.*.example.com' -> '*.example.com'.

    Most vendors treat a leading '*.' as matching any number of subdomain levels, so the
    collapsed form covers the same hostnames.
    """
    return LEADING_WILDCARDS.sub('*.', hostname)

def panw_format(hostname: str) -> str:
    """
    Formats a hostname for a PAN-OS URL category. The hostname is kept as-is because PAN-OS
    treats each '*' as exactly one label, and a trailing '/' anchors the match to the hostname.
    """
    return f"{hostname}/"

def ftgt_format(hostname: str) -> str:
    """
    Formats a hostname for a FortiGate external category feed, which only accepts a wildcard at
    the beginning of the FQDN. Everything up to and including the last '*' is replaced by a single
    leading '*', e.g. 'gsp*-ssl.ls.apple.com' -> '*-ssl.ls.apple.com' and
    'derp*.tailscale.com' -> '*.tailscale.com'. The result can match more hostnames than the source.
    """
    if '*' not in hostname:
        return hostname
    return '*' + hostname[hostname.rindex('*') + 1:]

def is_too_broad(hostname: str) -> bool:
    """True if a wildcard entry would match a whole top-level domain, e.g. '*.com'."""
    return hostname.startswith('*') and '.' not in hostname[1:].lstrip('.')


def is_leading_wildcard(hostname: str) -> bool:
    """True if the only wildcards in the hostname are whole leading labels, e.g. '*.*.example.com'."""
    return hostname.startswith('*.') and '*' not in LEADING_WILDCARDS.sub('', hostname)

def covered_by_suffix_wildcard(hostname: str, wildcard: str) -> bool:
    """Generic vendor semantics: '*.example.com' covers any hostname ending in '.example.com'."""
    return hostname != wildcard and hostname.endswith(wildcard[1:])

def covered_by_label_wildcard(hostname: str, wildcard: str) -> bool:
    """PAN-OS semantics: each '*' label in the wildcard matches exactly one label in the hostname."""
    host_labels = hostname.split('.')
    wildcard_labels = wildcard.split('.')
    if hostname == wildcard or len(host_labels) != len(wildcard_labels):
        return False
    return all(w == '*' or w == h for h, w in zip(host_labels, wildcard_labels))

def covered_by_ftgt_wildcard(hostname: str, wildcard: str) -> bool:
    """FortiGate semantics: a leading '*' matches any prefix, e.g. '*-ssl.ls.apple.com' or '*.example.com'."""
    return hostname != wildcard and hostname.endswith(wildcard[1:])

def find_covered_hostnames(hostnames: list, covered_by, is_wildcard=is_leading_wildcard) -> list:
    """
    Returns (hostname, [wildcards]) pairs for hostnames already matched by another wildcard entry.
    By default only wildcards made of whole leading labels are considered; mid-label wildcards are left alone.
    """
    wildcards = [h for h in hostnames if is_wildcard(h)]
    covered = []
    for hostname in hostnames:
        matches = [w for w in wildcards if covered_by(hostname, w)]
        if matches:
            covered.append((hostname, matches))
    return covered


def compile_directory_contents(dir_path: str, depth: int = 0, accumulated_path: str = "", root: str = None) -> list:
    """
    Recursively walks through directories, collecting the 'header' and 'hostnames' files of
    each end directory along with the directory names formatted with depth indication.

    Args:
    - dir_path (str): The path to the directory to start the walk from.
    - depth (int): The current depth of the recursion.
    - accumulated_path (str): Accumulated path names formatted with depth.
    - root (str): The top-level directory, used to name each section's source.

    Returns:
    - list: A list of sections, each a dict with 'title' (directory structure and header),
      'hostnames' (parsed entries) and 'source' (path relative to the root).
    """
    sections = []
    if not os.path.exists(dir_path):
        raise FileNotFoundError(f"Directory not found: {dir_path}")
    if root is None:
        root = dir_path

    # Only append directory names if not at the root
    if depth > 0:
        # Format directory name with appropriate depth
        dir_name = os.path.basename(dir_path)
        accumulated_path += f"{'#' * depth} {dir_name}\n"

    entries = sorted(os.listdir(dir_path), key=lambda x: x.lower())
    has_subdirectories = any(os.path.isdir(os.path.join(dir_path, entry)) for entry in entries)

    for entry in entries:
        full_path = os.path.join(dir_path, entry)
        if os.path.isdir(full_path):
            sections += compile_directory_contents(full_path, depth + 1, accumulated_path, root)

    # If at an "end directory", collect header and hostnames
    if not has_subdirectories:
        header_path = os.path.join(dir_path, 'header')
        hostnames_path = os.path.join(dir_path, 'hostnames')
        if os.path.isfile(header_path) and os.path.isfile(hostnames_path):
            header_content = read_file_content(header_path).strip()
            sections.append({
                'title': f"{accumulated_path}{'#' * (depth + 1)} {header_content}\n",
                'hostnames': parse_hostnames(hostnames_path),
                'source': os.path.relpath(dir_path, root),
            })

    return sections


def deduplicate(entries: list) -> dict:
    """
    Deduplicates (hostname, source) pairs, keeping the first occurrence.

    Returns:
    - dict: Each unique hostname mapped to the list of sources it appeared in.
    """
    unique = {}
    for hostname, source in entries:
        unique.setdefault(hostname, []).append(source)
    return unique

def report_duplicates(label: str, unique: dict):
    """Prints the hostnames that appeared more than once in an output file."""
    duplicates = {h: s for h, s in unique.items() if len(s) > 1}
    if duplicates:
        print(f"Duplicates removed from {label}: {len(duplicates)}")
        for hostname, sources in sorted(duplicates.items()):
            print(f"  {hostname}: {', '.join(sources)}")

def report_covered(label: str, covered: list, unique: dict, removed: bool = False):
    """Prints the hostnames already covered by a wildcard, and whether they were removed from the output."""
    if covered:
        print(f"Covered by a wildcard in {label} ({'removed' if removed else 'not removed'}): {len(covered)}")
        for hostname, wildcards in covered:
            print(f"  {hostname} ({', '.join(unique[hostname])}) <- {', '.join(wildcards)}")


def write_flat_list(file_name: str, timestamp: str, hostnames: list):
    """Writes a sorted list of entries with only the timestamp comment."""
    with open(file_name, 'w') as file:
        file.write(timestamp)
        for line in hostnames:
            file.write(f"{line}\n")

def write_compiled_list(dir_path: str):
    try:
        sections = compile_directory_contents(dir_path)
        if not sections:
            print("No valid header and hostnames files found in the directory tree.")
            return

        warnings = [(section['source'], message) for section in sections
                    for message in map(validate_hostname, section['hostnames']) if message]
        for source, message in warnings:
            print(f"WARNING {source}: {message}")

        timestamp = datetime.now(pytz.timezone("UTC")).strftime("# List compiled on %Y-%m-%d %H:%M:%S %Z\n")

        # Write the commented list. Wildcards are collapsed and duplicates removed within each vendor
        # section; a hostname shared by several vendors is still listed under each of them.
        with open(COMPILED_WITH_COMMENTS, 'w') as file:
            file.write(timestamp)
            for section in sections:
                hostnames = deduplicate((collapse_wildcards(h), section['source']) for h in section['hostnames'])
                file.write(section['title'])
                file.writelines(f"{hostname}\n" for hostname in hostnames)
                file.write("\n")

        entries = [(hostname, section['source']) for section in sections for hostname in section['hostnames']]
        print(f"Number of hostnames found: {len(entries)}")

        # Write the generic list, with multi-level wildcards collapsed to a single one.
        generic = deduplicate((collapse_wildcards(h), source) for h, source in entries)
        generic_sorted = sorted(generic, key=lambda x: x.lower())
        write_flat_list(COMPILED_WITHOUT_COMMENTS, timestamp, generic_sorted)
        print(f"Number of hostnames in {COMPILED_WITHOUT_COMMENTS}: {len(generic_sorted)}")
        report_duplicates(COMPILED_WITHOUT_COMMENTS, generic)
        report_covered(COMPILED_WITHOUT_COMMENTS, find_covered_hostnames(generic_sorted, covered_by_suffix_wildcard), generic)

        # Write a Palo Alto Networks specific list, keeping multi-level wildcards as-is.
        panw = deduplicate(entries)
        panw_sorted = sorted(panw, key=lambda x: x.lower())
        write_flat_list(PANW_COMPILED_WITHOUT_COMMENTS, timestamp, [panw_format(h) for h in panw_sorted])
        print(f"Number of hostnames in {PANW_COMPILED_WITHOUT_COMMENTS}: {len(panw_sorted)}")
        report_duplicates(PANW_COMPILED_WITHOUT_COMMENTS, panw)
        report_covered(PANW_COMPILED_WITHOUT_COMMENTS, find_covered_hostnames(panw_sorted, covered_by_label_wildcard), panw)

        # Write a FortiGate specific list, with every wildcard moved to the beginning of the FQDN and the
        # entries already covered by a wildcard removed. The source data and the other lists are unchanged.
        broadened = sorted({(h, ftgt_format(h), source) for h, source in entries if ftgt_format(h) != h})
        too_broad = [(h, f, source) for h, f, source in broadened if is_too_broad(f)]
        for hostname, formatted, source in too_broad:
            print(f"WARNING {source}: {hostname!r} would become {formatted!r}, skipped in {FTGT_COMPILED_WITHOUT_COMMENTS}")
        ftgt = deduplicate((ftgt_format(h), source) for h, source in entries if not is_too_broad(ftgt_format(h)))
        ftgt_sorted = sorted(ftgt, key=lambda x: x.lower())
        ftgt_covered = find_covered_hostnames(ftgt_sorted, covered_by_ftgt_wildcard, lambda h: h.startswith('*'))
        # Covering is a strict suffix relation, so the outermost wildcard of every covered entry is kept.
        ftgt_covered_names = {hostname for hostname, _ in ftgt_covered}
        ftgt_sorted = [h for h in ftgt_sorted if h not in ftgt_covered_names]
        write_flat_list(FTGT_COMPILED_WITHOUT_COMMENTS, timestamp, ftgt_sorted)
        print(f"Number of hostnames in {FTGT_COMPILED_WITHOUT_COMMENTS}: {len(ftgt_sorted)}")
        report_duplicates(FTGT_COMPILED_WITHOUT_COMMENTS, ftgt)
        # Collapsing '*.*.' is not reported here; it matches the generic lists.
        rewritten = [b for b in broadened if b not in too_broad and collapse_wildcards(b[0]) != b[1]]
        if rewritten:
            print(f"Broadened in {FTGT_COMPILED_WITHOUT_COMMENTS}: {len(rewritten)}")
            for hostname, formatted, source in rewritten:
                print(f"  {hostname} -> {formatted} ({source})")
        report_covered(FTGT_COMPILED_WITHOUT_COMMENTS, ftgt_covered, ftgt, removed=True)

        # Calculate hashes and write to file-validation.hash
        with open(HASH_FILE, 'w') as hashfile:
            for filename in [COMPILED_WITH_COMMENTS, COMPILED_WITHOUT_COMMENTS, PANW_COMPILED_WITHOUT_COMMENTS,
                             FTGT_COMPILED_WITHOUT_COMMENTS]:
                hash_val = calculate_file_hash(filename)
                hashfile.write(f"{hash_val}  {filename}\n")

    except FileNotFoundError as e:
        print(e)

def main():
    parser = argparse.ArgumentParser(description='Compile directory contents with structure representation.')
    parser.add_argument('directory', type=str, help='The path to the directory to start the compilation from.')

    args = parser.parse_args()

    write_compiled_list(args.directory)

if __name__ == '__main__':
    main()
