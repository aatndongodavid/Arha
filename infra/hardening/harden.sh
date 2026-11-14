#!/usr/bin/env bash
# Arha server hardening (S-14). Idempotent: safe to run again. Run as root on a fresh Ubuntu 24.04.
# Usage: DEPLOY_USER=deploy DEPLOY_SSH_KEY="ssh-ed25519 AAAA..." SSH_ALLOW_FROM="1.2.3.4/32" ./harden.sh
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
: "${DEPLOY_SSH_KEY:?Set DEPLOY_SSH_KEY to the public key allowed to deploy}"
SSH_ALLOW_FROM="${SSH_ALLOW_FROM:-any}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends ufw fail2ban unattended-upgrades chrony ca-certificates curl gnupg

# Deployment user, key only.
id "$DEPLOY_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$DEPLOY_USER"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
AUTH="/home/$DEPLOY_USER/.ssh/authorized_keys"
touch "$AUTH" && grep -qxF "$DEPLOY_SSH_KEY" "$AUTH" || echo "$DEPLOY_SSH_KEY" >> "$AUTH"
chown "$DEPLOY_USER:$DEPLOY_USER" "$AUTH" && chmod 600 "$AUTH"

# SSH: keys only, no root.
cat > /etc/ssh/sshd_config.d/10-arha.conf <<SSH
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AllowUsers $DEPLOY_USER
MaxAuthTries 3
SSH
sshd -t && systemctl reload ssh

# Firewall: 22 restricted, 80 and 443 open.
ufw --force reset >/dev/null
ufw default deny incoming && ufw default allow outgoing
if [ "$SSH_ALLOW_FROM" = "any" ]; then ufw limit 22/tcp; else ufw allow from "$SSH_ALLOW_FROM" to any port 22 proto tcp; fi
ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp
ufw --force enable

# fail2ban, automatic security updates, time sync.
cat > /etc/fail2ban/jail.d/arha.conf <<F2B
[sshd]
enabled = true
maxretry = 4
bantime = 1h
F2B
systemctl enable --now fail2ban chrony
cat > /etc/apt/apt.conf.d/20auto-upgrades <<APT
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT
systemctl enable --now unattended-upgrades

# Docker from the official repository, socket never exposed on TCP, deploy user without root shell access to it
# beyond the docker group (compose only).
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -y && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
install -d -m 755 /etc/docker
cat > /etc/docker/daemon.json <<DOCKER
{ "live-restore": true, "no-new-privileges": true, "log-driver": "json-file", "log-opts": { "max-size": "20m", "max-file": "5" } }
DOCKER
systemctl restart docker
usermod -aG docker "$DEPLOY_USER"

# Kernel network hardening.
cat > /etc/sysctl.d/60-arha.conf <<SYS
net.ipv4.conf.all.rp_filter = 1
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
SYS
sysctl --system >/dev/null

# Runtime directory for decrypted secrets (tmpfs) and data directory (mount the LUKS volume here, S-07).
install -d -m 700 -o "$DEPLOY_USER" /run/arha
install -d -m 750 /var/lib/arha
echo "Hardening complete. Verify: ufw status, sshd -T | grep -E 'permitroot|passwordauth', docker info."
