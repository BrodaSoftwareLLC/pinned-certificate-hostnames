import contextlib
import io
import os
import tempfile
import unittest

import compile as compiler

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def write_file(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as file:
        file.write(content)

def read_entries(path: str) -> list:
    """Returns the lines of a compiled file, excluding the timestamp comment."""
    with open(path) as file:
        return file.read().splitlines()[1:]

def compile_into(data_dir: str, out_dir: str) -> str:
    """Runs the compiler with out_dir as the working directory and returns its printed report."""
    cwd = os.getcwd()
    report = io.StringIO()
    try:
        os.chdir(out_dir)
        with contextlib.redirect_stdout(report):
            compiler.write_compiled_list(data_dir)
    finally:
        os.chdir(cwd)
    return report.getvalue()


class TestParseHostnames(unittest.TestCase):
    def test_strips_comments_whitespace_and_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'hostnames')
            write_file(path, "# full-line comment\n  Www.Example.com  \n\ndefault.exp-tas.com # AB testing\n*.*.example.org#note\n")
            self.assertEqual(compiler.parse_hostnames(path),
                             ['www.example.com', 'default.exp-tas.com', '*.*.example.org'])


class TestValidateHostname(unittest.TestCase):
    def test_valid(self):
        for hostname in ['example.com', '*.example.com', '*.*.fna.fbcdn.net', 'derp*.tailscale.com',
                         '*-prod.do.dsp.mp.microsoft.com', 'video-akpcw-cdn-spotify-com.akamaized.net']:
            self.assertEqual(compiler.validate_hostname(hostname), '', hostname)

    def test_invalid(self):
        for hostname in ['example.com:80', 'https://example.com', 'example.com/', 'a b.com',
                         'localhost', '.example.com', 'example..com', 'example.com.']:
            self.assertNotEqual(compiler.validate_hostname(hostname), '', hostname)


class TestWildcardFormatting(unittest.TestCase):
    def test_collapse_wildcards(self):
        cases = {
            '*.*.fna.fbcdn.net': '*.fna.fbcdn.net',
            '*.*.*.example.com': '*.example.com',
            '*.example.com': '*.example.com',
            'example.com': 'example.com',
            'derp*.tailscale.com': 'derp*.tailscale.com',
            '*-prod.do.dsp.mp.microsoft.com': '*-prod.do.dsp.mp.microsoft.com',
        }
        for hostname, expected in cases.items():
            self.assertEqual(compiler.collapse_wildcards(hostname), expected, hostname)

    def test_panw_format_keeps_multi_level_wildcards(self):
        self.assertEqual(compiler.panw_format('*.*.fna.fbcdn.net'), '*.*.fna.fbcdn.net/')
        self.assertEqual(compiler.panw_format('example.com'), 'example.com/')

    def test_is_leading_wildcard(self):
        self.assertTrue(compiler.is_leading_wildcard('*.example.com'))
        self.assertTrue(compiler.is_leading_wildcard('*.*.example.com'))
        self.assertFalse(compiler.is_leading_wildcard('example.com'))
        self.assertFalse(compiler.is_leading_wildcard('derp*.tailscale.com'))
        self.assertFalse(compiler.is_leading_wildcard('*-prod.example.com'))
        self.assertFalse(compiler.is_leading_wildcard('*.a*.example.com'))


class TestCoverage(unittest.TestCase):
    def test_suffix_semantics_match_any_depth(self):
        self.assertTrue(compiler.covered_by_suffix_wildcard('cdn.signal.org', '*.signal.org'))
        self.assertTrue(compiler.covered_by_suffix_wildcard('*.aot.trendmicro.com', '*.trendmicro.com'))
        self.assertFalse(compiler.covered_by_suffix_wildcard('signal.org', '*.signal.org'))
        self.assertFalse(compiler.covered_by_suffix_wildcard('*.signal.org', '*.signal.org'))
        self.assertFalse(compiler.covered_by_suffix_wildcard('notsignal.org', '*.signal.org'))

    def test_label_semantics_match_one_label_per_wildcard(self):
        self.assertTrue(compiler.covered_by_label_wildcard('cdn.signal.org', '*.signal.org'))
        self.assertTrue(compiler.covered_by_label_wildcard('a.b.fna.fbcdn.net', '*.*.fna.fbcdn.net'))
        self.assertFalse(compiler.covered_by_label_wildcard('*.aot.trendmicro.com', '*.trendmicro.com'))
        self.assertFalse(compiler.covered_by_label_wildcard('a.fna.fbcdn.net', '*.*.fna.fbcdn.net'))
        self.assertFalse(compiler.covered_by_label_wildcard('*.fna.fbcdn.net', '*.*.fna.fbcdn.net'))
        self.assertFalse(compiler.covered_by_label_wildcard('signal.org', '*.signal.org'))

    def test_find_covered_ignores_mid_label_wildcards(self):
        hostnames = ['derp*.tailscale.com', 'derp1.tailscale.com', '*.signal.org', 'cdn.signal.org']
        covered = compiler.find_covered_hostnames(hostnames, compiler.covered_by_suffix_wildcard)
        self.assertEqual(covered, [('cdn.signal.org', ['*.signal.org'])])


class TestDeduplicate(unittest.TestCase):
    def test_keeps_first_occurrence_and_all_sources(self):
        unique = compiler.deduplicate([('b.com', 'x'), ('a.com', 'x'), ('b.com', 'y')])
        self.assertEqual(list(unique), ['b.com', 'a.com'])
        self.assertEqual(unique['b.com'], ['x', 'y'])


class TestWriteCompiledList(unittest.TestCase):
    """End-to-end run over a small data tree covering the double wildcard and cross-vendor cases."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        data = os.path.join(cls.tmp.name, 'data')
        cls.out = os.path.join(cls.tmp.name, 'out')
        os.makedirs(cls.out)
        write_file(os.path.join(data, 'social-media/facebook/header'), "Facebook - 2024-02-07 \n")
        write_file(os.path.join(data, 'social-media/facebook/hostnames'),
                   "*.*.fna.fbcdn.net\nGraph.Facebook.com\n*.fna.fbcdn.net\n\n")
        write_file(os.path.join(data, 'vendors/microsoft/windows-store/header'), "Windows Store - 2024-02-07\n")
        write_file(os.path.join(data, 'vendors/microsoft/windows-store/hostnames'),
                   "fe3cr.delivery.mp.microsoft.com\n")
        write_file(os.path.join(data, 'vendors/microsoft/wsl/header'), "WSL - 2024-02-07\n")
        write_file(os.path.join(data, 'vendors/microsoft/wsl/hostnames'),
                   "fe3cr.delivery.mp.microsoft.com # shared with windows-store\n")
        cls.report = compile_into(data, cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def entries(self, file_name: str) -> list:
        return read_entries(os.path.join(self.out, file_name))

    def test_generic_list_collapses_then_deduplicates(self):
        self.assertEqual(self.entries(compiler.COMPILED_WITHOUT_COMMENTS),
                         ['*.fna.fbcdn.net', 'fe3cr.delivery.mp.microsoft.com', 'graph.facebook.com'])

    def test_panw_list_keeps_double_wildcard(self):
        self.assertEqual(self.entries(compiler.PANW_COMPILED_WITHOUT_COMMENTS),
                         ['*.*.fna.fbcdn.net/', '*.fna.fbcdn.net/', 'fe3cr.delivery.mp.microsoft.com/',
                          'graph.facebook.com/'])

    def test_commented_list_keeps_shared_hostname_under_each_vendor(self):
        self.assertEqual(self.entries(compiler.COMPILED_WITH_COMMENTS), [
            '# social-media', '## facebook', '### Facebook - 2024-02-07',
            '*.fna.fbcdn.net', 'graph.facebook.com', '',
            '# vendors', '## microsoft', '### windows-store', '#### Windows Store - 2024-02-07',
            'fe3cr.delivery.mp.microsoft.com', '',
            '# vendors', '## microsoft', '### wsl', '#### WSL - 2024-02-07',
            'fe3cr.delivery.mp.microsoft.com', '',
        ])

    def test_hash_file_lists_all_outputs(self):
        with open(os.path.join(self.out, compiler.HASH_FILE)) as file:
            hashes = dict(reversed(line.split('  ', 1)) for line in file.read().splitlines())
        self.assertEqual(list(hashes), [compiler.COMPILED_WITH_COMMENTS, compiler.COMPILED_WITHOUT_COMMENTS,
                                        compiler.PANW_COMPILED_WITHOUT_COMMENTS])
        for file_name, hash_val in hashes.items():
            self.assertEqual(compiler.calculate_file_hash(os.path.join(self.out, file_name)), hash_val)

    def test_report_names_duplicate_sources(self):
        self.assertIn('fe3cr.delivery.mp.microsoft.com: vendors/microsoft/windows-store, vendors/microsoft/wsl',
                      self.report)


class TestRepositoryData(unittest.TestCase):
    """Invariants that the real data/ tree must satisfy once compiled."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.report = compile_into(DATA_DIR, cls.tmp.name)
        cls.generic = read_entries(os.path.join(cls.tmp.name, compiler.COMPILED_WITHOUT_COMMENTS))
        cls.panw = read_entries(os.path.join(cls.tmp.name, compiler.PANW_COMPILED_WITHOUT_COMMENTS))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_validation_warnings(self):
        self.assertNotIn('WARNING', self.report)

    def test_no_duplicates(self):
        self.assertEqual(len(self.generic), len(set(self.generic)))
        self.assertEqual(len(self.panw), len(set(self.panw)))

    def test_entries_are_clean(self):
        for entry in self.generic + self.panw:
            self.assertNotIn('#', entry)
            self.assertNotIn(' ', entry)
            self.assertEqual(entry, entry.lower())

    def test_generic_list_has_no_multi_level_wildcards(self):
        self.assertFalse([entry for entry in self.generic if entry.startswith('*.*.')])

    def test_panw_list_is_anchored(self):
        self.assertTrue(all(entry.endswith('/') and not entry.endswith('//') for entry in self.panw))


if __name__ == '__main__':
    unittest.main()
