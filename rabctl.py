#!/usr/bin/env python3
"""
rabctl - RoleAgentBot Control CLI

Control interface for the Supervisor and JobScheduler via IPC.
Provides commands to check status, trigger jobs, pause/resume, restart actors, etc.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from supervisor.ipc import send_command


async def cmd_status(socket_path: Path):
    """Get status of supervisor and scheduler."""
    response = await send_command(socket_path, {"command": "status"})
    print(json.dumps(response, indent=2))


async def cmd_trigger(socket_path: Path, job_name: str):
    """Trigger a job immediately."""
    response = await send_command(socket_path, {"command": "trigger", "job": job_name})
    if response.get("error"):
        print(f"Error: {response['error']}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ Triggered job '{job_name}'")


async def cmd_pause(socket_path: Path, job_name: str):
    """Pause a job."""
    response = await send_command(socket_path, {"command": "pause", "job": job_name})
    if response.get("error"):
        print(f"Error: {response['error']}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ Paused job '{job_name}'")


async def cmd_resume(socket_path: Path, job_name: str):
    """Resume a paused job."""
    response = await send_command(socket_path, {"command": "resume", "job": job_name})
    if response.get("error"):
        print(f"Error: {response['error']}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ Resumed job '{job_name}'")


async def cmd_restart(socket_path: Path, actor_name: str):
    """Restart an actor."""
    response = await send_command(socket_path, {"command": "restart", "actor": actor_name})
    if response.get("error"):
        print(f"Error: {response['error']}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ Restarted actor '{actor_name}'")


async def cmd_shutdown(socket_path: Path):
    """Shutdown the supervisor and scheduler."""
    response = await send_command(socket_path, {"command": "shutdown"})
    if response.get("error"):
        print(f"Error: {response['error']}", file=sys.stderr)
        sys.exit(1)
    print("✅ Shutdown signal sent")


async def cmd_health(socket_path: Path):
    """Health check for systemd."""
    response = await send_command(socket_path, {"command": "status"})
    # Exit 0 if healthy, 1 if unhealthy
    if response.get("error") or not response.get("supervisor", {}).get("running"):
        sys.exit(1)
    sys.exit(0)


async def cmd_metrics(socket_path: Path):
    """Get Prometheus metrics."""
    response = await send_command(socket_path, {"command": "metrics"})
    if response.get("error"):
        print(f"Error: {response['error']}", file=sys.stderr)
        sys.exit(1)
    print(response.get("metrics", ""))


async def main():
    parser = argparse.ArgumentParser(description="RoleAgentBot Control CLI")
    parser.add_argument("--socket", type=Path, default=Path("/tmp/rab_ipc.sock"),
                        help="IPC socket path (default: /tmp/rab_ipc.sock)")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Status
    subparsers.add_parser("status", help="Get supervisor and scheduler status")

    # Trigger
    trigger_parser = subparsers.add_parser("trigger", help="Trigger a job immediately")
    trigger_parser.add_argument("job", help="Job name to trigger")

    # Pause
    pause_parser = subparsers.add_parser("pause", help="Pause a job")
    pause_parser.add_argument("job", help="Job name to pause")

    # Resume
    resume_parser = subparsers.add_parser("resume", help="Resume a paused job")
    resume_parser.add_argument("job", help="Job name to resume")

    # Restart
    restart_parser = subparsers.add_parser("restart", help="Restart an actor")
    restart_parser.add_argument("actor", help="Actor name to restart")

    # Shutdown
    subparsers.add_parser("shutdown", help="Shutdown supervisor and scheduler")

    # Health
    subparsers.add_parser("health", help="Health check (exit code 0/1)")

    # Metrics
    subparsers.add_parser("metrics", help="Get Prometheus metrics")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "status":
            await cmd_status(args.socket)
        elif args.command == "trigger":
            await cmd_trigger(args.socket, args.job)
        elif args.command == "pause":
            await cmd_pause(args.socket, args.job)
        elif args.command == "resume":
            await cmd_resume(args.socket, args.job)
        elif args.command == "restart":
            await cmd_restart(args.socket, args.actor)
        elif args.command == "shutdown":
            await cmd_shutdown(args.socket)
        elif args.command == "health":
            await cmd_health(args.socket)
        elif args.command == "metrics":
            await cmd_metrics(args.socket)
    except FileNotFoundError:
        print(f"Error: IPC socket not found at {args.socket}", file=sys.stderr)
        print("Is the bot running?", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
