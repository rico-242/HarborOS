"""Host virtualization support for Harbour's VM applications."""
import json, os, re, shutil, subprocess
from pathlib import Path

PACKAGES = ('qemu-system-x86', 'qemu-utils', 'libvirt-daemon-system', 'libvirt-clients', 'virtinst')

class Virtualization:
    def __init__(self, app, run, error):
        self.app, self.run, self.error = app, run, error

    def _command(self, name):
        return shutil.which(name) is not None

    def status(self):
        kvm = Path('/dev/kvm')
        tools = {n: self._command(n) for n in ('virsh','qemu-system-x86_64','virt-install')}
        services = {}
        for unit in ('libvirtd','virtqemud','virtlogd'):
            p = subprocess.run(['systemctl','is-active',unit], capture_output=True, text=True)
            services[unit] = p.stdout.strip() == 'active'
        socket = Path('/var/run/libvirt/libvirt-sock').exists()
        ready = kvm.exists() and tools['virsh'] and tools['qemu-system-x86_64'] and socket and any(services.values())
        return {'ready': ready, 'kvm': kvm.exists(), 'tools': tools, 'services': services,
                'libvirt_socket': socket, 'packages': list(PACKAGES),
                'message': 'Virtualization support is ready.' if ready else 'Install Virtualization Support to enable QEMU/KVM and libvirt.'}

    def install(self):
        if os.geteuid() != 0:
            raise self.error('Virtualization support must be installed by the Harbour system service.')
        def execute():
            self.app.job_progress('Preparing virtualization', 'Checking CPU virtualization and the KVM device.')
            if not Path('/dev/kvm').exists():
                raise self.error('KVM is unavailable. Enable Intel VT-x/AMD-V in firmware first.')
            self.app.job_progress('Installing virtualization', 'Installing signed Debian QEMU and libvirt packages.')
            env = dict(os.environ, DEBIAN_FRONTEND='noninteractive', NEEDRESTART_MODE='a')
            subprocess.run(['apt-get','update'], check=True, timeout=600, env=env)
            subprocess.run(['apt-get','install','-y',*PACKAGES], check=True, timeout=1200, env=env)
            for unit in ('libvirtd','virtqemud','virtlogd'):
                subprocess.run(['systemctl','enable','--now',unit], check=False, timeout=60)
            self.app.job_progress('Verifying virtualization', 'Checking libvirt connectivity and the VM application prerequisites.')
            state=self.status()
            if not state['ready']:
                raise self.error('Virtualization packages installed, but libvirt is not ready. Review the system journal.')
            return state
        return self.app.job('Enable Virtualization Support', execute, kind='system', target='qemu-kvm')
