#!/usr/bin/env bash
# FundLex Codex entrypoint.
#
# Two failure modes made interactive Codex unreliable over SSH:
#   1. a TUI running in the foreground dies with the SSH terminal and aborts
#      the turn it owns;
#   2. every TUI is its own thread-store writer, so an old detached client can
#      hold a conversation lock forever and a second `codex resume` fails with
#      "This conversation is open in another app".
#
# The primary path therefore uses Codex's managed app-server daemon (turns run
# in the daemon; the TUI is only a client) and never opens a second writer for
# a thread that a live legacy tmux client already owns.  The tmux path remains
# as a fallback for installations without a complete package.
set -euo pipefail

original_args=("$@")
codex_binary="${FUNDLEX_CODEX_BINARY:-$HOME/.local/bin/codex}"
managed_binary="$HOME/.codex/packages/app-server-daemon/current/bin/codex"
tmux_binary="${FUNDLEX_TMUX_BINARY:-/usr/bin/tmux}"
tmux_config="${FUNDLEX_CODEX_TMUX_CONFIG:-$HOME/.config/fundlex/codex-tmux.conf}"
tmux_socket="${FUNDLEX_CODEX_TMUX_SOCKET:-fundlex-codex}"
session_index="$HOME/.codex/session_index.jsonl"
lock_dir="$HOME/.codex/thread-writer-locks"

log() { printf '%s\n' "$*" >&2; }

daemon_healthy() {
    [[ -x "$codex_binary" ]] || return 1
    timeout 5 "$codex_binary" app-server daemon version >/dev/null 2>&1
}

ensure_daemon() {
    daemon_healthy && return 0
    local starter="$codex_binary"
    [[ -x "$managed_binary" ]] && starter="$managed_binary"
    timeout 30 "$starter" app-server daemon restart >/dev/null 2>&1 || \
        timeout 30 "$starter" app-server daemon start >/dev/null 2>&1 || true
    daemon_healthy
}

workspace_prefix() {
    local digest
    digest="$(printf '%s' "$PWD" | sha256sum)"
    printf 'codex-%s' "${digest:0:12}"
}

session_attached() {
    "$tmux_binary" -L "$tmux_socket" display-message -p -t "$1" '#{session_attached}' 2>/dev/null || echo 0
}

session_running() {
    "$tmux_binary" -L "$tmux_socket" capture-pane -p -t "$1" 2>/dev/null \
        | grep -qE 'esc to interrupt|Working \('
}

session_age_seconds() {
    local created now
    created="$("$tmux_binary" -L "$tmux_socket" display-message -p -t "$1" '#{session_created}' 2>/dev/null || echo 0)"
    now="$(date +%s)"
    (( created > 0 && now > created )) && echo $(( now - created )) || echo 0
}

human_age() {
    local s=$1
    if (( s >= 86400 )); then printf '%dd%dh' $((s / 86400)) $((s % 86400 / 3600))
    elif (( s >= 3600 )); then printf '%dh%dm' $((s / 3600)) $((s % 3600 / 60))
    elif (( s >= 60 )); then printf '%dm' $((s / 60))
    else printf '%ds' "$s"; fi
}

thread_title() {
    local id="$1" title
    title="$(grep -F "\"$id\"" "$session_index" 2>/dev/null | tail -1 \
        | sed -nE 's/.*"thread_name":"([^"]*)".*/\1/p')"
    printf '%s' "${title:-$id}"
}

# Print thread ids for which this process has an open writer-lock file.
threads_of_pid() {
    local pid="$1" fd target
    for fd in /proc/"$pid"/fd/*; do
        target="$(readlink "$fd" 2>/dev/null)" || continue
        [[ "$target" == "$lock_dir/"*.lock ]] || continue
        basename "$target" .lock
    done
}

is_daemon_pid() {
    tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null | grep -q -- '--managed-daemon'
}

pid_tty() {
    local pid="$1" n t
    for n in 0 1 2; do
        t="$(readlink "/proc/$pid/fd/$n" 2>/dev/null)" || continue
        [[ "$t" == /dev/pts/* ]] && { printf '%s' "$t"; return 0; }
    done
    return 1
}

tty_session() {
    "$tmux_binary" -L "$tmux_socket" list-panes -a \
        -F '#{pane_tty} #{session_name}' 2>/dev/null \
        | awk -v tty="$1" '$1 == tty { print $2; exit }'
}

lock_holders() {
    local id="$1" path="$lock_dir/$id.lock" fd target pid
    [[ -e "$path" ]] || return 0
    for fd in /proc/[0-9]*/fd/*; do
        target="$(readlink "$fd" 2>/dev/null)" || continue
        [[ "$target" == "$path" ]] || continue
        pid="${fd#/proc/}"; pid="${pid%%/*}"
        [[ "$pid" == "$$" ]] && continue
        is_daemon_pid "$pid" && continue
        printf '%s\n' "$pid"
    done | sort -un
}

attach_session() {
    local session="$1"
    log "接回后台 Codex 会话 $session（不会新开客户端，也不会抢锁）。"
    if [[ "${FUNDLEX_CODEX_DRY_RUN:-0}" == 1 ]]; then
        printf 'attach %s\n' "$session"
        exit 0
    fi
    if [[ -n "${TMUX:-}" ]]; then
        exec "$tmux_binary" -L "$tmux_socket" switch-client -t "$session"
    fi
    exec "$tmux_binary" -L "$tmux_socket" -f "$tmux_config" attach-session -t "$session"
}

cmd_ls() {
    local daemon_state="not running"
    if daemon_healthy; then
        daemon_state="running $(timeout 5 "$codex_binary" app-server daemon version 2>/dev/null \
            | sed -nE 's/.*"appServerVersion":"([^"]*)".*/\1/p')"
    fi
    printf 'App-server daemon: %s\n' "$daemon_state"
    local rows
    rows="$("$tmux_binary" -L "$tmux_socket" list-panes -a \
        -F '#{session_name} #{session_attached} #{pane_pid} #{session_created}' 2>/dev/null \
        | awk '$1 ~ /^codex-/' | sort -k4nr || true)"
    if [[ -z "$rows" ]]; then
        printf 'Legacy tmux sessions: none\n'
        return 0
    fi
    printf '\nLegacy tmux sessions (socket %s):\n' "$tmux_socket"
    printf '  %-44s %-7s %-7s %-7s %s\n' SESSION ATTACHED AGE STATE THREADS
    local name attached pid created state threads age id
    while read -r name attached pid created; do
        [[ -n "$name" ]] || continue
        state=idle; session_running "$name" && state=running
        age="$(human_age "$(session_age_seconds "$name")")"
        threads=""
        while read -r id; do
            [[ -n "$id" ]] || continue
            threads+="${threads:+, }$(thread_title "$id")"
        done < <(threads_of_pid "$pid")
        [[ -n "$threads" ]] || threads="-"
        printf '  %-44s %-7s %-7s %-7s %s\n' "$name" \
            "$([[ "$attached" == 0 ]] && echo no || echo yes)" "$age" "$state" "$threads"
    done <<< "$rows"
}

cmd_where() {
    local id="$1" pid tty session found=0
    while read -r pid; do
        [[ -n "$pid" ]] || continue
        found=1
        tty="$(pid_tty "$pid" || echo '?')"
        session="$(tty_session "$tty" || true)"
        printf 'holder pid=%s tty=%s tmux=%s title=%s\n' \
            "$pid" "$tty" "${session:-none}" "$(thread_title "$id")"
    done < <(lock_holders "$id")
    (( found )) || printf 'thread %s has no legacy writer\n' "$id"
}

cmd_close() {
    local target="${1:-}" force="${2:-}"
    [[ -n "$target" ]] || { log "usage: codex close <session> [--force]"; exit 2; }
    if [[ "$(session_attached "$target")" != 0 && "$force" != --force ]]; then
        log "会话 $target 仍连接着终端；先分离（Ctrl-b d）或加 --force。"
        exit 2
    fi
    if session_running "$target" && [[ "$force" != --force ]]; then
        log "会话 $target 仍有任务在运行；确认要中断请加 --force。"
        exit 2
    fi
    "$tmux_binary" -L "$tmux_socket" kill-session -t "$target" 2>/dev/null
    log "已关闭 $target。"
}

cmd_gc() {
    local hours=12
    [[ "${1:-}" == --hours ]] && hours="${2:-12}"
    local name attached pid created state age
    while read -r name attached pid created; do
        [[ -n "$name" ]] || continue
        [[ "$attached" == 0 ]] || continue
        session_running "$name" && continue
        age="$(session_age_seconds "$name")"
        (( age >= hours * 3600 )) || continue
        "$tmux_binary" -L "$tmux_socket" kill-session -t "$name" 2>/dev/null || true
        printf 'closed idle session %s (age %s)\n' "$name" "$(human_age "$age")"
    done < <("$tmux_binary" -L "$tmux_socket" list-panes -a \
        -F '#{session_name} #{session_attached} #{pane_pid} #{session_created}' 2>/dev/null \
        | awk '$1 ~ /^codex-/')
}

cmd_attach() {
    local requested="${1:-}" prefix sessions session
    prefix="$(workspace_prefix)"
    if [[ -n "$requested" ]]; then
        attach_session "$requested"
    fi
    mapfile -t sessions < <("$tmux_binary" -L "$tmux_socket" list-panes -a \
        -F '#{session_name} #{session_created}' 2>/dev/null \
        | awk -v p="$prefix" '$1 ~ "^"p { print }' | sort -k2nr | awk '{ print $1 }')
    if (( ${#sessions[@]} == 0 )); then
        log "当前目录没有后台 Codex tmux 会话。普通 codex 会直接连接 daemon；历史聊天用 codex resume --last。"
        exit 1
    fi
    attach_session "${sessions[0]}"
}

latest_thread_id() {
    [[ -f "$session_index" ]] || return 1
    sed -nE 's/.*"id":"([^"]+)".*"updated_at":"([^"]+)".*/\2 \1/p' "$session_index" \
        | sort | tail -1 | awk '{ print $2 }'
}

route_resume() {
    local id="$1" pid tty session
    while read -r pid; do
        [[ -n "$pid" ]] || continue
        tty="$(pid_tty "$pid" || true)"
        session="$(tty_session "$tty" || true)"
        if [[ -n "$session" ]]; then
            attach_session "$session"
        fi
        log "对话 $id 被活动进程 $pid（tty ${tty:-?}）占用，未在 tmux 中。请先退出该客户端；不要删除锁文件。"
        exit 3
    done < <(lock_holders "$id")
}

tmux_fallback() {
    [[ -x "$tmux_binary" ]] || { log "缺少 tmux，无法启用持久回退。"; exec "$codex_binary" "$@"; }
    local prefix session_name session created
    prefix="$(workspace_prefix)"
    session_name="${prefix}-$(date +%s)-$$"
    local has_no_daemon=0 has_full_access=0 arg
    for arg in "$@"; do
        [[ "$arg" == "--no-daemon" ]] && has_no_daemon=1
        [[ "$arg" == "--dangerously-bypass-approvals-and-sandbox" ]] && has_full_access=1
    done
    local extra=()
    (( has_no_daemon )) || extra+=(--no-daemon)
    (( has_full_access )) || extra+=(--dangerously-bypass-approvals-and-sandbox)
    local launch
    printf -v launch '%q ' "$codex_binary" "${extra[@]}" "$@"
    log "daemon 不可用，改用 tmux 兜底；Ctrl-b d 分离，任务在后台继续。"
    exec "$tmux_binary" -L "$tmux_socket" -f "$tmux_config" \
        new-session -s "$session_name" -c "$PWD" "exec $launch"
}

# ---- dispatch ---------------------------------------------------------------
# Our management verbs are resolved before Codex sees argv; everything else
# passes through.  Global options may precede the subcommand, so skip values.
skip_value=0
for argument in "$@"; do
    if (( skip_value )); then skip_value=0; continue; fi
    case "$argument" in
        -h|--help|-V|--version)
            exec "$codex_binary" "$@" ;;
        -c|--config|-C|--cd|-m|--model|-p|--profile|-i|--image|-s|--sandbox|-a|--ask-for-approval|--add-dir|--enable|--disable|--remote|--remote-auth-token-env|--local-provider)
            skip_value=1 ;;
        --) break ;;
        -*) continue ;;
        ls) shift; cmd_ls; exit 0 ;;
        where) shift; cmd_where "${1:?usage: codex where <thread-id>}"; exit 0 ;;
        attach) shift; cmd_attach "${1:-}"; exit 0 ;;
        close) shift; cmd_close "${1:-}" "${2:-}"; exit 0 ;;
        gc) shift; cmd_gc "$@"; exit 0 ;;
        persistent-help)
            sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        resume)
            shift
            target=""
            for argument in "$@"; do
                case "$argument" in
                    --last) target="$(latest_thread_id || true)" ;;
                    -*) ;;
                    *) target="$argument"; break ;;
                esac
            done
            [[ -n "$target" ]] && route_resume "$target"
            break ;;
        *) break ;;
    esac
done

# Noninteractive callers and callers already inside tmux are not wrapped.
if [[ ! -t 0 || ! -t 1 || -n "${TMUX:-}" ]]; then
    [[ "${FUNDLEX_CODEX_TMUX:-0}" == 1 ]] || exec "$codex_binary" "${original_args[@]}"
fi

if [[ "${FUNDLEX_CODEX_TMUX:-0}" == 1 ]]; then
    tmux_fallback "${original_args[@]}"
fi

if ensure_daemon; then
    if [[ "${FUNDLEX_CODEX_DRY_RUN:-0}" == 1 ]]; then
        printf 'exec %q ' "$codex_binary" "${original_args[@]}"; printf '\n'
        exit 0
    fi
    # The daemon owns the turn and the thread store.  Exiting this TUI (SSH
    # close) no longer aborts the work; `codex resume --last` reattaches.
    exec "$codex_binary" "${original_args[@]}"
fi
tmux_fallback "${original_args[@]}"
