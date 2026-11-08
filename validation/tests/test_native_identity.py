"""The imported extension must identify a run even with editable Python sources."""
import hashlib

import dtcc_qes
from dtcc_qes import _qes

from aij import runner


def test_editable_native_change_invalidates_fingerprint(tmp_path, monkeypatch):
    package = tmp_path / 'src' / 'dtcc_qes'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('# same Python sources\n')
    native = tmp_path / 'site-packages' / '_qes.so'
    native.parent.mkdir()
    native.write_bytes(b'first native build')
    monkeypatch.setattr(dtcc_qes, '__file__', str(package / '__init__.py'))
    monkeypatch.setattr(_qes, '__file__', str(native))
    runner.fingerprint.cache_clear()
    try:
        first = runner.fingerprint()
        identity = runner.native_identity()
        assert identity['sha256'] == hashlib.sha256(native.read_bytes()).hexdigest()
        native.write_bytes(b'second native build')
        runner.fingerprint.cache_clear()
        assert runner.fingerprint() != first
        # Moving the same binary into a regular package must not count it twice.
        regular = package / native.name
        regular.write_bytes(native.read_bytes())
        expected = runner.fingerprint()
        monkeypatch.setattr(_qes, '__file__', str(regular))
        runner.fingerprint.cache_clear()
        assert runner.fingerprint() == expected
    finally:
        runner.fingerprint.cache_clear()
