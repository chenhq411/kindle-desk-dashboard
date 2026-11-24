#!/bin/sh
# KDD resident display client. No firmware, Wi-Fi or boot-file changes.
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
TZ=CST-8
export TZ
BASE=/mnt/us/kdd
LOCK=/tmp/kdd-client.lock
EIPS=/usr/sbin/eips

case "${1:-}" in
    stop)
        if [ -r "$LOCK/pid" ]; then
            pid="$(cat "$LOCK/pid")"
            case "$pid" in ''|*[!0-9]*) exit 1;; esac
            if [ -r "/proc/$pid/cmdline" ] && grep -q 'KDD_client.sh' "/proc/$pid/cmdline"; then
                kill "$pid"
            fi
        fi
        exit 0
        ;;
    run) ;;
    *) echo 'Usage: KDD_client.sh run|stop'; exit 1;;
esac

mkdir -p "$BASE" || exit 1
if ! mkdir "$LOCK" 2>/dev/null; then
    existing="$(cat "$LOCK/pid" 2>/dev/null)"
    case "$existing" in ''|*[!0-9]*) echo 'Client lock needs review'; exit 1;; esac
    if kill -0 "$existing" 2>/dev/null; then echo 'Client already running'; exit 0; fi
    rm -f "$LOCK/pid"
    rmdir "$LOCK" || exit 1
    mkdir "$LOCK" || exit 1
fi
echo $$ > "$LOCK/pid"
gui_stopped=0
power_saved=''
cleanup() {
    trap - EXIT INT TERM HUP
    rm -f "$BASE/client.ready"
    if [ -n "$power_saved" ]; then
        lipc-set-prop com.lab126.powerd preventScreenSaver "$power_saved" >/dev/null 2>&1
    fi
    if [ "$gui_stopped" = 1 ]; then start lab126_gui >/dev/null 2>&1; fi
    printf 'stopped\n' > "$BASE/client.status"
    rm -f "$LOCK/pid"
    rmdir "$LOCK" 2>/dev/null
}
trap cleanup EXIT
trap 'exit 0' INT TERM HUP

power_saved="$(lipc-get-prop com.lab126.powerd preventScreenSaver 2>/dev/null)"
case "$power_saved" in 0|1) ;; *) power_saved=''; echo 'Cannot verify screensaver setting; stopped'; exit 1;; esac
lipc-set-prop com.lab126.powerd preventScreenSaver 1 >/dev/null 2>&1 || exit 1
gui_status="$(status lab126_gui 2>/dev/null)"
case "$gui_status" in
    *start/running*) stop lab126_gui >/dev/null 2>&1 || exit 1; gui_stopped=1;;
    *) echo 'GUI state not verified; stopped'; exit 1;;
esac
touch "$BASE/client.ready"
last_hash=''
last_page=''
last_clock=''
offline=0
draw_count=0
failures=0
while :; do
    now="$(date +%s)"
    heartbeat="$(cat "$BASE/heartbeat" 2>/dev/null)"
    case "$heartbeat" in ''|*[!0-9]*) heartbeat=0;; esac
    age=$((now - heartbeat))
    if [ "$age" -ge 0 ] && [ "$age" -le 90 ] && [ -r "$BASE/frame.state" ]; then
        read -r digest page full_every < "$BASE/frame.state"
        valid=1
        case "$digest" in ''|*[!0-9a-f]*) valid=0;; esac
        [ "${#digest}" = 64 ] || valid=0
        case "$page" in work|pc) ;; *) valid=0;; esac
        case "$full_every" in ''|*[!0-9]*) valid=0;; esac
        if [ "$valid" = 1 ] && [ "$full_every" -ge 1 ] && [ "$full_every" -le 120 ]; then
            if [ "$digest" != "$last_hash" ] || [ "$offline" = 1 ]; then
                actual="$(sha256sum "$BASE/frame.png" 2>/dev/null | cut -d' ' -f1)"
                if [ "$actual" = "$digest" ]; then
                    next=$((draw_count + 1))
                    if [ "$offline" = 1 ] || [ "$page" != "$last_page" ] || [ $((next % full_every)) = 0 ]; then "$EIPS" -c; fi
                    if "$EIPS" -g "$BASE/frame.png"; then
                        last_hash="$digest"; last_page="$page"; draw_count="$next"; offline=0; failures=0
                        printf 'online page=%s frames=%s\n' "$page" "$draw_count" > "$BASE/client.status"
                    else
                        failures=$((failures + 1))
                    fi
                fi
            fi
        fi
    else
        clock="$(date '+%Y-%m-%d %H:%M')"
        if [ "$clock" != "$last_clock" ] || [ "$offline" = 0 ]; then
            if [ "$offline" = 0 ]; then
                "$EIPS" -c
            else
                case "$(date +%M)" in 00|15|30|45) "$EIPS" -c;; esac
            fi
            "$EIPS" 5 6 'KINDLE DESK - OFFLINE'
            "$EIPS" 5 10 "$(date '+%H:%M')"
            "$EIPS" 5 13 "$(date '+%Y-%m-%d')"
            "$EIPS" 5 17 'Waiting for USB host'
            last_clock="$clock"; offline=1
            printf 'offline clock=%s\n' "$clock" > "$BASE/client.status"
        fi
    fi
    [ "$failures" -lt 3 ] || { echo 'Repeated eips failures; restoring reader'; exit 1; }
    sleep 5
done
