#!/usr/bin/env bash
# One-line installer for the AI Document Checker on Proxmox VE.
#
# Run on the Proxmox host as root:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/rnvegter/ai-document-checker/main/scripts/proxmox-install.sh)"
#
# Creates an unprivileged Debian LXC container, installs Docker and the app,
# writes .env and starts it. Every question can be answered in advance with an
# environment variable (see the list below); set AIC_YES=1 to accept defaults
# for anything not set and skip all questions.
#
#   AIC_CTID        container ID                 (default: next free ID)
#   AIC_HOSTNAME    container hostname           (default: ai-checker)
#   AIC_STORAGE     storage for the root disk    (default: local-lvm, local-zfs or the first suitable one)
#   AIC_TEMPLATE_STORAGE  storage for templates  (default: local)
#   AIC_DISK        root disk size in GB         (default: 8)
#   AIC_CORES       CPU cores                    (default: 2)
#   AIC_MEMORY      memory in MB                 (default: 2048)
#   AIC_BRIDGE      network bridge               (default: vmbr0)
#   AIC_IP          "dhcp" or an address like 192.168.1.50/24 (default: dhcp)
#   AIC_GATEWAY     gateway when AIC_IP is static
#   AIC_PORT        port the app is published on (default: 8000)
#   ANTHROPIC_API_KEY  Claude API key (optional; without it only the instant check works)
#   APP_PASSWORD    app password                 (default: a random one, shown at the end)
#   AIC_REPO        Git repository               (default: https://github.com/rnvegter/ai-document-checker.git)
#   AIC_BRANCH      Git branch                   (default: main)
set -Eeuo pipefail

REPO="${AIC_REPO:-https://github.com/rnvegter/ai-document-checker.git}"
BRANCH="${AIC_BRANCH:-main}"
APP_DIR=/opt/ai-document-checker
YES="${AIC_YES:-0}"

bold=$'\e[1m'; green=$'\e[32m'; red=$'\e[31m'; yellow=$'\e[33m'; reset=$'\e[0m'
step() { printf '%s==>%s %s\n' "$green" "$reset" "$*"; }
warn() { printf '%sWarning:%s %s\n' "$yellow" "$reset" "$*" >&2; }
die() { printf '%sError:%s %s\n' "$red" "$reset" "$*" >&2; exit 1; }

CTID=""
on_error() {
  local code=$?
  printf '\n%sInstallation failed (exit code %s).%s\n' "$red" "$code" "$reset" >&2
  if [[ -n "$CTID" ]] && pct status "$CTID" >/dev/null 2>&1; then
    printf 'Container %s was created. Inspect it with "pct enter %s",\n' "$CTID" "$CTID" >&2
    printf 'or remove it with "pct stop %s; pct destroy %s".\n' "$CTID" "$CTID" >&2
  fi
}
trap on_error ERR

# ask VAR "Question" default [secret]
ask() {
  local var=$1 question=$2 default=$3 secret=${4:-} answer
  if [[ -n "${!var:-}" ]]; then return; fi
  if [[ "$YES" == 1 || ! -t 0 ]]; then
    printf -v "$var" '%s' "$default"
    return
  fi
  if [[ -n "$secret" ]]; then
    read -r -s -p "$question${default:+ [$default]}: " answer; echo
  else
    read -r -p "$question [$default]: " answer
  fi
  printf -v "$var" '%s' "${answer:-$default}"
}

# ---------- Checks ----------

[[ $EUID -eq 0 ]] || die "Run this script as root on the Proxmox host."
for cmd in pct pveam pvesh pvesm; do
  command -v "$cmd" >/dev/null || die "'$cmd' not found. Run this script on a Proxmox VE host."
done

printf '\n%sAI Document Checker: Proxmox installer%s\n' "$bold" "$reset"
printf 'Creates a Debian LXC container with Docker and the app. Press Enter to accept a default.\n\n'

# ---------- Settings ----------

default_storage() {
  local list
  list=$(pvesm status -content rootdir 2>/dev/null | awk 'NR>1 && $3=="active" {print $1}')
  for s in local-lvm local-zfs; do
    grep -qx "$s" <<<"$list" && { echo "$s"; return; }
  done
  head -n1 <<<"$list"
}

AIC_CTID="${AIC_CTID:-}"
ask AIC_CTID "Container ID" "$(pvesh get /cluster/nextid)"
ask AIC_HOSTNAME "Hostname" "ai-checker"
ask AIC_STORAGE "Storage for the container disk" "$(default_storage)"
ask AIC_DISK "Disk size in GB" "8"
ask AIC_CORES "CPU cores" "2"
ask AIC_MEMORY "Memory in MB" "2048"
ask AIC_BRIDGE "Network bridge" "vmbr0"
ask AIC_IP "IP address (dhcp, or e.g. 192.168.1.50/24)" "dhcp"
if [[ "$AIC_IP" != dhcp ]]; then
  ask AIC_GATEWAY "Gateway" "$(ip route | awk '/^default/ {print $3; exit}')"
fi
ask AIC_PORT "Port for the app" "8000"
ask ANTHROPIC_API_KEY "Anthropic API key (optional, input hidden)" "" secret
ask APP_PASSWORD "App password (input hidden; Enter generates one)" "" secret

GENERATED_PASSWORD=0
if [[ -z "$APP_PASSWORD" ]]; then
  APP_PASSWORD=$(openssl rand -hex 12)
  GENERATED_PASSWORD=1
fi
AIC_TEMPLATE_STORAGE="${AIC_TEMPLATE_STORAGE:-local}"

# Validate before anything is created.
[[ -n "$AIC_STORAGE" ]] || die "No storage for containers found. Set AIC_STORAGE."
pvesm status -content rootdir 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$AIC_STORAGE" \
  || die "Storage '$AIC_STORAGE' does not exist or cannot hold containers."
pvesh get /cluster/nextid --vmid "$AIC_CTID" >/dev/null 2>&1 || die "ID $AIC_CTID is already in use or invalid."
for n in AIC_DISK AIC_CORES AIC_MEMORY AIC_PORT; do
  [[ "${!n}" =~ ^[0-9]+$ ]] || die "$n must be a number (got '${!n}')."
done
[[ "$AIC_IP" == dhcp || "$AIC_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$ ]] \
  || die "IP address must be 'dhcp' or look like 192.168.1.50/24."
ip link show "$AIC_BRIDGE" >/dev/null 2>&1 || die "Network bridge '$AIC_BRIDGE' not found."
for v in ANTHROPIC_API_KEY APP_PASSWORD; do
  [[ "${!v}" != *"'"* && "${!v}" != *$'\n'* ]] || die "$v must not contain quotes or line breaks."
done

NET="name=eth0,bridge=$AIC_BRIDGE,ip=$AIC_IP"
[[ "$AIC_IP" != dhcp && -n "${AIC_GATEWAY:-}" ]] && NET+=",gw=$AIC_GATEWAY"

printf '\n%sSummary%s\n' "$bold" "$reset"
printf '  Container  %s (%s), %s cores, %s MB RAM, %s GB on %s\n' \
  "$AIC_CTID" "$AIC_HOSTNAME" "$AIC_CORES" "$AIC_MEMORY" "$AIC_DISK" "$AIC_STORAGE"
printf '  Network    %s\n' "$NET"
printf '  App        port %s, Claude %s\n\n' "$AIC_PORT" "$([[ -n "$ANTHROPIC_API_KEY" ]] && echo enabled || echo "not configured")"
if [[ "$YES" != 1 && -t 0 ]]; then
  read -r -p "Create the container now? [Y/n]: " go
  [[ "${go:-y}" =~ ^[Yy] ]] || { echo "Cancelled."; exit 0; }
fi

# ---------- Template ----------

step "Finding the newest Debian template"
pveam update >/dev/null
TEMPLATE=$(pveam available --section system | awk '{print $2}' | grep -E '^debian-1[23]-standard' | sort -V | tail -n1)
[[ -n "$TEMPLATE" ]] || die "No Debian 12 or 13 template found in 'pveam available'."
if ! pveam list "$AIC_TEMPLATE_STORAGE" | awk '{print $1}' | grep -q "/$TEMPLATE$"; then
  step "Downloading $TEMPLATE"
  pveam download "$AIC_TEMPLATE_STORAGE" "$TEMPLATE" >/dev/null
fi

# ---------- Container ----------

step "Creating container $AIC_CTID"
pct create "$AIC_CTID" "$AIC_TEMPLATE_STORAGE:vztmpl/$TEMPLATE" \
  --hostname "$AIC_HOSTNAME" \
  --cores "$AIC_CORES" --memory "$AIC_MEMORY" --swap 512 \
  --rootfs "$AIC_STORAGE:$AIC_DISK" \
  --net0 "$NET" \
  --unprivileged 1 \
  --features nesting=1,keyctl=1 \
  --onboot 1 \
  --description "AI Document Checker ($REPO)" >/dev/null
CTID=$AIC_CTID
pct start "$CTID"

in_ct() { pct exec "$CTID" -- env LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive bash -c "$1"; }

step "Waiting for the network"
for _ in $(seq 1 30); do
  in_ct "getent hosts deb.debian.org" >/dev/null 2>&1 && break
  sleep 2
done
in_ct "getent hosts deb.debian.org" >/dev/null 2>&1 || die "The container has no network or DNS. Check bridge '$AIC_BRIDGE' and the IP settings."

# ---------- Software ----------

step "Updating Debian (this takes a few minutes)"
in_ct "apt-get update -qq && apt-get full-upgrade -y -qq >/dev/null && apt-get install -y -qq curl git ca-certificates nano >/dev/null"

step "Installing Docker"
in_ct "curl -fsSL https://get.docker.com | sh >/dev/null 2>&1 && docker --version"

step "Downloading the app"
in_ct "git clone -q --branch '$BRANCH' '$REPO' '$APP_DIR'"

step "Writing settings"
ENV_TMP=$(mktemp)
trap 'rm -f "$ENV_TMP"' EXIT
pct exec "$CTID" -- cat "$APP_DIR/.env.example" > "$ENV_TMP.example"
# Single quotes keep Docker Compose from interpreting $ and # in the values.
KEY="$ANTHROPIC_API_KEY" PASS="$APP_PASSWORD" PORT="$AIC_PORT" awk '
  /^ANTHROPIC_API_KEY=/ { print "ANTHROPIC_API_KEY='\''" ENVIRON["KEY"] "'\''"; next }
  /^APP_PASSWORD=/      { print "APP_PASSWORD='\''" ENVIRON["PASS"] "'\''"; next }
  /^PUBLISH_PORT=/      { print "PUBLISH_PORT=" ENVIRON["PORT"]; next }
  { print }
' "$ENV_TMP.example" > "$ENV_TMP"
rm -f "$ENV_TMP.example"
pct push "$CTID" "$ENV_TMP" "$APP_DIR/.env" --perms 600

step "Building and starting the app"
in_ct "cd '$APP_DIR' && docker compose up -d --build --quiet-pull >/dev/null 2>&1"

step "Checking that it runs"
healthy=0
for _ in $(seq 1 30); do
  if in_ct "curl -fsS http://localhost:$AIC_PORT/healthz" >/dev/null 2>&1; then healthy=1; break; fi
  sleep 2
done
[[ $healthy == 1 ]] || die "The app did not start. See the logs with: pct exec $CTID -- docker compose --project-directory $APP_DIR logs"

IP=$(pct exec "$CTID" -- hostname -I | awk '{print $1}')
trap - ERR

printf '\n%sThe AI Document Checker is running.%s\n\n' "$green$bold" "$reset"
printf '  Open       http://%s:%s\n' "${IP:-<container-ip>}" "$AIC_PORT"
printf '  Log in     any username, password: %s\n' "$([[ $GENERATED_PASSWORD == 1 ]] && echo "$APP_PASSWORD" || echo "the one you entered")"
printf '  Container  %s (%s)\n\n' "$CTID" "$AIC_HOSTNAME"
[[ -z "$ANTHROPIC_API_KEY" ]] && warn "No API key set: only the instant check works. Add it with \"pct enter $CTID\", then edit $APP_DIR/.env and run \"docker compose up -d\" in $APP_DIR."
printf 'Update later with:\n  pct exec %s -- bash -c "cd %s && git pull && docker compose up -d --build && docker image prune -f"\n' "$CTID" "$APP_DIR"
printf 'Settings:  pct enter %s, then edit %s/.env and run "docker compose up -d".\n' "$CTID" "$APP_DIR"
printf 'Put the app behind HTTPS before exposing it outside your network (see docs/PROXMOX.md).\n'
