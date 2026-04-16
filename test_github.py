import subprocess, os, tempfile, sys
fd, path = tempfile.mkstemp(suffix='.bat')
os.write(fd, b'@"' + sys.executable.encode() + b'" -c "import os, sys; sys.stdout.write(os.environ.get(\'VAST_SSH_PASSPHRASE\', \'\'))"\n')
os.close(fd)
env = os.environ.copy()
env['SSH_ASKPASS_REQUIRE'] = 'force'
env['SSH_ASKPASS'] = path
env['DISPLAY'] = 'dummy:0'
env['VAST_SSH_PASSPHRASE'] = 'wrongpass'
result = subprocess.run(['ssh', '-v', '-i', r'C:\Users\Pc_Lu\.ssh\id_ed25519', '-o', 'IdentitiesOnly=yes', 'git@github.com'], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
print('CODE:', result.returncode)
print('ERR:', result.stderr)
