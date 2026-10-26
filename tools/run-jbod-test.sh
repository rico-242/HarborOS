set -eu
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
python3 /tmp/harbor-test-jbod.py
