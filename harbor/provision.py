#!/usr/bin/env python3
"""Provision an appliance administrator from a password supplied on stdin."""
import argparse
import os
from pathlib import Path
import pwd
import sys
from server import atomic_json, password_record, run

parser = argparse.ArgumentParser()
parser.add_argument('--username', required=True)
parser.add_argument('--state', default='/var/lib/harbor')
args = parser.parse_args()
if os.geteuid() != 0:
    raise SystemExit('Run provisioning as root.')
password = sys.stdin.readline().rstrip('\n')
record = password_record(args.username, password)
try:
    pwd.getpwnam(args.username)
except KeyError:
    run('useradd', '-m', '-s', '/bin/bash', '-G', 'sudo', args.username)
run('chpasswd', input_text=args.username + ':' + password + '\n')
run('smbpasswd', '-s', '-a', args.username, input_text=password + '\n' + password + '\n')
state = Path(args.state)
state.mkdir(parents=True, exist_ok=True)
atomic_json(state / 'admin.json', record)
(state / 'setup-token').unlink(missing_ok=True)
print('Administrator and SMB account provisioned. No plaintext password stored.')
