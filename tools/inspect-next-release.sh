set -eu
printf 'Build capabilities\n'
command -v qemu-system-x86_64 || true
command -v xorriso || true
command -v mksquashfs || true
test -c /dev/kvm && echo KVM-available
df -h /DATA
docker image ls --format '{{.Repository}}:{{.Tag}}' | head -12
ls -ld /DATA/harbor/release/rootfs /DATA/harbor/rootfs /DATA/harbor/release/artifacts 2>/dev/null || true
python3 - <<'PY'
import urllib.request,json
u='https://api.github.com/repos/IceWhaleTech/CasaOS-AppStore/commits/main'
r=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'HarborOS-build'}),timeout=30))
print('Official catalog revision:',r['sha'])
PY
