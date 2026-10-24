# Installing on Proxmox VE

This guide installs the AI Document Checker on Proxmox VE 8 or 9.

## Quick install (one line)

Run this in the **Proxmox host** shell (Datacenter → your node → Shell) as root:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/rnvegter/ai-document-checker/main/scripts/proxmox-install.sh)"
```

It sets up [setup A](#a-lxc-container-with-docker-recommended) for you: an unprivileged Debian LXC container with
Docker, the app, a `.env` file and automatic start at boot. It asks a few questions; press Enter to accept a default:

| Question | Default |
|---|---|
| Container ID | next free ID |
| Hostname | `ai-checker` |
| Storage for the disk | `local-lvm`, `local-zfs` or the first suitable storage |
| Disk, CPU cores, memory | 8 GB, 2 cores, 2048 MB |
| Network bridge and IP | `vmbr0`, DHCP (or a static address such as `192.168.1.50/24` plus gateway) |
| Port | `8000` |
| Anthropic API key | none (optional; typing is hidden) |
| App password | a random one, shown at the end (typing is hidden) |

All input is checked before anything is created. At the end it shows the address, the password and the command to
update later. It takes about 5 minutes, mostly Debian updates and the Docker build.

Like any script you pipe from the internet, read it first if you want to know what it does:
[`scripts/proxmox-install.sh`](../scripts/proxmox-install.sh).

**Without questions:** set any answer as an environment variable and add `AIC_YES=1` to accept defaults for the
rest, for example:

```bash
AIC_YES=1 AIC_CTID=120 AIC_IP=192.168.1.50/24 AIC_GATEWAY=192.168.1.1 \
ANTHROPIC_API_KEY=sk-ant-... APP_PASSWORD=choose-one \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/rnvegter/ai-document-checker/main/scripts/proxmox-install.sh)"
```

The full list of variables is at the top of the script. A key typed on the command line ends up in your shell
history; use the questions instead if that matters.

If the installer stops with an error, it tells you which container it created so you can inspect or remove it.
To update an installed copy, use the [update commands](#updating).

## Manual installation

Prefer to do it by hand, or want a VM? Pick one of three setups:

| Setup | Best for | Notes |
|---|---|---|
| [A. LXC container with Docker](#a-lxc-container-with-docker-recommended) (recommended) | Most home labs and small teams | Light, uses the same Docker commands as the main README. |
| [B. Virtual machine with Docker](#b-virtual-machine-with-docker) | Shared or business use | Strongest isolation; Proxmox's own advice for running Docker. Uses a little more memory. |
| [C. LXC container without Docker](#c-lxc-container-without-docker) | The lightest possible install | Python and systemd only, no Docker. |

**Resources:** 2 CPU cores, 2 GB RAM and 8 GB disk are plenty (1 core and 1 GB work for light use). No GPU is needed:
Claude runs at Anthropic.

**Before you start, have ready:**

- Access to the Proxmox web interface and the node's **Shell** (Datacenter → your node → Shell).
- The name of your storage for containers and disks: usually `local-lvm`, or `local-zfs` on a ZFS install.
  Commands below use `local-lvm`; replace it if yours differs.
- Your network bridge, usually `vmbr0`.
- An Anthropic API key (optional; without it only the instant check works) and a password for the app.

---

## A. LXC container with Docker (recommended)

### 1. Download a Debian template

Run on the **Proxmox host** shell:

```bash
pveam update
TEMPLATE=$(pveam available --section system | awk '{print $2}' | grep -E '^debian-1[23]-standard' | sort -V | tail -1)
echo "$TEMPLATE"                      # e.g. debian-12-standard_12.7-1_amd64.tar.zst
pveam download local "$TEMPLATE"
```

### 2. Create and start the container

Still on the Proxmox host:

```bash
CTID=$(pvesh get /cluster/nextid)     # next free ID, or pick your own, e.g. 120
pct create "$CTID" "local:vztmpl/$TEMPLATE" \
  --hostname ai-checker \
  --cores 2 --memory 2048 --swap 512 \
  --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 1 \
  --features nesting=1,keyctl=1 \
  --onboot 1
pct start "$CTID"
echo "Container ID: $CTID"
```

- `nesting=1` and `keyctl=1` let Docker run inside the unprivileged container. Without them Docker fails to start
  containers.
- `--onboot 1` starts the container when the Proxmox host boots.
- For a fixed IP address instead of DHCP, use for example
  `--net0 name=eth0,bridge=vmbr0,ip=192.168.1.50/24,gw=192.168.1.1`.

<details>
<summary>Prefer the web interface?</summary>

Click **Create CT** and use: hostname `ai-checker`, unprivileged container ticked, a password or SSH key,
template `debian-12-standard` (or 13), disk 8 GB, 2 cores, 2048 MB memory, 512 MB swap, network on `vmbr0` with
DHCP or a static IP. Tick **Start after created**. Then go to the container → **Options → Features**, tick
**Nesting** and **keyctl**, and restart the container. Also set **Options → Start at boot** to Yes.
</details>

### 3. Install Docker and the app

Open a shell in the container from the Proxmox host (no password needed):

```bash
pct enter "$CTID"
```

Then, inside the container:

```bash
apt update && apt full-upgrade -y
apt install -y curl git ca-certificates nano
curl -fsSL https://get.docker.com | sh

git clone https://github.com/rnvegter/ai-document-checker.git /opt/ai-document-checker
cd /opt/ai-document-checker
cp .env.example .env
chmod 600 .env
nano .env                             # set ANTHROPIC_API_KEY and APP_PASSWORD, save with Ctrl+O, exit with Ctrl+X

docker compose up -d --build
docker compose ps                     # wait until STATUS shows "healthy" (about 30 seconds)
hostname -I                           # the container's IP address
```

Open `http://<container-ip>:8000` in a browser and log in with any username and your `APP_PASSWORD`.
Leave the container shell with `exit`.

---

## B. Virtual machine with Docker

### 1. Create the VM

1. Download a Debian netinst ISO from <https://www.debian.org/download> (or an Ubuntu Server ISO). In Proxmox, go to
   your ISO storage (for example **local → ISO Images**) and use **Download from URL** or **Upload**.
2. Click **Create VM** and use:
   - **OS:** the ISO you just added.
   - **System:** defaults, and tick **Qemu Agent**.
   - **Disks:** 16 GB on `local-lvm`.
   - **CPU:** 2 cores, type `host`.
   - **Memory:** 2048 MB.
   - **Network:** bridge `vmbr0`, model VirtIO.
3. Start the VM, open its **Console** and install Debian. Choose only **SSH server** and **standard system utilities**
   (no desktop).
4. In the VM's **Options**, set **Start at boot** to Yes.

### 2. Install Docker and the app

Log in to the VM (console or SSH) and become root with `su -`, then:

```bash
apt update && apt full-upgrade -y
apt install -y curl git ca-certificates nano qemu-guest-agent
systemctl enable --now qemu-guest-agent
curl -fsSL https://get.docker.com | sh

git clone https://github.com/rnvegter/ai-document-checker.git /opt/ai-document-checker
cd /opt/ai-document-checker
cp .env.example .env
chmod 600 .env
nano .env                             # set ANTHROPIC_API_KEY and APP_PASSWORD

docker compose up -d --build
docker compose ps
hostname -I
```

Open `http://<vm-ip>:8000`. With the guest agent running, Proxmox also shows the IP on the VM's **Summary** page.

---

## C. LXC container without Docker

Create the container exactly as in [A, steps 1 and 2](#1-download-a-debian-template) (you may leave out `keyctl=1`),
open a shell with `pct enter <CTID>`, and run inside it:

```bash
apt update && apt full-upgrade -y
apt install -y git python3 python3-venv curl nano

git clone https://github.com/rnvegter/ai-document-checker.git /opt/ai-document-checker
useradd --system --home-dir /opt/ai-document-checker --shell /usr/sbin/nologin aichecker
cd /opt/ai-document-checker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
sed -i 's/^HOST=.*/HOST=0.0.0.0/' .env  # listen on the network, not only inside the container
chmod 600 .env
nano .env                             # set ANTHROPIC_API_KEY and APP_PASSWORD
chown -R aichecker:aichecker /opt/ai-document-checker
```

Create the service so it starts automatically:

```bash
cat > /etc/systemd/system/ai-checker.service <<'EOF'
[Unit]
Description=AI Document Checker
After=network-online.target
Wants=network-online.target

[Service]
User=aichecker
WorkingDirectory=/opt/ai-document-checker
ExecStart=/opt/ai-document-checker/.venv/bin/python server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now ai-checker
systemctl status ai-checker --no-pager
hostname -I
```

Open `http://<container-ip>:8000` (or the `PORT` you set in `.env`).

---

## Updating

Take a snapshot first, so you can go back in seconds if something goes wrong (see [Snapshots](#snapshots-and-backups)).

**Setups A and B (Docker).** From the Proxmox host for a container:

```bash
pct exec <CTID> -- bash -c "cd /opt/ai-document-checker && git pull && docker compose up -d --build && docker image prune -f"
```

Or inside the container or VM:

```bash
cd /opt/ai-document-checker
git pull
docker compose up -d --build
docker image prune -f
```

**Setup C (no Docker),** inside the container:

```bash
cd /opt/ai-document-checker
runuser -u aichecker -- git pull
runuser -u aichecker -- .venv/bin/pip install -r requirements.txt --upgrade
systemctl restart ai-checker
```

**Operating system updates** (all setups), inside the container or VM:

```bash
apt update && apt full-upgrade -y
```

**Docker base image** (setups A and B), for security fixes in Python and its libraries:

```bash
cd /opt/ai-document-checker
docker compose build --pull --no-cache
docker compose up -d
```

After an update, check `.env.example` for new settings; the main [README](../README.md#updating) has a command that
lists them.

## Snapshots and backups

Snapshots need storage that supports them (LVM-thin such as `local-lvm`, ZFS or Ceph; not a plain directory).

```bash
# Container
pct snapshot <CTID> before-update
pct rollback <CTID> before-update     # go back
pct delsnapshot <CTID> before-update  # remove when no longer needed

# Virtual machine
qm snapshot <VMID> before-update
qm rollback <VMID> before-update
qm delsnapshot <VMID> before-update
```

For regular backups, go to **Datacenter → Backup → Add**, select the container or VM, choose a schedule and mode
**Snapshot**. Or run one by hand:

```bash
vzdump <CTID> --mode snapshot --compress zstd --storage local
```

Restore from the web interface (storage → **Backups** → **Restore**) or with `pct restore` / `qmrestore`.

A backup contains `.env` with your API key, so keep backup storage private. Users' history is stored in their own
browsers and is not part of the backup; they can export it from the History page.

## Network access and HTTPS

- **Find the IP:** `pct exec <CTID> -- hostname -I` on the host, or the **Summary** page of a VM with the guest agent.
- **Keep the address stable:** use a static IP, or reserve the address in your router's DHCP settings.
- **Limit access with the Proxmox firewall (optional):** on the container or VM, open **Firewall**, add a rule
  *Direction In, Action ACCEPT, Protocol tcp, Dest. port 8000, Source* your LAN (for example `192.168.1.0/24`),
  then enable the firewall under **Firewall → Options**.
- **HTTPS:** don't forward port 8000 on your router. Put the app behind a reverse proxy with HTTPS, such as an existing
  Nginx Proxy Manager, Traefik or Caddy:
  - Forward to `http://<container-ip>:8000`.
  - Allow uploads of at least `MAX_UPLOAD_MB` and requests of up to 10 minutes, because cleaning long documents takes
    a while. In Nginx Proxy Manager, add this under the proxy host's **Advanced** tab:

    ```nginx
    client_max_body_size 25m;
    proxy_read_timeout 600s;
    ```

  - The main [README](../README.md#https-and-reverse-proxy) has complete Caddy and nginx examples.

## Troubleshooting

| Problem | Fix |
|---|---|
| Docker fails inside the container with "permission denied", "operation not permitted" or AppArmor errors | Enable the features and restart: `pct set <CTID> --features nesting=1,keyctl=1` then `pct reboot <CTID>`. |
| Docker image builds fail or are very slow on ZFS storage | Update Proxmox (Proxmox VE 8.1 and newer handle Docker on ZFS well), or use setup B (VM). |
| No network inside the container | Check `pct config <CTID>` for the right bridge and IP settings, and that DHCP or the gateway is correct. |
| The page doesn't open from another computer | Inside the container: `docker compose ps` (or `systemctl status ai-checker`) and `curl http://localhost:8000/healthz`. If that works, check the Proxmox firewall rule and, for setup C, that `HOST=0.0.0.0` is in `.env`. |
| Disk full | Grow the disk with `pct resize <CTID> rootfs +4G` (or **Resources → Root Disk → Resize**), and clean up old images with `docker system prune`. |
| "perl: warning: Setting locale failed" during apt | Harmless in the Debian template. Fix with `dpkg-reconfigure locales` if it bothers you. |
| Claude features are greyed out or show errors | See the troubleshooting table in the main [README](../README.md#troubleshooting). |
