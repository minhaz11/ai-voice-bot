"""Send the fixed deployment document and wait for its result (no SDK credentials in code)."""
import json
import os
import subprocess
import time


def aws(*args):
    result = subprocess.run(['aws', *args, '--output', 'json'], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


command = aws('ssm', 'send-command', '--instance-ids', os.environ['INSTANCE_ID'],
              '--document-name', os.environ['DEPLOY_DOCUMENT'],
              '--parameters', json.dumps({'Commit': [os.environ['GITHUB_SHA']]}),
              '--timeout-seconds', '600')['Command']['CommandId']
print('Deployment command:', command, flush=True)
for _ in range(150):
    time.sleep(10)
    try:
        result = aws('ssm', 'get-command-invocation', '--command-id', command,
                     '--instance-id', os.environ['INSTANCE_ID'])
    except subprocess.CalledProcessError as error:
        if 'InvocationDoesNotExist' in error.stderr:
            continue
        raise
    if result['Status'] in ('Pending', 'InProgress', 'Delayed'):
        continue
    print(result.get('StandardOutputContent', ''))
    print(result.get('StandardErrorContent', ''))
    if result['Status'] != 'Success':
        raise SystemExit('Deployment failed: ' + result['Status'])
    break
else:
    raise SystemExit('Timed out waiting for deployment; inspect SSM before retrying.')
