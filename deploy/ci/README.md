# Automatic demo deployment

Every push to `main` runs the Python tests, then deploys the exact tested commit to
Jannet on EC2 in Mumbai. Pull requests run tests only. You can also run the workflow
manually from GitHub Actions on `main`.

GitHub uses OIDC temporary credentials. The AWS role trusts only this repository's
immutable identity on `main`, and permits only the deployment SSM document on the
specified instance plus command-status reads. No AWS access keys or Gemini keys
are stored in GitHub. Repository variables configure the role, instance and document:
`AWS_DEPLOY_ROLE_ARN`, `AWS_INSTANCE_ID`, `AWS_DEPLOY_DOCUMENT`.

The server prepares an isolated release and virtual environment, switches a symlink,
and restarts the app. A failed startup/configuration check restores the previous
release. Current and previous releases are retained. A restart briefly interrupts
service and active calls. Health checks do not validate every conversation or undo
incompatible database schema migrations; review schema changes separately.

The existing `/etc/jannet/app.env` and `/var/lib/jannet/appointments.sqlite3` remain
outside releases. Editing your laptop's `.env` does not change the deployed API key.
Do not commit `.env`, database files, or credentials.

## Infrastructure maintenance

The separate CloudFormation stack `jannet-github-deploy` manages the OIDC provider,
role, and SSM document. `template.json` is generated from `build-template.py` and
`deploy-release.sh`. After changing the server deployment script, regenerate the
template with `python3 deploy/ci/build-template.py`, review a CloudFormation change
set and update that stack. Ordinary application pushes do not modify infrastructure.
Use the existing stack parameter values when updating. Only administrators can
update the deployment document or IAM permissions.

Follow progress in the repository's **Actions → Test and deploy Jannet** page.
The GitHub job fails if tests, deployment, or the public HTTPS check fails. Inspect
the deployment log before retrying. To disable automatic deployment, disable this
workflow in GitHub Actions.
