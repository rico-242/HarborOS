set -eu
systemctl is-active harbor lightdm ssh smbd docker
systemctl --failed --no-pager
curl --fail --silent --cacert /var/lib/harbor/tls.crt https://127.0.0.1:8443/api/health
printf '\n'
ss -lntp | sed -n '/:8443\|:17080\|:17081/p'
findmnt -n -o SOURCE,FSTYPE,TARGET /srv/harbor/storage
ps -eo user,args | sed -n '/chromium --kiosk/p' | head -1
cat /etc/os-release
