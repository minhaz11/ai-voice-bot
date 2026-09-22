"""Exercise release switching and rollback without touching system services."""
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('fail_health', [False, True])
def test_deployment_switch_or_rollback(tmp_path, fail_health):
    source = Path(__file__).parents[1] / 'deploy/ci/deploy-release.sh'
    script = source.read_text()
    # Redirect every host path into this test's sandbox.
    for directory in ['/opt', '/etc', '/run', '/var/lib']:
        script = script.replace(directory + '/', str(tmp_path / directory.lstrip('/')) + '/')
    repo = tmp_path / 'opt/jannet'
    repo.mkdir(parents=True)
    sha = 'a' * 40
    release = tmp_path / 'opt/jannet-releases' / sha
    release.mkdir(parents=True)
    (release / '.ready').touch()
    (tmp_path / 'etc/jannet').mkdir(parents=True)
    (tmp_path / 'etc/jannet/app.env').write_text('TEST=1\n')
    (tmp_path / 'run/lock').mkdir(parents=True)
    (tmp_path / 'var/lib/jannet').mkdir(parents=True)
    current = tmp_path / 'opt/jannet-current'
    bins = tmp_path / 'bin'
    bins.mkdir()
    for name in ['git', 'mountpoint', 'systemctl', 'sleep']:
        file = bins / name
        file.write_text('#!/bin/sh\nexit 0\n')
        file.chmod(0o755)
    curl = bins / 'curl'
    curl.write_text('#!/bin/sh\n'
                    'if [ "$FAIL_HEALTH" = 1 ] && [ "$(readlink "$CURRENT")" = "$RELEASE" ]; then exit 1; fi\n'
                    'echo \'{"configured":true}\'\n')
    curl.chmod(0o755)
    result = subprocess.run(['bash'], input=script, text=True, capture_output=True,
                            env={**os.environ, 'PATH': str(bins) + ':' + os.environ['PATH'],
                                 'SSM_Commit': sha, 'FAIL_HEALTH': str(int(fail_health)),
                                 'CURRENT': str(current), 'RELEASE': str(release)}, timeout=20)
    assert result.returncode == (1 if fail_health else 0), result.stderr
    assert current.resolve() == (repo if fail_health else release)
    marker = tmp_path / 'var/lib/jannet/deployed-commit'
    if fail_health:
        assert not marker.exists()
        assert 'previous version restored' in result.stdout
    else:
        assert marker.read_text().strip() == sha
