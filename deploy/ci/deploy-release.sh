#!/usr/bin/env bash
# Executed by the restricted SSM document; Commit is passed as an environment variable.
set -euo pipefail
sha="${SSM_Commit:?Missing commit}"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || exit 2
exec 9>/run/lock/jannet-deploy.lock
flock -w 900 9
repo=/opt/jannet
releases=/opt/jannet-releases
current=/opt/jannet-current
release="$releases/$sha"
test -s /etc/jannet/app.env
mountpoint -q /var/lib/jannet
# Only commits already on this repository's main branch may be deployed.
git -C "$repo" fetch origin main
git -C "$repo" merge-base --is-ancestor "$sha" FETCH_HEAD
mkdir -p "$releases"
if [ ! -e "$release/.ready" ]; then
    mkdir -p "$release"
    git -C "$repo" archive "$sha" | tar -x -C "$release"
    python3 -m venv "$release/.venv"
    "$release/.venv/bin/pip" install --disable-pip-version-check -q -r "$release/requirements.lock.txt"
    touch "$release/.ready"
fi
[ -L "$current" ] || ln -s "$repo" "$current"
previous=$(readlink -f "$current")
# Runtime settings and the SQLite disk are outside all release directories.
mkdir -p /etc/systemd/system/jannet.service.d
cat > /etc/systemd/system/jannet.service.d/storage.conf <<'UNIT'
[Service]
WorkingDirectory=/opt/jannet-current
ExecStart=
ExecStart=/usr/bin/env DATABASE_PATH=/var/lib/jannet/appointments.sqlite3 /opt/jannet-current/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
UNIT
systemctl daemon-reload
switch_to() {
    ln -sfn "$1" "$current.next"
    mv -Tf "$current.next" "$current"
}
healthy() {
    for attempt in $(seq 1 45); do
        if systemctl is-active --quiet jannet && curl -fsS --max-time 3 http://127.0.0.1:8000/api/config | python3 -c 'import json,sys; assert json.load(sys.stdin)["configured"] is True' 2>/dev/null; then
            return 0
        fi
        sleep 2
    done
    return 1
}
rollback() {
    trap - ERR
    switch_to "$previous"
    systemctl restart jannet
    if healthy; then echo 'Deployment failed; previous version restored.'; else echo 'Rollback health check failed; manual recovery required.'; fi
    exit 1
}
trap rollback ERR
switch_to "$release"
systemctl restart jannet
healthy
trap - ERR
printf '%s\n' "$sha" > /var/lib/jannet/deployed-commit
# Keep current and previous releases so repeated deployments do not fill the disk.
for old in "$releases"/*; do
    [[ "$(basename "$old")" =~ ^[0-9a-f]{40}$ ]] || continue
    if [ "$old" != "$release" ] && [ "$old" != "$previous" ]; then rm -rf -- "$old"; fi
done
echo "Deployed $sha successfully."
